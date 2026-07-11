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


class _CanalQueFalhaNoDoc(FakeChannel):
    async def enviar_documento(self, *, contato, documento) -> str:
        raise RuntimeError("canal rejeitou a mídia (ex.: URL inacessível)")


async def test_falha_ao_enviar_documento_nao_derruba_atendimento():
    # Uma falha de entrega de documento (canal real recusando a mídia mock) não pode
    # abortar a resposta: o usuário ainda recebe o texto; documentos não entregues saem.
    doc = Documento(tenant_id=TENANT, nome="Boletim.pdf", categoria="boletim", url="http://x")
    responder = ResponderDuvida(
        embedder=fake_embedder(), store=FakeVectorStore(), llm=FakeLLM()
    )
    docs = RecuperarEEnviarDocumento(
        source=FakeDocumentSource([doc]), canal=_CanalQueFalhaNoDoc()
    )
    uc = ReceberMensagemRecebida(
        conversas=FakeConversaRepo(), responder=responder, documentos=docs
    )
    resp = await uc.executar(
        tenant_id=TENANT, contato="+551199", texto="Quero a segunda via do meu boletim"
    )
    assert resp.documentos == []  # nada entregue → não anuncia documento
    assert resp.texto  # a resposta de texto foi preservada
