"""Testa o limite de caracteres da mensagem do responsável (§G1).

Mensagem curta passa pelo fluxo normal (LLM); "textão" recebe o pedido de objetividade
**sem acionar a LLM** — o ponto da regra é não pagar inferência por um desabafo de três
páginas que a secretaria não vai conseguir tratar por WhatsApp.
"""

from __future__ import annotations

import uuid

from app.application.use_cases import AtenderConversa, RecuperarEEnviarDocumento
from tests.fakes import (
    FakeChannel,
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()


class _LLMContada(FakeLLM):
    def __init__(self) -> None:
        super().__init__()
        self.chamadas = 0

    async def gerar_com_ferramentas(self, *, sistema, turnos, ferramentas):
        self.chamadas += 1
        return await super().gerar_com_ferramentas(
            sistema=sistema, turnos=turnos, ferramentas=ferramentas
        )


def _montar(max_chars: int) -> tuple[AtenderConversa, FakeConversaRepo, _LLMContada]:
    conversas = FakeConversaRepo()
    llm = _LLMContada()
    uc = AtenderConversa(
        conversas=conversas,
        embedder=fake_embedder(),
        store=FakeVectorStore(),
        llm=llm,
        documentos=RecuperarEEnviarDocumento(
            source=FakeDocumentSource([]), canal=FakeChannel()
        ),
        max_chars=max_chars,
    )
    return uc, conversas, llm


async def test_mensagem_curta_passa_pelo_fluxo_normal():
    uc, _, llm = _montar(max_chars=50)
    resp = await uc.executar(tenant_id=TENANT, contato="+5511999990000", texto="Bom dia")
    assert "resposta para" in resp.texto.lower()
    assert llm.chamadas == 1


async def test_textao_recebe_pedido_de_objetividade_sem_llm():
    uc, conversas, llm = _montar(max_chars=20)
    resp = await uc.executar(
        tenant_id=TENANT, contato="+5511999990000", texto="x" * 100
    )
    assert "até 20" in resp.texto
    assert resp.fontes == []
    assert resp.documentos == []
    assert llm.chamadas == 0  # o custo que a regra existe para evitar
    # A mensagem do responsável e o aviso do bot foram registrados na conversa.
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato="+5511999990000")
    autores = [m["autor"] for m in conversas.mensagens[conversa.id]]
    assert autores == ["usuario", "bot"]


async def test_limite_desativado_deixa_textao_passar():
    uc, _, llm = _montar(max_chars=0)
    resp = await uc.executar(
        tenant_id=TENANT, contato="+5511999990000", texto="y" * 5000
    )
    assert "resposta para" in resp.texto.lower()
    assert llm.chamadas == 1
