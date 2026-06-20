"""Casos de uso da aplicação.

Orquestram as portas do domínio. Sem framework, sem ORM, sem SDK — apenas regras de
coordenação. Tudo é escopado por ``tenant_id`` (multi-tenant).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.application.prompts import montar_sistema, montar_sistema_agente
from app.domain.entities import (
    AtorAuditoria,
    Broadcast,
    Documento,
    FerramentaSpec,
    RegistroAuditoria,
    ResultadoFerramenta,
    StatusBroadcast,
    StatusEntrega,
    StatusTemplate,
    TipoConhecimento,
    TrechoConhecimento,
    TurnoConversa,
)
from app.domain.ports import (
    AuditLogRepository,
    BroadcastRepository,
    ContatoRepository,
    ConversaRepository,
    DocumentSource,
    Embedder,
    LLMProvider,
    MessageChannel,
    PromptTenantRepository,
    QuotaPolicy,
    RateLimiter,
    TemplateRepository,
    VectorStore,
)


# --------------------------------------------------------------------------- #
# Indexação de conhecimento (RAG)
# --------------------------------------------------------------------------- #
class IndexarConhecimento:
    def __init__(self, *, embedder: Embedder, store: VectorStore) -> None:
        self._embedder = embedder
        self._store = store

    async def executar(
        self,
        *,
        tenant_id: UUID,
        tipo: TipoConhecimento,
        titulo: str,
        conteudo: str,
    ) -> TrechoConhecimento:
        trecho = TrechoConhecimento(
            tenant_id=tenant_id, tipo=tipo, titulo=titulo, conteudo=conteudo
        )
        [embedding] = await self._embedder.embed([f"{titulo}\n{conteudo}"])
        await self._store.indexar(trecho, embedding)
        return trecho


# --------------------------------------------------------------------------- #
# Responder dúvida (RAG + LLM)
# --------------------------------------------------------------------------- #
@dataclass
class RespostaDuvida:
    texto: str
    fontes: list[str]


async def _instrucoes_do_tenant(
    prompts: PromptTenantRepository | None, tenant_id: UUID
) -> str:
    """Carrega o system prompt personalizado da escola, se houver (ou string vazia)."""
    if prompts is None:
        return ""
    prompt = await prompts.obter(tenant_id=tenant_id)
    return prompt.conteudo if prompt else ""


class ResponderDuvida:
    """Recupera trechos relevantes, monta contexto e chama o LLM para raciocinar.

    Quando há um ``PromptTenantRepository``, as instruções personalizadas da escola são
    anexadas ao prompt de sistema (o "CLAUDE.md" daquele tenant).
    """

    def __init__(
        self,
        *,
        embedder: Embedder,
        store: VectorStore,
        llm: LLMProvider,
        prompts: PromptTenantRepository | None = None,
        k: int = 4,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._llm = llm
        self._prompts = prompts
        self._k = k

    async def executar(
        self,
        *,
        tenant_id: UUID,
        pergunta: str,
        historico: list[dict[str, str]] | None = None,
    ) -> RespostaDuvida:
        [emb] = await self._embedder.embed([pergunta])
        resultados = await self._store.buscar(tenant_id=tenant_id, embedding=emb, k=self._k)

        contexto = "\n\n".join(
            f"[{r.trecho.titulo}]\n{r.trecho.conteudo}" for r in resultados
        )
        fontes = [r.trecho.titulo for r in resultados]

        mensagens = list(historico or [])
        mensagens.append({"role": "user", "content": pergunta})

        instrucoes = await _instrucoes_do_tenant(self._prompts, tenant_id)
        texto = await self._llm.gerar(
            sistema=montar_sistema(contexto, instrucoes), mensagens=mensagens
        )
        return RespostaDuvida(texto=texto, fontes=fontes)


# --------------------------------------------------------------------------- #
# Recuperar e enviar documento
# --------------------------------------------------------------------------- #
class RecuperarEEnviarDocumento:
    def __init__(self, *, source: DocumentSource, canal: MessageChannel) -> None:
        self._source = source
        self._canal = canal

    async def executar(
        self, *, tenant_id: UUID, contato: str, consulta: str
    ) -> list[Documento]:
        documentos = await self._source.buscar_documentos(
            tenant_id=tenant_id, contato=contato, consulta=consulta
        )
        for doc in documentos:
            await self._canal.enviar_documento(contato=contato, documento=doc)
        return documentos


# --------------------------------------------------------------------------- #
# Receber mensagem do usuário (entrada do chat)
# --------------------------------------------------------------------------- #
@dataclass
class RespostaMensagem:
    texto: str
    fontes: list[str]
    documentos: list[Documento]


# Palavras que sinalizam intenção de obter documentos.
_GATILHOS_DOC = ("boletim", "declaraç", "documento", "comprovante", "histórico", "historico")


class ReceberMensagemRecebida:
    """Ponto de entrada do inbound: persiste, roteia (doc vs dúvida) e responde."""

    def __init__(
        self,
        *,
        conversas: ConversaRepository,
        responder: ResponderDuvida,
        documentos: RecuperarEEnviarDocumento,
    ) -> None:
        self._conversas = conversas
        self._responder = responder
        self._documentos = documentos

    async def executar(
        self, *, tenant_id: UUID, contato: str, texto: str
    ) -> RespostaMensagem:
        conversa = await self._conversas.obter_ou_criar(tenant_id=tenant_id, contato=contato)
        await self._conversas.adicionar_mensagem(
            conversa_id=conversa.id, autor="usuario", texto=texto
        )
        historico = await self._conversas.historico(conversa_id=conversa.id)

        docs: list[Documento] = []
        if any(g in texto.lower() for g in _GATILHOS_DOC):
            docs = await self._documentos.executar(
                tenant_id=tenant_id, contato=contato, consulta=texto
            )

        resposta = await self._responder.executar(
            tenant_id=tenant_id, pergunta=texto, historico=historico[:-1]
        )

        texto_final = resposta.texto
        if docs:
            lista = "\n".join(f"• {d.nome}" for d in docs)
            texto_final += f"\n\nEnviei os seguintes documentos:\n{lista}"

        await self._conversas.adicionar_mensagem(
            conversa_id=conversa.id, autor="bot", texto=texto_final, fontes=resposta.fontes
        )
        return RespostaMensagem(texto=texto_final, fontes=resposta.fontes, documentos=docs)


# --------------------------------------------------------------------------- #
# Atendimento por agente (inbound via tool use)
# --------------------------------------------------------------------------- #
# Ferramentas expostas ao LLM. O modelo decide quando chamá-las — substitui o
# roteamento por palavra-chave de ``ReceberMensagemRecebida``.
FERRAMENTA_CONHECIMENTO = FerramentaSpec(
    nome="buscar_conhecimento",
    descricao=(
        "Busca na base oficial da escola (FAQs, avisos, procedimentos) trechos relevantes "
        "para responder dúvidas sobre regras, prazos, calendário, avisos e procedimentos. "
        "Use sempre que a resposta depender de informação institucional da escola."
    ),
    parametros={
        "type": "object",
        "properties": {
            "consulta": {
                "type": "string",
                "description": "A dúvida ou o tópico a buscar, em português.",
            }
        },
        "required": ["consulta"],
    },
)

FERRAMENTA_DOCUMENTO = FerramentaSpec(
    nome="recuperar_documento",
    descricao=(
        "Recupera e envia ao responsável documentos do aluno (boletim, declaração, histórico, "
        "calendário, comprovante). Use quando o responsável quiser obter, ver, baixar ou receber "
        "um documento — mesmo que ele não use a palavra 'documento'."
    ),
    parametros={
        "type": "object",
        "properties": {
            "consulta": {
                "type": "string",
                "description": "Descrição do documento desejado, em português.",
            }
        },
        "required": ["consulta"],
    },
)


class AtenderConversa:
    """Atendimento inbound orquestrado por agente (tool use).

    O LLM decide, a cada turno, se busca conhecimento, recupera documentos ou já responde.
    O loop é coordenado aqui (camada de aplicação); as ferramentas reusam ``VectorStore`` e
    ``RecuperarEEnviarDocumento``. Sem SDK, sem framework.
    """

    def __init__(
        self,
        *,
        conversas: ConversaRepository,
        embedder: Embedder,
        store: VectorStore,
        llm: LLMProvider,
        documentos: RecuperarEEnviarDocumento,
        prompts: PromptTenantRepository | None = None,
        auditoria: AuditLogRepository | None = None,
        k: int = 4,
        max_iteracoes: int = 4,
    ) -> None:
        self._conversas = conversas
        self._embedder = embedder
        self._store = store
        self._llm = llm
        self._documentos = documentos
        self._prompts = prompts
        self._auditoria = auditoria
        self._k = k
        self._max_iteracoes = max_iteracoes

    async def executar(
        self, *, tenant_id: UUID, contato: str, texto: str
    ) -> RespostaMensagem:
        conversa = await self._conversas.obter_ou_criar(tenant_id=tenant_id, contato=contato)
        await self._conversas.adicionar_mensagem(
            conversa_id=conversa.id, autor="usuario", texto=texto
        )
        historico = await self._conversas.historico(conversa_id=conversa.id)
        turnos = [TurnoConversa(papel=m["role"], texto=m["content"]) for m in historico]

        ferramentas = [FERRAMENTA_CONHECIMENTO, FERRAMENTA_DOCUMENTO]
        fontes: list[str] = []
        docs: list[Documento] = []

        instrucoes = await _instrucoes_do_tenant(self._prompts, tenant_id)
        sistema = montar_sistema_agente(instrucoes)

        texto_final = ""
        for _ in range(self._max_iteracoes):
            resposta = await self._llm.gerar_com_ferramentas(
                sistema=sistema, turnos=turnos, ferramentas=ferramentas
            )
            if not resposta.quer_ferramenta:
                texto_final = resposta.texto
                break

            turnos.append(
                TurnoConversa(
                    papel="assistant", texto=resposta.texto, chamadas=resposta.chamadas
                )
            )
            resultados: list[ResultadoFerramenta] = []
            for chamada in resposta.chamadas:
                conteudo = await self._executar_ferramenta(
                    chamada, tenant_id=tenant_id, contato=contato, fontes=fontes, docs=docs
                )
                resultados.append(ResultadoFerramenta(id=chamada.id, conteudo=conteudo))
            turnos.append(TurnoConversa(papel="user", resultados=resultados))
        else:
            # Atingiu o limite de iterações ainda pedindo ferramentas: encerra com cortesia.
            texto_final = (
                "Estou com dificuldade para concluir seu pedido agora. "
                "Por gentileza, entre em contato com a secretaria da escola para te ajudarmos."
            )

        await self._conversas.adicionar_mensagem(
            conversa_id=conversa.id, autor="bot", texto=texto_final, fontes=fontes
        )
        await self._auditar_resposta(
            tenant_id=tenant_id, contato=contato, pergunta=texto, resposta=texto_final,
            fontes=fontes, docs=docs,
        )
        return RespostaMensagem(texto=texto_final, fontes=fontes, documentos=docs)

    async def _auditar_resposta(
        self,
        *,
        tenant_id: UUID,
        contato: str,
        pergunta: str,
        resposta: str,
        fontes: list[str],
        docs: list[Documento],
    ) -> None:
        """Registra na auditoria que a LLM atendeu uma conversa (rastreabilidade)."""
        if self._auditoria is None:
            return

        def _resumir(texto: str, limite: int = 280) -> str:
            texto = " ".join(texto.split())
            return texto if len(texto) <= limite else texto[: limite - 1] + "…"

        registro = RegistroAuditoria(
            ator=AtorAuditoria.LLM,
            acao="llm.resposta",
            tenant_id=tenant_id,
            ator_id=contato,
            ator_nome="Assistente",
            descricao=f"Atendeu a conversa de {contato}",
            metadados={
                "pergunta": _resumir(pergunta),
                "resposta": _resumir(resposta),
                "fontes": fontes,
                "documentos": [d.nome for d in docs],
            },
        )
        try:
            await self._auditoria.registrar(registro)
        except Exception:  # noqa: BLE001 — auditar não pode quebrar o atendimento
            pass

    async def _executar_ferramenta(
        self,
        chamada,
        *,
        tenant_id: UUID,
        contato: str,
        fontes: list[str],
        docs: list[Documento],
    ) -> str:
        consulta = str(chamada.argumentos.get("consulta", "")).strip()

        if chamada.nome == FERRAMENTA_CONHECIMENTO.nome:
            [emb] = await self._embedder.embed([consulta or " "])
            resultados = await self._store.buscar(
                tenant_id=tenant_id, embedding=emb, k=self._k
            )
            if not resultados:
                return "Nenhum trecho relevante encontrado na base de conhecimento."
            for r in resultados:
                if r.trecho.titulo not in fontes:
                    fontes.append(r.trecho.titulo)
            return "\n\n".join(
                f"[{r.trecho.titulo}]\n{r.trecho.conteudo}" for r in resultados
            )

        if chamada.nome == FERRAMENTA_DOCUMENTO.nome:
            encontrados = await self._documentos.executar(
                tenant_id=tenant_id, contato=contato, consulta=consulta
            )
            docs.extend(encontrados)
            if not encontrados:
                return "Nenhum documento correspondente foi localizado."
            nomes = ", ".join(d.nome for d in encontrados)
            return f"Documentos enviados ao responsável: {nomes}."

        return f"Ferramenta desconhecida: {chamada.nome}."


# --------------------------------------------------------------------------- #
# Disparo ativo / broadcast (outbound via Meta)
# --------------------------------------------------------------------------- #
@dataclass
class ResultadoBroadcast:
    broadcast_id: UUID
    enviados: int
    falhas: int
    bloqueados_por_limite: int
    restante_cota: int
    status: StatusBroadcast


class EnviarBroadcast:
    """Dispara um broadcast respeitando template aprovado, rate limit e cota diária.

    Ao atingir a cota diária (tier Meta), os destinatários restantes ficam pendentes e
    o broadcast é marcado como ``PARCIAL_LIMITE`` para reenvio na próxima janela.
    """

    def __init__(
        self,
        *,
        broadcasts: BroadcastRepository,
        templates: TemplateRepository,
        canal: MessageChannel,
        quota: QuotaPolicy,
        rate_limiter: RateLimiter,
    ) -> None:
        self._broadcasts = broadcasts
        self._templates = templates
        self._canal = canal
        self._quota = quota
        self._rate_limiter = rate_limiter

    async def executar(self, *, broadcast: Broadcast) -> ResultadoBroadcast:
        template = await self._templates.obter(
            tenant_id=broadcast.tenant_id, template_id=broadcast.template_id
        )
        if template is None:
            raise ValueError("Template não encontrado para o tenant.")
        if template.status != StatusTemplate.APROVADO:
            raise ValueError(
                "O template precisa estar APROVADO pela Meta para disparo fora da janela de 24h."
            )

        enviados = falhas = bloqueados = 0
        broadcast.status = StatusBroadcast.EM_ENVIO

        for dest in broadcast.destinatarios:
            if dest.status in (StatusEntrega.ENVIADO, StatusEntrega.ENTREGUE, StatusEntrega.LIDO):
                continue

            cota = await self._quota.cota_do_dia(broadcast.tenant_id)
            if not cota.pode_enviar(1):
                bloqueados += 1
                continue  # fica pendente para a próxima janela

            await self._rate_limiter.aguardar_vaga()
            try:
                mensagem_id = await self._canal.enviar_template(
                    contato=dest.contato, template=template, parametros=dest.parametros
                )
                dest.status = StatusEntrega.ENVIADO
                dest.mensagem_id_externo = mensagem_id
                dest.atualizado_em = datetime.now(timezone.utc)
                await self._quota.consumir(broadcast.tenant_id, 1)
                enviados += 1
            except Exception:  # noqa: BLE001 — falha de envio não derruba o lote
                dest.status = StatusEntrega.FALHOU
                dest.atualizado_em = datetime.now(timezone.utc)
                falhas += 1

        broadcast.status = (
            StatusBroadcast.PARCIAL_LIMITE if bloqueados else StatusBroadcast.CONCLUIDO
        )
        await self._broadcasts.salvar(broadcast)

        cota_final = await self._quota.cota_do_dia(broadcast.tenant_id)
        return ResultadoBroadcast(
            broadcast_id=broadcast.id,
            enviados=enviados,
            falhas=falhas,
            bloqueados_por_limite=bloqueados,
            restante_cota=cota_final.restante,
            status=broadcast.status,
        )


class DispararNotificacaoAtiva:
    """Conveniência: cria e dispara um broadcast a partir de uma lista de contatos."""

    def __init__(self, *, enviar: EnviarBroadcast, broadcasts: BroadcastRepository) -> None:
        self._enviar = enviar
        self._broadcasts = broadcasts

    async def executar(
        self,
        *,
        tenant_id: UUID,
        template_id: UUID,
        titulo: str,
        destinatarios: list,  # list[DestinatarioBroadcast]
        agendado_para: datetime | None = None,
    ) -> ResultadoBroadcast:
        broadcast = Broadcast(
            tenant_id=tenant_id,
            template_id=template_id,
            titulo=titulo,
            destinatarios=destinatarios,
            agendado_para=agendado_para,
        )
        if agendado_para and agendado_para > datetime.now(timezone.utc):
            broadcast.status = StatusBroadcast.AGENDADO
            await self._broadcasts.salvar(broadcast)
            return ResultadoBroadcast(
                broadcast_id=broadcast.id,
                enviados=0,
                falhas=0,
                bloqueados_por_limite=0,
                restante_cota=0,
                status=StatusBroadcast.AGENDADO,
            )
        return await self._enviar.executar(broadcast=broadcast)


# --------------------------------------------------------------------------- #
# Confirmação de recebimento (não-entrega reativa)
# --------------------------------------------------------------------------- #
class RegistrarStatusEntrega:
    """Aplica os eventos de status de entrega da Meta (webhook) aos destinatários.

    A Meta envia, no webhook, atualizações ``sent``/``delivered``/``read``/``failed`` por
    mensagem (``wamid``). Este caso de uso percorre o payload e atualiza o status de cada
    destinatário correspondente. Os valores casam diretamente com ``StatusEntrega``.
    """

    def __init__(self, *, broadcasts: BroadcastRepository) -> None:
        self._broadcasts = broadcasts

    async def executar(self, *, payload: dict) -> int:
        atualizados = 0
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                valor = change.get("value", {}) or {}
                for evento in valor.get("statuses", []) or []:
                    mensagem_id = evento.get("id")
                    bruto = evento.get("status")
                    if not mensagem_id or not bruto:
                        continue
                    try:
                        status = StatusEntrega(bruto)
                    except ValueError:
                        continue  # status desconhecido da Meta — ignora
                    if await self._broadcasts.registrar_status(
                        mensagem_id_externo=mensagem_id, status=status
                    ):
                        atualizados += 1
        return atualizados


@dataclass
class AvisoNaoEntrega:
    """Um destinatário que (provavelmente) não recebeu o aviso de um broadcast."""

    contato: str  # telefone E.164
    nome: str  # nome do responsável, se cadastrado (ou "")
    status: StatusEntrega
    motivo: str  # "falha_envio" | "sem_confirmacao"
    atualizado_em: datetime | None


class VerificarRecebimentoBroadcast:
    """Não-entrega reativa: aponta quem não confirmou o recebimento de um broadcast.

    Análogo à "confirmação de recebimento" de e-mail. Depois de ``apos_minutos`` desde o
    envio, um destinatário ainda em ``ENVIADO`` (sem ``delivered``/``read`` pela Meta) é
    sinalizado como possível não-entrega (celular desligado, sem sinal...). Destinatários
    em ``FALHOU`` são sinalizados de imediato. ``ENTREGUE``/``LIDO`` confirmam recebimento;
    ``PENDENTE``/``ENFILEIRADO`` ainda nem foram enviados (limite de cota) e ficam de fora.
    """

    def __init__(
        self, *, broadcasts: BroadcastRepository, contatos: ContatoRepository
    ) -> None:
        self._broadcasts = broadcasts
        self._contatos = contatos

    async def executar(
        self, *, tenant_id: UUID, broadcast_id: UUID, apos_minutos: int = 60
    ) -> list[AvisoNaoEntrega]:
        broadcast = await self._broadcasts.obter(broadcast_id)
        if broadcast is None or broadcast.tenant_id != tenant_id:
            return []

        agora = datetime.now(timezone.utc)
        limite = timedelta(minutes=apos_minutos)
        avisos: list[AvisoNaoEntrega] = []
        for dest in broadcast.destinatarios:
            if dest.status == StatusEntrega.FALHOU:
                motivo = "falha_envio"
            elif dest.status == StatusEntrega.ENVIADO:
                ref = dest.atualizado_em
                if ref is not None and ref.tzinfo is None:
                    ref = ref.replace(tzinfo=timezone.utc)
                if ref is None or agora - ref < limite:
                    continue  # ainda dentro da janela de espera por confirmação
                motivo = "sem_confirmacao"
            else:
                continue  # entregue/lido = recebeu; pendente/enfileirado = não enviado

            contato = await self._contatos.por_telefone(
                tenant_id=tenant_id, telefone=dest.contato
            )
            avisos.append(
                AvisoNaoEntrega(
                    contato=dest.contato,
                    nome=contato.nome if contato else "",
                    status=dest.status,
                    motivo=motivo,
                    atualizado_em=dest.atualizado_em,
                )
            )
        return avisos
