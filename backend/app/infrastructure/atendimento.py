"""Registro de atendimento do inbound — implementações da porta ``RegistroAtendimento``.

Substitui `idempotencia.py` (cache LRU de processo). O motivo é o que o cache não
conseguia cobrir: a reentrega da Meta chega **enquanto** a primeira tentativa ainda está
esperando a LLM e, com mais de uma réplica, quase sempre em outro processo — que nada
sabia da primeira. O resultado era o mesmo recado respondido (e cobrado) duas vezes.

Dois adaptadores: ``SqlRegistroAtendimento`` (produção) e ``RegistroAtendimentoMemoria``
(testes e execução sem banco), com a mesma semântica de reserva.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.domain.entities import EstadoAtendimento

# Depois disso, uma reserva "em atendimento" é considerada abandonada (processo caiu, o
# deploy derrubou o worker no meio) e pode ser retomada. Sem esse teto, uma falha deixaria
# a mensagem travada para sempre e a reentrega da Meta nunca a atenderia.
RESERVA_ABANDONADA_SEGUNDOS = 180

# Quanto tempo o resumo do atendimento fica guardado — é insumo de log, não histórico.
RETENCAO_PADRAO_DIAS = 30


def _agora() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SqlRegistroAtendimento:
    """Reserva por ``INSERT ... ON CONFLICT``, num único statement atômico.

    Usa **sessão própria**, fora da transação da requisição: a reserva precisa ficar
    visível para as outras réplicas **antes** de a LLM responder, que é justamente a
    janela em que a reentrega chega. Se ela participasse do commit da requisição, só
    apareceria no fim — tarde demais para evitar o atendimento em dobro.
    """

    def __init__(
        self,
        sessionmaker: async_sessionmaker,
        *,
        reserva_abandonada_segundos: int = RESERVA_ABANDONADA_SEGUNDOS,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._abandono = reserva_abandonada_segundos

    async def iniciar(
        self, *, chave: str, tenant_id: UUID | None = None, origem: str = ""
    ) -> EstadoAtendimento:
        if not chave:
            # Mensagem sem wamid: não dá para deduplicar, então atende (o custo de perder
            # uma resposta é maior que o de uma duplicata improvável).
            return EstadoAtendimento.NOVO

        agora = _agora()
        corte = agora - timedelta(seconds=self._abandono)
        # A cláusula WHERE do DO UPDATE é o coração: só retoma o que está abandonado ou
        # falhou. Uma reserva viva e uma dúvida já concluída não casam e o UPDATE não
        # acontece — nesse caso nada é devolvido e descobrimos o estado no SELECT abaixo.
        reservar = text(
            """
            INSERT INTO inbound_atendimento
                (chave, tenant_id, origem, status, resumo, criado_em, atualizado_em)
            VALUES (:chave, :tenant_id, :origem, 'em_atendimento', '', :agora, :agora)
            ON CONFLICT (chave) DO UPDATE SET
                status = 'em_atendimento',
                atualizado_em = :agora,
                tenant_id = COALESCE(EXCLUDED.tenant_id, inbound_atendimento.tenant_id)
            WHERE inbound_atendimento.status = 'falhou'
               OR (inbound_atendimento.status = 'em_atendimento'
                   AND inbound_atendimento.atualizado_em < :corte)
            RETURNING (xmax = 0) AS inserido
            """
        )
        async with self._sessionmaker() as session:
            linha = (
                await session.execute(
                    reservar,
                    {
                        "chave": chave,
                        "tenant_id": tenant_id,
                        "origem": origem,
                        "agora": agora,
                        "corte": corte,
                    },
                )
            ).first()
            await session.commit()

            if linha is not None:
                # xmax = 0 identifica a linha recém-inserida (nenhuma versão anterior).
                return EstadoAtendimento.NOVO if linha[0] else EstadoAtendimento.RETOMADO

            status = (
                await session.execute(
                    text("SELECT status FROM inbound_atendimento WHERE chave = :chave"),
                    {"chave": chave},
                )
            ).scalar_one_or_none()

        if status == "concluida":
            return EstadoAtendimento.CONCLUIDA
        # Reserva viva de outro processo — ou a linha sumiu entre os dois statements
        # (limpeza concorrente), caso em que tratar como "em atendimento" apenas descarta
        # uma mensagem, que é o lado seguro do erro.
        return EstadoAtendimento.EM_ATENDIMENTO

    async def concluir(self, *, chave: str, resumo: str = "") -> None:
        if not chave:
            return
        async with self._sessionmaker() as session:
            await session.execute(
                text(
                    """
                    UPDATE inbound_atendimento
                       SET status = 'concluida', resumo = :resumo, atualizado_em = :agora
                     WHERE chave = :chave
                    """
                ),
                {"chave": chave, "resumo": resumo[:500], "agora": _agora()},
            )
            await session.commit()

    async def falhar(self, *, chave: str, erro: str = "") -> None:
        if not chave:
            return
        async with self._sessionmaker() as session:
            await session.execute(
                text(
                    """
                    UPDATE inbound_atendimento
                       SET status = 'falhou', resumo = :erro, atualizado_em = :agora
                     WHERE chave = :chave
                    """
                ),
                {"chave": chave, "erro": erro[:500], "agora": _agora()},
            )
            await session.commit()

    async def limpar_antigos(self, *, dias: int = RETENCAO_PADRAO_DIAS) -> int:
        """Descarta registros antigos. A reentrega da Meta acontece em segundos; guardar
        o histórico além disso serve só ao painel de logs."""
        corte = _agora() - timedelta(days=dias)
        async with self._sessionmaker() as session:
            resultado = await session.execute(
                text("DELETE FROM inbound_atendimento WHERE criado_em < :corte"),
                {"corte": corte},
            )
            await session.commit()
        return resultado.rowcount or 0


class RegistroAtendimentoMemoria:
    """Mesma semântica, no processo. Testes e execução sem banco."""

    def __init__(self, *, reserva_abandonada_segundos: int = RESERVA_ABANDONADA_SEGUNDOS) -> None:
        self._registros: dict[str, dict] = {}
        self._abandono = reserva_abandonada_segundos
        self._lock = asyncio.Lock()

    async def iniciar(
        self, *, chave: str, tenant_id: UUID | None = None, origem: str = ""
    ) -> EstadoAtendimento:
        if not chave:
            return EstadoAtendimento.NOVO
        agora = _agora()
        async with self._lock:
            atual = self._registros.get(chave)
            if atual is None:
                self._registros[chave] = {
                    "status": "em_atendimento",
                    "tenant_id": tenant_id,
                    "origem": origem,
                    "atualizado_em": agora,
                    "resumo": "",
                }
                return EstadoAtendimento.NOVO
            if atual["status"] == "concluida":
                return EstadoAtendimento.CONCLUIDA
            abandonada = (agora - atual["atualizado_em"]).total_seconds() >= self._abandono
            if atual["status"] == "falhou" or abandonada:
                atual.update(status="em_atendimento", atualizado_em=agora)
                return EstadoAtendimento.RETOMADO
            return EstadoAtendimento.EM_ATENDIMENTO

    async def concluir(self, *, chave: str, resumo: str = "") -> None:
        async with self._lock:
            registro = self._registros.get(chave)
            if registro is not None:
                registro.update(status="concluida", resumo=resumo[:500], atualizado_em=_agora())

    async def falhar(self, *, chave: str, erro: str = "") -> None:
        async with self._lock:
            registro = self._registros.get(chave)
            if registro is not None:
                registro.update(status="falhou", resumo=erro[:500], atualizado_em=_agora())
