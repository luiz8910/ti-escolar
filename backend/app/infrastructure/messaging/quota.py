"""Cota diária (tier Meta) persistida e rate limiter por token bucket."""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import MessageQuota
from app.infrastructure.db.models import QuotaORM


def _hoje() -> str:
    return datetime.now(timezone.utc).date().isoformat()


class SqlQuotaPolicy:
    """Controla destinatários únicos por dia por tenant (limite do tier Meta)."""

    def __init__(self, session: AsyncSession, *, limite_diario: int) -> None:
        self._s = session
        self._limite = limite_diario

    async def _orm_do_dia(self, tenant_id: uuid.UUID) -> QuotaORM:
        dia = _hoje()
        stmt = select(QuotaORM).where(QuotaORM.tenant_id == tenant_id, QuotaORM.dia == dia)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = QuotaORM(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                dia=dia,
                limite_diario=self._limite,
                enviados=0,
            )
            self._s.add(row)
            await self._s.flush()
        return row

    async def cota_do_dia(self, tenant_id: uuid.UUID) -> MessageQuota:
        row = await self._orm_do_dia(tenant_id)
        return MessageQuota(
            id=row.id,
            tenant_id=row.tenant_id,
            limite_diario=row.limite_diario,
            dia=row.dia,
            enviados=row.enviados,
        )

    async def consumir(self, tenant_id: uuid.UUID, quantidade: int) -> MessageQuota:
        row = await self._orm_do_dia(tenant_id)
        row.enviados += quantidade
        await self._s.flush()
        return MessageQuota(
            id=row.id,
            tenant_id=row.tenant_id,
            limite_diario=row.limite_diario,
            dia=row.dia,
            enviados=row.enviados,
        )


class TokenBucketRateLimiter:
    """Throttling da taxa por segundo da API (token bucket simples e assíncrono)."""

    def __init__(self, *, taxa_por_segundo: float = 20.0) -> None:
        self._intervalo = 1.0 / taxa_por_segundo if taxa_por_segundo > 0 else 0.0
        self._proximo = 0.0
        self._lock = asyncio.Lock()

    async def aguardar_vaga(self) -> None:
        if self._intervalo <= 0:
            return
        async with self._lock:
            agora = time.monotonic()
            espera = max(0.0, self._proximo - agora)
            self._proximo = max(agora, self._proximo) + self._intervalo
        if espera:
            await asyncio.sleep(espera)
