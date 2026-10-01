"""Simulador local do WhatsApp (``/api/dev/whatsapp``).

O que importa garantir é **onde ele não existe**: é uma rota sem login que responde com
LLM, a mesma combinação que fez o demo Next.js ser removido.
"""

from __future__ import annotations

import uuid

from app.config import Settings
from app.interfaces.api.simulador import EscolasDoSimulador, simulador_habilitado


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_habilitado_so_em_desenvolvimento_com_canal_demo():
    assert simulador_habilitado(_settings(app_env="development", message_channel="demo"))


def test_desligado_em_producao_e_no_homolog():
    # O homolog também roda em `demo` (§9c) — e é público.
    assert not simulador_habilitado(_settings(app_env="production", message_channel="demo"))
    assert not simulador_habilitado(_settings(app_env="staging", message_channel="demo"))


def test_desligado_quando_o_canal_efetivo_e_a_meta():
    s = _settings(
        app_env="development",
        message_channel="meta",
        meta_access_token="tok",
        meta_phone_number_id="123",
    )
    assert not simulador_habilitado(s)


class _Tenants:
    def __init__(self) -> None:
        self.id = uuid.uuid4()

    async def obter(self, tenant_id):
        return "escola" if tenant_id == self.id else None

    async def por_meta_phone_number_id(self, phone_number_id):
        return "real" if phone_number_id == "999" else None


async def test_resolve_o_id_do_simulador_e_mantem_o_roteamento_real():
    tenants = _Tenants()
    escolas = EscolasDoSimulador(tenants)  # type: ignore[arg-type]

    assert await escolas.por_meta_phone_number_id(f"simulador:{tenants.id}") == "escola"
    assert await escolas.por_meta_phone_number_id(f"simulador:{uuid.uuid4()}") is None
    assert await escolas.por_meta_phone_number_id("simulador:lixo") is None
    assert await escolas.por_meta_phone_number_id("999") == "real"
