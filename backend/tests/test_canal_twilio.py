"""Canal Twilio WhatsApp: adaptador outbound e webhook (status + inbound).

O adaptador é exercitado com o ``httpx`` monkeypatchado (sem rede); o webhook é
exercitado via ``TestClient`` com as dependências de BD/LLM substituídas por fakes.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from app.application.use_cases import RespostaMensagem
from app.domain.entities import (
    Broadcast,
    DestinatarioBroadcast,
    Documento,
    StatusEntrega,
)
from app.infrastructure.channel.twilio_channel import (
    TwilioMessageChannel,
    _com_prefixo_whatsapp,
)
from app.interfaces.api.webhook_twilio import _assinatura_valida, _sem_prefixo
from app.main import app
from app.interfaces.deps import get_broadcast_repo, get_receber_mensagem
from tests.fakes import FakeBroadcastRepo


# --------------------------------------------------------------------------- #
# Adaptador outbound
# --------------------------------------------------------------------------- #
class _FakeResp:
    def __init__(self, sid: str) -> None:
        self._sid = sid

    def raise_for_status(self) -> None:  # noqa: D401
        return None

    def json(self) -> dict:
        return {"sid": self._sid}


class _FakeAsyncClient:
    """Captura o último POST e devolve um sid fixo, sem tocar na rede."""

    ultimo: dict = {}

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc) -> None:
        return None

    async def post(self, url, *, data, auth):
        _FakeAsyncClient.ultimo = {"url": url, "data": data, "auth": auth}
        return _FakeResp("SM123")


@pytest.fixture(autouse=True)
def _mock_httpx(monkeypatch):
    _FakeAsyncClient.ultimo = {}
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)


def _canal() -> TwilioMessageChannel:
    return TwilioMessageChannel(
        account_sid="AC_test",
        auth_token="tok",
        from_number="+14155238886",
        status_callback_url="https://exemplo.test/api/webhook/twilio",
    )


def test_prefixo_whatsapp_idempotente():
    assert _com_prefixo_whatsapp("+5511999") == "whatsapp:+5511999"
    assert _com_prefixo_whatsapp("whatsapp:+5511999") == "whatsapp:+5511999"


async def test_enviar_texto_monta_payload_e_retorna_sid():
    sid = await _canal().enviar_texto(contato="+5515997454531", texto="Olá")
    assert sid == "SM123"
    data = _FakeAsyncClient.ultimo["data"]
    assert data["From"] == "whatsapp:+14155238886"
    assert data["To"] == "whatsapp:+5515997454531"
    assert data["Body"] == "Olá"
    assert data["StatusCallback"] == "https://exemplo.test/api/webhook/twilio"


async def test_enviar_documento_inclui_media_url():
    doc = Documento(
        tenant_id=uuid.uuid4(),
        nome="Boletim",
        categoria="boletim",
        url="https://exemplo.test/b.pdf",
    )
    await _canal().enviar_documento(contato="+5515997454531", documento=doc)
    data = _FakeAsyncClient.ultimo["data"]
    assert data["MediaUrl"] == "https://exemplo.test/b.pdf"
    assert data["Body"] == "Boletim"


# --------------------------------------------------------------------------- #
# Helpers do webhook
# --------------------------------------------------------------------------- #
def test_sem_prefixo():
    assert _sem_prefixo("whatsapp:+5515997454531") == "+5515997454531"
    assert _sem_prefixo("+5515997454531") == "+5515997454531"


def test_assinatura_valida_confere_hmac():
    # Assinatura calculada pelo mesmo algoritmo → deve validar; token errado → recusa.
    url = "https://x.test/api/webhook/twilio"
    params = {"B": "2", "A": "1"}
    import base64
    import hashlib
    import hmac

    base = url + "A1B2"
    boa = base64.b64encode(hmac.new(b"tok", base.encode(), hashlib.sha1).digest()).decode()
    assert _assinatura_valida(url=url, params=params, assinatura=boa, token="tok")
    assert not _assinatura_valida(url=url, params=params, assinatura=boa, token="errado")


# --------------------------------------------------------------------------- #
# Webhook (TestClient com dependências fakes)
# --------------------------------------------------------------------------- #
class _FakeReceber:
    def __init__(self) -> None:
        self.chamadas: list[tuple] = []

    async def executar(self, *, tenant_id, contato, texto) -> RespostaMensagem:
        self.chamadas.append((tenant_id, contato, texto))
        return RespostaMensagem(texto=f"eco: {texto}", fontes=[], documentos=[])


@pytest.fixture
def client_e_fakes():
    repo = FakeBroadcastRepo()
    receber = _FakeReceber()
    app.dependency_overrides[get_broadcast_repo] = lambda: repo
    app.dependency_overrides[get_receber_mensagem] = lambda: receber
    yield TestClient(app), repo, receber
    app.dependency_overrides.clear()


def test_webhook_inbound_roteia_e_responde_twiml(client_e_fakes):
    client, _repo, receber = client_e_fakes
    resp = client.post(
        "/api/webhook/twilio",
        data={"From": "whatsapp:+5515997454531", "To": "whatsapp:+14155238886", "Body": "Oi"},
    )
    assert resp.status_code == 200
    assert "<Message>eco: Oi</Message>" in resp.text
    assert receber.chamadas and receber.chamadas[0][1] == "+5515997454531"
    assert receber.chamadas[0][2] == "Oi"


def test_webhook_status_atualiza_destinatario(client_e_fakes):
    client, repo, _receber = client_e_fakes
    # Um broadcast com um destinatário cujo id externo é o MessageSid do Twilio.
    b = Broadcast(
        tenant_id=uuid.uuid4(),
        template_id=uuid.uuid4(),
        titulo="t",
        destinatarios=[DestinatarioBroadcast(contato="+5515997454531", parametros=[])],
    )
    b.destinatarios[0].mensagem_id_externo = "SMabc"
    repo.salvos[b.id] = b

    resp = client.post(
        "/api/webhook/twilio",
        data={"MessageSid": "SMabc", "MessageStatus": "delivered", "To": "whatsapp:+55159"},
    )
    assert resp.status_code == 200
    assert b.destinatarios[0].status == StatusEntrega.ENTREGUE
