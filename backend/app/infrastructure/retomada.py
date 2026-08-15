"""Tarefa de fundo que retoma disparos interrompidos pela cota (§9a-quinquies).

Segue o mesmo desenho do gravador de logs (`app/infrastructure/logs.py`): uma task asyncio
iniciada no `lifespan`, que acorda em intervalo fixo e pode ser parada no shutdown. O
projeto não tem scheduler, e subir um só por isto seria caro demais para uma passada que
custa uma consulta.

**A trava é o ponto delicado.** Com mais de uma réplica no Render — que é o cenário para o
qual o `RateLimiter` e a idempotência do inbound já foram desenhados —, dois processos
acordariam juntos, pegariam o mesmo broadcast e enviariam duas vezes para o mesmo
responsável: o status do destinatário só vira ``ENVIADO`` **depois** da chamada à Graph
API, então não há nada impedindo a corrida. Um `pg_try_advisory_lock` resolve com uma
linha: quem pega roda, quem não pega volta a dormir. É `try` e não `pg_advisory_lock`
porque esperar na trava só empilharia réplicas para fazer o mesmo trabalho.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.retomada_use_cases import RetomarBroadcastsPendentes

logger = logging.getLogger("broadcast.retomada")

# Chave arbitrária e fixa do advisory lock. Precisa ser única no banco entre os usos de
# lock do projeto — hoje é o único.
_LOCK_ID = 8_314_207


class RetomadorDeDisparos:
    def __init__(
        self,
        sessionmaker: Callable[[], AsyncSession],
        *,
        montar: Callable[[AsyncSession], RetomarBroadcastsPendentes],
        intervalo_segundos: int,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._montar = montar
        self._intervalo = max(60, intervalo_segundos)
        self._parar = asyncio.Event()
        self._tarefa: asyncio.Task | None = None

    def iniciar(self) -> None:
        if self._tarefa is None:
            self._parar.clear()
            self._tarefa = asyncio.create_task(
                self._rodar(), name="retomador-de-disparos"
            )

    async def parar(self) -> None:
        self._parar.set()
        if self._tarefa is not None:
            await asyncio.wait([self._tarefa], timeout=10)
            self._tarefa = None

    async def _rodar(self) -> None:
        while not self._parar.is_set():
            # Dorme **antes** da primeira passada: no boot o processo tem coisa melhor a
            # fazer, e um deploy em laço de reinício não deve virar rajada de disparos.
            try:
                await asyncio.wait_for(self._parar.wait(), timeout=self._intervalo)
            except asyncio.TimeoutError:
                pass
            if self._parar.is_set():
                return
            try:
                await self._passada()
            except Exception:  # noqa: BLE001 — a tarefa de fundo nunca pode morrer
                logger.exception("Falha na passada de retomada de disparos")

    async def _passada(self) -> None:
        async with self._sessionmaker() as sessao:
            travou = (
                await sessao.execute(
                    text("SELECT pg_try_advisory_lock(:id)"), {"id": _LOCK_ID}
                )
            ).scalar()
            if not travou:
                logger.debug("Outra réplica está retomando os disparos; pulando.")
                return
            try:
                await self._montar(sessao).executar()
                await sessao.commit()
            finally:
                await sessao.execute(
                    text("SELECT pg_advisory_unlock(:id)"), {"id": _LOCK_ID}
                )
