"""Webhook da Meta WhatsApp Cloud API.

- ``GET``: verificação do webhook (hub.challenge).
- ``POST``: recebe eventos. O mesmo envelope carrega **dois** caminhos, que convivem aqui:
  os **status de entrega** (sent/delivered/read/failed), aplicados aos destinatários dos
  broadcasts (base da confirmação de recebimento / não-entrega reativa, §9b); e as
  **mensagens recebidas** dos responsáveis, roteadas para o chatbot por
  ``ProcessarInboundMeta`` (§9e.1). A resposta ao responsável **não** vai no corpo desta
  requisição — a Meta espera ``200 OK`` e a resposta sai por uma nova chamada à API, feita
  pelo caso de uso a partir do número da própria escola.

**Autenticidade:** o endpoint é público, então todo ``POST`` é validado pelo
``X-Hub-Signature-256`` (HMAC-SHA256 do corpo bruto com o app secret) quando
``META_VALIDATE_SIGNATURE`` está ligado. Sem isso, qualquer um que descubra a URL pode
forjar status de entrega — mascarando como ``delivered`` um aviso que a escola precisa
saber que não chegou (§9b) — **e** forjar mensagens em nome de qualquer telefone,
consumindo cota de LLM de um tenant. Por isso o inbound roda **depois** da validação.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request, Response, status

from app.application.inbound_use_cases import ProcessarInboundMeta
from app.application.templates_use_cases import AtualizarStatusTemplateMeta
from app.application.use_cases import RegistrarStatusEntrega
from app.config import get_settings
from app.infrastructure.db.repositories import (
    SqlBroadcastRepository,
    SqlTemplateRepository,
    SqlWabaRepository,
)
from app.infrastructure.security import validar_assinatura_meta
from app.interfaces.deps import (
    get_broadcast_repo,
    get_processar_inbound_meta,
    get_template_repo,
    get_waba_repo,
)

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


@router.post("", response_model=None)
async def receber_evento(
    request: Request,
    broadcasts: SqlBroadcastRepository = Depends(get_broadcast_repo),
    inbound: ProcessarInboundMeta = Depends(get_processar_inbound_meta),
    templates: SqlTemplateRepository = Depends(get_template_repo),
    wabas: SqlWabaRepository = Depends(get_waba_repo),
) -> Response | dict:
    settings = get_settings()
    # Lê os BYTES BRUTOS: o HMAC é calculado sobre eles, antes de qualquer parse. Fazer
    # json.loads e reserializar mudaria os bytes e invalidaria a assinatura.
    corpo = await request.body()

    if settings.meta_validate_signature and not validar_assinatura_meta(
        corpo=corpo,
        cabecalho=request.headers.get("X-Hub-Signature-256"),
        app_secret=settings.meta_app_secret or "",
    ):
        # 403 seco: não revela se faltou o cabeçalho, se o segredo está ausente ou se o
        # HMAC não bateu — a diferença ajudaria quem está sondando o endpoint.
        logger.warning("Webhook Meta recusado: assinatura X-Hub-Signature-256 inválida")
        return Response(status_code=status.HTTP_403_FORBIDDEN)

    try:
        payload = json.loads(corpo)
    except json.JSONDecodeError:
        logger.warning("Webhook Meta recusado: corpo não é JSON válido")
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    # Aplica os status de entrega aos destinatários (sent/delivered/read/failed).
    atualizados = await RegistrarStatusEntrega(broadcasts=broadcasts).executar(payload=payload)

    # Revisão de template concluída (aprovado/rejeitado) ou categoria reclassificada. É o
    # que fecha o ciclo de submissão sem polling — a revisão da Meta é assíncrona e este
    # evento é o único aviso de que ela terminou.
    templates_atualizados = await AtualizarStatusTemplateMeta(
        templates=templates, wabas=wabas
    ).executar(payload=payload)

    # Mensagens recebidas → chatbot. Processado em linha, como o webhook anterior fazia: a
    # Meta reenvia o evento se o 200 demorar, e o cache de idempotência (por wamid) absorve
    # a reentrega. [Roadmap] fila/worker, para o 200 nunca depender da latência da LLM.
    inbound_resultado = await inbound.executar(payload=payload)

    logger.info(
        "Evento Meta recebido: %s (%d status de entrega; %d templates; inbound: %d "
        "recebidas, %d respondidas, %d descartadas, %d repetidas, %d ignoradas, "
        "%d limitadas)",
        payload.get("object"),
        atualizados,
        templates_atualizados,
        inbound_resultado.recebidas,
        inbound_resultado.respondidas,
        inbound_resultado.descartadas,
        inbound_resultado.repetidas,
        inbound_resultado.ignoradas,
        inbound_resultado.limitadas,
    )
    return {
        "status": "received",
        "status_atualizados": atualizados,
        "templates_atualizados": templates_atualizados,
        "mensagens_recebidas": inbound_resultado.recebidas,
        "mensagens_respondidas": inbound_resultado.respondidas,
        "mensagens_descartadas": inbound_resultado.descartadas,
    }
