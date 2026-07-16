"""Licenciamento/cobrança/bloqueio de escolas (tenants).

Casos de uso puros (sem BD/framework) com fakes em memória das portas.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.application.tenant_use_cases import (
    AtualizarEscola,
    BloquearEscola,
    CriarEscola,
    DefinirLicenca,
    DesbloquearEscola,
    NotificarLicencasAVencer,
)
from app.domain.entities import (
    PlanoTenant,
    StatusTenant,
    Tenant,
    Usuario,
)
from app.domain.entities import Papel

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


class FakeUsuarioRepo:
    def __init__(self, usuarios: list[Usuario] | None = None) -> None:
        self.usuarios = list(usuarios or [])

    async def por_email(self, email):
        return next((u for u in self.usuarios if u.email == email.lower()), None)

    async def criar(self, usuario):
        self.usuarios.append(usuario)
        return usuario

    async def listar(self, *, tenant_id=None):
        if tenant_id is None:
            return list(self.usuarios)
        return [u for u in self.usuarios if u.tenant_id == tenant_id]


class FakeEmailSender:
    def __init__(self) -> None:
        self.enviados: list[dict] = []

    async def enviar(self, *, destinatario, assunto, corpo):
        self.enviados.append({"para": destinatario, "assunto": assunto, "corpo": corpo})


# --------------------------------------------------------------------------- #
# Bloqueio / desbloqueio
# --------------------------------------------------------------------------- #
async def test_super_admin_bloqueia_e_registra_motivo():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)

    bloqueada = await BloquearEscola(tenants=repo).executar(
        criador=_super(), tenant_id=escola.id, motivo="Inadimplência"
    )
    assert bloqueada.status == StatusTenant.BLOQUEADO
    assert bloqueada.bloqueado is True
    assert bloqueada.motivo_bloqueio == "Inadimplência"
    assert bloqueada.bloqueado_em is not None


async def test_bloqueio_exige_motivo():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    with pytest.raises(ValueError, match="motivo"):
        await BloquearEscola(tenants=repo).executar(
            criador=_super(), tenant_id=escola.id, motivo="   "
        )


async def test_admin_de_tenant_nao_bloqueia():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    with pytest.raises(PermissionError):
        await BloquearEscola(tenants=repo).executar(
            criador=_admin(escola.id), tenant_id=escola.id, motivo="hack"
        )


async def test_desbloquear_limpa_estado():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    await BloquearEscola(tenants=repo).executar(
        criador=_super(), tenant_id=escola.id, motivo="x"
    )
    ativa = await DesbloquearEscola(tenants=repo).executar(criador=_super(), tenant_id=escola.id)
    assert ativa.status == StatusTenant.ATIVO
    assert ativa.motivo_bloqueio == ""
    assert ativa.bloqueado_em is None


# --------------------------------------------------------------------------- #
# Licença: plano, expiração e preservação ao renomear
# --------------------------------------------------------------------------- #
async def test_definir_licenca_anual_com_expiracao():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    expira = _now() + timedelta(days=10)
    out = await DefinirLicenca(tenants=repo).executar(
        criador=_super(), tenant_id=escola.id, plano=PlanoTenant.ANUAL, licenca_expira_em=expira
    )
    assert out.plano == PlanoTenant.ANUAL
    assert out.dias_para_expirar == 10
    assert out.licenca_expirada is False
    assert out.licenca_a_vencer(30) is True


async def test_licenca_expirada():
    t = Tenant(
        nome="X",
        slug="x",
        plano=PlanoTenant.ANUAL,
        licenca_expira_em=_now() - timedelta(days=1),
    )
    assert t.licenca_expirada is True
    assert t.dias_para_expirar == -1
    assert t.licenca_a_vencer(30) is False


async def test_renomear_preserva_licenciamento():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola X", telefone_contato=_CONTATO)
    await DefinirLicenca(tenants=repo).executar(
        criador=_super(),
        tenant_id=escola.id,
        plano=PlanoTenant.ANUAL,
        licenca_expira_em=_now() + timedelta(days=5),
    )
    await BloquearEscola(tenants=repo).executar(
        criador=_super(), tenant_id=escola.id, motivo="pagamento"
    )
    renomeada = await AtualizarEscola(tenants=repo).executar(
        criador=_super(), tenant_id=escola.id, nome="Escola Renomeada", telefone_contato=_CONTATO
    )
    assert renomeada.nome == "Escola Renomeada"
    assert renomeada.status == StatusTenant.BLOQUEADO
    assert renomeada.motivo_bloqueio == "pagamento"
    assert renomeada.plano == PlanoTenant.ANUAL


# --------------------------------------------------------------------------- #
# Aviso de vencimento por e-mail
# --------------------------------------------------------------------------- #
async def test_notifica_apenas_anual_a_vencer():
    repo = FakeTenantRepo()
    a_vencer = await CriarEscola(tenants=repo).executar(criador=_super(), nome="A Vencer", telefone_contato=_CONTATO)
    await DefinirLicenca(tenants=repo).executar(
        criador=_super(),
        tenant_id=a_vencer.id,
        plano=PlanoTenant.ANUAL,
        licenca_expira_em=_now() + timedelta(days=7),
    )
    # Mensal dentro da janela: não deve notificar.
    mensal = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Mensal", telefone_contato=_CONTATO)
    await DefinirLicenca(tenants=repo).executar(
        criador=_super(),
        tenant_id=mensal.id,
        plano=PlanoTenant.MENSAL,
        licenca_expira_em=_now() + timedelta(days=7),
    )
    # Anual longe do vencimento: não deve notificar.
    longe = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Longe", telefone_contato=_CONTATO)
    await DefinirLicenca(tenants=repo).executar(
        criador=_super(),
        tenant_id=longe.id,
        plano=PlanoTenant.ANUAL,
        licenca_expira_em=_now() + timedelta(days=200),
    )

    usuarios = FakeUsuarioRepo(
        [
            _admin(a_vencer.id),
            Usuario(
                nome="Inativo",
                email="inativo@a.test",
                senha_hash="x",
                papel=Papel.TENANT_ADMIN,
                tenant_id=a_vencer.id,
                ativo=False,
            ),
        ]
    )
    emails = FakeEmailSender()
    avisos = await NotificarLicencasAVencer(
        tenants=repo, usuarios=usuarios, emails=emails
    ).executar(dias_aviso=30)

    assert [a.tenant.nome for a in avisos] == ["A Vencer"]
    # Só o admin ativo recebe.
    assert [e["para"] for e in emails.enviados] == ["a@t.test"]
    assert "7 dia" in emails.enviados[0]["assunto"]
