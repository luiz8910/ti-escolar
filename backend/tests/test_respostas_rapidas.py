"""Testa as respostas rápidas ("atalhos") da escola e sua ingestão no RAG:

- criação valida chave única e conteúdo, e indexa o texto no vector store;
- o bot recupera a resposta rápida via RAG (escopado por tenant);
- edição reindexa (remove o conteúdo antigo e indexa o novo);
- desativar/remover apaga os trechos indexados.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.respostas_rapidas_use_cases import (
    AtualizarRespostaRapida,
    CriarRespostaRapida,
    ListarRespostasRapidas,
    ObterRespostaRapida,
    RemoverRespostaRapida,
)
from app.application.use_cases import ResponderDuvida
from tests.fakes import (
    FakeFonteConhecimentoRepo,
    FakeLLM,
    FakeRespostaRapidaRepo,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


def _ambiente():
    return {
        "respostas": FakeRespostaRapidaRepo(),
        "embedder": fake_embedder(),
        "store": FakeVectorStore(),
        "fontes": FakeFonteConhecimentoRepo(),
    }


async def test_criar_resposta_rapida_indexa_no_rag():
    amb = _ambiente()
    resposta = await CriarRespostaRapida(**amb).executar(
        tenant_id=TENANT,
        chave="Transporte escolar gratuito",
        conteudo="O transporte escolar gratuito é solicitado na secretaria com comprovante de endereço.",
    )
    assert resposta.ativo is True
    assert resposta.fonte_id is not None
    # Ficou indexada no vector store (trechos apontando para a fonte gerada).
    assert amb["store"]._itens
    assert all(t.fonte_id == resposta.fonte_id for t, _ in amb["store"]._itens)


async def test_bot_recupera_resposta_rapida_via_rag_isolada_por_tenant():
    amb = _ambiente()
    await CriarRespostaRapida(**amb).executar(
        tenant_id=TENANT,
        chave="Horário do portão",
        conteudo="O portão abre às 7h e fecha às 7h30. Após o horário, a entrada é pela secretaria.",
    )

    responder = ResponderDuvida(
        embedder=fake_embedder(), store=amb["store"], llm=FakeLLM()
    )
    resp = await responder.executar(tenant_id=TENANT, pergunta="que horas abre o portão?")
    assert "Horário do portão" in resp.fontes

    resp_outro = await responder.executar(
        tenant_id=OUTRO_TENANT, pergunta="que horas abre o portão?"
    )
    assert resp_outro.fontes == []


async def test_chave_duplicada_falha():
    amb = _ambiente()
    await CriarRespostaRapida(**amb).executar(
        tenant_id=TENANT, chave="Atestado", conteudo="Entregar o atestado em até 48h."
    )
    with pytest.raises(ValueError):
        await CriarRespostaRapida(**amb).executar(
            tenant_id=TENANT, chave="Atestado", conteudo="Outro conteúdo."
        )
    # Mesma chave em outro tenant é permitida.
    await CriarRespostaRapida(**amb).executar(
        tenant_id=OUTRO_TENANT, chave="Atestado", conteudo="Regra da outra escola."
    )


async def test_chave_e_conteudo_obrigatorios():
    amb = _ambiente()
    with pytest.raises(ValueError):
        await CriarRespostaRapida(**amb).executar(tenant_id=TENANT, chave="  ", conteudo="x")
    with pytest.raises(ValueError):
        await CriarRespostaRapida(**amb).executar(tenant_id=TENANT, chave="Pix APM", conteudo="  ")


async def test_criar_inativa_nao_indexa():
    amb = _ambiente()
    resposta = await CriarRespostaRapida(**amb).executar(
        tenant_id=TENANT, chave="Rascunho", conteudo="ainda não publicar", ativo=False
    )
    assert resposta.fonte_id is None
    assert amb["store"]._itens == []


async def test_atualizar_reindexa_conteudo():
    amb = _ambiente()
    resposta = await CriarRespostaRapida(**amb).executar(
        tenant_id=TENANT, chave="Faltas", conteudo="Regra antiga sobre faltas."
    )
    fonte_antiga = resposta.fonte_id

    atualizada = await AtualizarRespostaRapida(**amb).executar(
        tenant_id=TENANT,
        resposta_id=resposta.id,
        chave="Faltas",
        conteudo="Nova regra: justificar faltas em 48h pelo WhatsApp.",
    )
    assert atualizada.fonte_id is not None
    assert atualizada.fonte_id != fonte_antiga
    # Só existe uma fonte indexada (a antiga foi removida).
    assert len(await amb["fontes"].listar(tenant_id=TENANT)) == 1
    assert all(t.fonte_id == atualizada.fonte_id for t, _ in amb["store"]._itens)


async def test_desativar_remove_do_rag():
    amb = _ambiente()
    resposta = await CriarRespostaRapida(**amb).executar(
        tenant_id=TENANT, chave="Endereço da escola", conteudo="Rua Exemplo, 100."
    )
    assert amb["store"]._itens

    await AtualizarRespostaRapida(**amb).executar(
        tenant_id=TENANT,
        resposta_id=resposta.id,
        chave="Endereço da escola",
        conteudo="Rua Exemplo, 100.",
        ativo=False,
    )
    assert amb["store"]._itens == []
    obtida = await ObterRespostaRapida(respostas=amb["respostas"]).executar(
        tenant_id=TENANT, resposta_id=resposta.id
    )
    assert obtida.ativo is False
    assert obtida.fonte_id is None


async def test_remover_apaga_resposta_e_trechos():
    amb = _ambiente()
    resposta = await CriarRespostaRapida(**amb).executar(
        tenant_id=TENANT, chave="SEDU", conteudo="Portal SEDU: acesso do responsável."
    )
    removido = await RemoverRespostaRapida(**amb).executar(
        tenant_id=TENANT, resposta_id=resposta.id
    )
    assert removido is True
    assert amb["store"]._itens == []
    assert await ListarRespostasRapidas(respostas=amb["respostas"]).executar(
        tenant_id=TENANT
    ) == []
    # Remover de novo retorna False.
    assert not await RemoverRespostaRapida(**amb).executar(
        tenant_id=TENANT, resposta_id=resposta.id
    )


async def test_acesso_isolado_por_tenant_no_obter():
    amb = _ambiente()
    resposta = await CriarRespostaRapida(**amb).executar(
        tenant_id=TENANT, chave="Conselho Tutelar", conteudo="Telefone do Conselho Tutelar."
    )
    with pytest.raises(ValueError):
        await ObterRespostaRapida(respostas=amb["respostas"]).executar(
            tenant_id=OUTRO_TENANT, resposta_id=resposta.id
        )
