"""Webhook da Meta WhatsApp Cloud API.

- ``GET``: verificação do webhook (hub.challenge).
- ``POST``: recebe eventos. Os **status de entrega** (sent/delivered/read/failed) são
  aplicados aos destinatários dos broadcasts (base da confirmação de recebimento /
  não-entrega reativa). O roteamento de **mensagens inbound** reais para
  ``ReceberMensagemRecebida`` segue no roadmap.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, Response, status

from app.application.use_cases import RegistrarStatusEntrega
from app.config import get_settings
from app.infrastructure.db.repositories import SqlBroadcastRepository
from app.interfaces.deps import get_broadcast_repo

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
async def receber_evento(
    request: Request,
    broadcasts: SqlBroadcastRepository = Depends(get_broadcast_repo),
) -> dict:
    payload = await request.json()
    # Aplica os status de entrega aos destinatários (sent/delivered/read/failed).
    atualizados = await RegistrarStatusEntrega(broadcasts=broadcasts).executar(payload=payload)
    logger.info(
        "Evento Meta recebido: %s (%d status de entrega atualizados)",
        payload.get("object"),
        atualizados,
    )
    return {"status": "received", "status_atualizados": atualizados}
