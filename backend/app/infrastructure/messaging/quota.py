"""Cota de conversas iniciadas (janela de 24h do portfólio) e rate limiter por token bucket.

**Por que a janela é corrida e não o dia do calendário.** A Meta conta as conversas que o
negócio inicia com clientes únicos nas últimas 24 horas, devolvendo capacidade
continuamente à medida que cada envio completa esse prazo. Não existe virada à meia-noite.
A versão anterior contava `date()` em UTC, o que além de errado no conceito virava o "dia"
às 21h de Brasília — no meio do expediente da escola.

**E por que o teto é do portfólio.** Desde out/2025 o limite deixou de ser por número e
passou a ser do Meta Business Account, compartilhado por todas as WABAs e números abaixo
dele (§9e.3). Contando por escola, cinco escolas de teste acreditariam ter 1250 de
capacidade e a Graph API recusaria a 251ª — depois de o painel já ter dito que cabia.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import MessageQuota
from app.infrastructure.db.models import EnvioIniciadoORM, TenantORM, WabaORM

# A janela da Meta. Constante e não configuração: mudá-la não ajusta nada nosso, só faz a
# nossa contabilidade divergir da que vale, que é a deles.
JANELA_HORAS = 24


class SqlQuotaPolicy:
    """Conta destinatários **distintos** alcançados pelo portfólio nas últimas 24 horas."""

    def __init__(self, session: AsyncSession, *, limite_diario: int) -> None:
        self._s = session
        self._limite = limite_diario

    async def _portfolio(self, tenant_id: uuid.UUID) -> str:
        """Portfólio da escola, ou ``""`` quando ela ainda não tem conta do WhatsApp.

        O balde vazio é proposital: escola sem WABA não pode somar com quem tem portfólio
        conhecido (inflaria o consumo alheio) nem sumir da conta (esconderia envio real).
        """
        stmt = (
            select(WabaORM.meta_business_id)
            .select_from(TenantORM)
            .join(WabaORM, TenantORM.waba_id == WabaORM.id)
            .where(TenantORM.id == tenant_id)
        )
        return (await self._s.execute(stmt)).scalar_one_or_none() or ""

    async def cota(self, tenant_id: uuid.UUID) -> MessageQuota:
        portfolio = await self._portfolio(tenant_id)
        corte = _agora() - timedelta(hours=JANELA_HORAS)
        stmt = select(
            func.count(distinct(EnvioIniciadoORM.contato)),
            func.min(EnvioIniciadoORM.enviado_em),
        ).where(
            EnvioIniciadoORM.meta_business_id == portfolio,
            EnvioIniciadoORM.enviado_em > corte,
        )
        enviados, mais_antigo = (await self._s.execute(stmt)).one()
        return MessageQuota(
            tenant_id=tenant_id,
            limite_diario=self._limite,
            enviados=enviados or 0,
            # O envio mais antigo ainda na janela é o próximo a sair dela — é ele que
            # devolve a primeira vaga, e é isso que a tela deve dizer em vez de "amanhã".
            proxima_liberacao=(
                (mais_antigo + timedelta(hours=JANELA_HORAS)).replace(tzinfo=timezone.utc)
                if mais_antigo is not None
                else None
            ),
        )

    async def registrar_envio(self, tenant_id: uuid.UUID, contato: str) -> None:
        self._s.add(
            EnvioIniciadoORM(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                meta_business_id=await self._portfolio(tenant_id),
                contato=contato,
                enviado_em=_agora(),
            )
        )
        await self._s.flush()


def _agora() -> datetime:
    """UTC sem tzinfo, que é como o projeto grava datas no Postgres."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
