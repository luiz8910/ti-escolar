"""Testa grupos (disparo direcionado) e segurança de senha / permissões de admin."""

from __future__ import annotations

import uuid

import pytest

from app.application.admin_use_cases import (
    AdicionarContatoAoGrupo,
    CriarGrupo,
    CriarUsuario,
    EnviarBroadcastParaGrupo,
)
from app.application.use_cases import EnviarBroadcast
from app.domain.entities import (
    CategoriaTemplate,
    MessageTemplate,
    OrigemParametro,
    Papel,
    ParametroTemplate,
    StatusBroadcast,
    StatusTemplate,
    TemplateNaWaba,
    Tenant,
    Usuario,
)
from app.infrastructure.security import (
    criar_token,
    decodificar_token,
    hash_senha,
    verificar_senha,
)
from tests.fakes import (
    FakeBroadcastRepo,
    FakeChannel,
    FakeGrupoRepo,
    FakeQuota,
    FakeRateLimiter,
    FakeTemplateRepo,
    WABA_PADRAO_ID,
)

TENANT = uuid.uuid4()


class _FakeTenantRepo:
    """Só o que o disparo precisa: o nome da escola, para o `{{n}}` que a assina."""

    async def obter(self, tenant_id):
        return Tenant(id=tenant_id, nome="EM Rosa Cury", slug="rosacury")


def _template() -> MessageTemplate:
    return MessageTemplate(
        tenant_id=TENANT,
        nome="aviso",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}! {{2}}",
        wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
    )


# --------------------------- senha / hashing ------------------------------- #
def test_hash_de_senha_verifica_corretamente():
    h = hash_senha("escola123")
    assert h != "escola123"  # não armazena em texto puro
    assert verificar_senha("escola123", h)
    assert not verificar_senha("errada", h)


# --------------------------- token JWT ------------------------------------- #
def test_token_jwt_roundtrip():
    token = criar_token(
        {"sub": "u1", "email": "a@t.test"}, segredo="segredo", expira_em_segundos=60
    )
    payload = decodificar_token(token, segredo="segredo")
    assert payload is not None
    assert payload["sub"] == "u1"
    assert payload["email"] == "a@t.test"
    assert payload["exp"] > payload["iat"]


def test_token_jwt_rejeita_assinatura_invalida():
    token = criar_token({"email": "a@t.test"}, segredo="segredo", expira_em_segundos=60)
    # Segredo diferente → assinatura não confere.
    assert decodificar_token(token, segredo="outro") is None
    # Token adulterado também é rejeitado.
    assert decodificar_token(token + "x", segredo="segredo") is None
    assert decodificar_token("nao-e-um-jwt", segredo="segredo") is None


def test_token_jwt_rejeita_expirado():
    token = criar_token({"email": "a@t.test"}, segredo="segredo", expira_em_segundos=-1)
    assert decodificar_token(token, segredo="segredo") is None


# --------------------------- grupo -> broadcast ---------------------------- #
async def test_envio_para_grupo_resolve_membros():
    grupos = FakeGrupoRepo()
    criar = CriarGrupo(grupos=grupos)
    grupo = await criar.executar(tenant_id=TENANT, nome="Turma 5A")
    add = AdicionarContatoAoGrupo(grupos=grupos)
    await add.executar(tenant_id=TENANT, grupo_id=grupo.id, nome="Maria", telefone="+5511900000001")
    await add.executar(tenant_id=TENANT, grupo_id=grupo.id, nome="João", telefone="+5511900000002")

    template = _template()
    canal = FakeChannel()
    enviar = EnviarBroadcast(
        broadcasts=FakeBroadcastRepo(),
        templates=FakeTemplateRepo(template),
        canal=canal,
        quota=FakeQuota(limite_diario=1000),
        rate_limiter=FakeRateLimiter(),
    )
    uc = EnviarBroadcastParaGrupo(
        grupos=grupos,
        enviar=enviar,
        templates=FakeTemplateRepo(template),
        tenants=_FakeTenantRepo(),
    )

    resultado = await uc.executar(
        tenant_id=TENANT,
        grupo_id=grupo.id,
        template_id=template.id,
        titulo="Reunião",
        parametros=[
            ParametroTemplate(origem=OrigemParametro.RESPONSAVEL),
            ParametroTemplate(
                origem=OrigemParametro.TEXTO, texto="Reunião dia 20/06 às 19h"
            ),
        ],
    )

    assert resultado.total_contatos == 2
    assert resultado.broadcast.enviados == 2
    assert resultado.broadcast.status == StatusBroadcast.CONCLUIDO
    # Só os 2 contatos do grupo receberam.
    assert {c for c, _ in canal.enviados} == {"+5511900000001", "+5511900000002"}


async def test_envio_para_grupo_vazio_falha():
    grupos = FakeGrupoRepo()
    grupo = await CriarGrupo(grupos=grupos).executar(tenant_id=TENANT, nome="Vazio")
    template = _template()
    enviar = EnviarBroadcast(
        broadcasts=FakeBroadcastRepo(),
        templates=FakeTemplateRepo(template),
        canal=FakeChannel(),
        quota=FakeQuota(limite_diario=1000),
        rate_limiter=FakeRateLimiter(),
    )
    uc = EnviarBroadcastParaGrupo(
        grupos=grupos,
        enviar=enviar,
        templates=FakeTemplateRepo(template),
        tenants=_FakeTenantRepo(),
    )
    with pytest.raises(ValueError, match="sem contatos"):
        await uc.executar(
            tenant_id=TENANT,
            grupo_id=grupo.id,
            template_id=template.id,
            titulo="x",
            parametros=[],
        )


# --------------------------- permissões de admin --------------------------- #
class _FakeUsuarioRepo:
    def __init__(self):
        self.criados = []

    async def por_email(self, email):
        return None

    async def criar(self, usuario):
        self.criados.append(usuario)
        return usuario

    async def listar(self, *, tenant_id=None):
        return self.criados


async def test_admin_de_tenant_nao_cria_super_admin():
    repo = _FakeUsuarioRepo()
    admin_tenant = Usuario(
        nome="A", email="a@t.test", senha_hash="x", papel=Papel.TENANT_ADMIN, tenant_id=TENANT
    )
    uc = CriarUsuario(usuarios=repo)
    with pytest.raises(PermissionError):
        await uc.executar(
            criador=admin_tenant,
            nome="Hacker",
            email="h@t.test",
            senha="123",
            papel=Papel.SUPER_ADMIN,
            tenant_id=None,
        )


async def test_super_admin_cria_admin_de_tenant():
    repo = _FakeUsuarioRepo()
    super_admin = Usuario(
        nome="S", email="s@x.test", senha_hash="x", papel=Papel.SUPER_ADMIN, tenant_id=None
    )
    uc = CriarUsuario(usuarios=repo)
    novo = await uc.executar(
        criador=super_admin,
        nome="Admin Escola",
        email="admin@escola.test",
        senha="123",
        papel=Papel.TENANT_ADMIN,
        tenant_id=TENANT,
    )
    assert novo.papel == Papel.TENANT_ADMIN
    assert novo.tenant_id == TENANT


# ------------------- parâmetros do template no disparo --------------------- #
def _disparo(template: MessageTemplate, grupos):
    return EnviarBroadcastParaGrupo(
        grupos=grupos,
        enviar=EnviarBroadcast(
            broadcasts=FakeBroadcastRepo(),
            templates=FakeTemplateRepo(template),
            canal=FakeChannel(),
            quota=FakeQuota(limite_diario=1000),
            rate_limiter=FakeRateLimiter(),
        ),
        templates=FakeTemplateRepo(template),
        tenants=_FakeTenantRepo(),
    )


async def _grupo_com_um_contato():
    grupos = FakeGrupoRepo()
    grupo = await CriarGrupo(grupos=grupos).executar(tenant_id=TENANT, nome="Turma")
    await AdicionarContatoAoGrupo(grupos=grupos).executar(
        tenant_id=TENANT, grupo_id=grupo.id, nome="Maria", telefone="+5511900000001"
    )
    return grupos, grupo


async def test_contagem_de_parametros_diferente_do_corpo_e_recusada():
    """O bug que só aparecia na Graph API, depois de consumir a cota.

    O disparo mandava dois parâmetros fixos; o corpo do `aviso_reuniao` passou a ter três
    quando ganhou o nome da escola em `{{2}}`. A Meta recusa por contagem, destinatário a
    destinatário — e a falha chegava como "não entregue", não como erro de configuração.
    """
    grupos, grupo = await _grupo_com_um_contato()
    template = _template()  # corpo com {{1}} e {{2}}
    with pytest.raises(ValueError, match="2 variável"):
        await _disparo(template, grupos).executar(
            tenant_id=TENANT,
            grupo_id=grupo.id,
            template_id=template.id,
            titulo="Reunião",
            parametros=[ParametroTemplate(origem=OrigemParametro.TEXTO, texto="só um")],
        )


async def test_parametros_resolvem_responsavel_escola_e_texto():
    grupos, grupo = await _grupo_com_um_contato()
    template = MessageTemplate(
        tenant_id=TENANT,
        nome="aviso_reuniao",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}! A escola {{2}} informa: {{3}} Fale com a secretaria.",
        wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
    )
    canal = FakeChannel()
    uc = EnviarBroadcastParaGrupo(
        grupos=grupos,
        enviar=EnviarBroadcast(
            broadcasts=FakeBroadcastRepo(),
            templates=FakeTemplateRepo(template),
            canal=canal,
            quota=FakeQuota(limite_diario=1000),
            rate_limiter=FakeRateLimiter(),
        ),
        templates=FakeTemplateRepo(template),
        tenants=_FakeTenantRepo(),
    )
    await uc.executar(
        tenant_id=TENANT,
        grupo_id=grupo.id,
        template_id=template.id,
        titulo="Reunião",
        parametros=[
            ParametroTemplate(origem=OrigemParametro.RESPONSAVEL),
            ParametroTemplate(origem=OrigemParametro.ESCOLA),
            ParametroTemplate(origem=OrigemParametro.TEXTO, texto="a reunião é dia 20/08."),
        ],
    )
    assert canal.parametros_enviados[0] == [
        "Maria",
        "EM Rosa Cury",
        "a reunião é dia 20/08.",
    ]


async def test_template_de_outra_escola_nao_dispara():
    """`obter` já é escopado por tenant; aqui é a garantia de que o disparo usa esse caminho."""
    grupos, grupo = await _grupo_com_um_contato()
    template = _template()
    de_outra_escola = MessageTemplate(
        tenant_id=uuid.uuid4(),
        nome="alheio",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}! {{2}}",
        wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
    )
    uc = EnviarBroadcastParaGrupo(
        grupos=grupos,
        enviar=EnviarBroadcast(
            broadcasts=FakeBroadcastRepo(),
            templates=FakeTemplateRepo(template),
            canal=FakeChannel(),
            quota=FakeQuota(limite_diario=1000),
            rate_limiter=FakeRateLimiter(),
        ),
        templates=FakeTemplateRepo(template),
        tenants=_FakeTenantRepo(),
    )
    with pytest.raises(ValueError, match="não encontrado"):
        await uc.executar(
            tenant_id=TENANT,
            grupo_id=grupo.id,
            template_id=de_outra_escola.id,
            titulo="x",
            parametros=[],
        )
