"""Testa os avisos temporizados: CRUD, vigência (janela de tempo) e a resposta
automática do bot que anexa o aviso vigente ao inbound.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from app.application.avisos_use_cases import (
    AtualizarAvisoTemporizado,
    AvisoVigente,
    CriarAvisoTemporizado,
    ListarAvisosTemporizados,
    ObterAvisoTemporizado,
    RemoverAvisoTemporizado,
)
from app.application.use_cases import (
    AtenderConversa,
    ReceberMensagemRecebida,
    RecuperarEEnviarDocumento,
    ResponderDuvida,
)
from app.domain.entities import _now
from tests.fakes import (
    FakeAvisoTemporizadoRepo,
    FakeChannel,
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


async def test_criar_e_listar_aviso():
    avisos = FakeAvisoTemporizadoRepo()
    aviso = await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, mensagem="Secretaria fechada à tarde hoje."
    )
    assert aviso.ativo is True
    listados = await ListarAvisosTemporizados(avisos=avisos).executar(tenant_id=TENANT)
    assert [a.id for a in listados] == [aviso.id]


async def test_mensagem_obrigatoria():
    avisos = FakeAvisoTemporizadoRepo()
    with pytest.raises(ValueError):
        await CriarAvisoTemporizado(avisos=avisos).executar(tenant_id=TENANT, mensagem="   ")


async def test_expiracao_antes_do_inicio_falha():
    avisos = FakeAvisoTemporizadoRepo()
    agora = _now()
    with pytest.raises(ValueError):
        await CriarAvisoTemporizado(avisos=avisos).executar(
            tenant_id=TENANT,
            mensagem="janela inválida",
            inicia_em=agora,
            expira_em=agora - timedelta(hours=1),
        )


async def test_vigencia_respeita_janela_e_flag_ativo():
    avisos = FakeAvisoTemporizadoRepo()
    agora = _now()

    # Aviso já expirado — não vigente.
    await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT,
        mensagem="expirado",
        inicia_em=agora - timedelta(days=2),
        expira_em=agora - timedelta(days=1),
    )
    assert await AvisoVigente(avisos=avisos).executar(tenant_id=TENANT) is None

    # Aviso futuro — ainda não vigente.
    await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, mensagem="futuro", inicia_em=agora + timedelta(days=1)
    )
    assert await AvisoVigente(avisos=avisos).executar(tenant_id=TENANT) is None

    # Aviso vigente agora.
    vigente = await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT,
        mensagem="vigente agora",
        inicia_em=agora - timedelta(hours=1),
        expira_em=agora + timedelta(hours=1),
    )
    encontrado = await AvisoVigente(avisos=avisos).executar(tenant_id=TENANT)
    assert encontrado is not None and encontrado.id == vigente.id


async def test_aviso_inativo_nao_e_vigente():
    avisos = FakeAvisoTemporizadoRepo()
    aviso = await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, mensagem="sempre", ativo=False
    )
    assert aviso.vigente_em() is False
    assert await AvisoVigente(avisos=avisos).executar(tenant_id=TENANT) is None


async def test_atualizar_e_remover():
    avisos = FakeAvisoTemporizadoRepo()
    aviso = await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, mensagem="antigo"
    )
    atualizado = await AtualizarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, aviso_id=aviso.id, mensagem="novo texto", ativo=False
    )
    assert atualizado.mensagem == "novo texto"
    assert atualizado.ativo is False

    assert await RemoverAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, aviso_id=aviso.id
    )
    assert not await RemoverAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, aviso_id=aviso.id
    )


async def test_isolamento_por_tenant():
    avisos = FakeAvisoTemporizadoRepo()
    aviso = await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, mensagem="da escola A"
    )
    with pytest.raises(ValueError):
        await ObterAvisoTemporizado(avisos=avisos).executar(
            tenant_id=OUTRO_TENANT, aviso_id=aviso.id
        )
    assert await AvisoVigente(avisos=avisos).executar(tenant_id=OUTRO_TENANT) is None


# --------------------- integração com o inbound --------------------------- #
def _receber(avisos_repo):
    responder = ResponderDuvida(
        embedder=fake_embedder(), store=FakeVectorStore(), llm=FakeLLM()
    )
    docs = RecuperarEEnviarDocumento(source=FakeDocumentSource([]), canal=FakeChannel())
    return ReceberMensagemRecebida(
        conversas=FakeConversaRepo(),
        responder=responder,
        documentos=docs,
        avisos=avisos_repo,
    )


async def test_bot_anexa_aviso_vigente_na_resposta():
    avisos = FakeAvisoTemporizadoRepo()
    await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, mensagem="Por motivo de saúde, a secretaria não abre à tarde hoje."
    )
    uc = _receber(avisos)
    resp = await uc.executar(tenant_id=TENANT, contato="+551199", texto="bom dia")
    assert "secretaria não abre à tarde hoje" in resp.texto


async def test_bot_sem_aviso_vigente_nao_altera_resposta():
    avisos = FakeAvisoTemporizadoRepo()
    await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, mensagem="aviso inativo", ativo=False
    )
    uc = _receber(avisos)
    resp = await uc.executar(tenant_id=TENANT, contato="+551199", texto="bom dia")
    assert "📢" not in resp.texto


async def test_atender_conversa_anexa_aviso_vigente():
    # O atendimento por agente (usado no chat/demo) também anexa o aviso vigente.
    avisos = FakeAvisoTemporizadoRepo()
    await CriarAvisoTemporizado(avisos=avisos).executar(
        tenant_id=TENANT, mensagem="Aviso do agente vigente."
    )
    docs = RecuperarEEnviarDocumento(source=FakeDocumentSource([]), canal=FakeChannel())
    uc = AtenderConversa(
        conversas=FakeConversaRepo(),
        embedder=fake_embedder(),
        store=FakeVectorStore(),
        llm=FakeLLM(),
        documentos=docs,
        avisos=avisos,
    )
    resp = await uc.executar(tenant_id=TENANT, contato="+551199", texto="bom dia")
    assert "Aviso do agente vigente." in resp.texto
