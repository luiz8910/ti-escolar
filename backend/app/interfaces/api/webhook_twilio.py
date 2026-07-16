"""Webhook do Twilio WhatsApp (inbound + status de entrega).

Ao contrário da Meta (JSON), o Twilio faz ``POST`` **form-urlencoded** e espera **TwiML**
(XML) como resposta para responder ao usuário na mesma requisição.

- **Status de entrega** (``MessageStatus``): atualiza o destinatário do broadcast pelo
  ``MessageSid`` (mesmo id externo que ``TwilioMessageChannel`` retorna no envio).
- **Mensagem recebida** (``Body``/``From``): roteia para ``ReceberMensagemRecebida`` (o
  chatbot) e devolve a resposta em TwiML. O número único do Sandbox mapeia para um único
  tenant (``TWILIO_DEFAULT_TENANT_ID``; default = tenant demo).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from urllib.parse import parse_qsl
from uuid import UUID
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, Request, Response, status

from app.config import Settings
from app.domain.entities import StatusEntrega
from app.infrastructure.db.repositories import SqlBroadcastRepository
from app.infrastructure.db.repositories_admin import SqlTenantRepository
from app.interfaces.deps import (
    get_broadcast_repo,
    get_receber_mensagem,
    get_settings_dep,
    get_tenant_repo,
)

logger = logging.getLogger("webhook.twilio")
router = APIRouter(prefix="/api/webhook/twilio", tags=["webhook"])

# Tenant demo (fallback quando TWILIO_DEFAULT_TENANT_ID não é definido).
_TENANT_DEMO = UUID("00000000-0000-0000-0000-000000000001")

# Status do Twilio → StatusEntrega do domínio. Estados intermediários
# (queued/sending/accepted) são ignorados.
_STATUS_TWILIO: dict[str, StatusEntrega] = {
    "sent": StatusEntrega.ENVIADO,
    "delivered": StatusEntrega.ENTREGUE,
    "read": StatusEntrega.LIDO,
    "failed": StatusEntrega.FALHOU,
    "undelivered": StatusEntrega.FALHOU,
}


def _sem_prefixo(numero: str) -> str:
    """Remove o prefixo ``whatsapp:`` deixando o telefone em E.164."""
    return numero.split(":", 1)[1] if numero.startswith("whatsapp:") else numero


def _assinatura_valida(*, url: str, params: dict[str, str], assinatura: str, token: str) -> bool:
    """Valida o cabeçalho ``X-Twilio-Signature`` (HMAC-SHA1, base64), só stdlib.

    Algoritmo do Twilio: URL do webhook + cada par (nome+valor) ordenado por nome,
    concatenados, com HMAC-SHA1 usando o auth token como chave.
    """
    base = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    esperado = base64.b64encode(
        hmac.new(token.encode(), base.encode(), hashlib.sha1).digest()
    ).decode()
    return hmac.compare_digest(esperado, assinatura)


def _twiml(texto: str | None = None) -> Response:
    corpo = f"<Message>{escape(texto)}</Message>" if texto else ""
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?><Response>{corpo}</Response>',
        media_type="application/xml",
    )


@router.post("")
async def receber_evento(
    request: Request,
    broadcasts: SqlBroadcastRepository = Depends(get_broadcast_repo),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
    receber=Depends(get_receber_mensagem),
    settings: Settings = Depends(get_settings_dep),
) -> Response:
    # O Twilio envia application/x-www-form-urlencoded — parseamos com a stdlib para
    # evitar a dependência python-multipart do request.form().
    corpo_bruto = (await request.body()).decode("utf-8")
    params = dict(parse_qsl(corpo_bruto))

    if settings.twilio_validate_signature and settings.twilio_auth_token:
        assinatura = request.headers.get("X-Twilio-Signature", "")
        if not _assinatura_valida(
            url=str(request.url),
            params=params,
            assinatura=assinatura,
            token=settings.twilio_auth_token,
        ):
            logger.warning("Assinatura X-Twilio-Signature inválida — evento recusado")
            return Response(status_code=status.HTTP_403_FORBIDDEN)

    # Callback de status de entrega.
    if "MessageStatus" in params:
        sid = params.get("MessageSid", "")
        entrega = _STATUS_TWILIO.get(params["MessageStatus"])
        if sid and entrega is not None:
            atualizado = await broadcasts.registrar_status(
                mensagem_id_externo=sid, status=entrega
            )
            logger.info(
                "Status Twilio %s → %s (sid=%s, atualizado=%s)",
                params["MessageStatus"],
                entrega.value,
                sid,
                atualizado,
            )
        return _twiml()

    # Mensagem recebida (inbound) → roteia para o chatbot e responde via TwiML.
    corpo = (params.get("Body") or "").strip()
    origem = params.get("From", "")
    if corpo and origem:
        # Roteia pelo número de destino (To = número da escola). Sem escola cadastrada com
        # esse número (ex.: número único do Sandbox), cai no tenant padrão.
        destino = _sem_prefixo(params.get("To", ""))
        escola = await tenants.por_whatsapp(destino) if destino else None
        if escola is not None:
            tenant_id = escola.id
        elif settings.twilio_default_tenant_id:
            tenant_id = UUID(settings.twilio_default_tenant_id)
        else:
            tenant_id = _TENANT_DEMO
        resposta = await receber.executar(
            tenant_id=tenant_id, contato=_sem_prefixo(origem), texto=corpo
        )
        return _twiml(resposta.texto)

    return _twiml()
