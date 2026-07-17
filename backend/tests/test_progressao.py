"""Testa a progressão de série e o ciclo de vida do responsável (§F1): promoção para a
série seguinte, formatura na última série (ex-aluno) e inativação de responsáveis sem
nenhum aluno ativo.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.progressao_use_cases import (
    InativarResponsaveisSemAlunosAtivos,
    PromoverSerie,
    PromoverTurmas,
)
from app.domain.entities import Aluno, Contato, Sala
from tests.fakes import FakeAlunoRepo, FakeContatoRepo, FakeSalaRepo

TENANT = uuid.uuid4()


def _repos():
    alunos = FakeAlunoRepo()
    salas = FakeSalaRepo()
    contatos = FakeContatoRepo()
    alunos.contatos = contatos
    salas.contatos = contatos
    return alunos, salas, contatos


async def test_promover_move_ativos_para_serie_seguinte():
    alunos, salas, _ = _repos()
    quinto = await salas.criar(Sala(tenant_id=TENANT, nome="5º A"))
    sexto = await salas.criar(Sala(tenant_id=TENANT, nome="6º A"))
    ativo = await alunos.criar(Aluno(tenant_id=TENANT, nome="João", sala_id=quinto.id))
    exaluno = await alunos.criar(
        Aluno(tenant_id=TENANT, nome="Antigo", sala_id=quinto.id, ativo=False)
    )

    resultado = await PromoverSerie(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, origem_sala_id=quinto.id, destino_sala_id=sexto.id
    )

    assert resultado.alunos_promovidos == 1
    assert resultado.alunos_formados == 0
    assert (await alunos.obter(tenant_id=TENANT, aluno_id=ativo.id)).sala_id == sexto.id
    # Ex-aluno não é movido.
    assert (await alunos.obter(tenant_id=TENANT, aluno_id=exaluno.id)).sala_id == quinto.id


async def test_promover_ultima_serie_forma_alunos():
    alunos, salas, _ = _repos()
    nono = await salas.criar(Sala(tenant_id=TENANT, nome="9º A"))
    aluno = await alunos.criar(Aluno(tenant_id=TENANT, nome="Maria", sala_id=nono.id))

    resultado = await PromoverSerie(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, origem_sala_id=nono.id, destino_sala_id=None
    )

    assert resultado.alunos_formados == 1
    assert resultado.alunos_promovidos == 0
    atualizado = await alunos.obter(tenant_id=TENANT, aluno_id=aluno.id)
    assert atualizado.ativo is False
    assert atualizado.sala_id == nono.id  # permanece para histórico


async def test_promover_destino_igual_origem_falha():
    alunos, salas, _ = _repos()
    sala = await salas.criar(Sala(tenant_id=TENANT, nome="5º A"))
    with pytest.raises(ValueError):
        await PromoverSerie(alunos=alunos, salas=salas).executar(
            tenant_id=TENANT, origem_sala_id=sala.id, destino_sala_id=sala.id
        )


async def test_promover_turmas_em_lote():
    alunos, salas, _ = _repos()
    s5 = await salas.criar(Sala(tenant_id=TENANT, nome="5º A"))
    s6 = await salas.criar(Sala(tenant_id=TENANT, nome="6º A"))
    s9 = await salas.criar(Sala(tenant_id=TENANT, nome="9º A"))
    await alunos.criar(Aluno(tenant_id=TENANT, nome="A", sala_id=s5.id))
    await alunos.criar(Aluno(tenant_id=TENANT, nome="B", sala_id=s9.id))

    resultados = await PromoverTurmas(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT,
        promocoes=[(s5.id, s6.id), (s9.id, None)],
    )
    assert len(resultados) == 2
    assert resultados[0].alunos_promovidos == 1
    assert resultados[1].alunos_formados == 1


async def test_inativa_responsavel_so_quando_todos_alunos_inativos():
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()

    # Responsável com todos os alunos ex-alunos → inativa.
    pai_ex = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai Ex", telefone="+5511111110000"))
    a1 = Aluno(tenant_id=TENANT, nome="A1", sala_id=sala_id, ativo=False, responsaveis=[pai_ex])
    await alunos.criar(a1)

    # Responsável com um aluno ainda ativo → mantém.
    pai_ativo = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai Ativo", telefone="+5511222220000"))
    a2 = Aluno(tenant_id=TENANT, nome="A2", sala_id=sala_id, ativo=True, responsaveis=[pai_ativo])
    a3 = Aluno(tenant_id=TENANT, nome="A3", sala_id=sala_id, ativo=False, responsaveis=[pai_ativo])
    await alunos.criar(a2)
    await alunos.criar(a3)

    # Responsável sem alunos vinculados → mantém.
    pai_sem = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai Sem", telefone="+5511333330000"))

    inativados = await InativarResponsaveisSemAlunosAtivos(
        alunos=alunos, contatos=contatos
    ).executar(tenant_id=TENANT)

    assert [r.contato_id for r in inativados] == [pai_ex.id]
    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai_ex.id)).ativo is False
    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai_ativo.id)).ativo is True
    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai_sem.id)).ativo is True


async def test_inativar_idempotente():
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()
    pai = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai", telefone="+5511111110000"))
    await alunos.criar(
        Aluno(tenant_id=TENANT, nome="A", sala_id=sala_id, ativo=False, responsaveis=[pai])
    )
    inativar = InativarResponsaveisSemAlunosAtivos(alunos=alunos, contatos=contatos)
    primeiros = await inativar.executar(tenant_id=TENANT)
    assert len(primeiros) == 1
    # Segunda passada não re-inativa quem já está inativo.
    segundos = await inativar.executar(tenant_id=TENANT)
    assert segundos == []
