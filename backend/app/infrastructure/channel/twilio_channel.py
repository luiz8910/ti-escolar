"""Adaptador Twilio WhatsApp (inbound + outbound).

Implementa a porta ``MessageChannel`` usando a API REST do Twilio
(``/2010-04-01/Accounts/{sid}/Messages.json``). Alternativa à Meta Cloud API: o
**Sandbox de WhatsApp** do Twilio funciona sem verificação de empresa, útil para
testar envio/recebimento de imediato.

O Sandbox não usa os templates HSM da Meta — dentro da janela de 24h (aberta quando o
usuário entra no Sandbox com ``join <palavra>``) o corpo do template é enviado como texto
livre. Templates "de verdade" no Twilio usam o Content API (``ContentSid``) — fica para
depois. A cota diária e o throttling continuam nos casos de uso (``QuotaPolicy`` /
``RateLimiter``), não aqui.
"""

from __future__ import annotations

import httpx

from app.domain.entities import Documento, MessageTemplate

_BASE = "https://api.twilio.com/2010-04-01"


def _com_prefixo_whatsapp(numero: str) -> str:
    """Garante o prefixo ``whatsapp:`` exigido pelo Twilio (idempotente)."""
    numero = numero.strip()
    return numero if numero.startswith("whatsapp:") else f"whatsapp:{numero}"


class TwilioMessageChannel:
    def __init__(
        self,
        *,
        account_sid: str,
        auth_token: str,
        from_number: str,
        status_callback_url: str | None = None,
    ) -> None:
        self._account_sid = account_sid
        self._auth = httpx.BasicAuth(account_sid, auth_token)
        self._from = _com_prefixo_whatsapp(from_number)
        self._status_callback_url = status_callback_url

    @property
    def _url(self) -> str:
        return f"{_BASE}/Accounts/{self._account_sid}/Messages.json"

    async def _post(self, data: dict[str, str]) -> str:
        data = {"From": self._from, **data}
        if self._status_callback_url:
            data.setdefault("StatusCallback", self._status_callback_url)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._url, data=data, auth=self._auth)
            resp.raise_for_status()
            payload = resp.json()
        return payload["sid"]

    async def enviar_texto(self, *, contato: str, texto: str) -> str:
        return await self._post({"To": _com_prefixo_whatsapp(contato), "Body": texto})

    async def enviar_template(
        self, *, contato: str, template: MessageTemplate, parametros: list[str]
    ) -> str:
        corpo = template.corpo
        for i, p in enumerate(parametros, start=1):
            corpo = corpo.replace(f"{{{{{i}}}}}", p)
        return await self._post({"To": _com_prefixo_whatsapp(contato), "Body": corpo})

    async def enviar_documento(self, *, contato: str, documento: Documento) -> str:
        return await self._post(
            {
                "To": _com_prefixo_whatsapp(contato),
                "Body": documento.nome,
                "MediaUrl": documento.url,
            }
        )
