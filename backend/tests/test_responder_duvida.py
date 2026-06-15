"""Testa o fluxo RAG: indexação + recuperação + geração."""

from __future__ import annotations

import uuid

import pytest

from app.application.use_cases import IndexarConhecimento, ResponderDuvida
from app.domain.entities import TipoConhecimento
from tests.fakes import FakeLLM, FakeVectorStore, fake_embedder

TENANT = uuid.uuid4()


@pytest.fixture
async def store_indexado():
    store = FakeVectorStore()
    embedder = fake_embedder()
    indexar = IndexarConhecimento(embedder=embedder, store=store)
    await indexar.executar(
        tenant_id=TENANT,
        tipo=TipoConhecimento.PROCEDIMENTO,
        titulo="Horário de funcionamento",
        conteudo="A secretaria atende das 7h30 às 17h, de segunda a sexta.",
    )
    await indexar.executar(
        tenant_id=TENANT,
        tipo=TipoConhecimento.FAQ,
        titulo="Uniforme escolar",
        conteudo="O uso do uniforme é obrigatório todos os dias.",
    )
    return store, embedder


async def test_responder_usa_contexto_recuperado(store_indexado):
    store, embedder = store_indexado
    llm = FakeLLM()
    responder = ResponderDuvida(embedder=embedder, store=store, llm=llm)

    resposta = await responder.executar(
        tenant_id=TENANT, pergunta="Qual o horário da secretaria?"
    )

    # O trecho mais relevante deve aparecer como fonte e no contexto do sistema.
    assert "Horário de funcionamento" in resposta.fontes
    assert "secretaria atende" in llm.ultimo_sistema


async def test_isolamento_por_tenant(store_indexado):
    store, embedder = store_indexado
    llm = FakeLLM()
    responder = ResponderDuvida(embedder=embedder, store=store, llm=llm)

    outro_tenant = uuid.uuid4()
    resposta = await responder.executar(
        tenant_id=outro_tenant, pergunta="Qual o horário da secretaria?"
    )

    assert resposta.fontes == []  # nada vaza de outro tenant
