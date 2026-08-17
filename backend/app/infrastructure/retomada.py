"""Tarefa de fundo que retoma disparos interrompidos pela cota (§9a-quinquies).

Segue o mesmo desenho do gravador de logs (`app/infrastructure/logs.py`): uma task asyncio
iniciada no `lifespan`, que pode ser parada no shutdown. O projeto não tem scheduler, e
subir um só por isto seria caro demais para uma passada que custa uma consulta.

**Segue uma grade, não um intervalo** (`JanelaDeExecucao`). O intervalo fixo de 30 min
significava 48 passadas por dia, todos os dias: cada uma abria sessão mesmo sem nada a
fazer, o que mantinha o Postgres serverless acordado 24/7 — e podia mandar aviso escolar de
madrugada, no dia em que a cota liberasse às 3h. A espera é fatiada em blocos de 15 min que
só olham o relógio, sem tocar no banco.

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
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.retomada_use_cases import RetomarBroadcastsPendentes
from app.domain.entities import JanelaDeExecucao

logger = logging.getLogger("broadcast.retomada")


def _agora() -> datetime:
    return datetime.now(timezone.utc)

# Chave arbitrária e fixa do advisory lock. Precisa ser única no banco entre os usos de
# lock do projeto — hoje é o único.
_LOCK_ID = 8_314_207


class RetomadorDeDisparos:
    def __init__(
        self,
        sessionmaker: Callable[[], AsyncSession],
        *,
        montar: Callable[[AsyncSession], RetomarBroadcastsPendentes],
        janela: JanelaDeExecucao,
        agora: Callable[[], datetime] = _agora,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._montar = montar
        self._janela = janela
        # Injetável só para o teste poder posicionar o relógio numa terça às 6h59 sem
        # esperar até terça.
        self._agora = agora
        self._parar = asyncio.Event()
        self._acordar = asyncio.Event()
        self._tarefa: asyncio.Task | None = None

    def iniciar(self) -> None:
        if self._tarefa is None:
            self._parar.clear()
            self._tarefa = asyncio.create_task(
                self._rodar(), name="retomador-de-disparos"
            )

    def cutucar(self) -> None:
        """Drena agora, sem esperar o próximo horário da grade.

        Quem chama é a rota de disparo, logo depois de gravar o broadcast. Sem isto, um
        aviso criado às 8h só sairia às 12h30 — a grade existe para o que a **máquina**
        decide reenviar, não para segurar o que uma pessoa acabou de mandar.

        É um `Event` em memória, não polling: custa zero consulta enquanto ninguém dispara.
        O preço é depender de rota e tarefa estarem no mesmo processo, o que o `fly.toml`
        garante ao fixar uma máquina só. Com duas réplicas, o disparo feito na réplica B
        espera a grade — atraso, nunca envio perdido, e o advisory lock segue impedindo que
        as duas peguem o mesmo broadcast.
        """
        self._acordar.set()

    async def parar(self) -> None:
        self._parar.set()
        self._acordar.set()  # solta a espera imediatamente
        if self._tarefa is not None:
            await asyncio.wait([self._tarefa], timeout=10)
            self._tarefa = None

    async def _rodar(self) -> None:
        # Dorme **antes** da primeira passada: no boot o processo tem coisa melhor a fazer,
        # e um deploy em laço de reinício não deve virar rajada de disparos. Com a grade,
        # isso significa que um deploy às 12h31 pula o slot das 12h30 — seguro, porque o
        # prazo de validade do disparo é de 7 dias e o próximo slot vem em horas.
        alvo = self._janela.proxima_execucao(self._agora())
        while not self._parar.is_set():
            espera = (alvo - self._agora()).total_seconds() if alvo else None
            if espera is None or espera > 0:
                # Fatias de no máximo 15 min, reavaliando o relógio. Reavaliar é aritmética
                # em memória e **não abre sessão** — é o que faz a tarefa custar zero
                # CU-hora fora dos horários. As fatias protegem contra deriva de relógio e
                # contra suspensão da máquina, sem transformar a espera em polling de banco.
                #
                # Espera nos dois eventos: o horário chega OU alguém dispara pelo painel.
                # Com a janela desligada (`alvo is None`) só o cutucão acorda — a grade some,
                # o disparo manual continua saindo.
                limite = 900 if espera is None else min(espera, 900)
                try:
                    await asyncio.wait_for(self._acordar.wait(), timeout=limite)
                except asyncio.TimeoutError:
                    continue
                if self._parar.is_set():
                    return
                # Cutucão: drena agora e recalcula a grade a partir daqui.
                self._acordar.clear()
                alvo = self._janela.proxima_execucao(self._agora())
                await self._passada_protegida()
                continue
            if self._parar.is_set():
                return
            # Calcula o próximo alvo **antes** da passada: se ela demorar além do slot
            # seguinte, o que se perde é uma passada, não a grade inteira.
            alvo = self._janela.proxima_execucao(self._agora())
            await self._passada_protegida()

    async def _passada_protegida(self) -> None:
        """A passada sem deixar exceção escapar — a tarefa de fundo nunca pode morrer.

        Se ela morresse, o sintoma seria disparo que simplesmente para de acontecer, sem
        erro em lugar nenhum: exatamente a classe de falha silenciosa que este projeto já
        pagou caro para aprender a evitar.
        """
        try:
            await self._passada()
        except Exception:  # noqa: BLE001
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
