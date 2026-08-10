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

from app.main import app


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
# Chat de demonstração — removido: não pode voltar a existir por acidente
# --------------------------------------------------------------------------- #


def test_chat_demo_nao_existe_mais(client: TestClient):
    """As rotas do simulador eram as únicas sem login que gravavam conversa e gastavam LLM.

    Com o WhatsApp real no ar elas foram removidas; este teste é o que impede um
    ``include_router`` distraído de reabrir a superfície pública.
    """
    resp = client.post(
        "/api/chat/mensagens",
        json={"tenant_id": str(uuid4()), "contato": "+5511988887777", "texto": "oi"},
    )
    assert resp.status_code == 404
    assert not any(
        rota.path.startswith("/api/chat") for rota in app.routes if hasattr(rota, "path")
    )
