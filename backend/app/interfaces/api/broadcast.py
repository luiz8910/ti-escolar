"""Rotas de outbound: disparo de broadcasts e consulta de cota diária (tier Meta).

**Autenticação obrigatória.** Estas rotas recebem o ``tenant_id`` no corpo/URL, então sem
identidade elas seriam um disparador aberto: quem soubesse a URL pública e um ``tenant_id``
enviaria WhatsApp aos responsáveis de qualquer escola, pelo número dela, queimando a cota
diária. `_exige_acesso_tenant` amarra o solicitante à própria escola (o super admin passa em
qualquer uma) e `_exige_tenant_ativo` barra escola suspensa.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.application.use_cases import EnviarBroadcast
from app.domain.entities import Broadcast, DestinatarioBroadcast, Usuario
from app.infrastructure.db.repositories_admin import SqlTenantRepository
from app.infrastructure.messaging.quota import SqlQuotaPolicy
from app.interfaces.api.admin import (
    _exige_acesso_tenant,
    _exige_tenant_ativo,
    usuario_autenticado,
)
from app.interfaces.deps import get_enviar_broadcast, get_quota_policy, get_tenant_repo
from app.interfaces.dto import BroadcastEntrada, BroadcastSaida, QuotaSaida

router = APIRouter(prefix="/api/broadcasts", tags=["broadcasts"])


@router.post("", response_model=BroadcastSaida)
async def disparar_broadcast(
    payload: BroadcastEntrada,
    solicitante: Usuario = Depends(usuario_autenticado),
    uc: EnviarBroadcast = Depends(get_enviar_broadcast),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> BroadcastSaida:
    _exige_acesso_tenant(solicitante, payload.tenant_id)
    # Escola suspensa (bloqueada por inadimplência ou cancelada) não dispara mensagens.
    await _exige_tenant_ativo(payload.tenant_id, tenants)
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
    solicitante: Usuario = Depends(usuario_autenticado),
    policy: SqlQuotaPolicy = Depends(get_quota_policy),
) -> QuotaSaida:
    _exige_acesso_tenant(solicitante, tenant_id)
    cota = await policy.cota_do_dia(tenant_id)
    return QuotaSaida(
        tenant_id=tenant_id,
        dia=cota.dia,
        limite_diario=cota.limite_diario,
        enviados=cota.enviados,
        restante=cota.restante,
    )
