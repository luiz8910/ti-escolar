"""Catálogo de templates (HSM): criação, submissão à Meta e sincronização de status.

**Dois escopos, de propósito** (§9a):

- **Global** (``tenant_id`` nulo) — o caso comum. Um ``aviso_geral`` com o nome da escola
  em ``{{1}}`` é aprovado uma vez e serve todas. Só o super admin mexe: o template é ativo
  compartilhado, e deixar cada escola criar global seria dar a uma escola o poder de
  alterar o que as outras usam.
- **Por escola** — para o que é mesmo específico dela, com o nome prefixado pelo slug.
  Aqui o admin da escola cria, porque o estrago fica contido no nome dela.

**Um texto, N submissões.** Template é aprovado por **WABA**, e uma WABA não comporta
todas as escolas (§9e.3). Então o global é *replicado*: submetido em cada conta ativa, com
um id e um status próprios em cada uma (``TemplateNaWaba``). O texto continua um só — o
que se replica é a submissão, não o cadastro.

**A submissão é assíncrona.** ``CriarTemplate`` devolve ``pendente``; quem transforma em
``aprovado`` é o webhook ``message_template_status_update`` (ou a sincronização manual,
para quando o webhook falhar). Nada disso libera envio sozinho — ``EnviarBroadcast`` e a
retomada de atendimento continuam exigindo aprovação **na WABA daquela escola**.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from app.application.validacao_template import (
    TemplateInvalido,
    nome_com_prefixo,
    normalizar_nome_template,
    validar_categoria,
    validar_corpo_template,
    validar_exemplos,
)
from app.domain.entities import (
    CategoriaTemplate,
    MessageTemplate,
    TemplateNaWaba,
    TemplateRemoto,
    Usuario,
    Waba,
)
from app.domain.ports import (
    CatalogoTemplates,
    TemplateRepository,
    TenantRepository,
    WabaRepository,
)

logger = logging.getLogger("templates")

IDIOMA_PADRAO = "pt_BR"


class TemplateNaoEncontrado(LookupError):
    pass


class PermissaoTemplateNegada(PermissionError):
    pass


class SemContaWhatsApp(RuntimeError):
    """Não há WABA onde submeter — a escola não tem conta, ou nenhuma está ativa."""


class CatalogoIndisponivelEmTodasAsContas(RuntimeError):
    """Nenhuma conta aceitou a submissão. A mensagem carrega o motivo de cada uma."""

    def __init__(self, motivos: str) -> None:
        super().__init__(
            f"A Meta não aceitou o template em nenhuma conta. {motivos}".strip()
        )


@dataclass(frozen=True)
class ResultadoSincronizacao:
    verificados: int
    atualizados: int
    desconhecidos: int  # existem na Meta e não no nosso banco


@dataclass(frozen=True)
class ResultadoReplicacao:
    """O que faltava replicar e o que foi. Ver ``ReplicarTemplates``."""

    submetidos: int
    falhas: int
    ja_existiam: int


def _pode_gerir_globais(usuario: Usuario) -> bool:
    return usuario.tenant_id is None


def _exige_permissao(usuario: Usuario, template: MessageTemplate) -> None:
    """Global só o super admin mexe; da escola, quem tem acesso àquela escola.

    A checagem de acesso ao tenant já vem feita pela rota (`_exige_acesso_tenant`); o que
    esta função acrescenta é a trava do escopo global, que a rota não teria como inferir.
    """
    if template.global_ and not _pode_gerir_globais(usuario):
        raise PermissaoTemplateNegada(
            "Templates globais são do catálogo compartilhado entre as escolas e só o "
            "super admin pode alterá-los."
        )


async def _submeter_nas_contas(
    *,
    catalogo: CatalogoTemplates,
    template: MessageTemplate,
    contas: list[Waba],
) -> tuple[list[TemplateNaWaba], list[str]]:
    """Submete o mesmo texto em cada conta. Devolve (entradas gravadas, erros).

    **Falha em uma conta não desfaz as outras.** Desfazer significaria apagar na Meta o que
    já foi aceito, gastando outra submissão para voltar ao início — e a conta que falhou
    costuma ter falhado por rede, não por recusa. A conta que não recebeu simplesmente
    **não ganha entrada**: ``status_em`` a lê como ``RASCUNHO`` (não enviável, e visível
    como "não submetido" no painel), e ``ReplicarTemplates`` reprocessa depois.
    """
    entradas: list[TemplateNaWaba] = []
    erros: list[str] = []
    for conta in contas:
        try:
            remoto = await catalogo.submeter(template, meta_waba_id=conta.meta_waba_id)
        except Exception as exc:  # noqa: BLE001 — a recusa de uma conta não derruba as demais
            logger.warning(
                "Template %r não foi submetido na conta %r: %s", template.nome, conta.nome, exc
            )
            erros.append(f"{conta.nome}: {exc}")
            continue
        entradas.append(
            TemplateNaWaba(
                waba_id=conta.id,
                status=remoto.status,
                meta_template_id=remoto.meta_template_id,
                motivo_rejeicao=remoto.motivo_rejeicao,
            )
        )
        # A Meta pode reclassificar a categoria na própria submissão (aviso que ela
        # entende como divulgação vira marketing). Guardar o que ela decidiu, e não o que
        # pedimos, é o que faz a tela mostrar o custo real.
        template.categoria = remoto.categoria
    return entradas, erros


class CriarTemplate:
    """Valida, submete à Meta (em cada conta) e persiste como pendente.

    **Ordem importa:** submete primeiro, grava depois. Gravar antes deixaria no catálogo
    um template que a Meta recusou — e a secretaria o veria na lista, tentaria disparar e
    receberia o erro só lá na frente, sem saber por quê.
    """

    def __init__(
        self,
        *,
        templates: TemplateRepository,
        catalogo: CatalogoTemplates,
        tenants: TenantRepository,
        wabas: WabaRepository,
    ) -> None:
        self._templates = templates
        self._catalogo = catalogo
        self._tenants = tenants
        self._wabas = wabas

    async def _contas_alvo(self, tenant_id: UUID | None) -> list[Waba]:
        """Global vai para toda conta ativa; da escola, só para a conta dela.

        A assimetria é o ponto da feature: o texto compartilhado precisa existir em toda
        conta para servir toda escola, enquanto o texto de uma escola só faz sentido onde
        o número dela está — submetê-lo nas outras ocuparia o nome em contas que nunca o
        usariam e multiplicaria por N o risco de rejeição num ativo compartilhado.
        """
        if tenant_id is None:
            ativas = await self._wabas.listar(apenas_ativas=True)
            if not ativas:
                raise SemContaWhatsApp(
                    "Nenhuma conta do WhatsApp Business ativa está cadastrada — não há "
                    "onde submeter o template. Cadastre uma em Administração → Contas "
                    "WhatsApp."
                )
            return ativas

        escola = await self._tenants.obter(tenant_id)
        if escola is None:
            raise TemplateNaoEncontrado("Escola não encontrada.")
        if escola.waba_id is None:
            raise SemContaWhatsApp(
                f"A escola {escola.nome} ainda não está vinculada a uma conta do "
                "WhatsApp Business. Defina a conta no cadastro da escola."
            )
        conta = await self._wabas.obter(escola.waba_id)
        if conta is None:
            raise SemContaWhatsApp(
                "A conta do WhatsApp Business vinculada a esta escola não existe mais."
            )
        return [conta]

    async def executar(
        self,
        *,
        usuario: Usuario,
        nome: str,
        corpo: str,
        categoria: CategoriaTemplate,
        exemplos: list[str] | None = None,
        idioma: str = IDIOMA_PADRAO,
        tenant_id: UUID | None = None,
    ) -> MessageTemplate:
        if tenant_id is None and not _pode_gerir_globais(usuario):
            raise PermissaoTemplateNegada(
                "Só o super admin cria template global. Para um aviso específico da sua "
                "escola, crie um template da escola."
            )

        categoria = validar_categoria(categoria)
        placeholders = validar_corpo_template(corpo)
        exemplos_validos = validar_exemplos(placeholders=placeholders, exemplos=exemplos or [])

        contas = await self._contas_alvo(tenant_id)

        nome = normalizar_nome_template(nome)
        if tenant_id is not None:
            escola = await self._tenants.obter(tenant_id)
            if escola is None:
                raise TemplateNaoEncontrado("Escola não encontrada.")
            nome = nome_com_prefixo(slug=escola.slug, nome=nome)

        # A Meta rejeita nome duplicado na WABA com um erro genérico; conferir aqui dá a
        # mensagem certa e não queima uma submissão.
        existente = await self._templates.por_nome_e_idioma(nome=nome, idioma=idioma)
        if existente is not None:
            raise TemplateInvalido(
                f"Já existe um template chamado {nome!r} em {idioma}. Escolha outro nome "
                "ou remova o atual."
            )

        template = MessageTemplate(
            tenant_id=tenant_id,
            nome=nome,
            categoria=categoria,
            idioma=idioma,
            corpo=corpo.strip(),
            exemplos=exemplos_validos,
        )

        entradas, erros = await _submeter_nas_contas(
            catalogo=self._catalogo, template=template, contas=contas
        )
        if not entradas:
            # Nenhuma conta aceitou: não há template nenhum na Meta, e gravar aqui criaria
            # uma linha fantasma no catálogo que ocuparia o nome sem existir do outro lado.
            raise CatalogoIndisponivelEmTodasAsContas("; ".join(erros))

        template.wabas = entradas
        salvo = await self._templates.salvar(template)
        logger.info(
            "Template %r (%s) submetido em %d de %d conta(s): status=%s",
            salvo.nome,
            salvo.escopo,
            len(entradas),
            len(contas),
            salvo.status.value,
        )
        return salvo


class ListarTemplates:
    def __init__(self, *, templates: TemplateRepository) -> None:
        self._templates = templates

    async def executar(self, *, tenant_id: UUID) -> list[MessageTemplate]:
        return await self._templates.listar(tenant_id=tenant_id)


class ObterTemplate:
    def __init__(self, *, templates: TemplateRepository) -> None:
        self._templates = templates

    async def executar(self, *, tenant_id: UUID, template_id: UUID) -> MessageTemplate:
        template = await self._templates.obter(tenant_id=tenant_id, template_id=template_id)
        if template is None:
            raise TemplateNaoEncontrado("Template não encontrado.")
        return template


class RemoverTemplate:
    """Apaga na Meta — em **todas** as contas onde foi submetido — e no nosso catálogo.

    Falha da Meta **não** é engolida: apagar só do nosso lado deixaria o nome ocupado lá,
    e a próxima tentativa de criar com o mesmo nome bateria num erro que não faria sentido
    para quem acabou de ver a lista vazia. Com várias contas isso vale por conta: sobrar em
    uma basta para o nome seguir ocupado nela.
    """

    def __init__(
        self,
        *,
        templates: TemplateRepository,
        catalogo: CatalogoTemplates,
        wabas: WabaRepository,
    ) -> None:
        self._templates = templates
        self._catalogo = catalogo
        self._wabas = wabas

    async def executar(
        self, *, usuario: Usuario, tenant_id: UUID, template_id: UUID
    ) -> None:
        template = await self._templates.obter(tenant_id=tenant_id, template_id=template_id)
        if template is None:
            raise TemplateNaoEncontrado("Template não encontrado.")
        _exige_permissao(usuario, template)

        for entrada in template.wabas:
            conta = await self._wabas.obter(entrada.waba_id)
            if conta is None:  # conta já removida: não há o que apagar do outro lado
                continue
            await self._catalogo.remover(
                nome=template.nome, meta_waba_id=conta.meta_waba_id
            )

        await self._templates.remover(template.id)
        logger.info(
            "Template %r removido do catálogo e de %d conta(s) na Meta",
            template.nome,
            len(template.wabas),
        )


class SincronizarTemplates:
    """Puxa os status da Meta, conta a conta, e aplica ao catálogo.

    É a rede de segurança do webhook: webhook perdido é indistinguível de template ainda
    em análise, e sem uma forma de reconciliar alguém ficaria esperando para sempre por
    uma aprovação que já saiu.

    **Percorre cada WABA**, e não só a "principal": o mesmo texto tem status próprio em
    cada conta, e sincronizar uma delas deixaria as outras congeladas no estado da
    submissão.
    """

    def __init__(
        self,
        *,
        templates: TemplateRepository,
        catalogo: CatalogoTemplates,
        wabas: WabaRepository,
    ) -> None:
        self._templates = templates
        self._catalogo = catalogo
        self._wabas = wabas

    async def executar(self) -> ResultadoSincronizacao:
        contas = await self._wabas.listar(apenas_ativas=True)
        locais = await self._templates.listar_todos()
        por_chave = {(t.nome, t.idioma): t for t in locais}

        verificados = 0
        atualizados = 0
        desconhecidos = 0
        tocados: dict[UUID, MessageTemplate] = {}

        for conta in contas:
            try:
                remotos = await self._catalogo.listar(meta_waba_id=conta.meta_waba_id)
            except Exception as exc:  # noqa: BLE001 — uma conta fora não cancela as demais
                logger.warning("Não foi possível listar templates de %r: %s", conta.nome, exc)
                continue
            verificados += len(remotos)
            for remoto in remotos:
                local = por_chave.get((remoto.nome, remoto.idioma))
                if local is None:
                    # Template criado direto no WhatsApp Manager. Não importamos: sem
                    # saber se é global ou de uma escola, o palpite erraria o isolamento.
                    desconhecidos += 1
                    continue
                if _aplicar_remoto(local, remoto, waba_id=conta.id):
                    tocados[local.id] = local

        for local in tocados.values():
            await self._templates.salvar(local)
            atualizados += 1

        logger.info(
            "Sincronização de templates: %d conta(s), %d na Meta, %d atualizados, "
            "%d fora do catálogo",
            len(contas),
            verificados,
            atualizados,
            desconhecidos,
        )
        return ResultadoSincronizacao(
            verificados=verificados, atualizados=atualizados, desconhecidos=desconhecidos
        )


class ReplicarTemplates:
    """Submete os templates globais nas contas onde ainda não existem.

    É o que faz uma **conta nova** herdar o catálogo compartilhado. Sem isso, cadastrar a
    WABA seguinte deixaria as escolas dela sem nenhum template aprovado — e a falha
    apareceria só no primeiro disparo, para a escola que acabou de entrar.

    Também recupera a submissão que falhou por rede na criação (§``_submeter_nas_contas``).
    Só mexe em template **global**: o de uma escola pertence à conta dela e replicá-lo
    ocuparia o nome em contas que nunca o usariam.
    """

    def __init__(
        self,
        *,
        templates: TemplateRepository,
        catalogo: CatalogoTemplates,
        wabas: WabaRepository,
    ) -> None:
        self._templates = templates
        self._catalogo = catalogo
        self._wabas = wabas

    async def executar(self) -> ResultadoReplicacao:
        contas = await self._wabas.listar(apenas_ativas=True)
        if not contas:
            raise SemContaWhatsApp("Nenhuma conta do WhatsApp Business ativa cadastrada.")

        submetidos = falhas = ja_existiam = 0
        for template in await self._templates.listar_todos():
            if not template.global_:
                continue
            faltantes = [c for c in contas if template.na_waba(c.id) is None]
            ja_existiam += len(contas) - len(faltantes)
            if not faltantes:
                continue
            entradas, erros = await _submeter_nas_contas(
                catalogo=self._catalogo, template=template, contas=faltantes
            )
            falhas += len(erros)
            submetidos += len(entradas)
            if entradas:
                template.wabas = list(template.wabas) + entradas
                await self._templates.salvar(template)

        logger.info(
            "Replicação de templates: %d submetidos, %d já existiam, %d falhas",
            submetidos,
            ja_existiam,
            falhas,
        )
        return ResultadoReplicacao(
            submetidos=submetidos, falhas=falhas, ja_existiam=ja_existiam
        )


def _aplicar_remoto(
    local: MessageTemplate, remoto: TemplateRemoto, *, waba_id: UUID
) -> bool:
    """Copia o que a Meta decidiu **naquela conta**. Devolve se algo mudou.

    A categoria é do texto (a Meta reclassifica igual em toda conta) e por isso fica na
    entidade; status, motivo e id são da conta.
    """
    mudou = False
    entrada = local.na_waba(waba_id)
    if entrada is None:
        # Existe na Meta e ainda não no nosso registro daquela conta — foi submetido por
        # fora, ou a gravação da submissão se perdeu. Adotar é melhor que ignorar: sem
        # isso o painel diria "não submetido" para um template que está lá.
        entrada = TemplateNaWaba(waba_id=waba_id, status=remoto.status)
        local.wabas = list(local.wabas) + [entrada]
        mudou = True
    if entrada.status is not remoto.status:
        entrada.status = remoto.status
        mudou = True
    if entrada.motivo_rejeicao != remoto.motivo_rejeicao:
        entrada.motivo_rejeicao = remoto.motivo_rejeicao
        mudou = True
    if remoto.meta_template_id and entrada.meta_template_id != remoto.meta_template_id:
        entrada.meta_template_id = remoto.meta_template_id
        mudou = True
    if local.categoria is not remoto.categoria:
        local.categoria = remoto.categoria
        mudou = True
    return mudou


class AtualizarStatusTemplateMeta:
    """Aplica o evento ``message_template_status_update`` do webhook.

    O evento **não traz escola nenhuma** — templates não pertencem a escola —, então a
    busca é cross-tenant. É a única leitura do produto que ignora ``tenant_id`` de
    propósito, e pode fazê-lo porque o remetente do evento já foi provado pela assinatura
    HMAC do webhook (§9e.2).

    **Qual conta, porém, o evento diz:** ``entry[].id`` é o id da WABA. Isso importa desde
    que o mesmo texto passou a existir em várias — sem olhar a entry, uma aprovação na
    conta A marcaria aprovado o template da conta B, que é exatamente a mentira que o
    modelo por conta veio corrigir. O ``message_template_id`` é único na Meta inteira e
    identifica as duas coisas de uma vez; a entry é o desempate de quando ele não vem.
    """

    def __init__(
        self, *, templates: TemplateRepository, wabas: WabaRepository
    ) -> None:
        self._templates = templates
        self._wabas = wabas

    async def executar(self, *, payload: dict) -> int:
        atualizados = 0
        for entrada in payload.get("entry", []) or []:
            conta = await self._wabas.por_meta_id(str(entrada.get("id") or ""))
            for mudanca in entrada.get("changes", []) or []:
                campo = mudanca.get("field")
                if campo not in (
                    "message_template_status_update",
                    "template_category_update",
                ):
                    continue
                if await self._aplicar(mudanca.get("value") or {}, conta=conta):
                    atualizados += 1
        return atualizados

    async def _aplicar(self, valor: dict, *, conta: Waba | None) -> bool:
        achado = await self._localizar(valor, conta=conta)
        if achado is None:
            logger.info(
                "Evento de template ignorado: %r não está no catálogo",
                valor.get("message_template_name"),
            )
            return False
        template, waba_id = achado

        # **Status é da conta; categoria é do texto.** A reclassificação vale igual em
        # toda conta e não depende de saber qual delas mandou o evento — condicioná-la à
        # entrada faria perder a informação que mais custa perder, já que é ela que muda
        # o preço do disparo.
        mudou = False
        entrada = template.na_waba(waba_id) if waba_id is not None else None
        evento = valor.get("event") or valor.get("new_template_status")
        if evento and entrada is None:
            logger.info(
                "Status de template ignorado: %r não foi submetido na conta do evento",
                valor.get("message_template_name"),
            )
        elif evento and entrada is not None:
            from app.infrastructure.channel.meta_templates import (
                motivo_da_meta,
                status_da_meta,
            )

            novo = status_da_meta(str(evento))
            motivo = motivo_da_meta(
                status_bruto=str(evento), motivo=valor.get("reason")
            )
            if entrada.status is not novo:
                entrada.status = novo
                mudou = True
            if entrada.motivo_rejeicao != motivo:
                entrada.motivo_rejeicao = motivo
                mudou = True

        nova_categoria = valor.get("new_category")
        if nova_categoria:
            from app.infrastructure.channel.meta_templates import categoria_da_meta

            categoria = categoria_da_meta(str(nova_categoria))
            if template.categoria is not categoria:
                # Reclassificação muda o preço do disparo. Registrar em warning porque é
                # o tipo de mudança que ninguém percebe até a fatura.
                logger.warning(
                    "Meta reclassificou o template %r de %s para %s",
                    template.nome,
                    template.categoria.value,
                    categoria.value,
                )
                template.categoria = categoria
                mudou = True

        if mudou:
            await self._templates.salvar(template)
            logger.info(
                "Template %r atualizado pelo webhook: status=%s categoria=%s",
                template.nome,
                entrada.status.value if entrada else "—",
                template.categoria.value,
            )
        return mudou

    async def _localizar(
        self, valor: dict, *, conta: Waba | None
    ) -> tuple[MessageTemplate, UUID | None] | None:
        """Devolve o template e a conta do evento (``None`` quando não dá para saber).

        Sem conta ainda vale localizar: a reclassificação de categoria é do texto e se
        aplica de qualquer forma. Só o status fica de fora.
        """
        meta_id = str(valor.get("message_template_id") or "")
        if meta_id:
            achado = await self._templates.por_meta_id(meta_id)
            if achado is not None:
                # O id é emitido por conta, então ele já aponta a entrada exata — mesmo
                # que a entry venha de uma WABA que não conhecemos.
                entrada = next(
                    (w for w in achado.wabas if w.meta_template_id == meta_id), None
                )
                if entrada is not None:
                    return achado, entrada.waba_id

        nome = valor.get("message_template_name")
        idioma = valor.get("message_template_language") or IDIOMA_PADRAO
        if not nome:
            return None
        template = await self._templates.por_nome_e_idioma(
            nome=str(nome), idioma=str(idioma)
        )
        # Sem saber de que conta veio, o **status** não é aplicado (seria chute, e o chute
        # erra justamente quando há mais de uma conta). Devolver assim mesmo permite que a
        # categoria, que não depende da conta, seja aplicada.
        if template is None:
            return None
        return template, (conta.id if conta else None)
