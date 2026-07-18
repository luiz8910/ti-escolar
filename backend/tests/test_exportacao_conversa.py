"""Testa a exportação de conversa para fins legais (§H1): documento formatado com
cabeçalho institucional, recorte por período e erro quando a conversa não existe.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.application.exportacao_use_cases import ExportarConversaLegal
from app.domain.entities import Autor, Conversa, Mensagem, Tenant
from tests.fakes import FakeConversaExportRepo, FakeTenantRepo

TENANT = uuid.uuid4()


def _dt(dia: int) -> datetime:
    return datetime(2026, 7, dia, 10, 0, tzinfo=timezone.utc)


async def _cenario():
    conversas = FakeConversaExportRepo()
    conversa = Conversa(tenant_id=TENANT, contato="+5511999990000")
    mensagens = [
        Mensagem(conversa_id=conversa.id, autor=Autor.USUARIO, texto="Bom dia", criado_em=_dt(10)),
        Mensagem(
            conversa_id=conversa.id,
            autor=Autor.BOT,
            texto="Olá, como podemos ajudar?",
            criado_em=_dt(11),
            fontes=["Horário da secretaria"],
        ),
        Mensagem(conversa_id=conversa.id, autor=Autor.USUARIO, texto="Obrigada", criado_em=_dt(20)),
    ]
    conversas.registrar_conversa(conversa, mensagens)
    tenants = FakeTenantRepo([Tenant(id=TENANT, nome="EM Rosa Cury", slug="rosa-cury")])
    return conversas, conversa, tenants


async def test_exportar_conversa_completa():
    conversas, conversa, tenants = await _cenario()
    exportada = await ExportarConversaLegal(conversas=conversas, tenants=tenants).executar(
        tenant_id=TENANT, conversa_id=conversa.id
    )
    assert exportada.total_mensagens == 3
    assert "EM Rosa Cury" in exportada.documento
    assert "+5511999990000" in exportada.documento
    assert "Responsável" in exportada.documento
    assert "Escola (assistente)" in exportada.documento
    assert "Horário da secretaria" in exportada.documento  # fontes citadas


async def test_exportar_conversa_recorta_por_periodo():
    conversas, conversa, tenants = await _cenario()
    exportada = await ExportarConversaLegal(conversas=conversas, tenants=tenants).executar(
        tenant_id=TENANT,
        conversa_id=conversa.id,
        inicio=_dt(9),
        fim=_dt(12),
    )
    # A terceira mensagem (dia 20) fica fora do recorte.
    assert exportada.total_mensagens == 2
    assert "Obrigada" not in exportada.documento


async def test_exportar_conversa_inexistente_falha():
    conversas, _, tenants = await _cenario()
    with pytest.raises(ValueError):
        await ExportarConversaLegal(conversas=conversas, tenants=tenants).executar(
            tenant_id=TENANT, conversa_id=uuid.uuid4()
        )


async def test_exportar_conversa_de_outro_tenant_falha():
    conversas, conversa, tenants = await _cenario()
    with pytest.raises(ValueError):
        await ExportarConversaLegal(conversas=conversas, tenants=tenants).executar(
            tenant_id=uuid.uuid4(), conversa_id=conversa.id
        )
