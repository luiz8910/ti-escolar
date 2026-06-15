"""Adaptador Meta WhatsApp Cloud API (outbound).

Implementa a porta ``MessageChannel`` para disparo real. As mensagens de texto livre só são
permitidas dentro da janela de atendimento de 24h; fora dela é obrigatório usar templates
(HSM) aprovados — por isso ``enviar_template`` é o caminho dos broadcasts.

A cota diária por tier e o throttling são aplicados nos casos de uso via ``QuotaPolicy`` e
``RateLimiter``, não aqui.
"""

from __future__ import annotations

import httpx

from app.domain.entities import Documento, MessageTemplate

_BASE = "https://graph.facebook.com/v21.0"


class MetaMessageChannel:
    def __init__(self, *, phone_number_id: str, access_token: str) -> None:
        self._phone_number_id = phone_number_id
        self._headers = {"Authorization": f"Bearer {access_token}"}

    @property
    def _url(self) -> str:
        return f"{_BASE}/{self._phone_number_id}/messages"

    async def _post(self, payload: dict) -> str:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(self._url, headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["messages"][0]["id"]

    async def enviar_texto(self, *, contato: str, texto: str) -> str:
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": contato,
                "type": "text",
                "text": {"body": texto},
            }
        )

    async def enviar_template(
        self, *, contato: str, template: MessageTemplate, parametros: list[str]
    ) -> str:
        componentes = []
        if parametros:
            componentes.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in parametros],
                }
            )
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": contato,
                "type": "template",
                "template": {
                    "name": template.nome,
                    "language": {"code": template.idioma},
                    "components": componentes,
                },
            }
        )

    async def enviar_documento(self, *, contato: str, documento: Documento) -> str:
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": contato,
                "type": "document",
                "document": {"link": documento.url, "filename": documento.nome},
            }
        )
