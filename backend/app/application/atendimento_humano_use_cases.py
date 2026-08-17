"""Atendimento humano: o assistente entrega a conversa à secretaria (§6j).

O produto passou a **atender** com o inbound real (§9e.1), mas atender não é responder
tudo: há assunto que exige decisão de gente — uma matrícula específica, uma reclamação,
uma ocorrência com o aluno. Este módulo é a ponte, e ela tem três regras que valem mais
que o código que as implementa:

- **Nunca encaminhar de saída.** O assistente tenta responder primeiro. Encaminhamento na
  primeira mensagem transformaria o produto num formulário de contato caro.
- **Perguntar antes.** Ao desistir, ele *oferece* ("quer que eu chame alguém da
  secretaria?") e só o "sim" do responsável abre o atendimento. A exceção é o responsável
  que já pediu uma pessoa explicitamente: aí a pergunta seria burocracia.
- **Respeitar o expediente.** Fora do horário o atendimento **entra na fila mesmo assim**
  (recusar perderia justamente o recado de quem escreve à noite), mas o que o assistente
  promete ao responsável é o próximo dia útil — a partir de ``Tenant``, nunca da base de
  conhecimento.

Do lado do responsável não existe "transferência": é a **mesma conversa de WhatsApp**, com
a resposta saindo pelo mesmo número da escola. Quem muda é quem escreve do outro lado.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.application.paginacao import (
    POR_PAGINA_PADRAO,
    Pagina,
    normalizar_paginacao,
)
from app.domain.entities import (
    STATUS_ATENDIMENTO_NA_FILA,
    AtendimentoHumano,
    Autor,
    CategoriaTemplate,
    MessageTemplate,
    StatusAtendimentoHumano,
    StatusTemplate,
    Tenant,
    Usuario,
    formatar_hora,
)
from app.domain.ports import (
    AtendimentoHumanoRepository,
    ContatoRepository,
    ConversaRepository,
    MessageChannel,
    QuotaPolicy,
    TemplateRepository,
    TenantRepository,
)

logger = logging.getLogger("atendimento.humano")

# Uma oferta sem resposta não vale para sempre: passado esse prazo ela é descartada e o
# assistente pode oferecer de novo. Sem isso, uma oferta ignorada em março impediria a
# pergunta em agosto — ou, pior, autorizaria um encaminhamento direto meses depois.
OFERTA_VALIDA_HORAS = 24

# Respostas do assistente que precisam existir na conversa antes de ele poder desistir.
# Não é regra de prompt: é validada em código, porque o prompt é sugestão.
MIN_RESPOSTAS_ANTES_DE_ENCAMINHAR = 2


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EncaminhamentoRecusado(Exception):
    """O encaminhamento não é permitido agora.

    A mensagem é **orientação para o modelo**, não erro para o usuário: ela volta como
    resultado da ferramenta e diz ao assistente o que fazer em vez de encaminhar.
    """

    def __init__(self, orientacao: str) -> None:
        super().__init__(orientacao)
        self.orientacao = orientacao


def formatar_retorno(escola: Tenant, *, agora: datetime | None = None) -> str:
    """Quando a secretaria volta a atender, em texto para o responsável ler.

    Sai do campo ``expediente_*`` da escola — é a única fonte da promessa feita a quem
    está esperando.
    """
    agora = agora or _now()
    if escola.dentro_do_expediente(agora):
        return "agora"
    proxima = escola.proxima_abertura(agora)
    if proxima is None:
        return ""

    local = escola.hora_local(proxima)
    hoje = escola.hora_local(agora).date()
    hora = formatar_hora(local.time())
    if local.date() == hoje:
        return f"hoje a partir das {hora}"
    if local.date() == hoje + timedelta(days=1):
        return f"amanhã a partir das {hora}"
    dias = {
        1: "segunda-feira",
        2: "terça-feira",
        3: "quarta-feira",
        4: "quinta-feira",
        5: "sexta-feira",
        6: "sábado",
        7: "domingo",
    }
    return f"{dias[local.isoweekday()]} ({local:%d/%m}) a partir das {hora}"


class _BaseAtendimento:
    """Infra comum: buscar a escola, nomear o responsável e expirar oferta vencida."""

    def __init__(
        self,
        *,
        atendimentos: AtendimentoHumanoRepository,
        tenants: TenantRepository | None = None,
        contatos: ContatoRepository | None = None,
    ) -> None:
        self._atendimentos = atendimentos
        self._tenants = tenants
        self._contatos = contatos

    async def _escola(self, tenant_id: UUID) -> Tenant | None:
        if self._tenants is None:
            return None
        return await self._tenants.obter(tenant_id)

    async def _nome_do_contato(self, *, tenant_id: UUID, telefone: str) -> str:
        if self._contatos is None:
            return ""
        contato = await self._contatos.por_telefone(tenant_id=tenant_id, telefone=telefone)
        return contato.nome if contato else ""

    async def _vivo_na_conversa(self, conversa_id: UUID) -> AtendimentoHumano | None:
        """O atendimento vivo da conversa, já descartando oferta vencida."""
        atual = await self._atendimentos.em_aberto_por_conversa(conversa_id=conversa_id)
        if atual is None:
            return None
        if atual.status is StatusAtendimentoHumano.OFERECIDO:
            referencia = atual.ofereceu_em or atual.criado_em
            if _now() - referencia > timedelta(hours=OFERTA_VALIDA_HORAS):
                atual.status = StatusAtendimentoHumano.DESCARTADO
                await self._atendimentos.atualizar(atual)
                return None
        return atual


class OferecerAtendimentoHumano(_BaseAtendimento):
    """Registra que o assistente ofereceu atendimento humano e ainda espera o "sim".

    Não coloca nada na fila da secretaria: só o "sim" do responsável faz isso
    (``EscalarParaSecretaria``). O registro existe para dois fins — impedir que o
    assistente encaminhe sem ter perguntado, e medir quantas ofertas são ignoradas.
    """

    async def executar(
        self, *, tenant_id: UUID, conversa_id: UUID, contato: str, motivo: str = ""
    ) -> AtendimentoHumano:
        atual = await self._vivo_na_conversa(conversa_id)
        if atual is not None:
            # Já oferecido (ou já na fila): não duplica o card.
            if motivo.strip() and not atual.motivo:
                atual.motivo = motivo.strip()
                atual = await self._atendimentos.atualizar(atual)
            return atual

        agora = _now()
        return await self._atendimentos.criar(
            AtendimentoHumano(
                tenant_id=tenant_id,
                conversa_id=conversa_id,
                contato=contato,
                contato_nome=await self._nome_do_contato(
                    tenant_id=tenant_id, telefone=contato
                ),
                motivo=motivo.strip(),
                status=StatusAtendimentoHumano.OFERECIDO,
                ofereceu_em=agora,
                ultima_mensagem_responsavel_em=agora,
            )
        )


class EscalarParaSecretaria(_BaseAtendimento):
    """Põe a conversa na fila da secretaria — com as duas travas do §6j.

    Idempotente por conversa: o responsável insistir três vezes não vira três cards.
    """

    async def executar(
        self,
        *,
        tenant_id: UUID,
        conversa_id: UUID,
        contato: str,
        motivo: str = "",
        pedido_explicito: bool = False,
        respostas_anteriores: int = 0,
        abertura_direta: bool = False,
    ) -> AtendimentoHumano:
        atual = await self._vivo_na_conversa(conversa_id)

        # `abertura_direta` é a exceção **da escola**, não do responsável: assuntos que
        # sempre exigem uma pessoa e são sensíveis ao relógio — hoje, a saída antecipada
        # do aluno (§6l). Perguntar "quer que eu chame alguém?" ali gastaria justamente os
        # minutos que importam, e a resposta seria sempre "sim".
        sem_travas = pedido_explicito or abertura_direta

        # Trava 1 — não nas primeiras mensagens. Quem pediu uma pessoa explicitamente
        # passa: exigir que ele espere duas respostas automáticas seria hostil.
        if (
            not sem_travas
            and atual is None
            and respostas_anteriores < MIN_RESPOSTAS_ANTES_DE_ENCAMINHAR
        ):
            raise EncaminhamentoRecusado(
                "Ainda não houve tentativa suficiente de responder. Busque na base de "
                "conhecimento da escola e responda ao responsável; só ofereça atendimento "
                "humano se de fato não for possível resolver."
            )

        # Trava 2 — oferecer antes de encaminhar.
        if atual is None and not sem_travas:
            oferta = await OferecerAtendimentoHumano(
                atendimentos=self._atendimentos,
                tenants=self._tenants,
                contatos=self._contatos,
            ).executar(
                tenant_id=tenant_id,
                conversa_id=conversa_id,
                contato=contato,
                motivo=motivo,
            )
            raise EncaminhamentoRecusado(
                "Antes de encaminhar, pergunte ao responsável se ele deseja falar com "
                "alguém da secretaria e aguarde a confirmação. A oferta foi registrada "
                f"(id {oferta.id})."
            )

        agora = _now()
        escola = await self._escola(tenant_id)
        # Fora do expediente o atendimento entra na fila do mesmo jeito: descartar perderia
        # o recado de quem escreve à noite, que é justamente quem mais depende do canal.
        fora = bool(escola) and not escola.dentro_do_expediente(agora)

        if atual is not None:
            if atual.status in STATUS_ATENDIMENTO_NA_FILA:
                if motivo.strip():
                    atual.motivo = motivo.strip()
                atual.ultima_mensagem_responsavel_em = agora
                return await self._atendimentos.atualizar(atual)
            # Estava OFERECIDO: o "sim" chegou.
            atual.status = StatusAtendimentoHumano.ABERTO
            atual.confirmado_em = agora
            atual.fora_expediente = fora
            atual.ultima_mensagem_responsavel_em = agora
            if motivo.strip():
                atual.motivo = motivo.strip()
            return await self._atendimentos.atualizar(atual)

        # Pedido explícito sem oferta anterior: abre direto.
        return await self._atendimentos.criar(
            AtendimentoHumano(
                tenant_id=tenant_id,
                conversa_id=conversa_id,
                contato=contato,
                contato_nome=await self._nome_do_contato(
                    tenant_id=tenant_id, telefone=contato
                ),
                motivo=motivo.strip(),
                status=StatusAtendimentoHumano.ABERTO,
                ofereceu_em=agora,
                confirmado_em=agora,
                fora_expediente=fora,
                ultima_mensagem_responsavel_em=agora,
            )
        )


class RegistrarRetornoDoResponsavel:
    """O responsável escreveu de novo numa conversa que já está com a secretaria.

    Faz duas coisas indispensáveis: renova a base da **janela de 24h** (senão o atendente
    perde o direito ao texto livre sem que nada tenha mudado do lado do responsável) e
    devolve o atendimento à fila se ele já estava marcado como resolvido — assunto que
    volta não é assunto resolvido.
    """

    def __init__(self, *, atendimentos: AtendimentoHumanoRepository) -> None:
        self._atendimentos = atendimentos

    async def executar(
        self, *, atendimento: AtendimentoHumano, quando: datetime | None = None
    ) -> AtendimentoHumano:
        atendimento.ultima_mensagem_responsavel_em = quando or _now()
        if atendimento.status is StatusAtendimentoHumano.RESOLVIDO:
            atendimento.status = StatusAtendimentoHumano.ABERTO
            atendimento.resolvido_em = None
        return await self._atendimentos.atualizar(atendimento)


class _NomeadorDeContatos:
    """Preenche ``contato_nome`` **na leitura**, a partir do cadastro atual.

    O campo persistido é um retrato do momento em que o atendimento nasceu — e o caso
    comum é justamente o responsável ainda não estar cadastrado quando escreve. Sem esta
    releitura, o card fica com o telefone cru para sempre, mesmo depois de a secretaria
    cadastrar a pessoa. Resolver aqui também cobre a troca de nome (casamento, correção
    de grafia) sem precisar reescrever histórico.

    Em lote: uma consulta por página, não uma por card.
    """

    def __init__(self, contatos: ContatoRepository | None) -> None:
        self._contatos = contatos

    async def nomear(
        self, tenant_id: UUID, atendimentos: Sequence[AtendimentoHumano]
    ) -> None:
        if self._contatos is None or not atendimentos:
            return
        encontrados = await self._contatos.por_telefones(
            tenant_id=tenant_id, telefones=[a.contato for a in atendimentos]
        )
        for atendimento in atendimentos:
            contato = encontrados.get(atendimento.contato)
            if contato is not None and contato.nome:
                atendimento.contato_nome = contato.nome


class ListarAtendimentos:
    """Fila da secretaria, mais antigos primeiro (maior tempo de espera no topo)."""

    def __init__(
        self,
        *,
        atendimentos: AtendimentoHumanoRepository,
        contatos: ContatoRepository | None = None,
    ) -> None:
        self._atendimentos = atendimentos
        self._nomeador = _NomeadorDeContatos(contatos)

    async def executar(
        self,
        *,
        tenant_id: UUID,
        status: list[StatusAtendimentoHumano] | None = None,
        atendente_id: UUID | None = None,
        pagina: int = 1,
        por_pagina: int = POR_PAGINA_PADRAO,
    ) -> Pagina[AtendimentoHumano]:
        pagina, por_pagina = normalizar_paginacao(pagina, por_pagina)
        # Sem filtro explícito, "a fila" é o que exige ação — não o arquivo de resolvidos.
        alvo = list(status) if status else list(STATUS_ATENDIMENTO_NA_FILA)
        total = await self._atendimentos.contar(
            tenant_id=tenant_id, status=alvo, atendente_id=atendente_id
        )
        itens = await self._atendimentos.listar(
            tenant_id=tenant_id,
            status=alvo,
            atendente_id=atendente_id,
            pagina=pagina,
            por_pagina=por_pagina,
        )
        await self._nomeador.nomear(tenant_id, itens)
        return Pagina(itens=itens, total=total, pagina=pagina, por_pagina=por_pagina)


class ContarAtendimentosPendentes:
    """Contador do badge do painel: quantos responsáveis estão esperando agora."""

    def __init__(self, *, atendimentos: AtendimentoHumanoRepository) -> None:
        self._atendimentos = atendimentos

    async def executar(self, *, tenant_id: UUID) -> int:
        return await self._atendimentos.contar(
            tenant_id=tenant_id, status=list(STATUS_ATENDIMENTO_NA_FILA)
        )


class ObterAtendimento:
    def __init__(
        self,
        *,
        atendimentos: AtendimentoHumanoRepository,
        contatos: ContatoRepository | None = None,
    ) -> None:
        self._atendimentos = atendimentos
        self._nomeador = _NomeadorDeContatos(contatos)

    async def executar(
        self, *, tenant_id: UUID, atendimento_id: UUID
    ) -> AtendimentoHumano | None:
        atendimento = await self._atendimentos.obter(
            tenant_id=tenant_id, atendimento_id=atendimento_id
        )
        if atendimento is not None:
            await self._nomeador.nomear(tenant_id, [atendimento])
        return atendimento


async def _carregar(
    atendimentos: AtendimentoHumanoRepository, *, tenant_id: UUID, atendimento_id: UUID
) -> AtendimentoHumano:
    atendimento = await atendimentos.obter(
        tenant_id=tenant_id, atendimento_id=atendimento_id
    )
    if atendimento is None:
        raise ValueError("Atendimento não encontrado.")
    return atendimento


class AssumirAtendimento:
    """Uma pessoa da secretaria toma o caso para si.

    Trava explícita: dois atendentes respondendo o mesmo responsável ao mesmo tempo é o
    modo de falha óbvio de uma fila compartilhada, e o responsável recebe duas respostas
    possivelmente contraditórias pelo mesmo número.
    """

    def __init__(self, *, atendimentos: AtendimentoHumanoRepository) -> None:
        self._atendimentos = atendimentos

    async def executar(
        self, *, tenant_id: UUID, atendimento_id: UUID, usuario: Usuario
    ) -> AtendimentoHumano:
        atendimento = await _carregar(
            self._atendimentos, tenant_id=tenant_id, atendimento_id=atendimento_id
        )
        if atendimento.atendente_id and atendimento.atendente_id != usuario.id:
            raise ValueError(
                f"Este atendimento já está com {atendimento.atendente_nome or 'outra pessoa'}."
            )
        if atendimento.status is StatusAtendimentoHumano.RESOLVIDO:
            raise ValueError("Este atendimento já foi resolvido.")
        atendimento.atendente_id = usuario.id
        atendimento.atendente_nome = usuario.nome
        atendimento.assumido_em = atendimento.assumido_em or _now()
        atendimento.status = StatusAtendimentoHumano.EM_ATENDIMENTO
        return await self._atendimentos.atualizar(atendimento)


class ResponderAtendimento:
    """A secretaria responde — **no mesmo fio**, pelo número da própria escola.

    Ordem importa: envia primeiro, grava depois. Gravar antes deixaria no histórico uma
    resposta que o responsável nunca recebeu, que é a pior forma de erro aqui — a escola
    acreditaria ter respondido.

    Fora da janela de 24h da Meta o texto livre é recusado pela Graph API; nesse caso a
    conversa é reaberta por **template aprovado** (§A9), e a falta do template vira erro
    explícito no painel em vez de mensagem que some.
    """

    def __init__(
        self,
        *,
        atendimentos: AtendimentoHumanoRepository,
        conversas: ConversaRepository,
        canal: MessageChannel,
        tenants: TenantRepository | None = None,
        templates: TemplateRepository | None = None,
        template_retomada: str = "",
        quota: QuotaPolicy | None = None,
    ) -> None:
        self._atendimentos = atendimentos
        self._conversas = conversas
        self._canal = canal
        self._tenants = tenants
        self._templates = templates
        self._template_retomada = template_retomada
        # Reabrir conversa por template é conversa **iniciada pelo negócio**: consome o
        # mesmo teto de 24h dos broadcasts. Sem isto o contador mentia para baixo, e a
        # escola descobria o limite pela recusa da Graph API no meio de um disparo.
        self._quota = quota

    async def executar(
        self,
        *,
        tenant_id: UUID,
        atendimento_id: UUID,
        usuario: Usuario,
        texto: str,
    ) -> AtendimentoHumano:
        texto = (texto or "").strip()
        if not texto:
            raise ValueError("Escreva a resposta ao responsável.")

        atendimento = await _carregar(
            self._atendimentos, tenant_id=tenant_id, atendimento_id=atendimento_id
        )
        if atendimento.atendente_id and atendimento.atendente_id != usuario.id:
            raise ValueError(
                f"Este atendimento está com {atendimento.atendente_nome or 'outra pessoa'}. "
                "Peça para ela liberar antes de responder."
            )

        escola = await self._tenants.obter(tenant_id) if self._tenants else None
        remetente = (escola.remetente_canal or None) if escola else None

        if atendimento.janela_aberta():
            await self._canal.enviar_texto(
                contato=atendimento.contato, texto=texto, remetente=remetente
            )
        else:
            await self._responder_fora_da_janela(
                atendimento, texto=texto, remetente=remetente, escola=escola
            )

        await self._conversas.adicionar_mensagem(
            conversa_id=atendimento.conversa_id,
            autor=Autor.ATENDENTE.value,
            texto=texto,
            autor_nome=usuario.nome,
        )

        # Responder é assumir: quem escreveu passa a ser o dono do caso.
        atendimento.atendente_id = usuario.id
        atendimento.atendente_nome = usuario.nome
        atendimento.assumido_em = atendimento.assumido_em or _now()
        atendimento.status = StatusAtendimentoHumano.EM_ATENDIMENTO
        return await self._atendimentos.atualizar(atendimento)

    async def _responder_fora_da_janela(
        self,
        atendimento: AtendimentoHumano,
        *,
        texto: str,
        remetente: str | None,
        escola: Tenant | None,
    ) -> None:
        """Reabre a conversa por template quando as 24h já passaram (§A9)."""
        template = await self._template_de_retomada(
            atendimento.tenant_id, waba_id=escola.waba_id if escola else None
        )
        if template is None:
            raise ValueError(
                "A janela de 24h do WhatsApp expirou para este responsável e não há "
                f"template de retomada aprovado ({self._template_retomada or '—'}). "
                "Cadastre e aprove o template na Meta para reabrir conversas antigas."
            )
        nome_escola = escola.nome if escola else "a escola"
        await self._canal.enviar_template(
            contato=atendimento.contato,
            template=template,
            # O corpo do template aprovado tem dois parâmetros: a escola e a resposta.
            parametros=[nome_escola, texto],
            remetente=remetente,
        )
        if self._quota is not None:
            # Depois do envio, nunca antes: cota consumida por mensagem que não saiu é
            # capacidade jogada fora, e aqui o excedente não tem retomada que o recupere.
            await self._quota.registrar_envio(atendimento.tenant_id, atendimento.contato)
        logger.info(
            "Atendimento %s respondido por template de retomada (janela de 24h expirada)",
            atendimento.id,
        )

    async def _template_de_retomada(
        self, tenant_id: UUID, *, waba_id: UUID | None
    ) -> MessageTemplate | None:
        if not self._template_retomada or self._templates is None:
            return None
        template = await self._templates.por_nome(
            tenant_id=tenant_id, nome=self._template_retomada
        )
        if template is None:
            return None
        # Aprovado **na conta desta escola**: o mesmo texto pode estar aprovado em outra
        # WABA e não existir nesta, e aí a Graph API recusa o envio.
        aprovado = (
            template.aprovado_em(waba_id)
            if waba_id is not None
            else template.status is StatusTemplate.APROVADO
        )
        if not aprovado:
            # Template não aprovado é template que a Meta recusa: melhor o erro claro
            # acima do que uma chamada que falha na Graph API sem explicação.
            return None
        if template.categoria is not CategoriaTemplate.UTILITY:
            logger.warning(
                "Template de retomada %r não é utility — a Meta pode recusar o envio.",
                template.nome,
            )
        return template


class ResolverAtendimento:
    """Fecha o caso — e, com ele, a **sessão de conversa** (§13).

    Assunto resolvido não deve continuar carregando contexto para o próximo, que costuma
    ser outro completamente: o pai volta em setembro para falar de uniforme e o modelo
    ainda está lendo a reclamação de março. Se o responsável escrever de novo, a próxima
    mensagem abre uma sessão nova; se ele voltar **no mesmo assunto**, o atendimento é
    reaberto por ``RegistrarRetornoDoResponsavel``, que sabe disso.

    ``conversas`` é opcional para o caso de uso seguir testável sem repositório de
    conversa — encerrar é efeito colateral, não o objetivo.
    """

    def __init__(
        self,
        *,
        atendimentos: AtendimentoHumanoRepository,
        conversas: ConversaRepository | None = None,
    ) -> None:
        self._atendimentos = atendimentos
        self._conversas = conversas

    async def executar(
        self, *, tenant_id: UUID, atendimento_id: UUID, usuario: Usuario
    ) -> AtendimentoHumano:
        atendimento = await _carregar(
            self._atendimentos, tenant_id=tenant_id, atendimento_id=atendimento_id
        )
        atendimento.status = StatusAtendimentoHumano.RESOLVIDO
        atendimento.resolvido_em = _now()
        if not atendimento.atendente_id:
            atendimento.atendente_id = usuario.id
            atendimento.atendente_nome = usuario.nome
        resolvido = await self._atendimentos.atualizar(atendimento)
        if self._conversas is not None:
            await self._conversas.encerrar(conversa_id=atendimento.conversa_id)
        return resolvido


class ReabrirAtendimento:
    """Devolve o caso à fila — e o libera, porque quem reabre nem sempre é quem atende."""

    def __init__(self, *, atendimentos: AtendimentoHumanoRepository) -> None:
        self._atendimentos = atendimentos

    async def executar(
        self, *, tenant_id: UUID, atendimento_id: UUID, liberar: bool = False
    ) -> AtendimentoHumano:
        atendimento = await _carregar(
            self._atendimentos, tenant_id=tenant_id, atendimento_id=atendimento_id
        )
        atendimento.status = StatusAtendimentoHumano.ABERTO
        atendimento.resolvido_em = None
        if liberar:
            atendimento.atendente_id = None
            atendimento.atendente_nome = ""
            atendimento.assumido_em = None
        return await self._atendimentos.atualizar(atendimento)


class MesaDeAtendimento:
    """Fachada do atendimento humano para quem atende a conversa (``AtenderConversa``).

    Existe para não despejar cinco colaboradores no construtor do caso de uso do inbound.
    Reúne o que o assistente precisa saber e fazer a respeito da secretaria: se alguém já
    assumiu esta conversa, registrar a oferta, encaminhar de fato e dizer quando a escola
    retorna.
    """

    def __init__(
        self,
        *,
        atendimentos: AtendimentoHumanoRepository,
        tenants: TenantRepository | None = None,
        contatos: ContatoRepository | None = None,
    ) -> None:
        self._atendimentos = atendimentos
        self._tenants = tenants
        self._contatos = contatos
        self._oferecer = OferecerAtendimentoHumano(
            atendimentos=atendimentos, tenants=tenants, contatos=contatos
        )
        self._escalar = EscalarParaSecretaria(
            atendimentos=atendimentos, tenants=tenants, contatos=contatos
        )
        self._retorno = RegistrarRetornoDoResponsavel(atendimentos=atendimentos)

    async def vivo_na_conversa(self, conversa_id: UUID) -> AtendimentoHumano | None:
        return await self._atendimentos.em_aberto_por_conversa(conversa_id=conversa_id)

    async def registrar_retorno(self, atendimento: AtendimentoHumano) -> AtendimentoHumano:
        return await self._retorno.executar(atendimento=atendimento)

    async def oferecer(
        self, *, tenant_id: UUID, conversa_id: UUID, contato: str, motivo: str
    ) -> AtendimentoHumano:
        return await self._oferecer.executar(
            tenant_id=tenant_id, conversa_id=conversa_id, contato=contato, motivo=motivo
        )

    async def escalar(
        self,
        *,
        tenant_id: UUID,
        conversa_id: UUID,
        contato: str,
        motivo: str,
        pedido_explicito: bool = False,
        respostas_anteriores: int = 0,
        abertura_direta: bool = False,
    ) -> AtendimentoHumano:
        return await self._escalar.executar(
            tenant_id=tenant_id,
            conversa_id=conversa_id,
            contato=contato,
            motivo=motivo,
            pedido_explicito=pedido_explicito,
            respostas_anteriores=respostas_anteriores,
            abertura_direta=abertura_direta,
        )

    async def previsao_de_retorno(self, tenant_id: UUID) -> str:
        """"agora", "amanhã a partir das 7h30"... — o que o assistente pode prometer."""
        if self._tenants is None:
            return ""
        escola = await self._tenants.obter(tenant_id)
        return formatar_retorno(escola) if escola else ""

    async def expediente(self, tenant_id: UUID) -> str:
        if self._tenants is None:
            return ""
        escola = await self._tenants.obter(tenant_id)
        return escola.descricao_expediente if escola else ""
