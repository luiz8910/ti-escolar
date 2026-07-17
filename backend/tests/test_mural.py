"""Testa o mural do professor (§A1): publicação de recados, confirmação de leitura,
status (quem leu / quem não leu), re-notificação dos não-lidos e login do professor.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.cadastro_use_cases import CadastrarProfessor
from app.application.mural_use_cases import (
    AutenticarProfessor,
    ConfirmarLeituraRecado,
    ListarRecados,
    ListarRecadosDoProfessor,
    ObterStatusLeitura,
    PublicarRecado,
    RemoverRecado,
    ReNotificarRecadoNaoLido,
)
from tests.fakes import FakeChannel, FakeMuralRepo, FakeProfessorRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


async def _dois_professores():
    professores = FakeProfessorRepo()
    p1 = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Prof. Ana", telefone="+5511999990001", senha="segredo1"
    )
    p2 = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Prof. Bruno", telefone="+5511999990002"
    )
    return professores, p1, p2


async def test_publicar_recado_valida_campos():
    mural = FakeMuralRepo()
    with pytest.raises(ValueError):
        await PublicarRecado(mural=mural).executar(tenant_id=TENANT, titulo=" ", corpo="x")
    with pytest.raises(ValueError):
        await PublicarRecado(mural=mural).executar(tenant_id=TENANT, titulo="t", corpo=" ")


async def test_confirmacao_de_leitura_e_status():
    mural = FakeMuralRepo()
    professores, p1, p2 = await _dois_professores()
    recado = await PublicarRecado(mural=mural).executar(
        tenant_id=TENANT, titulo="Reunião sexta", corpo="Comparecer às 17h."
    )

    # Ninguém leu ainda.
    resumos = await ListarRecados(mural=mural, professores=professores).executar(
        tenant_id=TENANT
    )
    assert resumos[0].total_professores == 2
    assert resumos[0].total_lidos == 0
    assert resumos[0].total_nao_lidos == 2

    # p1 confirma leitura (idempotente).
    await ConfirmarLeituraRecado(mural=mural).executar(
        tenant_id=TENANT, recado_id=recado.id, professor_id=p1.id
    )
    await ConfirmarLeituraRecado(mural=mural).executar(
        tenant_id=TENANT, recado_id=recado.id, professor_id=p1.id
    )

    status = await ObterStatusLeitura(mural=mural, professores=professores).executar(
        tenant_id=TENANT, recado_id=recado.id
    )
    assert [p.id for p, _ in status.lidos] == [p1.id]
    assert [p.id for p in status.nao_lidos] == [p2.id]


async def test_lista_do_professor_marca_lido():
    mural = FakeMuralRepo()
    _, p1, _ = await _dois_professores()
    recado = await PublicarRecado(mural=mural).executar(
        tenant_id=TENANT, titulo="Aviso", corpo="conteúdo"
    )
    antes = await ListarRecadosDoProfessor(mural=mural).executar(
        tenant_id=TENANT, professor_id=p1.id
    )
    assert antes[0].lido is False

    await ConfirmarLeituraRecado(mural=mural).executar(
        tenant_id=TENANT, recado_id=recado.id, professor_id=p1.id
    )
    depois = await ListarRecadosDoProfessor(mural=mural).executar(
        tenant_id=TENANT, professor_id=p1.id
    )
    assert depois[0].lido is True
    assert depois[0].lido_em is not None


async def test_renotificar_apenas_nao_lidos_com_telefone():
    mural = FakeMuralRepo()
    professores, p1, p2 = await _dois_professores()
    recado = await PublicarRecado(mural=mural).executar(
        tenant_id=TENANT, titulo="Importante", corpo="ler hoje"
    )
    # p1 leu; p2 não leu (mas tem telefone).
    await ConfirmarLeituraRecado(mural=mural).executar(
        tenant_id=TENANT, recado_id=recado.id, professor_id=p1.id
    )
    canal = FakeChannel()
    avisados = await ReNotificarRecadoNaoLido(
        mural=mural, professores=professores, canal=canal
    ).executar(tenant_id=TENANT, recado_id=recado.id)
    assert avisados == 1
    assert canal.enviados == [(p2.telefone, "texto")]


async def test_remover_recado_e_isolamento():
    mural = FakeMuralRepo()
    professores, _, _ = await _dois_professores()
    recado = await PublicarRecado(mural=mural).executar(
        tenant_id=TENANT, titulo="x", corpo="y"
    )
    # Outro tenant não vê nem o status.
    with pytest.raises(ValueError):
        await ObterStatusLeitura(mural=mural, professores=professores).executar(
            tenant_id=OUTRO_TENANT, recado_id=recado.id
        )
    assert await RemoverRecado(mural=mural).executar(
        tenant_id=TENANT, recado_id=recado.id
    )
    assert not await RemoverRecado(mural=mural).executar(
        tenant_id=TENANT, recado_id=recado.id
    )


# --------------------------- login do professor --------------------------- #
async def test_login_professor_valida_senha():
    professores, p1, p2 = await _dois_professores()
    autenticar = AutenticarProfessor(professores=professores)

    # Senha correta.
    ok = await autenticar.executar(
        tenant_id=TENANT, telefone=p1.telefone, senha="segredo1"
    )
    assert ok is not None and ok.id == p1.id

    # Senha errada.
    assert (
        await autenticar.executar(tenant_id=TENANT, telefone=p1.telefone, senha="errada")
        is None
    )
    # Professor sem senha definida não loga.
    assert (
        await autenticar.executar(tenant_id=TENANT, telefone=p2.telefone, senha="x")
        is None
    )
    # Tenant errado não loga.
    assert (
        await autenticar.executar(
            tenant_id=OUTRO_TENANT, telefone=p1.telefone, senha="segredo1"
        )
        is None
    )
