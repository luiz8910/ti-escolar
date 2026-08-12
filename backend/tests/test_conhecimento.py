"""Testa a base de conhecimento alimentada pela escola:

- ingestão (fragmentação + indexação no RAG, escopada por tenant);
- remoção de um documento (fonte) e de seus trechos;
- system prompt personalizado por tenant e sua injeção no prompt de sistema.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.conhecimento_use_cases import (
    AtualizarFonteConhecimento,
    DefinirAtivoFonteConhecimento,
    DefinirPromptTenant,
    IngerirDocumento,
    ListarFontesConhecimento,
    ObterFonteConhecimento,
    ObterPromptTenant,
    RemoverFonteConhecimento,
    fragmentar,
)
from app.application.use_cases import ResponderDuvida
from app.domain.entities import TipoConhecimento
from tests.fakes import (
    FakeFonteConhecimentoRepo,
    FakeLLM,
    FakePromptTenantRepo,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


# --------------------------- fragmentação --------------------------------- #
def test_fragmentar_agrupa_paragrafos_respeitando_limite():
    texto = "\n\n".join(f"Parágrafo {i} " + "x" * 300 for i in range(4))
    trechos = fragmentar(texto, max_chars=400)
    assert len(trechos) >= 2
    assert all(t.strip() for t in trechos)


def test_fragmentar_texto_vazio():
    assert fragmentar("   \n\n  ") == []


# --------------------------- ingestão (RAG) -------------------------------- #
def _ingestao() -> tuple[IngerirDocumento, FakeVectorStore, FakeFonteConhecimentoRepo]:
    store = FakeVectorStore()
    fontes = FakeFonteConhecimentoRepo()
    uc = IngerirDocumento(embedder=fake_embedder(), store=store, fontes=fontes)
    return uc, store, fontes


async def test_ingerir_documento_indexa_trechos_com_fonte():
    uc, store, fontes = _ingestao()
    conteudo = "\n\n".join(f"Procedimento {i}: " + "detalhe " * 40 for i in range(3))

    fonte = await uc.executar(
        tenant_id=TENANT, nome="Manual de procedimentos", conteudo=conteudo
    )

    assert fonte.total_trechos >= 1
    assert fonte.tipo == TipoConhecimento.PROCEDIMENTO
    # Todos os trechos indexados apontam para a fonte criada.
    assert all(t.fonte_id == fonte.id for t, _ in store._itens)
    assert (await ListarFontesConhecimento(fontes=fontes).executar(tenant_id=TENANT)) == [fonte]


async def test_ingestao_e_recuperavel_no_rag_e_isolada_por_tenant():
    uc, store, _ = _ingestao()
    await uc.executar(
        tenant_id=TENANT,
        nome="Regras de uniforme",
        conteudo="O uniforme é obrigatório todos os dias letivos, inclusive em provas.",
    )

    embedder = fake_embedder()
    responder = ResponderDuvida(embedder=embedder, store=store, llm=FakeLLM())
    resp = await responder.executar(tenant_id=TENANT, pergunta="o uniforme é obrigatório?")
    assert "Regras de uniforme" in resp.fontes

    # Outro tenant não enxerga o documento.
    resp_outro = await responder.executar(
        tenant_id=OUTRO_TENANT, pergunta="o uniforme é obrigatório?"
    )
    assert resp_outro.fontes == []


async def test_ingerir_documento_vazio_falha():
    uc, _, _ = _ingestao()
    with pytest.raises(ValueError):
        await uc.executar(tenant_id=TENANT, nome="Vazio", conteudo="   ")


async def test_remover_fonte_apaga_trechos_e_metadados():
    uc, store, fontes = _ingestao()
    fonte = await uc.executar(
        tenant_id=TENANT, nome="A remover", conteudo="conteúdo qualquer de procedimento"
    )
    assert store._itens

    remover = RemoverFonteConhecimento(fontes=fontes, store=store)
    assert await remover.executar(tenant_id=TENANT, fonte_id=fonte.id)
    assert store._itens == []
    assert await ListarFontesConhecimento(fontes=fontes).executar(tenant_id=TENANT) == []
    # Remover de novo retorna False.
    assert not await remover.executar(tenant_id=TENANT, fonte_id=fonte.id)


# --------------------------- system prompt do tenant ----------------------- #
async def test_definir_e_obter_prompt_do_tenant():
    prompts = FakePromptTenantRepo()
    await DefinirPromptTenant(prompts=prompts).executar(
        tenant_id=TENANT, conteudo="Trate todos pelo primeiro nome."
    )
    obtido = await ObterPromptTenant(prompts=prompts).executar(tenant_id=TENANT)
    assert obtido.conteudo == "Trate todos pelo primeiro nome."

    # Tenant sem prompt definido recebe conteúdo vazio (não None).
    vazio = await ObterPromptTenant(prompts=prompts).executar(tenant_id=OUTRO_TENANT)
    assert vazio.conteudo == ""


async def test_prompt_do_tenant_entra_no_sistema_do_responder():
    store = FakeVectorStore()
    prompts = FakePromptTenantRepo()
    await DefinirPromptTenant(prompts=prompts).executar(
        tenant_id=TENANT, conteudo="REGRA-DA-ESCOLA-XYZ"
    )
    llm = FakeLLM()
    responder = ResponderDuvida(
        embedder=fake_embedder(), store=store, llm=llm, prompts=prompts
    )

    await responder.executar(tenant_id=TENANT, pergunta="qualquer coisa")
    assert "REGRA-DA-ESCOLA-XYZ" in llm.ultimo_sistema


# --------------------- edição e interruptor de indexação ------------------- #
def _gestao() -> tuple[
    IngerirDocumento,
    AtualizarFonteConhecimento,
    DefinirAtivoFonteConhecimento,
    FakeVectorStore,
    FakeFonteConhecimentoRepo,
]:
    store = FakeVectorStore()
    fontes = FakeFonteConhecimentoRepo()
    embedder = fake_embedder()
    return (
        IngerirDocumento(embedder=embedder, store=store, fontes=fontes),
        AtualizarFonteConhecimento(fontes=fontes, embedder=embedder, store=store),
        DefinirAtivoFonteConhecimento(fontes=fontes, embedder=embedder, store=store),
        store,
        fontes,
    )


def _trechos(store: FakeVectorStore, fonte_id: uuid.UUID) -> list[str]:
    return [t.conteudo for t, _ in store._itens if t.fonte_id == fonte_id]


async def test_ingestao_guarda_o_texto_original():
    """Sem isso o documento só existia fragmentado: dava para apagar, nunca para reler."""
    uc, _, _, _, fontes = _gestao()
    fonte = await uc.executar(
        tenant_id=TENANT, nome="Uniforme", conteudo="O uniforme é obrigatório."
    )
    guardada = await ObterFonteConhecimento(fontes=fontes).executar(
        tenant_id=TENANT, fonte_id=fonte.id
    )
    assert guardada is not None
    assert guardada.conteudo == "O uniforme é obrigatório."
    assert guardada.ativo is True


async def test_editar_reindexa_e_nao_deixa_trecho_antigo_no_rag():
    """O trecho órfão é o risco real: o bot responderia a regra revogada."""
    ingerir, atualizar, _, store, _ = _gestao()
    fonte = await ingerir.executar(
        tenant_id=TENANT, nome="Portão", conteudo="O portão fecha às 7h30."
    )

    editada = await atualizar.executar(
        tenant_id=TENANT,
        fonte_id=fonte.id,
        nome="Portão",
        conteudo="O portão fecha às 8h00.",
        tipo=TipoConhecimento.PROCEDIMENTO,
    )

    # Mesmo id: quem edita está corrigindo *aquele* documento.
    assert editada.id == fonte.id
    indexado = " ".join(_trechos(store, fonte.id))
    assert "8h00" in indexado
    assert "7h30" not in indexado


async def test_desativar_tira_do_rag_sem_apagar_o_texto():
    ingerir, _, definir_ativo, store, _ = _gestao()
    fonte = await ingerir.executar(
        tenant_id=TENANT, nome="Recesso", conteudo="Recesso de julho: dias 1 a 15."
    )
    assert _trechos(store, fonte.id)

    desativada = await definir_ativo.executar(
        tenant_id=TENANT, fonte_id=fonte.id, ativo=False
    )

    assert desativada.ativo is False
    assert _trechos(store, fonte.id) == []
    # O texto continua guardado — desativar não é apagar.
    assert "Recesso de julho" in desativada.conteudo
    # E o número de fragmentos descreve o documento, não o interruptor.
    assert desativada.total_trechos == fonte.total_trechos


async def test_reativar_devolve_o_documento_ao_rag():
    ingerir, _, definir_ativo, store, _ = _gestao()
    fonte = await ingerir.executar(
        tenant_id=TENANT, nome="Recesso", conteudo="Recesso de julho: dias 1 a 15."
    )
    await definir_ativo.executar(tenant_id=TENANT, fonte_id=fonte.id, ativo=False)

    await definir_ativo.executar(tenant_id=TENANT, fonte_id=fonte.id, ativo=True)

    assert "Recesso de julho" in " ".join(_trechos(store, fonte.id))


async def test_editar_documento_desativado_nao_o_reindexa():
    """Salvar uma correção não pode ressuscitar no RAG o que a escola tirou do ar."""
    ingerir, atualizar, definir_ativo, store, _ = _gestao()
    fonte = await ingerir.executar(
        tenant_id=TENANT, nome="Antigo", conteudo="Regra revogada."
    )
    await definir_ativo.executar(tenant_id=TENANT, fonte_id=fonte.id, ativo=False)

    await atualizar.executar(
        tenant_id=TENANT,
        fonte_id=fonte.id,
        nome="Antigo",
        conteudo="Regra revogada, com correção de grafia.",
        tipo=TipoConhecimento.PROCEDIMENTO,
        ativo=False,
    )

    assert _trechos(store, fonte.id) == []


async def test_edicao_e_desativacao_nao_atravessam_tenant():
    ingerir, atualizar, definir_ativo, _, _ = _gestao()
    fonte = await ingerir.executar(
        tenant_id=TENANT, nome="Interno", conteudo="Conteúdo da escola A."
    )

    with pytest.raises(ValueError):
        await atualizar.executar(
            tenant_id=OUTRO_TENANT,
            fonte_id=fonte.id,
            nome="Sequestrado",
            conteudo="Conteúdo trocado.",
            tipo=TipoConhecimento.PROCEDIMENTO,
        )
    with pytest.raises(ValueError):
        await definir_ativo.executar(
            tenant_id=OUTRO_TENANT, fonte_id=fonte.id, ativo=False
        )


async def test_editar_com_texto_vazio_e_recusado():
    ingerir, atualizar, _, _, _ = _gestao()
    fonte = await ingerir.executar(tenant_id=TENANT, nome="Algo", conteudo="Conteúdo.")

    with pytest.raises(ValueError):
        await atualizar.executar(
            tenant_id=TENANT,
            fonte_id=fonte.id,
            nome="Algo",
            conteudo="   \n\n  ",
            tipo=TipoConhecimento.PROCEDIMENTO,
        )
