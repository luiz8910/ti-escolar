"""Painel de logs — auditoria operacional do super admin (§16).

**Exclusivo do super admin**, como `/api/admin/seguranca`. O log cru é cross-tenant por
natureza (uma falha de roteamento do inbound não pertence a escola nenhuma) e carrega
detalhe de infraestrutura — traceback, rota, id interno — que não é material para a
secretaria da escola.

O que a escola precisa ver do próprio funcionamento continua em HISTÓRICO (§13):
conversas, disparos e auditoria de ações, tudo escopado por tenant.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.logs_use_cases import (
    POR_PAGINA_PADRAO,
    ListarAtendimentosInbound,
    ListarLogs,
    ResumoObservabilidade,
)
from app.domain.entities import AtendimentoInbound, RegistroLog, ResumoLogs, Usuario
from app.infrastructure.db.repositories_logs import SqlLogRepository
from app.interfaces.api.admin import _exige_super_admin, usuario_autenticado
from app.interfaces.deps import get_session
from app.interfaces.dto import (
    AtendimentoInboundSaida,
    ContagemSaida,
    LogSaida,
    LogsPaginaSaida,
    PaginaMeta,
    ResumoLogsSaida,
)

router = APIRouter(prefix="/api/admin/logs", tags=["admin"])


def _log_saida(r: RegistroLog) -> LogSaida:
    return LogSaida(
        id=r.id,
        criado_em=r.criado_em,
        nivel=r.nivel.value,
        logger=r.logger,
        mensagem=r.mensagem,
        correlacao_id=r.correlacao_id,
        rota=r.rota,
        metodo=r.metodo,
        status_code=r.status_code,
        duracao_ms=r.duracao_ms,
        tenant_id=r.tenant_id,
        excecao=r.excecao,
        metadados=r.metadados,
    )


def _resumo_saida(r: ResumoLogs) -> ResumoLogsSaida:
    return ResumoLogsSaida(
        janela_horas=r.janela_horas,
        total=r.total,
        erros=r.erros,
        alertas=r.alertas,
        requisicoes=r.requisicoes,
        duracao_media_ms=r.duracao_media_ms,
        duracao_p95_ms=r.duracao_p95_ms,
        taxa_erro_percentual=r.taxa_erro_percentual,
        saudavel=r.saudavel,
        atendimentos_concluidos=r.atendimentos_concluidos,
        atendimentos_em_andamento=r.atendimentos_em_andamento,
        atendimentos_falhos=r.atendimentos_falhos,
        rotas_mais_lentas=[
            ContagemSaida(rotulo=c.rotulo, quantidade=c.quantidade) for c in r.rotas_mais_lentas
        ],
        erros_mais_comuns=[
            ContagemSaida(rotulo=c.rotulo, quantidade=c.quantidade) for c in r.erros_mais_comuns
        ],
    )


def _atendimento_saida(a: AtendimentoInbound) -> AtendimentoInboundSaida:
    return AtendimentoInboundSaida(
        chave=a.chave,
        status=a.status,
        origem=a.origem,
        resumo=a.resumo,
        tenant_id=a.tenant_id,
        tenant_nome=a.tenant_nome,
        criado_em=a.criado_em,
        atualizado_em=a.atualizado_em,
    )


@router.get("/resumo", response_model=ResumoLogsSaida)
async def resumo(
    janela_horas: int = Query(24, ge=1, le=720),
    solicitante: Usuario = Depends(usuario_autenticado),
    session: AsyncSession = Depends(get_session),
) -> ResumoLogsSaida:
    _exige_super_admin(solicitante)
    dados = await ResumoObservabilidade(SqlLogRepository(session)).executar(
        janela_horas=janela_horas
    )
    return _resumo_saida(dados)


@router.get("", response_model=LogsPaginaSaida)
async def listar(
    nivel: str = "",
    logger_nome: str = "",
    correlacao_id: str = "",
    busca: str = "",
    tenant_id: UUID | None = None,
    apenas_falhas: bool = False,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA_PADRAO, ge=1, le=200),
    solicitante: Usuario = Depends(usuario_autenticado),
    session: AsyncSession = Depends(get_session),
) -> LogsPaginaSaida:
    _exige_super_admin(solicitante)
    pagina_logs = await ListarLogs(SqlLogRepository(session)).executar(
        nivel=nivel,
        logger_nome=logger_nome,
        correlacao_id=correlacao_id,
        busca=busca,
        tenant_id=tenant_id,
        apenas_falhas=apenas_falhas,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return LogsPaginaSaida(
        itens=[_log_saida(r) for r in pagina_logs.itens],
        meta=PaginaMeta(
            pagina=pagina_logs.pagina,
            por_pagina=pagina_logs.por_pagina,
            total=pagina_logs.total,
            total_paginas=pagina_logs.total_paginas,
        ),
        loggers=pagina_logs.loggers,
    )


@router.get("/atendimentos", response_model=list[AtendimentoInboundSaida])
async def atendimentos(
    status: str = "",
    limite: int = Query(30, ge=1, le=200),
    solicitante: Usuario = Depends(usuario_autenticado),
    session: AsyncSession = Depends(get_session),
) -> list[AtendimentoInboundSaida]:
    """Fila de atendimentos do WhatsApp: o que concluiu, o que está em curso, o que falhou."""
    _exige_super_admin(solicitante)
    itens = await ListarAtendimentosInbound(SqlLogRepository(session)).executar(
        status=status, limite=limite
    )
    return [_atendimento_saida(a) for a in itens]
