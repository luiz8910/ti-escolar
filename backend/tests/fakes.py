"""Implementações em memória das portas, para testar os casos de uso sem BD/rede."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.domain.entities import (
    Broadcast,
    Conversa,
    Documento,
    MessageQuota,
    MessageTemplate,
    RespostaLLM,
    ResultadoBusca,
    TrechoConhecimento,
    TurnoConversa,
)
from app.infrastructure.llm.fake_provider import FakeEmbedder


class FakeVectorStore:
    def __init__(self) -> None:
        self._itens: list[tuple[TrechoConhecimento, list[float]]] = []

    async def indexar(self, trecho: TrechoConhecimento, embedding: list[float]) -> None:
        self._itens.append((trecho, embedding))

    async def buscar(self, *, tenant_id, embedding, k=4) -> list[ResultadoBusca]:
        def cos(a, b):
            return sum(x * y for x, y in zip(a, b))

        candidatos = [
            (t, cos(embedding, e)) for t, e in self._itens if t.tenant_id == tenant_id
        ]
        candidatos.sort(key=lambda x: x[1], reverse=True)
        return [ResultadoBusca(trecho=t, score=s) for t, s in candidatos[:k]]


class FakeLLM:
    def __init__(self, respostas: list[RespostaLLM] | None = None) -> None:
        self.ultimo_sistema = ""
        # Roteiro determinístico para ``gerar_com_ferramentas`` (uma RespostaLLM por iteração).
        self._respostas = list(respostas or [])
        self.turnos_recebidos: list[list[TurnoConversa]] = []

    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        self.ultimo_sistema = sistema
        pergunta = next((m["content"] for m in reversed(mensagens) if m["role"] == "user"), "")
        return f"resposta para: {pergunta}"

    async def gerar_com_ferramentas(
        self, *, sistema: str, turnos: list[TurnoConversa], ferramentas
    ) -> RespostaLLM:
        self.ultimo_sistema = sistema
        self.turnos_recebidos.append(list(turnos))
        if self._respostas:
            return self._respostas.pop(0)
        # Sem roteiro: responde direto, sem ferramentas.
        ultimo = next((t.texto for t in reversed(turnos) if t.papel == "user" and t.texto), "")
        return RespostaLLM(texto=f"resposta para: {ultimo}")


class FakeConversaRepo:
    def __init__(self) -> None:
        self.mensagens: dict[uuid.UUID, list[dict]] = {}
        self.conversas: dict[tuple, Conversa] = {}

    async def obter_ou_criar(self, *, tenant_id, contato) -> Conversa:
        chave = (tenant_id, contato)
        if chave not in self.conversas:
            c = Conversa(tenant_id=tenant_id, contato=contato)
            self.conversas[chave] = c
            self.mensagens[c.id] = []
        return self.conversas[chave]

    async def adicionar_mensagem(self, *, conversa_id, autor, texto, fontes=None) -> None:
        self.mensagens.setdefault(conversa_id, []).append(
            {"autor": autor, "texto": texto, "fontes": fontes or []}
        )

    async def historico(self, *, conversa_id, limite=20) -> list[dict[str, str]]:
        msgs = self.mensagens.get(conversa_id, [])[-limite:]
        return [
            {"role": "assistant" if m["autor"] == "bot" else "user", "content": m["texto"]}
            for m in msgs
        ]


class FakeDocumentSource:
    def __init__(self, documentos: list[Documento] | None = None) -> None:
        self._docs = documentos or []

    async def buscar_documentos(self, *, tenant_id, contato, consulta) -> list[Documento]:
        return [d for d in self._docs if d.tenant_id == tenant_id]


class FakeChannel:
    def __init__(self, *, falhar_em: set[str] | None = None) -> None:
        self.enviados: list[tuple[str, str]] = []
        self._falhar_em = falhar_em or set()

    async def enviar_texto(self, *, contato, texto) -> str:
        self.enviados.append((contato, "texto"))
        return "x"

    async def enviar_template(self, *, contato, template, parametros) -> str:
        if contato in self._falhar_em:
            raise RuntimeError("falha simulada")
        self.enviados.append((contato, "template"))
        return "x"

    async def enviar_documento(self, *, contato, documento) -> str:
        self.enviados.append((contato, "documento"))
        return "x"


class FakeQuota:
    def __init__(self, *, limite_diario: int) -> None:
        self._quotas: dict[uuid.UUID, MessageQuota] = {}
        self._limite = limite_diario

    def _q(self, tenant_id) -> MessageQuota:
        if tenant_id not in self._quotas:
            self._quotas[tenant_id] = MessageQuota(
                tenant_id=tenant_id,
                limite_diario=self._limite,
                dia=datetime.now(timezone.utc).date().isoformat(),
            )
        return self._quotas[tenant_id]

    async def cota_do_dia(self, tenant_id) -> MessageQuota:
        return self._q(tenant_id)

    async def consumir(self, tenant_id, quantidade) -> MessageQuota:
        q = self._q(tenant_id)
        q.enviados += quantidade
        return q


class FakeRateLimiter:
    def __init__(self) -> None:
        self.chamadas = 0

    async def aguardar_vaga(self) -> None:
        self.chamadas += 1


class FakeBroadcastRepo:
    def __init__(self) -> None:
        self.salvos: dict[uuid.UUID, Broadcast] = {}

    async def salvar(self, broadcast: Broadcast) -> None:
        self.salvos[broadcast.id] = broadcast

    async def obter(self, broadcast_id) -> Broadcast | None:
        return self.salvos.get(broadcast_id)


class FakeTemplateRepo:
    def __init__(self, template: MessageTemplate | None = None) -> None:
        self._template = template

    async def obter(self, *, tenant_id, template_id) -> MessageTemplate | None:
        if self._template and self._template.tenant_id == tenant_id:
            return self._template
        return None


def fake_embedder() -> FakeEmbedder:
    # Dimensão pequena nos testes para velocidade.
    return FakeEmbedder(dimensao=64)


class FakeGrupoRepo:
    def __init__(self) -> None:
        self.grupos: dict[uuid.UUID, "Grupo"] = {}

    async def criar(self, grupo):
        self.grupos[grupo.id] = grupo
        return grupo

    async def obter(self, *, tenant_id, grupo_id):
        g = self.grupos.get(grupo_id)
        return g if g and g.tenant_id == tenant_id else None

    async def listar(self, *, tenant_id):
        return [g for g in self.grupos.values() if g.tenant_id == tenant_id]

    async def adicionar_contato(self, *, tenant_id, grupo_id, nome, telefone):
        from app.domain.entities import Contato

        g = self.grupos[grupo_id]
        contato = Contato(tenant_id=tenant_id, nome=nome, telefone=telefone)
        g.membros.append(contato)
        return contato

    async def membros(self, *, tenant_id, grupo_id):
        g = await self.obter(tenant_id=tenant_id, grupo_id=grupo_id)
        return list(g.membros) if g else []
