"""Webhook da Meta WhatsApp Cloud API.

- ``GET``: verificação do webhook (hub.challenge).
- ``POST``: recebe eventos. No scaffold apenas registra; o roteamento de mensagens reais
  para ``ReceberMensagemRecebida`` fica no roadmap (inbound real do WhatsApp).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

from app.config import get_settings

logger = logging.getLogger("webhook.meta")
router = APIRouter(prefix="/api/webhook/meta", tags=["webhook"])


@router.get("")
async def verificar(request: Request) -> Response:
    params = request.query_params
    modo = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    if modo == "subscribe" and token == get_settings().meta_webhook_verify_token:
        return Response(content=challenge, media_type="text/plain")
    return Response(status_code=status.HTTP_403_FORBIDDEN)


@router.post("")
async def receber_evento(request: Request) -> dict:
    payload = await request.json()
    # Aqui entrariam: status de entrega (sent/delivered/read/failed) e mensagens inbound.
    logger.info("Evento Meta recebido: %s", payload.get("object"))
    return {"status": "received"}
