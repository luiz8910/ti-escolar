"""Consulta dos logs da aplicação e dos atendimentos do inbound (§16).

Só leitura: a **escrita** é feita fora da sessão da requisição, pelo gravador de fundo
(`app/infrastructure/logs.py`), justamente para não acoplar a latência das respostas —
nem a sorte do commit delas — ao registro de log.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import (
    AtendimentoInbound,
    ContagemRotulada,
    NivelLog,
    RegistroLog,
    ResumoLogs,
)
from app.infrastructure.db.models import (
    InboundAtendimentoORM,
    LogAplicacaoORM,
    TenantORM,
)


def _para_registro(r: LogAplicacaoORM) -> RegistroLog:
    return RegistroLog(
        id=r.id,
        nivel=NivelLog(r.nivel),
        mensagem=r.mensagem,
        logger=r.logger,
        correlacao_id=r.correlacao_id,
        rota=r.rota,
        metodo=r.metodo,
        status_code=r.status_code,
        duracao_ms=r.duracao_ms,
        tenant_id=r.tenant_id,
        excecao=r.excecao,
        metadados=r.metadados or {},
        criado_em=r.criado_em,
    )


def _corte(horas: int) -> datetime:
    return (datetime.now(timezone.utc) - timedelta(hours=horas)).replace(tzinfo=None)


class SqlLogRepository:
    """Leitura dos logs, com os filtros que o painel oferece."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def listar(
        self,
        *,
        nivel: NivelLog | None = None,
        logger_nome: str = "",
        correlacao_id: str = "",
        busca: str = "",
        tenant_id: uuid.UUID | None = None,
        apenas_falhas: bool = False,
        pagina: int = 1,
        por_pagina: int = 10,
    ) -> tuple[list[RegistroLog], int]:
        """Página de logs, mais recentes primeiro, com o total para o paginador."""
        filtros = []
        if nivel is not None:
            filtros.append(LogAplicacaoORM.nivel == nivel.value)
        if apenas_falhas:
            filtros.append(LogAplicacaoORM.nivel.in_(["ERROR", "CRITICAL"]))
        if logger_nome:
            filtros.append(LogAplicacaoORM.logger == logger_nome)
        if correlacao_id:
            filtros.append(LogAplicacaoORM.correlacao_id == correlacao_id)
        if tenant_id is not None:
            filtros.append(LogAplicacaoORM.tenant_id == tenant_id)
        if busca:
            filtros.append(LogAplicacaoORM.mensagem.ilike(f"%{busca}%"))

        total = (
            await self._s.execute(
                select(func.count()).select_from(LogAplicacaoORM).where(*filtros)
            )
        ).scalar_one()

        stmt = (
            select(LogAplicacaoORM)
            .where(*filtros)
            .order_by(LogAplicacaoORM.criado_em.desc())
            .offset(max(0, (pagina - 1) * por_pagina))
            .limit(por_pagina)
        )
        linhas = (await self._s.execute(stmt)).scalars().all()
        return [_para_registro(r) for r in linhas], int(total)

    async def loggers_disponiveis(self, *, janela_horas: int = 24) -> list[str]:
        """Loggers que apareceram na janela — alimenta o filtro do painel sem hardcode."""
        stmt = (
            select(LogAplicacaoORM.logger)
            .where(LogAplicacaoORM.criado_em >= _corte(janela_horas))
            .group_by(LogAplicacaoORM.logger)
            .order_by(func.count().desc())
            .limit(30)
        )
        return [n for n in (await self._s.execute(stmt)).scalars().all() if n]

    async def resumo(self, *, janela_horas: int = 24) -> ResumoLogs:
        corte = _corte(janela_horas)

        totais = (
            await self._s.execute(
                select(LogAplicacaoORM.nivel, func.count())
                .where(LogAplicacaoORM.criado_em >= corte)
                .group_by(LogAplicacaoORM.nivel)
            )
        ).all()
        por_nivel = {nivel: int(qtd) for nivel, qtd in totais}

        # Requisições = linhas com duração medida (as emitidas pelo middleware).
        duracoes = (
            await self._s.execute(
                select(
                    func.count(),
                    func.coalesce(func.avg(LogAplicacaoORM.duracao_ms), 0),
                    func.coalesce(
                        func.percentile_cont(0.95).within_group(
                            LogAplicacaoORM.duracao_ms.asc()
                        ),
                        0,
                    ),
                ).where(
                    LogAplicacaoORM.criado_em >= corte,
                    LogAplicacaoORM.duracao_ms.isnot(None),
                )
            )
        ).one()

        rotas = (
            await self._s.execute(
                select(
                    LogAplicacaoORM.rota,
                    cast(func.avg(LogAplicacaoORM.duracao_ms), Integer),
                )
                .where(
                    LogAplicacaoORM.criado_em >= corte,
                    LogAplicacaoORM.duracao_ms.isnot(None),
                    LogAplicacaoORM.rota != "",
                )
                .group_by(LogAplicacaoORM.rota)
                .order_by(func.avg(LogAplicacaoORM.duracao_ms).desc())
                .limit(5)
            )
        ).all()

        erros = (
            await self._s.execute(
                select(LogAplicacaoORM.mensagem, func.count())
                .where(
                    LogAplicacaoORM.criado_em >= corte,
                    LogAplicacaoORM.nivel.in_(["ERROR", "CRITICAL"]),
                )
                .group_by(LogAplicacaoORM.mensagem)
                .order_by(func.count().desc())
                .limit(5)
            )
        ).all()

        atendimentos = (
            await self._s.execute(
                select(InboundAtendimentoORM.status, func.count())
                .where(InboundAtendimentoORM.criado_em >= corte)
                .group_by(InboundAtendimentoORM.status)
            )
        ).all()
        por_status = {status: int(qtd) for status, qtd in atendimentos}

        return ResumoLogs(
            janela_horas=janela_horas,
            total=sum(por_nivel.values()),
            erros=por_nivel.get("ERROR", 0) + por_nivel.get("CRITICAL", 0),
            alertas=por_nivel.get("WARNING", 0),
            requisicoes=int(duracoes[0] or 0),
            duracao_media_ms=int(duracoes[1] or 0),
            duracao_p95_ms=int(duracoes[2] or 0),
            atendimentos_concluidos=por_status.get("concluida", 0),
            atendimentos_em_andamento=por_status.get("em_atendimento", 0),
            atendimentos_falhos=por_status.get("falhou", 0),
            rotas_mais_lentas=[
                ContagemRotulada(rotulo=rota, quantidade=int(media or 0))
                for rota, media in rotas
            ],
            erros_mais_comuns=[
                ContagemRotulada(rotulo=msg[:120], quantidade=int(qtd)) for msg, qtd in erros
            ],
        )

    async def atendimentos(
        self, *, status: str = "", limite: int = 30
    ) -> list[AtendimentoInbound]:
        """Últimos atendimentos do WhatsApp — a visão de "fila" do painel."""
        stmt = (
            select(InboundAtendimentoORM, TenantORM.nome)
            .outerjoin(TenantORM, TenantORM.id == InboundAtendimentoORM.tenant_id)
            .order_by(InboundAtendimentoORM.atualizado_em.desc())
            .limit(max(1, min(limite, 200)))
        )
        if status:
            stmt = stmt.where(InboundAtendimentoORM.status == status)
        linhas = (await self._s.execute(stmt)).all()
        return [
            AtendimentoInbound(
                chave=r.chave,
                status=r.status,
                origem=r.origem,
                resumo=r.resumo,
                criado_em=r.criado_em,
                atualizado_em=r.atualizado_em,
                tenant_id=r.tenant_id,
                tenant_nome=nome or "",
            )
            for r, nome in linhas
        ]
