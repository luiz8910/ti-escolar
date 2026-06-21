"""Testa o cadastro de professores e a atribuição à série (Sala.professor_id)."""

from __future__ import annotations

import uuid

import pytest

from app.application.cadastro_use_cases import (
    AtribuirProfessorASala,
    AtualizarProfessor,
    CadastrarProfessor,
    CriarSala,
    ListarProfessores,
    ListarSeriesDoProfessor,
    ObterProfessor,
    RemoverProfessor,
    RemoverProfessorDaSala,
)
from tests.fakes import FakeProfessorRepo, FakeSalaRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


def _repos() -> tuple[FakeProfessorRepo, FakeSalaRepo]:
    professores = FakeProfessorRepo()
    salas = FakeSalaRepo()
    salas.professores = professores  # o fake resolve o nome do professor ao atribuir
    return professores, salas


# --------------------------- professores (CRUD) --------------------------- #
async def test_cadastrar_professor():
    professores, _ = _repos()
    prof = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Prof. Ana", telefone="+5511988880001"
    )
    assert prof.nome == "Prof. Ana"
    listados = await ListarProfessores(professores=professores).executar(tenant_id=TENANT)
    assert [p.id for p in listados] == [prof.id]


async def test_telefone_duplicado_no_tenant_falha():
    professores, _ = _repos()
    cadastrar = CadastrarProfessor(professores=professores)
    await cadastrar.executar(tenant_id=TENANT, nome="Ana", telefone="+5511988880001")
    with pytest.raises(ValueError, match="telefone"):
        await cadastrar.executar(tenant_id=TENANT, nome="Outra", telefone="+5511988880001")


async def test_mesmo_telefone_em_tenants_diferentes_e_permitido():
    professores, _ = _repos()
    cadastrar = CadastrarProfessor(professores=professores)
    await cadastrar.executar(tenant_id=TENANT, nome="Ana", telefone="+5511988880001")
    await cadastrar.executar(tenant_id=OUTRO_TENANT, nome="Ana", telefone="+5511988880001")


async def test_atualizar_professor_mantendo_unicidade():
    professores, _ = _repos()
    cadastrar = CadastrarProfessor(professores=professores)
    p1 = await cadastrar.executar(tenant_id=TENANT, nome="Ana", telefone="+5511988880001")
    await cadastrar.executar(tenant_id=TENANT, nome="Bia", telefone="+5511988880002")

    atualizar = AtualizarProfessor(professores=professores)
    atualizado = await atualizar.executar(
        tenant_id=TENANT, professor_id=p1.id, nome="Ana S.", telefone="+5511988880009"
    )
    assert atualizado.nome == "Ana S."

    with pytest.raises(ValueError, match="telefone"):
        await atualizar.executar(
            tenant_id=TENANT, professor_id=p1.id, nome="Ana S.", telefone="+5511988880002"
        )


# --------------------- atribuição professor ↔ série ----------------------- #
async def test_atribuir_professor_a_serie_e_listar_series():
    professores, salas = _repos()
    prof = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Prof. Ana", telefone="+5511988880001"
    )
    sala_a = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    sala_b = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="5ª série A")

    # Um professor pode conduzir várias séries.
    for sala in (sala_a, sala_b):
        s = await AtribuirProfessorASala(salas=salas).executar(
            tenant_id=TENANT, sala_id=sala.id, professor_id=prof.id
        )
        assert s.professor_id == prof.id
        assert s.professor_nome == "Prof. Ana"

    series = await ListarSeriesDoProfessor(salas=salas).executar(
        tenant_id=TENANT, professor_id=prof.id
    )
    assert {s.id for s in series} == {sala_a.id, sala_b.id}


async def test_reatribuir_substitui_o_professor_anterior():
    professores, salas = _repos()
    p1 = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511988880001"
    )
    p2 = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Bia", telefone="+5511988880002"
    )
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")

    await AtribuirProfessorASala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, professor_id=p1.id
    )
    s = await AtribuirProfessorASala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, professor_id=p2.id
    )
    assert s.professor_id == p2.id


async def test_remover_professor_da_serie():
    professores, salas = _repos()
    prof = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511988880001"
    )
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    await AtribuirProfessorASala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, professor_id=prof.id
    )

    s = await RemoverProfessorDaSala(salas=salas).executar(tenant_id=TENANT, sala_id=sala.id)
    assert s.professor_id is None
    assert s.professor_nome == ""


async def test_atribuir_professor_de_outro_tenant_falha():
    professores, salas = _repos()
    prof_outro = await CadastrarProfessor(professores=professores).executar(
        tenant_id=OUTRO_TENANT, nome="Intruso", telefone="+5511988880007"
    )
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    with pytest.raises(ValueError):
        await AtribuirProfessorASala(salas=salas).executar(
            tenant_id=TENANT, sala_id=sala.id, professor_id=prof_outro.id
        )


async def test_remover_professor():
    professores, _ = _repos()
    prof = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511988880001"
    )
    assert await RemoverProfessor(professores=professores).executar(
        tenant_id=TENANT, professor_id=prof.id
    )
    assert await ListarProfessores(professores=professores).executar(tenant_id=TENANT) == []
    with pytest.raises(ValueError):
        await ObterProfessor(professores=professores).executar(
            tenant_id=TENANT, professor_id=prof.id
        )
