"""Testa o cadastro de pais/responsáveis e salas (turmas): CRUD, vínculo e relatório."""

from __future__ import annotations

import uuid

import pytest

from app.application.cadastro_use_cases import (
    AtualizarPai,
    AtualizarSala,
    CadastrarPai,
    CriarSala,
    DesvincularPaiDaSala,
    ListarPais,
    RelatorioPaisDaSala,
    RemoverPai,
    RemoverSala,
    VincularPaiASala,
)
from tests.fakes import FakeContatoRepo, FakeSalaRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


def _repos() -> tuple[FakeContatoRepo, FakeSalaRepo]:
    contatos = FakeContatoRepo()
    salas = FakeSalaRepo()
    salas.contatos = contatos  # o fake resolve pais por id ao vincular
    return contatos, salas


# --------------------------- pais (CRUD) ----------------------------------- #
async def test_cadastrar_pai_e_relacionar_com_sala():
    contatos, salas = _repos()
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")

    pai = await CadastrarPai(contatos=contatos, salas=salas).executar(
        tenant_id=TENANT,
        nome="Maria Souza",
        telefone="+5511999990001",
        sala_ids=[sala.id],
    )

    assert pai.nome == "Maria Souza"
    pais_da_sala = await RelatorioPaisDaSala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id
    )
    assert [c.id for c in pais_da_sala] == [pai.id]


async def test_telefone_duplicado_no_tenant_falha():
    contatos, salas = _repos()
    cadastrar = CadastrarPai(contatos=contatos, salas=salas)
    await cadastrar.executar(tenant_id=TENANT, nome="Maria", telefone="+5511999990001")
    with pytest.raises(ValueError, match="telefone"):
        await cadastrar.executar(tenant_id=TENANT, nome="Outra", telefone="+5511999990001")


async def test_mesmo_telefone_em_tenants_diferentes_e_permitido():
    contatos, salas = _repos()
    cadastrar = CadastrarPai(contatos=contatos, salas=salas)
    await cadastrar.executar(tenant_id=TENANT, nome="Maria", telefone="+5511999990001")
    # Não deve levantar: o telefone é único só dentro do tenant.
    await cadastrar.executar(tenant_id=OUTRO_TENANT, nome="Maria", telefone="+5511999990001")


async def test_atualizar_pai_mantendo_unicidade_de_telefone():
    contatos, salas = _repos()
    cadastrar = CadastrarPai(contatos=contatos, salas=salas)
    p1 = await cadastrar.executar(tenant_id=TENANT, nome="Maria", telefone="+5511999990001")
    await cadastrar.executar(tenant_id=TENANT, nome="João", telefone="+5511999990002")

    atualizar = AtualizarPai(contatos=contatos)
    atualizado = await atualizar.executar(
        tenant_id=TENANT, contato_id=p1.id, nome="Maria S.", telefone="+5511999990009"
    )
    assert atualizado.nome == "Maria S."
    assert atualizado.telefone == "+5511999990009"

    # Não pode assumir o telefone de outro responsável.
    with pytest.raises(ValueError, match="telefone"):
        await atualizar.executar(
            tenant_id=TENANT, contato_id=p1.id, nome="Maria S.", telefone="+5511999990002"
        )


async def test_remover_pai():
    contatos, salas = _repos()
    pai = await CadastrarPai(contatos=contatos, salas=salas).executar(
        tenant_id=TENANT, nome="Maria", telefone="+5511999990001"
    )
    assert await RemoverPai(contatos=contatos).executar(tenant_id=TENANT, contato_id=pai.id)
    assert await ListarPais(contatos=contatos).executar(tenant_id=TENANT) == []
    # Remover de novo retorna False.
    assert not await RemoverPai(contatos=contatos).executar(tenant_id=TENANT, contato_id=pai.id)


# --------------------------- salas (CRUD + vínculo) ------------------------ #
async def test_crud_e_vinculo_de_sala():
    contatos, salas = _repos()
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    sala = await AtualizarSala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, nome="4ª série B - Manhã", descricao="turma da manhã"
    )
    assert sala.nome == "4ª série B - Manhã"

    pai = await CadastrarPai(contatos=contatos, salas=salas).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511999990003"
    )
    await VincularPaiASala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, contato_id=pai.id
    )
    assert len(await RelatorioPaisDaSala(salas=salas).executar(tenant_id=TENANT, sala_id=sala.id)) == 1

    await DesvincularPaiDaSala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, contato_id=pai.id
    )
    assert await RelatorioPaisDaSala(salas=salas).executar(tenant_id=TENANT, sala_id=sala.id) == []

    assert await RemoverSala(salas=salas).executar(tenant_id=TENANT, sala_id=sala.id)


async def test_vincular_pai_de_outro_tenant_falha():
    contatos, salas = _repos()
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    # Pai cadastrado em outro tenant não pode ser vinculado a uma sala deste tenant.
    pai_outro = await CadastrarPai(contatos=contatos, salas=salas).executar(
        tenant_id=OUTRO_TENANT, nome="Intruso", telefone="+5511999990007"
    )
    with pytest.raises(ValueError):
        await VincularPaiASala(salas=salas).executar(
            tenant_id=TENANT, sala_id=sala.id, contato_id=pai_outro.id
        )
