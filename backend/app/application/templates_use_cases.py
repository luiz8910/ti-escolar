"""Catálogo de templates (HSM): criação, submissão à Meta e sincronização de status.

**Dois escopos, de propósito** (§9a):

- **Global** (``tenant_id`` nulo) — o caso comum. Um ``aviso_geral`` com o nome da escola
  em ``{{1}}`` é aprovado uma vez e serve todas. Só o super admin mexe: o template é da
  WABA, que é ativo compartilhado, e deixar cada escola criar global seria dar a uma
  escola o poder de alterar o que as outras usam.
- **Por escola** — para o que é mesmo específico dela, com o nome prefixado pelo slug.
  Aqui o admin da escola cria, porque o estrago fica contido no nome dela.

**A submissão é assíncrona.** ``CriarTemplate`` devolve ``pendente``; quem transforma em
``aprovado`` é o webhook ``message_template_status_update`` (ou a sincronização manual,
para quando o webhook falhar). Nada disso libera envio sozinho — ``EnviarBroadcast`` e a
retomada de atendimento continuam exigindo ``StatusTemplate.APROVADO``.
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
    StatusTemplate,
    TemplateRemoto,
    Usuario,
)
from app.domain.ports import (
    CatalogoTemplates,
    TemplateRepository,
    TenantRepository,
)

logger = logging.getLogger("templates")

IDIOMA_PADRAO = "pt_BR"


class TemplateNaoEncontrado(LookupError):
    pass


class PermissaoTemplateNegada(PermissionError):
    pass


@dataclass(frozen=True)
class ResultadoSincronizacao:
    verificados: int
    atualizados: int
    desconhecidos: int  # existem na Meta e não no nosso banco


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


class CriarTemplate:
    """Valida, submete à Meta e persiste como pendente.

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
    ) -> None:
        self._templates = templates
        self._catalogo = catalogo
        self._tenants = tenants

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
            status=StatusTemplate.PENDENTE,
        )

        remoto = await self._catalogo.submeter(template)
        template.meta_template_id = remoto.meta_template_id
        template.status = remoto.status
        template.motivo_rejeicao = remoto.motivo_rejeicao
        # A Meta pode reclassificar a categoria na própria submissão (aviso que ela
        # entende como divulgação vira marketing). Guardar o que ela decidiu, e não o que
        # pedimos, é o que faz a tela mostrar o custo real.
        template.categoria = remoto.categoria

        salvo = await self._templates.salvar(template)
        logger.info(
            "Template %r (%s) submetido à Meta: status=%s",
            salvo.nome,
            salvo.escopo,
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
    """Apaga na Meta e no nosso catálogo.

    Falha da Meta **não** é engolida: apagar só do nosso lado deixaria o nome ocupado lá,
    e a próxima tentativa de criar com o mesmo nome bateria num erro que não faria sentido
    para quem acabou de ver a lista vazia.
    """

    def __init__(
        self, *, templates: TemplateRepository, catalogo: CatalogoTemplates
    ) -> None:
        self._templates = templates
        self._catalogo = catalogo

    async def executar(
        self, *, usuario: Usuario, tenant_id: UUID, template_id: UUID
    ) -> None:
        template = await self._templates.obter(tenant_id=tenant_id, template_id=template_id)
        if template is None:
            raise TemplateNaoEncontrado("Template não encontrado.")
        _exige_permissao(usuario, template)

        await self._catalogo.remover(nome=template.nome)
        await self._templates.remover(template.id)
        logger.info("Template %r removido do catálogo e da Meta", template.nome)


class SincronizarTemplates:
    """Puxa os status da Meta e aplica ao catálogo — a rede de segurança do webhook.

    O webhook é o caminho normal; isto existe porque webhook perdido é indistinguível de
    template ainda em análise, e sem uma forma de reconciliar alguém ficaria esperando
    para sempre por uma aprovação que já saiu.
    """

    def __init__(
        self, *, templates: TemplateRepository, catalogo: CatalogoTemplates
    ) -> None:
        self._templates = templates
        self._catalogo = catalogo

    async def executar(self) -> ResultadoSincronizacao:
        remotos = await self._catalogo.listar()
        locais = await self._templates.listar_todos()
        por_chave = {(t.nome, t.idioma): t for t in locais}

        atualizados = 0
        desconhecidos = 0
        for remoto in remotos:
            local = por_chave.get((remoto.nome, remoto.idioma))
            if local is None:
                # Template criado direto no WhatsApp Manager. Não importamos: sem saber
                # se é global ou de uma escola, o palpite erraria o isolamento.
                desconhecidos += 1
                continue
            if _aplicar_remoto(local, remoto):
                await self._templates.salvar(local)
                atualizados += 1

        logger.info(
            "Sincronização de templates: %d na Meta, %d atualizados, %d fora do catálogo",
            len(remotos),
            atualizados,
            desconhecidos,
        )
        return ResultadoSincronizacao(
            verificados=len(remotos), atualizados=atualizados, desconhecidos=desconhecidos
        )


def _aplicar_remoto(local: MessageTemplate, remoto: TemplateRemoto) -> bool:
    """Copia o que a Meta decidiu. Devolve se algo mudou (para não gravar à toa)."""
    mudou = False
    if local.status is not remoto.status:
        local.status = remoto.status
        mudou = True
    if local.motivo_rejeicao != remoto.motivo_rejeicao:
        local.motivo_rejeicao = remoto.motivo_rejeicao
        mudou = True
    if local.categoria is not remoto.categoria:
        local.categoria = remoto.categoria
        mudou = True
    if remoto.meta_template_id and local.meta_template_id != remoto.meta_template_id:
        local.meta_template_id = remoto.meta_template_id
        mudou = True
    return mudou


class AtualizarStatusTemplateMeta:
    """Aplica o evento ``message_template_status_update`` do webhook.

    O evento **não traz escola nenhuma** — templates são da WABA —, então a busca é
    cross-tenant: pelo id da Meta, e pelo par (nome, idioma) quando o id não vem. É a
    única leitura do produto que ignora ``tenant_id`` de propósito, e pode fazê-lo porque
    o remetente do evento já foi provado pela assinatura HMAC do webhook (§9e.2).
    """

    def __init__(self, *, templates: TemplateRepository) -> None:
        self._templates = templates

    async def executar(self, *, payload: dict) -> int:
        atualizados = 0
        for entrada in payload.get("entry", []) or []:
            for mudanca in entrada.get("changes", []) or []:
                campo = mudanca.get("field")
                if campo not in (
                    "message_template_status_update",
                    "template_category_update",
                ):
                    continue
                if await self._aplicar(mudanca.get("value") or {}):
                    atualizados += 1
        return atualizados

    async def _aplicar(self, valor: dict) -> bool:
        template = await self._localizar(valor)
        if template is None:
            logger.info(
                "Evento de template ignorado: %r não está no catálogo",
                valor.get("message_template_name"),
            )
            return False

        mudou = False
        evento = valor.get("event") or valor.get("new_template_status")
        if evento:
            from app.infrastructure.channel.meta_templates import (
                motivo_da_meta,
                status_da_meta,
            )

            novo = status_da_meta(str(evento))
            motivo = motivo_da_meta(
                status_bruto=str(evento), motivo=valor.get("reason")
            )
            if template.status is not novo:
                template.status = novo
                mudou = True
            if template.motivo_rejeicao != motivo:
                template.motivo_rejeicao = motivo
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
                template.status.value,
                template.categoria.value,
            )
        return mudou

    async def _localizar(self, valor: dict) -> MessageTemplate | None:
        meta_id = valor.get("message_template_id")
        if meta_id:
            achado = await self._templates.por_meta_id(str(meta_id))
            if achado is not None:
                return achado
        nome = valor.get("message_template_name")
        idioma = valor.get("message_template_language") or IDIOMA_PADRAO
        if nome:
            return await self._templates.por_nome_e_idioma(nome=str(nome), idioma=str(idioma))
        return None
