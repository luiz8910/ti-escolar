"""Limite de taxa de entrada — implementações da porta ``ControleTaxa``.

Item 5 do checklist de pré-deploy (§15). Dois adaptadores:

- ``SqlControleTaxa``: janela fixa no Postgres, **compartilhada por todas as instâncias**.
  É a que roda em produção — um contador de processo daria ao atacante uma cota por
  réplica e seria zerado a cada deploy.
- ``ControleTaxaMemoria``: mesma semântica, em processo. Serve aos testes e a quem sobe a
  API sem banco.

**Janela fixa, não deslizante.** No pior caso ela deixa passar até 2× o limite na virada
da janela; para brute force de senha isso é irrelevante (10 tentativas em 5 min em vez de
5), e o custo de manter uma janela deslizante seria uma linha por tentativa em vez de uma
por chave.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.domain.entities import ResultadoTaxa
from app.infrastructure.db.models import ControleTaxaORM


def _agora() -> datetime:
    # Naive em UTC: a coluna é ``timestamp without time zone``, como no resto do schema.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _resultado(
    *, contador: int, limite: int, janela_inicio: datetime, janela_segundos: int, agora: datetime
) -> ResultadoTaxa:
    fim_da_janela = janela_inicio + timedelta(seconds=janela_segundos)
    retry_after = max(1, int((fim_da_janela - agora).total_seconds()))
    return ResultadoTaxa(
        permitido=contador <= limite,
        restantes=max(0, limite - contador),
        retry_after=retry_after,
        contador=contador,
    )


class SqlControleTaxa:
    """Contador de janela fixa no Postgres, atômico via ``INSERT ... ON CONFLICT``.

    Usa **sessão própria**, não a da requisição, e comita na hora. Isso é essencial: uma
    tentativa de login malsucedida termina em ``HTTPException``, e a sessão da requisição
    faz *rollback* — o que apagaria justamente a tentativa que precisávamos contar.
    """

    def __init__(self, sessionmaker: async_sessionmaker) -> None:
        self._sessionmaker = sessionmaker

    async def registrar(
        self, *, chave: str, limite: int, janela_segundos: int
    ) -> ResultadoTaxa:
        agora = _agora()
        corte = agora - timedelta(seconds=janela_segundos)
        # A janela vencida é reiniciada no mesmo statement: sem isso, ler-depois-escrever
        # abriria espaço para duas requisições simultâneas zerarem o contador uma da outra.
        sql = text(
            """
            INSERT INTO controle_taxa (chave, janela_inicio, contador)
            VALUES (:chave, :agora, 1)
            ON CONFLICT (chave) DO UPDATE SET
                contador = CASE
                    WHEN controle_taxa.janela_inicio < :corte THEN 1
                    ELSE controle_taxa.contador + 1
                END,
                janela_inicio = CASE
                    WHEN controle_taxa.janela_inicio < :corte THEN :agora
                    ELSE controle_taxa.janela_inicio
                END
            RETURNING contador, janela_inicio
            """
        )
        async with self._sessionmaker() as session:
            linha = (
                await session.execute(
                    sql, {"chave": chave, "agora": agora, "corte": corte}
                )
            ).one()
            await session.commit()
        contador, janela_inicio = int(linha[0]), linha[1]
        return _resultado(
            contador=contador,
            limite=limite,
            janela_inicio=janela_inicio,
            janela_segundos=janela_segundos,
            agora=agora,
        )

    async def limpar_vencidos(self, *, mais_velhos_que_segundos: int = 86_400) -> int:
        """Remove janelas antigas. A tabela é de trabalho: sem limpeza, cada IP que já
        bateu no login uma vez deixaria uma linha para sempre."""
        corte = _agora() - timedelta(seconds=mais_velhos_que_segundos)
        async with self._sessionmaker() as session:
            resultado = await session.execute(
                delete(ControleTaxaORM).where(ControleTaxaORM.janela_inicio < corte)
            )
            await session.commit()
        return resultado.rowcount or 0


class ControleTaxaMemoria:
    """Mesma semântica de janela fixa, no processo. Testes e execução sem banco."""

    def __init__(self) -> None:
        self._janelas: dict[str, tuple[datetime, int]] = {}
        self._lock = asyncio.Lock()

    async def registrar(
        self, *, chave: str, limite: int, janela_segundos: int
    ) -> ResultadoTaxa:
        agora = _agora()
        corte = agora - timedelta(seconds=janela_segundos)
        async with self._lock:
            janela_inicio, contador = self._janelas.get(chave, (agora, 0))
            if janela_inicio < corte:
                janela_inicio, contador = agora, 0
            contador += 1
            self._janelas[chave] = (janela_inicio, contador)
        return _resultado(
            contador=contador,
            limite=limite,
            janela_inicio=janela_inicio,
            janela_segundos=janela_segundos,
            agora=agora,
        )
