"""Rotas de outbound: disparo de broadcasts e consulta de cota diária (tier Meta)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.application.use_cases import EnviarBroadcast
from app.domain.entities import Broadcast, DestinatarioBroadcast
from app.infrastructure.messaging.quota import SqlQuotaPolicy
from app.interfaces.deps import get_enviar_broadcast, get_quota_policy
from app.interfaces.dto import BroadcastEntrada, BroadcastSaida, QuotaSaida

router = APIRouter(prefix="/api/broadcasts", tags=["broadcasts"])


@router.post("", response_model=BroadcastSaida)
async def disparar_broadcast(
    payload: BroadcastEntrada,
    uc: EnviarBroadcast = Depends(get_enviar_broadcast),
) -> BroadcastSaida:
    broadcast = Broadcast(
        tenant_id=payload.tenant_id,
        template_id=payload.template_id,
        titulo=payload.titulo,
        destinatarios=[
            DestinatarioBroadcast(contato=d.contato, parametros=d.parametros)
            for d in payload.destinatarios
        ],
    )
    resultado = await uc.executar(broadcast=broadcast)
    return BroadcastSaida(
        broadcast_id=resultado.broadcast_id,
        status=resultado.status.value,
        enviados=resultado.enviados,
        falhas=resultado.falhas,
        bloqueados_por_limite=resultado.bloqueados_por_limite,
        restante_cota=resultado.restante_cota,
    )


@router.get("/quota/{tenant_id}", response_model=QuotaSaida)
async def consultar_quota(
    tenant_id: UUID,
    policy: SqlQuotaPolicy = Depends(get_quota_policy),
) -> QuotaSaida:
    cota = await policy.cota_do_dia(tenant_id)
    return QuotaSaida(
        tenant_id=tenant_id,
        dia=cota.dia,
        limite_diario=cota.limite_diario,
        enviados=cota.enviados,
        restante=cota.restante,
    )
