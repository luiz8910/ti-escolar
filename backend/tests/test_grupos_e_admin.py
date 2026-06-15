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
    Papel,
    StatusBroadcast,
    StatusTemplate,
    Usuario,
)
from app.infrastructure.security import hash_senha, verificar_senha
from tests.fakes import (
    FakeBroadcastRepo,
    FakeChannel,
    FakeGrupoRepo,
    FakeQuota,
    FakeRateLimiter,
    FakeTemplateRepo,
)

TENANT = uuid.uuid4()


def _template() -> MessageTemplate:
    return MessageTemplate(
        tenant_id=TENANT,
        nome="aviso",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}! {{2}}",
        status=StatusTemplate.APROVADO,
    )


# --------------------------- senha / hashing ------------------------------- #
def test_hash_de_senha_verifica_corretamente():
    h = hash_senha("escola123")
    assert h != "escola123"  # não armazena em texto puro
    assert verificar_senha("escola123", h)
    assert not verificar_senha("errada", h)


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
    uc = EnviarBroadcastParaGrupo(grupos=grupos, enviar=enviar)

    resultado = await uc.executar(
        tenant_id=TENANT,
        grupo_id=grupo.id,
        template_id=template.id,
        titulo="Reunião",
        mensagem="Reunião dia 20/06 às 19h",
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
    uc = EnviarBroadcastParaGrupo(grupos=grupos, enviar=enviar)
    with pytest.raises(ValueError, match="sem contatos"):
        await uc.executar(
            tenant_id=TENANT,
            grupo_id=grupo.id,
            template_id=template.id,
            titulo="x",
            mensagem="y",
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
