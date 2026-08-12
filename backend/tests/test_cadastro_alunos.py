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
    DesativarAluno,
    ReativarAluno,
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
    return await CadastrarPai(contatos=contatos).executar(
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

    da_s1 = (
        await ListarAlunos(alunos=alunos).executar(tenant_id=TENANT, sala_id=s1.id)
    ).itens
    assert [a.nome for a in da_s1] == ["A"]


async def test_desativar_aluno_preserva_o_registro():
    """A "exclusão" do painel é soft delete: o aluno vira ex-aluno, mas o registro de que
    estudou aqui — e os vínculos com os responsáveis — permanecem."""
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )

    desativado = await DesativarAluno(alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, motivo="Transferido para outra escola"
    )

    assert desativado is not None and not desativado.ativo
    assert desativado.desativado_em is not None
    assert desativado.motivo_desativacao == "Transferido para outra escola"
    # Continua existindo: some da lista de matriculados, não da base.
    assert (await ListarAlunos(alunos=alunos).executar(tenant_id=TENANT)).itens != []
    assert (
        await ListarAlunos(alunos=alunos).executar(
            tenant_id=TENANT, apenas_ativos=True
        )
    ).itens == []
    ex_alunos = (
        await ListarAlunos(alunos=alunos).executar(
            tenant_id=TENANT, apenas_ativos=False
        )
    ).itens
    assert [a.id for a in ex_alunos] == [aluno.id]


async def test_desativar_duas_vezes_nao_reescreve_a_data_de_saida():
    """O que interessa é quando o aluno saiu, não o último clique no botão."""
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )
    primeiro = await DesativarAluno(alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, motivo="Transferido"
    )
    segundo = await DesativarAluno(alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, motivo="Outro motivo"
    )
    assert segundo.desativado_em == primeiro.desativado_em
    assert segundo.motivo_desativacao == "Transferido"


async def test_reativar_desfaz_a_desativacao():
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )
    await DesativarAluno(alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, motivo="engano"
    )

    reativado = await ReativarAluno(alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    )

    assert reativado.ativo
    assert reativado.desativado_em is None
    assert reativado.motivo_desativacao == ""


async def test_desativar_aluno_de_outro_tenant_nao_encontra():
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )
    assert (
        await DesativarAluno(alunos=alunos).executar(
            tenant_id=uuid.uuid4(), aluno_id=aluno.id
        )
        is None
    )


# --------------------- exclusão de série (estratégias) --------------------- #
async def test_excluir_serie_com_alunos_exige_destino():
    """O caminho mais fácil da tela não pode destruir histórico: antes, excluir a série
    sem informar destino apagava os alunos dela junto."""
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )

    with pytest.raises(ValueError, match="destino"):
        await RemoverSala(salas=salas, alunos=alunos).executar(
            tenant_id=TENANT, sala_id=sala.id
        )

    # Nem a série nem os alunos foram tocados.
    assert await salas.obter(tenant_id=TENANT, sala_id=sala.id) is not None
    assert (await ListarAlunos(alunos=alunos).executar(tenant_id=TENANT)).total == 1


async def test_excluir_serie_vazia_dispensa_destino():
    alunos, _, salas = _repos()
    sala = await _sala(salas)

    assert await RemoverSala(salas=salas, alunos=alunos).executar(
        tenant_id=TENANT, sala_id=sala.id
    )
    assert await salas.obter(tenant_id=TENANT, sala_id=sala.id) is None


async def test_ex_aluno_tambem_bloqueia_a_exclusao_sem_destino():
    """O ex-aluno continua vinculado à série; apagá-la em silêncio o levaria junto."""
    alunos, _, salas = _repos()
    sala = await _sala(salas)
    aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Pedro", sala_id=sala.id
    )
    await DesativarAluno(alunos=alunos).executar(tenant_id=TENANT, aluno_id=aluno.id)

    with pytest.raises(ValueError, match="destino"):
        await RemoverSala(salas=salas, alunos=alunos).executar(
            tenant_id=TENANT, sala_id=sala.id
        )


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
