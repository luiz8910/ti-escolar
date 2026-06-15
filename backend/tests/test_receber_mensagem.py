"""Testa o roteamento inbound: dúvida simples vs. pedido de documento."""

from __future__ import annotations

import uuid

from app.application.use_cases import (
    ReceberMensagemRecebida,
    RecuperarEEnviarDocumento,
    ResponderDuvida,
)
from app.domain.entities import Documento
from tests.fakes import (
    FakeChannel,
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()


def _montar(documentos=None):
    responder = ResponderDuvida(
        embedder=fake_embedder(), store=FakeVectorStore(), llm=FakeLLM()
    )
    canal = FakeChannel()
    docs = RecuperarEEnviarDocumento(
        source=FakeDocumentSource(documentos or []), canal=canal
    )
    return (
        ReceberMensagemRecebida(
            conversas=FakeConversaRepo(), responder=responder, documentos=docs
        ),
        canal,
    )


async def test_duvida_simples_nao_envia_documento():
    uc, canal = _montar()
    resp = await uc.executar(tenant_id=TENANT, contato="+551199", texto="Qual o horário?")
    assert resp.documentos == []
    assert canal.enviados == []


async def test_pedido_de_boletim_envia_documento():
    doc = Documento(tenant_id=TENANT, nome="Boletim.pdf", categoria="boletim", url="http://x")
    uc, canal = _montar([doc])
    resp = await uc.executar(
        tenant_id=TENANT, contato="+551199", texto="Quero a segunda via do meu boletim"
    )
    assert len(resp.documentos) == 1
    assert canal.enviados == [("+551199", "documento")]
    assert "Boletim.pdf" in resp.texto
