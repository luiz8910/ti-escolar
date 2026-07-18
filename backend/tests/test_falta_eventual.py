"""Testa o aviso de falta de professor e a chamada de eventual (§I1): registro,
disparo aos eventuais (pelo número da escola), confirmação, cancelamento e exceções.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.falta_use_cases import (
    CancelarFalta,
    ChamarEventual,
    ConfirmarEventual,
    ListarFaltas,
    RegistrarFaltaProfessor,
)
from app.domain.entities import Professor, StatusFalta, Tenant
from tests.fakes import (
    FakeAvisoFaltaRepo,
    FakeChannel,
    FakeProfessorRepo,
    FakeTenantRepo,
)

TENANT = uuid.uuid4()


async def _cenario():
    faltas = FakeAvisoFaltaRepo()
    professores = FakeProfessorRepo()
    prof = await professores.criar(
        Professor(tenant_id=TENANT, nome="Prof. Ana", telefone="+5511999990000")
    )
    tenants = FakeTenantRepo(
        [Tenant(id=TENANT, nome="EM Rosa Cury", slug="rosa-cury", whatsapp_numero="+5515333330000")]
    )
    return faltas, professores, prof, tenants


# --------------------------- sucesso --------------------------- #
async def test_registrar_falta_resolve_nome_do_professor():
    faltas, professores, prof, _ = await _cenario()
    aviso = await RegistrarFaltaProfessor(
        faltas=faltas, professores=professores
    ).executar(
        tenant_id=TENANT, data="2026-07-20", motivo="Consulta médica", professor_id=prof.id
    )
    assert aviso.professor_nome == "Prof. Ana"
    assert aviso.status == StatusFalta.ABERTA


async def test_chamar_eventual_notifica_pelo_numero_da_escola():
    faltas, professores, prof, tenants = await _cenario()
    aviso = await RegistrarFaltaProfessor(faltas=faltas, professores=professores).executar(
        tenant_id=TENANT, data="2026-07-20", professor_id=prof.id
    )
    canal = FakeChannel()
    atualizado = await ChamarEventual(
        faltas=faltas, canal=canal, tenants=tenants
    ).executar(
        tenant_id=TENANT,
        aviso_id=aviso.id,
        telefones=["+5511988880001", "+5511988880002"],
    )
    assert len(canal.enviados) == 2
    assert canal.remetente == "+5515333330000"
    assert atualizado.eventuais_chamados == ["+5511988880001", "+5511988880002"]
    assert atualizado.status == StatusFalta.ABERTA  # segue aberta até confirmar


async def test_confirmar_eventual_marca_coberta():
    faltas, professores, prof, _ = await _cenario()
    aviso = await RegistrarFaltaProfessor(faltas=faltas, professores=professores).executar(
        tenant_id=TENANT, data="2026-07-20", professor_id=prof.id
    )
    coberta = await ConfirmarEventual(faltas=faltas).executar(
        tenant_id=TENANT,
        aviso_id=aviso.id,
        eventual_nome="Prof. Beatriz",
        eventual_telefone="+5511988880001",
    )
    assert coberta.status == StatusFalta.COBERTA
    assert coberta.eventual_nome == "Prof. Beatriz"

    abertas = await ListarFaltas(faltas=faltas).executar(
        tenant_id=TENANT, status=StatusFalta.ABERTA
    )
    assert abertas == []


# --------------------------- exceções --------------------------- #
async def test_registrar_falta_sem_data_falha():
    faltas, professores, _, _ = await _cenario()
    with pytest.raises(ValueError):
        await RegistrarFaltaProfessor(faltas=faltas, professores=professores).executar(
            tenant_id=TENANT, data="  "
        )


async def test_registrar_falta_professor_inexistente_falha():
    faltas, professores, _, _ = await _cenario()
    with pytest.raises(ValueError):
        await RegistrarFaltaProfessor(faltas=faltas, professores=professores).executar(
            tenant_id=TENANT, data="2026-07-20", professor_id=uuid.uuid4()
        )


async def test_chamar_eventual_sem_telefones_falha():
    faltas, professores, prof, tenants = await _cenario()
    aviso = await RegistrarFaltaProfessor(faltas=faltas, professores=professores).executar(
        tenant_id=TENANT, data="2026-07-20", professor_id=prof.id
    )
    with pytest.raises(ValueError):
        await ChamarEventual(faltas=faltas, canal=FakeChannel(), tenants=tenants).executar(
            tenant_id=TENANT, aviso_id=aviso.id, telefones=["", "   "]
        )


async def test_chamar_eventual_falta_inexistente_falha():
    faltas, _, _, tenants = await _cenario()
    with pytest.raises(ValueError):
        await ChamarEventual(faltas=faltas, canal=FakeChannel(), tenants=tenants).executar(
            tenant_id=TENANT, aviso_id=uuid.uuid4(), telefones=["+5511988880001"]
        )


async def test_chamar_eventual_para_falta_cancelada_falha():
    faltas, professores, prof, tenants = await _cenario()
    aviso = await RegistrarFaltaProfessor(faltas=faltas, professores=professores).executar(
        tenant_id=TENANT, data="2026-07-20", professor_id=prof.id
    )
    await CancelarFalta(faltas=faltas).executar(tenant_id=TENANT, aviso_id=aviso.id)
    with pytest.raises(ValueError):
        await ChamarEventual(faltas=faltas, canal=FakeChannel(), tenants=tenants).executar(
            tenant_id=TENANT, aviso_id=aviso.id, telefones=["+5511988880001"]
        )
