"""Ficha financeira/histórico da escola: cancelamento (churn), preços e derivações.

Casos de uso puros (sem BD/framework) com fakes em memória das portas.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.application.tenant_use_cases import (
    CancelarEscola,
    CriarEscola,
    DefinirLicenca,
    ObterFichaFinanceira,
    ReativarEscola,
)
from app.domain.entities import (
    MetricasUsoEscola,
    Papel,
    PlanoTenant,
    StatusPagamento,
    StatusTenant,
    Tenant,
    Usuario,
)

# Telefone de contato válido (o campo é obrigatório ao criar/atualizar escolas).
_CONTATO = "+5511999990001"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _super() -> Usuario:
    return Usuario(
        nome="S", email="s@x.test", senha_hash="x", papel=Papel.SUPER_ADMIN, tenant_id=None
    )


def _admin(tenant_id: uuid.UUID) -> Usuario:
    return Usuario(
        nome="A", email="a@t.test", senha_hash="x", papel=Papel.TENANT_ADMIN, tenant_id=tenant_id
    )


class FakeTenantRepo:
    def __init__(self) -> None:
        self.tenants: dict[uuid.UUID, Tenant] = {}
        self.metricas: dict[uuid.UUID, MetricasUsoEscola] = {}

    async def criar(self, tenant: Tenant) -> Tenant:
        self.tenants[tenant.id] = tenant
        return tenant

    async def obter(self, tenant_id):
        return self.tenants.get(tenant_id)

    async def por_slug(self, slug):
        return next((t for t in self.tenants.values() if t.slug == slug), None)

    async def listar(self):
        return list(self.tenants.values())

    async def atualizar(self, tenant: Tenant) -> Tenant:
        self.tenants[tenant.id] = tenant
        return tenant

    async def metricas_uso(self, tenant_id) -> MetricasUsoEscola:
        return self.metricas.get(tenant_id, MetricasUsoEscola())


# --------------------------------------------------------------------------- #
# Cancelamento (churn) / reativação
# --------------------------------------------------------------------------- #
async def test_cancelar_registra_data_e_motivo():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)

    cancelada = await CancelarEscola(tenants=repo).executar(
        criador=_super(), tenant_id=escola.id, motivo="Encerrou o contrato"
    )
    assert cancelada.status == StatusTenant.CANCELADO
    assert cancelada.cancelado is True
    assert cancelada.acesso_suspenso is True
    assert cancelada.motivo_cancelamento == "Encerrou o contrato"
    assert cancelada.cancelado_em is not None
    assert cancelada.motivo_suspensao == "Encerrou o contrato"


async def test_cancelamento_exige_motivo():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    with pytest.raises(ValueError, match="motivo"):
        await CancelarEscola(tenants=repo).executar(
            criador=_super(), tenant_id=escola.id, motivo="  "
        )


async def test_admin_de_tenant_nao_cancela():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    with pytest.raises(PermissionError):
        await CancelarEscola(tenants=repo).executar(
            criador=_admin(escola.id), tenant_id=escola.id, motivo="hack"
        )


async def test_reativar_limpa_cancelamento():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    await CancelarEscola(tenants=repo).executar(
        criador=_super(), tenant_id=escola.id, motivo="x"
    )
    ativa = await ReativarEscola(tenants=repo).executar(criador=_super(), tenant_id=escola.id)
    assert ativa.status == StatusTenant.ATIVO
    assert ativa.cancelado is False
    assert ativa.motivo_cancelamento == ""
    assert ativa.cancelado_em is None


# --------------------------------------------------------------------------- #
# Preços / MRR / ARR
# --------------------------------------------------------------------------- #
async def test_definir_precos_e_mrr_arr_mensal():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    out = await DefinirLicenca(tenants=repo).executar(
        criador=_super(),
        tenant_id=escola.id,
        plano=PlanoTenant.MENSAL,
        licenca_expira_em=None,
        valor_mensal_centavos=29900,
        valor_anual_centavos=299000,
    )
    assert out.valor_mensal_centavos == 29900
    assert out.mrr_centavos == 29900
    assert out.arr_centavos == 29900 * 12


async def test_mrr_no_plano_anual_normaliza_por_doze():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    out = await DefinirLicenca(tenants=repo).executar(
        criador=_super(),
        tenant_id=escola.id,
        plano=PlanoTenant.ANUAL,
        licenca_expira_em=None,
        valor_anual_centavos=120000,
    )
    assert out.plano == PlanoTenant.ANUAL
    assert out.mrr_centavos == 10000  # 120000 / 12
    assert out.arr_centavos == 120000


async def test_definir_licenca_preserva_precos_quando_omitidos():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    await DefinirLicenca(tenants=repo).executar(
        criador=_super(),
        tenant_id=escola.id,
        plano=PlanoTenant.MENSAL,
        licenca_expira_em=None,
        valor_mensal_centavos=15000,
    )
    # Novo ajuste só de plano/expiração não zera o preço cadastrado.
    out = await DefinirLicenca(tenants=repo).executar(
        criador=_super(),
        tenant_id=escola.id,
        plano=PlanoTenant.ANUAL,
        licenca_expira_em=None,
    )
    assert out.valor_mensal_centavos == 15000


async def test_preco_negativo_recusado():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    with pytest.raises(ValueError, match="negativo"):
        await DefinirLicenca(tenants=repo).executar(
            criador=_super(),
            tenant_id=escola.id,
            plano=PlanoTenant.MENSAL,
            licenca_expira_em=None,
            valor_mensal_centavos=-1,
        )


# --------------------------------------------------------------------------- #
# Ficha financeira (derivações)
# --------------------------------------------------------------------------- #
async def test_ficha_consolida_uso_e_financas():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    # Início há ~3 meses (90 dias).
    escola.criado_em = _now() - timedelta(days=90)
    await DefinirLicenca(tenants=repo).executar(
        criador=_super(),
        tenant_id=escola.id,
        plano=PlanoTenant.MENSAL,
        licenca_expira_em=_now() + timedelta(days=20),
        valor_mensal_centavos=29900,
    )
    repo.metricas[escola.id] = MetricasUsoEscola(
        total_usuarios_ativos=2, total_contatos=10, total_alunos=8, total_conversas=5,
        total_broadcasts=3,
    )

    ficha = await ObterFichaFinanceira(tenants=repo).executar(
        solicitante=_super(), tenant_id=escola.id, limite_diario_meta=1000
    )
    assert ficha is not None
    assert ficha.meses_ativos == 3
    assert ficha.receita_acumulada_centavos == 3 * 29900
    assert ficha.uso.total_alunos == 8
    assert ficha.status_pagamento == StatusPagamento.EM_DIA
    assert ficha.health_score == 100


async def test_ficha_health_score_penaliza_bloqueio_e_tier_baixo():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    escola.status = StatusTenant.BLOQUEADO
    await repo.atualizar(escola)

    ficha = await ObterFichaFinanceira(tenants=repo).executar(
        solicitante=_super(), tenant_id=escola.id, limite_diario_meta=500
    )
    assert ficha is not None
    assert ficha.status_pagamento == StatusPagamento.INADIMPLENTE
    # -50 (bloqueio) -10 (tier < 1000) = 40.
    assert ficha.health_score == 40


async def test_ficha_cancelada_zera_health_score():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    await CancelarEscola(tenants=repo).executar(
        criador=_super(), tenant_id=escola.id, motivo="saiu"
    )
    ficha = await ObterFichaFinanceira(tenants=repo).executar(
        solicitante=_super(), tenant_id=escola.id, limite_diario_meta=-1
    )
    assert ficha is not None
    assert ficha.health_score == 0
    assert ficha.status_pagamento == StatusPagamento.CANCELADO


async def test_ficha_exige_super_admin():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    with pytest.raises(PermissionError):
        await ObterFichaFinanceira(tenants=repo).executar(
            solicitante=_admin(escola.id), tenant_id=escola.id, limite_diario_meta=1000
        )
