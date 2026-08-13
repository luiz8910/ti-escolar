"""Casos de uso da aplicação.

Orquestram as portas do domínio. Sem framework, sem ORM, sem SDK — apenas regras de
coordenação. Tudo é escopado por ``tenant_id`` (multi-tenant).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable
from uuid import UUID

from app.application.atendimento_humano_use_cases import (
    EncaminhamentoRecusado,
    MesaDeAtendimento,
)
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
    AvisoTemporizadoRepository,
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
    TenantRepository,
    VectorStore,
)

_logger = logging.getLogger("app.use_cases")


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
        # Enviar é tolerante a falhas: a indisponibilidade de um documento (ex.: o canal
        # rejeita a mídia) não pode derrubar o atendimento inteiro. Só os documentos
        # efetivamente entregues entram na resposta ao usuário.
        entregues: list[Documento] = []
        for doc in documentos:
            try:
                await self._canal.enviar_documento(contato=contato, documento=doc)
                entregues.append(doc)
            except Exception:  # noqa: BLE001
                _logger.warning(
                    "Falha ao enviar documento '%s' para %s (tenant %s)",
                    doc.nome,
                    contato,
                    tenant_id,
                    exc_info=True,
                )
        return entregues


# --------------------------------------------------------------------------- #
# Receber mensagem do usuário (entrada do chat)
# --------------------------------------------------------------------------- #
@dataclass
class RespostaMensagem:
    texto: str
    fontes: list[str]
    documentos: list[Documento]


@runtime_checkable
class Atendedor(Protocol):
    """Quem atende uma mensagem recebida e devolve o que responder.

    Contrato entre o transporte (o webhook da Meta, em ``ProcessarInboundMeta``) e o
    atendimento propriamente dito (``AtenderConversa``). Existe para que o inbound não
    dependa de uma classe concreta: quem trata o envelope da Meta não deve ter opinião
    sobre como a resposta é produzida.

    ``texto`` vazio significa **não responder** — é como o assistente fica em silêncio
    quando uma pessoa da secretaria assumiu a conversa (§6j).
    """

    async def executar(
        self, *, tenant_id: UUID, contato: str, texto: str
    ) -> RespostaMensagem: ...


# --------------------------------------------------------------------------- #
# Atendimento por agente (inbound via tool use)
# --------------------------------------------------------------------------- #
# Ferramentas expostas ao LLM. O modelo decide quando chamá-las — é o que substituiu o
# antigo roteamento por palavra-chave do inbound.
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

FERRAMENTA_OFERECER_HUMANO = FerramentaSpec(
    nome="oferecer_atendimento_humano",
    descricao=(
        "Registra que você vai PERGUNTAR ao responsável se ele deseja falar com alguém da "
        "secretaria. Use quando não conseguir resolver o pedido com a base de conhecimento "
        "— por exemplo, quando o assunto exigir decisão da escola, tratar de um caso "
        "específico de um aluno, ou for reclamação/ocorrência. NÃO use na primeira "
        "mensagem da conversa: tente responder antes."
    ),
    parametros={
        "type": "object",
        "properties": {
            "motivo": {
                "type": "string",
                "description": (
                    "Resumo em uma frase do que o responsável precisa. É o que a "
                    "secretaria lê antes de abrir a conversa."
                ),
            }
        },
        "required": ["motivo"],
    },
)

FERRAMENTA_ESCALAR = FerramentaSpec(
    nome="escalar_para_secretaria",
    descricao=(
        "Encaminha a conversa para uma pessoa da secretaria assumir. Use APENAS quando o "
        "responsável já tiver CONFIRMADO que quer falar com alguém (depois de "
        "`oferecer_atendimento_humano`), ou quando ele mesmo pedir explicitamente para "
        "falar com uma pessoa — neste caso passe pedido_explicito=true."
    ),
    parametros={
        "type": "object",
        "properties": {
            "motivo": {
                "type": "string",
                "description": (
                    "Resumo em uma frase do que o responsável precisa, para a secretaria "
                    "entender o caso sem reler a conversa inteira."
                ),
            },
            "pedido_explicito": {
                "type": "boolean",
                "description": (
                    "true somente quando o próprio responsável pediu para falar com uma "
                    "pessoa/atendente/secretaria."
                ),
            },
        },
        "required": ["motivo"],
    },
)

FERRAMENTA_SAIDA_ANTECIPADA = FerramentaSpec(
    nome="registrar_saida_antecipada",
    descricao=(
        "Abre um chamado na secretaria para o aluno sair mais cedo (buscar antes do fim "
        "da aula, liberar por consulta médica, retirada antecipada). Use assim que o "
        "responsável pedir isso — NÃO pergunte se ele quer falar com alguém, e NÃO espere "
        "outras mensagens: este assunto sempre vai para uma pessoa. Você precisa do NOME "
        "DO ALUNO; se ele não tiver dito, pergunte e chame a ferramenta depois."
    ),
    parametros={
        "type": "object",
        "properties": {
            "nome_aluno": {
                "type": "string",
                "description": "Nome do aluno que vai sair mais cedo.",
            },
            "nome_responsavel": {
                "type": "string",
                "description": (
                    "Nome de quem está pedindo. Só é necessário quando a ferramenta "
                    "avisar que o número não está cadastrado."
                ),
            },
            "horario": {
                "type": "string",
                "description": "Horário da saída, como o responsável disse (ex.: '11h').",
            },
            "motivo": {
                "type": "string",
                "description": "Motivo, se ele tiver dito (ex.: 'consulta médica').",
            },
        },
        "required": ["nome_aluno"],
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
        avisos: AvisoTemporizadoRepository | None = None,
        mesa: MesaDeAtendimento | None = None,
        contatos: ContatoRepository | None = None,
        k: int = 4,
        max_iteracoes: int = 4,
        max_chars: int = 0,
    ) -> None:
        self._conversas = conversas
        self._embedder = embedder
        self._store = store
        self._llm = llm
        self._documentos = documentos
        self._prompts = prompts
        self._auditoria = auditoria
        # Opcional: aviso temporizado vigente é anexado à resposta (ver §C2).
        self._avisos = avisos
        # Opcional: atendimento humano (§6j). Sem ela o assistente nunca encaminha — é o
        # que mantém o caso de uso utilizável em testes e em instalações sem secretaria.
        self._mesa = mesa
        # Opcional: usado para saber se quem escreve já está cadastrado — é o que decide
        # se a saída antecipada (§6l) precisa perguntar o nome do responsável.
        self._contatos = contatos
        self._k = k
        self._max_iteracoes = max_iteracoes
        # Limite de caracteres da mensagem do responsável (§G1); <= 0 desativa.
        self._max_chars = max_chars

    async def executar(
        self, *, tenant_id: UUID, contato: str, texto: str
    ) -> RespostaMensagem:
        conversa = await self._conversas.obter_ou_criar(tenant_id=tenant_id, contato=contato)
        await self._conversas.adicionar_mensagem(
            conversa_id=conversa.id, autor="usuario", texto=texto
        )

        # Alguém da secretaria já assumiu esta conversa (§6j): o assistente **cala**. Sem
        # isso ele responderia por cima da pessoa, e o responsável receberia duas respostas
        # possivelmente contraditórias pelo mesmo número. A mensagem é só registrada — e
        # renova a janela de 24h de quem vai responder.
        if self._mesa is not None:
            atendimento = await self._mesa.vivo_na_conversa(conversa.id)
            if atendimento is not None and atendimento.na_fila:
                await self._mesa.registrar_retorno(atendimento)
                return RespostaMensagem(texto="", fontes=[], documentos=[])

        # §G1 — mensagem "textão": pede objetividade sem acionar a LLM (assunto de
        # secretaria pede recado curto). Só quando há limite configurado.
        if self._max_chars > 0 and len(texto) > self._max_chars:
            aviso_limite = (
                f"Para agilizar o atendimento, envie mensagens de até {self._max_chars} "
                "caracteres. Por gentileza, resuma a sua mensagem em poucas linhas e "
                "reenvie — assim a secretaria consegue te responder mais rápido."
            )
            await self._conversas.adicionar_mensagem(
                conversa_id=conversa.id, autor="bot", texto=aviso_limite
            )
            return RespostaMensagem(texto=aviso_limite, fontes=[], documentos=[])

        historico = await self._conversas.historico(conversa_id=conversa.id)
        turnos = [TurnoConversa(papel=m["role"], texto=m["content"]) for m in historico]
        # Quantas vezes o assistente já respondeu nesta conversa — insumo da trava "não
        # encaminhar nas primeiras mensagens" (§6j).
        respostas_anteriores = sum(1 for m in historico if m["role"] == "assistant")

        ferramentas = [FERRAMENTA_CONHECIMENTO, FERRAMENTA_DOCUMENTO]
        if self._mesa is not None:
            ferramentas += [
                FERRAMENTA_OFERECER_HUMANO,
                FERRAMENTA_ESCALAR,
                FERRAMENTA_SAIDA_ANTECIPADA,
            ]
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
                    chamada,
                    tenant_id=tenant_id,
                    contato=contato,
                    conversa_id=conversa.id,
                    fontes=fontes,
                    docs=docs,
                    respostas_anteriores=respostas_anteriores,
                )
                resultados.append(ResultadoFerramenta(id=chamada.id, conteudo=conteudo))
            turnos.append(TurnoConversa(papel="user", resultados=resultados))
        else:
            # Atingiu o limite de iterações ainda pedindo ferramentas: encerra com cortesia.
            texto_final = (
                "Estou com dificuldade para concluir seu pedido agora. "
                "Por gentileza, entre em contato com a secretaria da escola para te ajudarmos."
            )

        if self._avisos is not None:
            aviso = await self._avisos.vigente(tenant_id=tenant_id)
            if aviso:
                texto_final = f"📢 {aviso.mensagem}\n\n{texto_final}"

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
        conversa_id: UUID,
        fontes: list[str],
        docs: list[Documento],
        respostas_anteriores: int = 0,
    ) -> str:
        if chamada.nome == FERRAMENTA_SAIDA_ANTECIPADA.nome:
            return await self._ferramenta_saida_antecipada(
                chamada, tenant_id=tenant_id, contato=contato, conversa_id=conversa_id
            )

        if chamada.nome in (FERRAMENTA_OFERECER_HUMANO.nome, FERRAMENTA_ESCALAR.nome):
            return await self._ferramenta_atendimento_humano(
                chamada,
                tenant_id=tenant_id,
                contato=contato,
                conversa_id=conversa_id,
                respostas_anteriores=respostas_anteriores,
            )

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

    async def _ferramenta_saida_antecipada(
        self, chamada, *, tenant_id: UUID, contato: str, conversa_id: UUID
    ) -> str:
        """Aluno vai sair mais cedo: abre o chamado direto, sem perguntar (§6l).

        É a **exceção declarada** à regra "perguntar antes de encaminhar" (§6j): a saída
        antecipada sempre exige decisão de gente (a escola precisa saber quem retira a
        criança e autorizar), e é sensível ao relógio. Perguntar "quer que eu chame
        alguém?" gastaria justamente os minutos que importam, para uma resposta que seria
        sempre "sim".

        O que **não** se dispensa são os dois dados sem os quais a secretaria não consegue
        agir: o nome do aluno e — quando o número não está cadastrado — o nome de quem
        está pedindo. Sem eles o card chegaria como "alguém quer buscar alguém", e a
        secretaria teria de reabrir a conversa para perguntar o que o assistente já
        poderia ter perguntado.
        """
        if self._mesa is None:  # defensivo: a ferramenta nem é oferecida sem mesa
            return "Encaminhamento para a secretaria não está disponível nesta escola."

        aluno = str(chamada.argumentos.get("nome_aluno", "")).strip()
        if not aluno:
            return (
                "Falta o nome do aluno. Pergunte de forma cordial qual é o nome completo "
                "do aluno que vai sair mais cedo e chame esta ferramenta de novo."
            )

        responsavel = str(chamada.argumentos.get("nome_responsavel", "")).strip()
        if not responsavel:
            cadastrado = (
                await self._contatos.por_telefone(tenant_id=tenant_id, telefone=contato)
                if self._contatos is not None
                else None
            )
            if cadastrado is None:
                # Só perguntamos quando o número é desconhecido: pedir o nome a quem já
                # está cadastrado seria a escola fingindo não conhecer a família.
                return (
                    "Este número não está cadastrado na escola. Pergunte o nome completo "
                    "de quem está pedindo a saída e chame esta ferramenta de novo, com o "
                    "nome do aluno e o nome do responsável."
                )
            responsavel = cadastrado.nome

        horario = str(chamada.argumentos.get("horario", "")).strip()
        motivo_dito = str(chamada.argumentos.get("motivo", "")).strip()
        # Motivo estruturado: é o que a secretaria lê no card sem abrir a conversa.
        partes = [f"Saída antecipada — aluno: {aluno}"]
        if responsavel:
            partes.append(f"responsável: {responsavel}")
        if horario:
            partes.append(f"horário: {horario}")
        if motivo_dito:
            partes.append(f"motivo: {motivo_dito}")

        await self._mesa.escalar(
            tenant_id=tenant_id,
            conversa_id=conversa_id,
            contato=contato,
            motivo=" · ".join(partes),
            abertura_direta=True,
        )
        retorno = await self._mesa.previsao_de_retorno(tenant_id)
        quando = f" A secretaria responde {retorno}." if retorno else ""
        return (
            f"Chamado aberto na secretaria para a saída antecipada de {aluno}. "
            "Confirme ao responsável que o pedido já foi registrado e que a secretaria "
            f"vai confirmar a liberação por aqui.{quando} NÃO pergunte se ele quer falar "
            "com alguém — isso já foi feito."
        )

    async def _ferramenta_atendimento_humano(
        self,
        chamada,
        *,
        tenant_id: UUID,
        contato: str,
        conversa_id: UUID,
        respostas_anteriores: int,
    ) -> str:
        """Oferta e encaminhamento à secretaria (§6j).

        As travas ("não nas primeiras mensagens", "oferecer antes de encaminhar") ficam no
        caso de uso, não aqui e não no prompt: o modelo pode ignorar uma instrução de
        texto, e o efeito seria criar fila de atendimento indevida — trabalho para uma
        pessoa real do outro lado.
        """
        if self._mesa is None:  # defensivo: a ferramenta nem é oferecida sem mesa
            return "Encaminhamento para a secretaria não está disponível nesta escola."

        motivo = str(chamada.argumentos.get("motivo", "")).strip()

        if chamada.nome == FERRAMENTA_OFERECER_HUMANO.nome:
            await self._mesa.oferecer(
                tenant_id=tenant_id,
                conversa_id=conversa_id,
                contato=contato,
                motivo=motivo,
            )
            expediente = await self._mesa.expediente(tenant_id)
            horario = f" A secretaria atende {expediente}." if expediente else ""
            return (
                "Oferta registrada. Agora PERGUNTE ao responsável, de forma cordial, se "
                "ele deseja que alguém da secretaria assuma o atendimento, e aguarde a "
                f"resposta dele.{horario}"
            )

        pedido_explicito = bool(chamada.argumentos.get("pedido_explicito", False))
        try:
            await self._mesa.escalar(
                tenant_id=tenant_id,
                conversa_id=conversa_id,
                contato=contato,
                motivo=motivo,
                pedido_explicito=pedido_explicito,
                respostas_anteriores=respostas_anteriores,
            )
        except EncaminhamentoRecusado as recusa:
            # Não é erro: é o caso de uso dizendo ao modelo o que fazer em vez disso.
            return recusa.orientacao

        previsao = await self._mesa.previsao_de_retorno(tenant_id)
        quando = (
            f" Informe que o retorno será {previsao}." if previsao and previsao != "agora" else
            " A secretaria está em expediente agora."
        )
        return (
            "Atendimento encaminhado à secretaria. Confirme ao responsável que alguém da "
            "escola vai assumir a conversa por aqui mesmo, neste WhatsApp."
            f"{quando} Não prometa nenhum outro prazo."
        )


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
        tenants: TenantRepository | None = None,
    ) -> None:
        self._broadcasts = broadcasts
        self._templates = templates
        self._canal = canal
        self._quota = quota
        self._rate_limiter = rate_limiter
        # Opcional: resolve o número (From) da escola para o outbound sair do próprio
        # número dela. Sem repositório, o canal usa seu número padrão.
        self._tenants = tenants

    async def executar(self, *, broadcast: Broadcast) -> ResultadoBroadcast:
        template = await self._templates.obter(
            tenant_id=broadcast.tenant_id, template_id=broadcast.template_id
        )
        if template is None:
            raise ValueError("Template não encontrado para o tenant.")

        # Número da própria escola como remetente (multi-tenant); vazio = padrão do canal.
        # ``remetente_canal`` entrega o ``meta_phone_number_id`` (o que a Graph API exige na
        # URL de envio) e cai no E.164 quando a escola ainda não tem id na Meta.
        remetente: str | None = None
        escola = None
        if self._tenants is not None:
            escola = await self._tenants.obter(broadcast.tenant_id)
            remetente = (escola.remetente_canal or None) if escola else None

        # A pergunta não é "este template está aprovado?", e sim "está aprovado **na conta
        # em que está o número desta escola**?". Template é revisado por WABA, e o mesmo
        # texto aprovado na conta A não existe na B: perguntar em geral fazia a trava
        # liberar o disparo para a Graph API recusar depois (§9e.3).
        if escola is not None:
            if not template.aprovado_em(escola.waba_id):
                raise ValueError(
                    "O template precisa estar APROVADO pela Meta, na conta do WhatsApp "
                    "desta escola, para disparo fora da janela de 24h."
                )
        elif template.status != StatusTemplate.APROVADO:
            # Sem repositório de escola não dá para saber a conta; o status agregado é o
            # **pior** entre as contas, então cair nele erra para o lado seguro.
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
                    contato=dest.contato,
                    template=template,
                    parametros=dest.parametros,
                    remetente=remetente,
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
