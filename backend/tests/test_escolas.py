"""Testa o CRUD de escolas (tenants) e a visualização de conversas/broadcasts.

Usa fakes em memória das portas, sem BD nem framework (camada de aplicação pura).
"""

from __future__ import annotations

import uuid

import pytest

from app.application.tenant_use_cases import (
    AtualizarEscola,
    CriarEscola,
    ListarBroadcastsDaEscola,
    ListarConversasDaEscola,
    ObterConversaDaEscola,
    RemoverEscola,
    normalizar_whatsapp,
    slugify,
)
from app.domain.entities import (
    Autor,
    Broadcast,
    Conversa,
    DestinatarioBroadcast,
    Mensagem,
    Papel,
    ResumoConversa,
    ResumoEscola,
    Tenant,
    Usuario,
)


def _super() -> Usuario:
    return Usuario(
        nome="S", email="s@x.test", senha_hash="x", papel=Papel.SUPER_ADMIN, tenant_id=None
    )


def _admin(tenant_id: uuid.UUID) -> Usuario:
    return Usuario(
        nome="A", email="a@t.test", senha_hash="x", papel=Papel.TENANT_ADMIN, tenant_id=tenant_id
    )


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
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

    async def por_whatsapp(self, numero):
        if not numero:
            return None
        return next((t for t in self.tenants.values() if t.whatsapp_numero == numero), None)

    async def listar(self):
        return list(self.tenants.values())

    async def listar_resumos(self):
        return [ResumoEscola(tenant=t) for t in self.tenants.values()]

    async def atualizar(self, tenant: Tenant) -> Tenant:
        self.tenants[tenant.id] = tenant
        return tenant

    async def remover(self, tenant_id) -> bool:
        return self.tenants.pop(tenant_id, None) is not None


class FakeConversaView:
    def __init__(self, *, resumos=None, conversa=None, mensagens=None) -> None:
        self._resumos = resumos or []
        self._conversa = conversa
        self._mensagens = mensagens or []

    async def listar_resumos(self, *, tenant_id):
        return [r for r in self._resumos if r.conversa.tenant_id == tenant_id]

    async def obter_conversa(self, *, tenant_id, conversa_id):
        c = self._conversa
        if c and c.tenant_id == tenant_id and c.id == conversa_id:
            return c
        return None

    async def mensagens(self, *, conversa_id):
        return list(self._mensagens)


class FakeBroadcastView:
    def __init__(self, broadcasts) -> None:
        self._b = broadcasts

    async def listar(self, *, tenant_id):
        return [b for b in self._b if b.tenant_id == tenant_id]


# --------------------------------------------------------------------------- #
# slug
# --------------------------------------------------------------------------- #
def test_slugify_remove_acentos_e_espacos():
    assert slugify("Colégio São José") == "colegio-sao-jose"
    assert slugify("  Escola   Demo!! ") == "escola-demo"
    assert slugify("@@@") == "escola"


# --------------------------------------------------------------------------- #
# CRUD de escolas
# --------------------------------------------------------------------------- #
async def test_super_admin_cria_escola_com_slug_derivado():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Escola Nova")
    assert escola.slug == "escola-nova"
    assert await repo.por_slug("escola-nova") is escola


async def test_admin_de_tenant_nao_cria_escola():
    repo = FakeTenantRepo()
    with pytest.raises(PermissionError):
        await CriarEscola(tenants=repo).executar(criador=_admin(uuid.uuid4()), nome="Hack")


async def test_slug_duplicado_falha():
    repo = FakeTenantRepo()
    await CriarEscola(tenants=repo).executar(criador=_super(), nome="A", slug="repetido")
    with pytest.raises(ValueError, match="slug"):
        await CriarEscola(tenants=repo).executar(criador=_super(), nome="B", slug="repetido")


async def test_atualizar_escola_inexistente():
    repo = FakeTenantRepo()
    with pytest.raises(ValueError, match="não encontrada"):
        await AtualizarEscola(tenants=repo).executar(
            criador=_super(), tenant_id=uuid.uuid4(), nome="X"
        )


async def test_atualizar_mantem_data_de_criacao():
    repo = FakeTenantRepo()
    original = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Antiga")
    atualizada = await AtualizarEscola(tenants=repo).executar(
        criador=_super(), tenant_id=original.id, nome="Renomeada"
    )
    assert atualizada.nome == "Renomeada"
    assert atualizada.slug == "renomeada"
    assert atualizada.criado_em == original.criado_em


async def test_remover_escola():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(criador=_super(), nome="Some")
    assert await RemoverEscola(tenants=repo).executar(criador=_super(), tenant_id=escola.id) is True
    assert await RemoverEscola(tenants=repo).executar(criador=_super(), tenant_id=escola.id) is False


# --------------------------------------------------------------------------- #
# Número de WhatsApp por escola (multi-tenant)
# --------------------------------------------------------------------------- #
def test_normalizar_whatsapp():
    assert normalizar_whatsapp("") == ""
    assert normalizar_whatsapp("  ") == ""
    assert normalizar_whatsapp("whatsapp:+1 (415) 523-8886") == "+14155238886"
    assert normalizar_whatsapp("+55 11 98888-7777") == "+5511988887777"
    with pytest.raises(ValueError, match="inválido"):
        normalizar_whatsapp("123")


async def test_cria_escola_com_whatsapp_normalizado():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(
        criador=_super(), nome="Colégio A", whatsapp_numero="whatsapp:+14155238886"
    )
    assert escola.whatsapp_numero == "+14155238886"
    assert await repo.por_whatsapp("+14155238886") is escola


async def test_whatsapp_duplicado_entre_escolas_falha():
    repo = FakeTenantRepo()
    await CriarEscola(tenants=repo).executar(
        criador=_super(), nome="Escola 1", whatsapp_numero="+14155238886"
    )
    with pytest.raises(ValueError, match="já está vinculado"):
        await CriarEscola(tenants=repo).executar(
            criador=_super(), nome="Escola 2", whatsapp_numero="+1 415 523 8886"
        )


async def test_atualizar_mantem_proprio_whatsapp():
    repo = FakeTenantRepo()
    escola = await CriarEscola(tenants=repo).executar(
        criador=_super(), nome="Escola", whatsapp_numero="+14155238886"
    )
    # Reeditar a mesma escola com o mesmo número não deve conflitar consigo mesma.
    atualizada = await AtualizarEscola(tenants=repo).executar(
        criador=_super(),
        tenant_id=escola.id,
        nome="Escola Renomeada",
        whatsapp_numero="+14155238886",
    )
    assert atualizada.whatsapp_numero == "+14155238886"


# --------------------------------------------------------------------------- #
# Visualização de conversas e broadcasts
# --------------------------------------------------------------------------- #
async def test_listar_conversas_escopa_por_tenant():
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    c1 = Conversa(tenant_id=t1, contato="+5511900000001")
    c2 = Conversa(tenant_id=t2, contato="+5511900000002")
    repo = FakeConversaView(
        resumos=[
            ResumoConversa(conversa=c1, total_mensagens=3, ultima_mensagem="oi"),
            ResumoConversa(conversa=c2, total_mensagens=1),
        ]
    )
    out = await ListarConversasDaEscola(conversas=repo).executar(tenant_id=t1)
    assert [r.conversa.contato for r in out] == ["+5511900000001"]


async def test_obter_conversa_de_outro_tenant_retorna_none():
    t1 = uuid.uuid4()
    conversa = Conversa(tenant_id=t1, contato="+5511900000000")
    repo = FakeConversaView(
        conversa=conversa,
        mensagens=[Mensagem(conversa_id=conversa.id, autor=Autor.USUARIO, texto="Olá")],
    )
    uc = ObterConversaDaEscola(conversas=repo)
    assert await uc.executar(tenant_id=uuid.uuid4(), conversa_id=conversa.id) is None
    res = await uc.executar(tenant_id=t1, conversa_id=conversa.id)
    assert res is not None
    assert res.mensagens[0].texto == "Olá"


async def test_listar_broadcasts_escopa_por_tenant():
    t1, t2 = uuid.uuid4(), uuid.uuid4()
    b1 = Broadcast(
        tenant_id=t1,
        template_id=uuid.uuid4(),
        titulo="Reunião de pais",
        destinatarios=[DestinatarioBroadcast(contato="+5511900000001")],
    )
    b2 = Broadcast(tenant_id=t2, template_id=uuid.uuid4(), titulo="Outro")
    out = await ListarBroadcastsDaEscola(broadcasts=FakeBroadcastView([b1, b2])).executar(
        tenant_id=t1
    )
    assert len(out) == 1
    assert out[0].broadcast.titulo == "Reunião de pais"
