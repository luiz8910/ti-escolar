"""Testa o limite de caracteres da mensagem do responsável (§G1).

Mensagem curta passa pelo fluxo normal (LLM); "textão" recebe o pedido de objetividade
sem acionar a LLM.
"""

from __future__ import annotations

import uuid

from app.application.use_cases import (
    ReceberMensagemRecebida,
    RecuperarEEnviarDocumento,
    ResponderDuvida,
)
from tests.fakes import (
    FakeChannel,
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()


def _montar(max_chars: int) -> tuple[ReceberMensagemRecebida, FakeConversaRepo]:
    conversas = FakeConversaRepo()
    responder = ResponderDuvida(
        embedder=fake_embedder(), store=FakeVectorStore(), llm=FakeLLM()
    )
    documentos = RecuperarEEnviarDocumento(source=FakeDocumentSource(), canal=FakeChannel())
    receber = ReceberMensagemRecebida(
        conversas=conversas,
        responder=responder,
        documentos=documentos,
        max_chars=max_chars,
    )
    return receber, conversas


async def test_mensagem_curta_passa_pelo_fluxo_normal():
    receber, _ = _montar(max_chars=50)
    resp = await receber.executar(tenant_id=TENANT, contato="+5511999990000", texto="Bom dia")
    # Fluxo normal aciona a LLM (fake responde "resposta para: ...").
    assert "resposta para" in resp.texto.lower()


async def test_textao_recebe_pedido_de_objetividade_sem_llm():
    receber, conversas = _montar(max_chars=20)
    texto = "x" * 100
    resp = await receber.executar(
        tenant_id=TENANT, contato="+5511999990000", texto=texto
    )
    assert "até 20" in resp.texto
    assert resp.fontes == []
    assert resp.documentos == []
    # A mensagem do usuário e o aviso do bot foram registrados (2 mensagens), sem chamar a LLM.
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato="+5511999990000")
    autores = [m["autor"] for m in conversas.mensagens[conversa.id]]
    assert autores == ["usuario", "bot"]


async def test_limite_desativado_deixa_textao_passar():
    receber, _ = _montar(max_chars=0)
    resp = await receber.executar(
        tenant_id=TENANT, contato="+5511999990000", texto="y" * 5000
    )
    assert "resposta para" in resp.texto.lower()
