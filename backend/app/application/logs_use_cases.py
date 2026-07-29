"""Casos de uso do painel de logs (§16).

A regra de negócio aqui é pequena de propósito — o valor está na consulta —, mas ela
existe: **normalizar a paginação** (o cliente não define o teto) e **decidir a janela**
do resumo. Deixar isso na rota espalharia o mesmo `min/max` por cada endpoint.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.domain.entities import (
    AtendimentoInbound,
    NivelLog,
    RegistroLog,
    ResumoLogs,
)

# Página pequena por padrão: log é para investigar, não para rolar. O teto impede que um
# `?por_pagina=100000` transforme a tela de diagnóstico no próximo incidente.
POR_PAGINA_PADRAO = 10
POR_PAGINA_MAXIMO = 200
JANELA_MAXIMA_HORAS = 24 * 30


def normalizar_paginacao(
    pagina: int | None, por_pagina: int | None
) -> tuple[int, int]:
    """Página ≥ 1 e tamanho dentro do teto — a origem é o cliente, não se confia nela."""
    p = max(1, int(pagina or 1))
    tamanho = int(por_pagina or POR_PAGINA_PADRAO)
    return p, max(1, min(tamanho, POR_PAGINA_MAXIMO))


@dataclass(frozen=True)
class PaginaDeLogs:
    itens: list[RegistroLog]
    total: int
    pagina: int
    por_pagina: int
    loggers: list[str]

    @property
    def total_paginas(self) -> int:
        if self.por_pagina <= 0:
            return 1
        return max(1, -(-self.total // self.por_pagina))


class ListarLogs:
    """Página de logs com os filtros do painel."""

    def __init__(self, logs) -> None:
        self._logs = logs

    async def executar(
        self,
        *,
        nivel: str = "",
        logger_nome: str = "",
        correlacao_id: str = "",
        busca: str = "",
        tenant_id: uuid.UUID | None = None,
        apenas_falhas: bool = False,
        pagina: int = 1,
        por_pagina: int = POR_PAGINA_PADRAO,
    ) -> PaginaDeLogs:
        pagina, por_pagina = normalizar_paginacao(pagina, por_pagina)
        nivel_enum: NivelLog | None = None
        if nivel:
            try:
                nivel_enum = NivelLog(nivel.upper())
            except ValueError:
                # Nível inexistente não é erro: apenas não filtra, e a tela mostra tudo.
                nivel_enum = None

        itens, total = await self._logs.listar(
            nivel=nivel_enum,
            logger_nome=logger_nome.strip(),
            correlacao_id=correlacao_id.strip(),
            busca=busca.strip(),
            tenant_id=tenant_id,
            apenas_falhas=apenas_falhas,
            pagina=pagina,
            por_pagina=por_pagina,
        )
        loggers = await self._logs.loggers_disponiveis()
        return PaginaDeLogs(
            itens=itens,
            total=total,
            pagina=pagina,
            por_pagina=por_pagina,
            loggers=loggers,
        )


class ResumoObservabilidade:
    """Visão agregada da janela recente (a tela de abertura do painel)."""

    def __init__(self, logs) -> None:
        self._logs = logs

    async def executar(self, *, janela_horas: int = 24) -> ResumoLogs:
        janela = max(1, min(int(janela_horas or 24), JANELA_MAXIMA_HORAS))
        return await self._logs.resumo(janela_horas=janela)


class ListarAtendimentosInbound:
    """Últimos atendimentos de WhatsApp e em que pé estão."""

    def __init__(self, logs) -> None:
        self._logs = logs

    async def executar(
        self, *, status: str = "", limite: int = 30
    ) -> list[AtendimentoInbound]:
        return await self._logs.atendimentos(status=status.strip(), limite=limite)
