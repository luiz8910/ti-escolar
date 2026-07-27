"""Rotas sem login: nenhuma delas pode aceitar um ``tenant_id`` arbitrário.

Estes testes existem por causa de um furo real: `POST /api/broadcasts` não exigia
autenticação e recebia o ``tenant_id`` no corpo — quem soubesse a URL pública disparava
WhatsApp aos responsáveis de qualquer escola, pelo número dela, queimando a cota diária.
São testes de **borda HTTP** (o resto da suíte é de casos de uso) porque o que se verifica
aqui é exatamente o que o roteador exige antes de chegar ao caso de uso.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.interfaces.api.chat import _demo_liberado
from app.main import app

DEMO_TENANT = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _broadcast_payload(tenant_id: str) -> dict:
    return {
        "tenant_id": tenant_id,
        "template_id": str(uuid4()),
        "titulo": "Reunião de pais",
        "destinatarios": [{"contato": "+5511988887777", "parametros": []}],
    }


# --------------------------------------------------------------------------- #
# Broadcasts — exigem login
# --------------------------------------------------------------------------- #


def test_disparar_broadcast_sem_token_e_recusado(client: TestClient):
    resp = client.post("/api/broadcasts", json=_broadcast_payload(str(uuid4())))
    assert resp.status_code == 401


def test_disparar_broadcast_com_token_invalido_e_recusado(client: TestClient):
    resp = client.post(
        "/api/broadcasts",
        json=_broadcast_payload(str(uuid4())),
        headers={"Authorization": "Bearer token-forjado"},
    )
    assert resp.status_code == 401


def test_consultar_quota_sem_token_e_recusado(client: TestClient):
    """A cota revela o consumo de uma escola — não é dado público."""
    resp = client.get(f"/api/broadcasts/quota/{uuid4()}")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Chat demo — público, porém preso ao tenant de vitrine
# --------------------------------------------------------------------------- #


def test_chat_demo_recusa_tenant_que_nao_e_o_de_vitrine(client: TestClient):
    """Sem isso o demo grava conversa e gasta LLM de uma escola real."""
    resp = client.post(
        "/api/chat/mensagens",
        json={"tenant_id": str(uuid4()), "contato": "+5511988887777", "texto": "oi"},
    )
    assert resp.status_code == 403


def test_chat_demo_ws_recusa_tenant_que_nao_e_o_de_vitrine(client: TestClient):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/chat/ws/{uuid4()}/+5511988887777") as ws:
            ws.send_text("oi")
            ws.receive_json()


def test_demo_liberado_aceita_o_tenant_de_vitrine():
    from uuid import UUID

    get_settings.cache_clear()
    try:
        assert _demo_liberado(UUID(DEMO_TENANT))
        assert not _demo_liberado(uuid4())
    finally:
        get_settings.cache_clear()


def test_demo_desligado_recusa_ate_o_tenant_de_vitrine(monkeypatch):
    """`CHAT_DEMO_HABILITADO=false` fecha o demo inteiro em produção."""
    from uuid import UUID

    monkeypatch.setenv("CHAT_DEMO_HABILITADO", "false")
    get_settings.cache_clear()
    try:
        assert not _demo_liberado(UUID(DEMO_TENANT))
    finally:
        get_settings.cache_clear()


def test_id_de_vitrine_malformado_fecha_o_demo(monkeypatch):
    """Configuração inválida fecha em vez de abrir."""
    monkeypatch.setenv("CHAT_DEMO_TENANT_ID", "isto-nao-e-um-uuid")
    get_settings.cache_clear()
    try:
        from uuid import UUID

        assert not _demo_liberado(UUID(DEMO_TENANT))
    finally:
        get_settings.cache_clear()
