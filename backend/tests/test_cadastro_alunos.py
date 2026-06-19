"""Testa o CRUD de alunos: cadastro, série (1:1 obrigatória), responsáveis (N:N),
isolamento por tenant e exclusão de série (mover x excluir alunos)."""

from __future__ import annotations

import uuid

import pytest

from app.application.cadastro_use_cases import (
    AtualizarAluno,
    CadastrarAluno,
    CadastrarPai,
    CriarSala,
    DesvincularResponsavelDoAluno,
    ListarAlunos,
    RemoverAluno,
    RemoverSala,
    VincularResponsavelAoAluno,
)
from tests.fakes import FakeAlunoRepo, FakeContatoRepo, FakeSalaRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


def _repos() -> tuple[FakeAlunoRepo, FakeContatoRepo, FakeSalaRepo]:
    contatos = FakeContatoRepo()
    salas = FakeSalaRepo()
    salas.contatos = contatos
    alunos = FakeAlunoRepo()
    alunos.contatos = contatos
    return alunos, contatos, salas


async def _sala(salas, *, tenant_id=TENANT, nome="4ª série B"):
    return await CriarSala(salas=salas).executar(tenant_id=tenant_id, nome=nome)


async def _pai(contatos, salas, *, tenant_id=TENANT, nome="Maria", telefone="+5511999990001"):
    return await CadastrarPai(contatos=contatos, salas=salas).executar(
        tenant_id=tenant_id, nome=nome, telefone=telefone
    )


# --------------------------- cadastro + série ------------------------------ #
async def test_cadastrar_aluno_com_serie_e_responsaveis():
    alunos, contatos, salas = _repos()
    sala = await _sala(salas)
    pai = await _pai(contatos, salas)

    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT,
        nome="Pedro Souza",
        sala_id=sala.id,
        matricula="2026-001",
        responsavel_ids=[pai.id],
    )

    assert aluno.nome == "Pedro Souza"
    assert aluno.sala_id == sala.id
    assert [c.id for c in aluno.responsaveis] == [pai.id]


async def test_serie_inexistente_no_tenant_falha():
    alunos, _, salas = _repos()
    sala_outro = await _sala(salas, tenant_id=OUTRO_TENANT, nome="Intrusa")
    with pytest.raises(ValueError, match="[Ss]érie"):
        await CadastrarAluno(alunos=alunos, salas=salas).executar(
            tenant_id=TENANT, nome="Pedro", sala_id=sala_outro.id
        )


# --------------------------- responsáveis (N:N) ---------------------------- #
async def test_vincular_e_desvincular_varios_responsaveis():
    alunos, contatos, salas = _repos()
    sala = await _sala(salas)
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )
    mae = await _pai(contatos, salas, nome="Mãe", telefone="+5511999990001")
    pai = await _pai(contatos, salas, nome="Pai", telefone="+5511999990002")

    vincular = VincularResponsavelAoAluno(alunos=alunos)
    await vincular.executar(tenant_id=TENANT, aluno_id=aluno.id, contato_id=mae.id)
    await vincular.executar(tenant_id=TENANT, aluno_id=aluno.id, contato_id=pai.id)
    # Idempotente: vincular o mesmo responsável de novo não duplica.
    await vincular.executar(tenant_id=TENANT, aluno_id=aluno.id, contato_id=mae.id)

    atual = await alunos.obter(tenant_id=TENANT, aluno_id=aluno.id)
    assert {c.id for c in atual.responsaveis} == {mae.id, pai.id}

    await DesvincularResponsavelDoAluno(alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, contato_id=mae.id
    )
    atual = await alunos.obter(tenant_id=TENANT, aluno_id=aluno.id)
    assert [c.id for c in atual.responsaveis] == [pai.id]


async def test_vincular_responsavel_de_outro_tenant_falha():
    alunos, contatos, salas = _repos()
    sala = await _sala(salas)
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )
    intruso = await _pai(contatos, salas, tenant_id=OUTRO_TENANT, telefone="+5511999990009")
    with pytest.raises(ValueError):
        await VincularResponsavelAoAluno(alunos=alunos).executar(
            tenant_id=TENANT, aluno_id=aluno.id, contato_id=intruso.id
        )


# --------------------------- atualização + remoção ------------------------- #
async def test_atualizar_aluno_troca_serie_e_marca_ex_aluno():
    alunos, _, salas = _repos()
    s1 = await _sala(salas, nome="4ª série B")
    s2 = await _sala(salas, nome="5ª série A")
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=s1.id
    )

    atualizado = await AtualizarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, aluno_id=aluno.id, nome="Pedro S.", sala_id=s2.id, ativo=False
    )
    assert atualizado.sala_id == s2.id
    assert atualizado.ativo is False
    assert atualizado.nome == "Pedro S."


async def test_filtrar_alunos_por_serie():
    alunos, _, salas = _repos()
    s1 = await _sala(salas, nome="4ª série B")
    s2 = await _sala(salas, nome="5ª série A")
    cadastrar = CadastrarAluno(alunos=alunos, salas=salas)
    await cadastrar.executar(tenant_id=TENANT, nome="A", sala_id=s1.id)
    await cadastrar.executar(tenant_id=TENANT, nome="B", sala_id=s2.id)

    da_s1 = await ListarAlunos(alunos=alunos).executar(tenant_id=TENANT, sala_id=s1.id)
    assert [a.nome for a in da_s1] == ["A"]


async def test_remover_aluno():
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )
    assert await RemoverAluno(alunos=alunos).executar(tenant_id=TENANT, aluno_id=aluno.id)
    assert await ListarAlunos(alunos=alunos).executar(tenant_id=TENANT) == []
    assert not await RemoverAluno(alunos=alunos).executar(tenant_id=TENANT, aluno_id=aluno.id)


# --------------------- exclusão de série (estratégias) --------------------- #
async def test_excluir_serie_excluindo_os_alunos():
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )

    removida = await RemoverSala(salas=salas, alunos=alunos).executar(
        tenant_id=TENANT, sala_id=sala.id
    )
    assert removida
    # Sem mover_para, os alunos da série somem junto.
    assert await ListarAlunos(alunos=alunos).executar(tenant_id=TENANT) == []
    assert await salas.obter(tenant_id=TENANT, sala_id=sala.id) is None


async def test_excluir_serie_movendo_alunos_para_outra():
    alunos, _, salas = _repos()
    origem = await _sala(salas, nome="4ª série B")
    destino = await _sala(salas, nome="5ª série A")
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=origem.id
    )

    removida = await RemoverSala(salas=salas, alunos=alunos).executar(
        tenant_id=TENANT, sala_id=origem.id, mover_para=destino.id
    )
    assert removida
    movido = await alunos.obter(tenant_id=TENANT, aluno_id=aluno.id)
    assert movido.sala_id == destino.id
    assert await salas.obter(tenant_id=TENANT, sala_id=origem.id) is None


async def test_mover_para_a_propria_serie_falha():
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    with pytest.raises(ValueError, match="diferente"):
        await RemoverSala(salas=salas, alunos=alunos).executar(
            tenant_id=TENANT, sala_id=sala.id, mover_para=sala.id
        )


async def test_mover_para_serie_inexistente_falha():
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    with pytest.raises(ValueError, match="[Ss]érie"):
        await RemoverSala(salas=salas, alunos=alunos).executar(
            tenant_id=TENANT, sala_id=sala.id, mover_para=uuid.uuid4()
        )
