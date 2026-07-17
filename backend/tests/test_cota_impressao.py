"""Testa a cota (franquia mensal) e o relatório de impressões por professor (§B2):
upsert de cota, relatório agregado por competência, marcação de excedente e filtragem
de canceladas/outro mês.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.application.impressao_use_cases import (
    DefinirCotaImpressao,
    ListarCotasImpressao,
    RelatorioImpressaoMensal,
    RemoverCotaImpressao,
)
from app.domain.entities import Professor, SolicitacaoImpressao, StatusImpressao
from tests.fakes import (
    FakeCotaImpressaoRepo,
    FakeProfessorRepo,
    FakeSolicitacaoImpressaoRepo,
)

TENANT = uuid.uuid4()


def _sol(professor, *, copias, mes="2026-07", status=StatusImpressao.CONCLUIDA):
    criado = datetime.fromisoformat(f"{mes}-10T12:00:00+00:00")
    return SolicitacaoImpressao(
        tenant_id=TENANT,
        arquivo_nome="a.pdf",
        professor_id=professor.id,
        professor_nome=professor.nome,
        copias=copias,
        status=status,
        criado_em=criado,
        atualizado_em=criado,
    )


async def test_definir_cota_upsert_e_validacao():
    cotas = FakeCotaImpressaoRepo()
    professores = FakeProfessorRepo()
    prof = await professores.criar(
        Professor(tenant_id=TENANT, nome="Prof. Ana", telefone="+5511999990000")
    )

    definir = DefinirCotaImpressao(cotas=cotas, professores=professores)
    c1 = await definir.executar(tenant_id=TENANT, professor_id=prof.id, limite_mensal=3000)
    assert c1.limite_mensal == 3000
    assert c1.professor_nome == "Prof. Ana"

    # Upsert: redefinir não cria duplicata.
    await definir.executar(tenant_id=TENANT, professor_id=prof.id, limite_mensal=5000)
    todas = await cotas.listar(tenant_id=TENANT)
    assert len(todas) == 1
    assert todas[0].limite_mensal == 5000

    with pytest.raises(ValueError):
        await definir.executar(
            tenant_id=TENANT, professor_id=uuid.uuid4(), limite_mensal=100
        )


async def test_limite_negativo_vira_ilimitado():
    cotas = FakeCotaImpressaoRepo()
    professores = FakeProfessorRepo()
    prof = await professores.criar(
        Professor(tenant_id=TENANT, nome="Prof. Ana", telefone="+5511999990000")
    )
    c = await DefinirCotaImpressao(cotas=cotas, professores=professores).executar(
        tenant_id=TENANT, professor_id=prof.id, limite_mensal=-5
    )
    assert c.limite_mensal == 0
    assert c.ilimitado is True


async def test_relatorio_agrega_e_marca_excedente():
    solicitacoes = FakeSolicitacaoImpressaoRepo()
    cotas = FakeCotaImpressaoRepo()
    professores = FakeProfessorRepo()
    ana = await professores.criar(
        Professor(tenant_id=TENANT, nome="Ana", telefone="+5511111110000")
    )
    bruno = await professores.criar(
        Professor(tenant_id=TENANT, nome="Bruno", telefone="+5511222220000")
    )

    # Ana: 3000 + 500 = 3500 cópias em julho; cota 3000 → excedeu.
    await solicitacoes.criar(_sol(ana, copias=3000))
    await solicitacoes.criar(_sol(ana, copias=500))
    # Uma cancelada não conta.
    await solicitacoes.criar(_sol(ana, copias=9999, status=StatusImpressao.CANCELADA))
    # De outro mês não conta.
    await solicitacoes.criar(_sol(ana, copias=1000, mes="2026-06"))
    # Bruno: 100 cópias, cota 3000 → não excedeu.
    await solicitacoes.criar(_sol(bruno, copias=100))

    await DefinirCotaImpressao(cotas=cotas, professores=professores).executar(
        tenant_id=TENANT, professor_id=ana.id, limite_mensal=3000
    )
    await DefinirCotaImpressao(cotas=cotas, professores=professores).executar(
        tenant_id=TENANT, professor_id=bruno.id, limite_mensal=3000
    )

    relatorio = await RelatorioImpressaoMensal(
        solicitacoes=solicitacoes, cotas=cotas, professores=professores
    ).executar(tenant_id=TENANT, competencia="2026-07")

    por_nome = {linha.professor_nome: linha for linha in relatorio.linhas}
    assert por_nome["Ana"].total_copias == 3500
    assert por_nome["Ana"].total_solicitacoes == 2
    assert por_nome["Ana"].excedeu is True
    assert por_nome["Bruno"].total_copias == 100
    assert por_nome["Bruno"].excedeu is False
    assert relatorio.total_copias == 3600


async def test_relatorio_inclui_professor_com_cota_sem_consumo():
    solicitacoes = FakeSolicitacaoImpressaoRepo()
    cotas = FakeCotaImpressaoRepo()
    professores = FakeProfessorRepo()
    ana = await professores.criar(
        Professor(tenant_id=TENANT, nome="Ana", telefone="+5511111110000")
    )
    await DefinirCotaImpressao(cotas=cotas, professores=professores).executar(
        tenant_id=TENANT, professor_id=ana.id, limite_mensal=3000
    )
    relatorio = await RelatorioImpressaoMensal(
        solicitacoes=solicitacoes, cotas=cotas, professores=professores
    ).executar(tenant_id=TENANT, competencia="2026-07")
    assert len(relatorio.linhas) == 1
    assert relatorio.linhas[0].total_copias == 0
    assert relatorio.linhas[0].restante == 3000


async def test_remover_cota():
    cotas = FakeCotaImpressaoRepo()
    professores = FakeProfessorRepo()
    prof = await professores.criar(
        Professor(tenant_id=TENANT, nome="Ana", telefone="+5511111110000")
    )
    await DefinirCotaImpressao(cotas=cotas, professores=professores).executar(
        tenant_id=TENANT, professor_id=prof.id, limite_mensal=3000
    )
    assert await RemoverCotaImpressao(cotas=cotas).executar(
        tenant_id=TENANT, professor_id=prof.id
    )
    assert await cotas.por_professor(tenant_id=TENANT, professor_id=prof.id) is None
    # Listagem resolve nomes mesmo vazia.
    assert await ListarCotasImpressao(cotas=cotas, professores=professores).executar(
        tenant_id=TENANT
    ) == []
