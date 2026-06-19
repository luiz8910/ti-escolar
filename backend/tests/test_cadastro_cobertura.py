"""Testa o alerta de cobertura de contatos da turma: alunos sem nenhum responsável
com telefone vinculado e a notificação ao professor para coletar os faltantes."""

from __future__ import annotations

import uuid

import pytest

from app.application.cadastro_use_cases import (
    AtualizarAluno,
    CadastrarAluno,
    CadastrarPai,
    CoberturaDeContatosDaSala,
    CriarSala,
    NotificarProfessorContatosFaltantes,
    ResumoCoberturaDasSalas,
)
from tests.fakes import FakeAlunoRepo, FakeChannel, FakeContatoRepo, FakeSalaRepo

TENANT = uuid.uuid4()


def _repos() -> tuple[FakeAlunoRepo, FakeContatoRepo, FakeSalaRepo]:
    contatos = FakeContatoRepo()
    salas = FakeSalaRepo()
    salas.contatos = contatos
    alunos = FakeAlunoRepo()
    alunos.contatos = contatos
    return alunos, contatos, salas


async def _sala(salas, *, nome="4ª série B"):
    return await CriarSala(salas=salas).executar(tenant_id=TENANT, nome=nome)


async def _pai(contatos, salas, *, telefone):
    return await CadastrarPai(contatos=contatos, salas=salas).executar(
        tenant_id=TENANT, nome="Resp", telefone=telefone
    )


# ----------------------------- cobertura ----------------------------------- #
async def test_cobertura_conta_alunos_sem_responsavel_com_telefone():
    alunos, contatos, salas = _repos()
    sala = await _sala(salas)
    pai = await _pai(contatos, salas, telefone="+5511999990001")
    cadastrar = CadastrarAluno(alunos=alunos, salas=salas)

    # 1 com responsável, 2 sem nenhum responsável.
    await cadastrar.executar(
        tenant_id=TENANT, nome="Com contato", sala_id=sala.id, responsavel_ids=[pai.id]
    )
    await cadastrar.executar(tenant_id=TENANT, nome="Sem contato A", sala_id=sala.id)
    await cadastrar.executar(tenant_id=TENANT, nome="Sem contato B", sala_id=sala.id)

    cobertura = await CoberturaDeContatosDaSala(salas=salas, alunos=alunos).executar(
        tenant_id=TENANT, sala_id=sala.id
    )
    assert cobertura.total_alunos == 3
    assert cobertura.total_sem_contato == 2
    assert {a.nome for a in cobertura.alunos_sem_contato} == {"Sem contato A", "Sem contato B"}


async def test_cobertura_ignora_ex_alunos():
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Ex aluno", sala_id=sala.id
    )
    # Marca como ex-aluno: não deve entrar na contagem da cobertura.
    await AtualizarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, aluno_id=aluno.id, nome=aluno.nome, sala_id=sala.id, ativo=False
    )

    cobertura = await CoberturaDeContatosDaSala(salas=salas, alunos=alunos).executar(
        tenant_id=TENANT, sala_id=sala.id
    )
    assert cobertura.total_alunos == 0
    assert cobertura.total_sem_contato == 0


async def test_cobertura_sala_inexistente_falha():
    alunos, _, salas = _repos()
    with pytest.raises(ValueError, match="[Ss]ala"):
        await CoberturaDeContatosDaSala(salas=salas, alunos=alunos).executar(
            tenant_id=TENANT, sala_id=uuid.uuid4()
        )


async def test_resumo_cobertura_por_sala():
    alunos, contatos, salas = _repos()
    s1 = await _sala(salas, nome="4ª série B")
    s2 = await _sala(salas, nome="5ª série A")
    pai = await _pai(contatos, salas, telefone="+5511999990001")
    cadastrar = CadastrarAluno(alunos=alunos, salas=salas)
    await cadastrar.executar(tenant_id=TENANT, nome="A", sala_id=s1.id)
    await cadastrar.executar(
        tenant_id=TENANT, nome="B", sala_id=s2.id, responsavel_ids=[pai.id]
    )

    coberturas = await ResumoCoberturaDasSalas(salas=salas, alunos=alunos).executar(
        tenant_id=TENANT
    )
    por_sala = {c.sala_id: c for c in coberturas}
    assert por_sala[s1.id].total_sem_contato == 1
    assert por_sala[s2.id].total_sem_contato == 0


# --------------------------- notificar professor --------------------------- #
async def test_notificar_professor_envia_aviso_dos_faltantes():
    alunos, _, salas = _repos()
    canal = FakeChannel()
    sala = await _sala(salas)
    await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Sem contato", sala_id=sala.id
    )

    cobertura, id_externo = await NotificarProfessorContatosFaltantes(
        salas=salas, alunos=alunos, canal=canal
    ).executar(
        tenant_id=TENANT, sala_id=sala.id, telefone_professor="+5511988887777"
    )

    assert id_externo == "x"
    assert cobertura.total_sem_contato == 1
    assert canal.enviados == [("+5511988887777", "texto")]


async def test_notificar_professor_sem_faltantes_falha():
    alunos, contatos, salas = _repos()
    canal = FakeChannel()
    sala = await _sala(salas)
    pai = await _pai(contatos, salas, telefone="+5511999990001")
    await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Com contato", sala_id=sala.id, responsavel_ids=[pai.id]
    )

    with pytest.raises(ValueError, match="já têm"):
        await NotificarProfessorContatosFaltantes(
            salas=salas, alunos=alunos, canal=canal
        ).executar(tenant_id=TENANT, sala_id=sala.id, telefone_professor="+5511988887777")
    assert canal.enviados == []


async def test_notificar_professor_sem_telefone_falha():
    alunos, _, salas = _repos()
    canal = FakeChannel()
    sala = await _sala(salas)
    await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Sem contato", sala_id=sala.id
    )
    with pytest.raises(ValueError, match="[Tt]elefone"):
        await NotificarProfessorContatosFaltantes(
            salas=salas, alunos=alunos, canal=canal
        ).executar(tenant_id=TENANT, sala_id=sala.id, telefone_professor="  ")
