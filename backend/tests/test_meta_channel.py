"""Outbound multi-tenant: o ``MetaMessageChannel`` honra o ``remetente`` (§9e.1).

Na Graph API o número de origem **é o caminho da URL** (``/{phone_number_id}/messages``),
não um campo do corpo. Antes o adaptador fixava o id da env no construtor e ignorava o
``remetente``, de modo que toda escola disparava pelo mesmo número. Aqui se testa a
montagem da URL e a resolução do broadcast ponta a ponta, sem rede.
"""

from __future__ import annotations

import uuid

from app.application.use_cases import EnviarBroadcast
from app.domain.entities import (
    Broadcast,
    CategoriaTemplate,
    DestinatarioBroadcast,
    MessageTemplate,
    StatusTemplate,
    Tenant,
)
from app.infrastructure.channel.meta_channel import MetaMessageChannel
from tests.fakes import FakeQuota, FakeRateLimiter

PADRAO = "000000000000000"
PID_ESCOLA = "123456789012345"


def _canal() -> MetaMessageChannel:
    return MetaMessageChannel(phone_number_id=PADRAO, access_token="token-de-teste")


# --------------------------------------------------------------------------- #
# Montagem da URL de envio
# --------------------------------------------------------------------------- #
def test_remetente_da_escola_define_o_numero_de_origem():
    assert _canal()._origem(PID_ESCOLA) == PID_ESCOLA


def test_sem_remetente_cai_no_numero_padrao_da_env():
    for vazio in (None, "", "   "):
        assert _canal()._origem(vazio) == PADRAO


def test_e164_nao_vira_caminho_de_url():
    """Escola sem ``meta_phone_number_id``: o E.164 não é aceito pela Graph API."""
    assert _canal()._origem("+5511988887777") == PADRAO


# --------------------------------------------------------------------------- #
# Resolução ponta a ponta no broadcast
# --------------------------------------------------------------------------- #
class _CanalEspiao:
    def __init__(self) -> None:
        self.remetentes: list[str | None] = []

    async def enviar_texto(self, *, contato, texto, remetente=None) -> str:
        return "x"

    async def enviar_template(self, *, contato, template, parametros, remetente=None) -> str:
        self.remetentes.append(remetente)
        return f"wamid.{contato}"

    async def enviar_documento(self, *, contato, documento, remetente=None) -> str:
        return "x"


class _TenantRepo:
    def __init__(self, tenant: Tenant) -> None:
        self._t = tenant

    async def obter(self, tenant_id):
        return self._t if self._t.id == tenant_id else None


class _TemplateRepo:
    def __init__(self, template: MessageTemplate) -> None:
        self._t = template

    async def obter(self, *, tenant_id, template_id):
        return self._t


class _BroadcastRepo:
    async def salvar(self, broadcast):
        return broadcast


async def _disparar(escola: Tenant) -> _CanalEspiao:
    template = MessageTemplate(
        tenant_id=escola.id,
        nome="aviso_geral",
        categoria=CategoriaTemplate.UTILITY,
        corpo="Olá, {{1}}!",
        idioma="pt_BR",
        status=StatusTemplate.APROVADO,
    )
    broadcast = Broadcast(
        tenant_id=escola.id,
        titulo="Aviso de reunião",
        template_id=template.id,
        destinatarios=[DestinatarioBroadcast(contato="+5511900000001")],
    )
    canal = _CanalEspiao()
    await EnviarBroadcast(
        broadcasts=_BroadcastRepo(),
        templates=_TemplateRepo(template),
        canal=canal,
        quota=FakeQuota(limite_diario=100),
        rate_limiter=FakeRateLimiter(),
        tenants=_TenantRepo(escola),
    ).executar(broadcast=broadcast)
    return canal


async def test_broadcast_sai_pelo_phone_number_id_da_escola():
    escola = Tenant(
        id=uuid.uuid4(),
        nome="EM Rosa Cury",
        slug="rosa-cury",
        whatsapp_numero="+5515333330000",
        meta_phone_number_id=PID_ESCOLA,
    )
    canal = await _disparar(escola)
    assert canal.remetentes == [PID_ESCOLA]


async def test_broadcast_de_escola_sem_id_na_meta_usa_o_e164():
    escola = Tenant(
        id=uuid.uuid4(), nome="Escola", slug="escola", whatsapp_numero="+5515333330000"
    )
    canal = await _disparar(escola)
    assert canal.remetentes == ["+5515333330000"]
