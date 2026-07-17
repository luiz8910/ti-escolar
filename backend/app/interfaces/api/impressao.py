"""Rotas da fila de impressão (solicitações dos professores à secretaria).

CRUD escopado por tenant, protegido pela autenticação por JWT do módulo ``admin``
(a secretaria/administração gerencia a fila). A submissão pelo próprio professor
autenticado é adicionada no mural do professor (§A1).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.impressao_use_cases import (
    AtualizarStatusImpressao,
    ListarFilaImpressao,
    ObterSolicitacaoImpressao,
    RemoverSolicitacaoImpressao,
    SolicitarImpressao,
)
from app.domain.entities import SolicitacaoImpressao, StatusImpressao, Usuario
from app.infrastructure.db.repositories_admin import SqlProfessorRepository
from app.infrastructure.db.repositories_comunicacao import (
    SqlSolicitacaoImpressaoRepository,
)
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import get_impressao_repo, get_professor_repo
from app.interfaces.dto import (
    ImpressaoEntrada,
    ImpressaoSaida,
    ImpressaoStatusEntrada,
)

router = APIRouter(prefix="/api/admin", tags=["impressao"])


def _saida(s: SolicitacaoImpressao) -> ImpressaoSaida:
    return ImpressaoSaida(
        id=s.id,
        professor_id=s.professor_id,
        professor_nome=s.professor_nome,
        arquivo_nome=s.arquivo_nome,
        arquivo_url=s.arquivo_url,
        copias=s.copias,
        colorido=s.colorido,
        frente_verso=s.frente_verso,
        observacao=s.observacao,
        status=s.status.value,
        criado_em=s.criado_em,
        atualizado_em=s.atualizado_em,
    )


def _parse_status(bruto: str) -> StatusImpressao:
    try:
        return StatusImpressao(bruto)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Status inválido: {bruto}. Use pendente, em_processo, concluida ou cancelada."
            ),
        ) from e


@router.post("/impressao", response_model=ImpressaoSaida, status_code=status.HTTP_201_CREATED)
async def solicitar_impressao(
    payload: ImpressaoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoImpressaoRepository = Depends(get_impressao_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> ImpressaoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        solicitacao = await SolicitarImpressao(
            solicitacoes=solicitacoes, professores=professores
        ).executar(
            tenant_id=payload.tenant_id,
            arquivo_nome=payload.arquivo_nome,
            professor_id=payload.professor_id,
            arquivo_url=payload.arquivo_url,
            copias=payload.copias,
            colorido=payload.colorido,
            frente_verso=payload.frente_verso,
            observacao=payload.observacao,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(solicitacao)


@router.get("/impressao/tenant/{tenant_id}", response_model=list[ImpressaoSaida])
async def listar_fila_impressao(
    tenant_id: UUID,
    status_filtro: str | None = None,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoImpressaoRepository = Depends(get_impressao_repo),
) -> list[ImpressaoSaida]:
    """Fila de impressão do tenant. ``?status_filtro=`` limita por status."""
    _exige_acesso_tenant(usuario, tenant_id)
    filtro = _parse_status(status_filtro) if status_filtro else None
    fila = await ListarFilaImpressao(solicitacoes=solicitacoes).executar(
        tenant_id=tenant_id, status=filtro
    )
    return [_saida(s) for s in fila]


@router.get("/impressao/{solicitacao_id}", response_model=ImpressaoSaida)
async def obter_impressao(
    solicitacao_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoImpressaoRepository = Depends(get_impressao_repo),
) -> ImpressaoSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        solicitacao = await ObterSolicitacaoImpressao(solicitacoes=solicitacoes).executar(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _saida(solicitacao)


@router.put("/impressao/{solicitacao_id}/status", response_model=ImpressaoSaida)
async def atualizar_status_impressao(
    solicitacao_id: UUID,
    payload: ImpressaoStatusEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoImpressaoRepository = Depends(get_impressao_repo),
) -> ImpressaoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    novo_status = _parse_status(payload.status)
    try:
        solicitacao = await AtualizarStatusImpressao(solicitacoes=solicitacoes).executar(
            tenant_id=payload.tenant_id, solicitacao_id=solicitacao_id, status=novo_status
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _saida(solicitacao)


@router.delete("/impressao/{solicitacao_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_impressao(
    solicitacao_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoImpressaoRepository = Depends(get_impressao_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverSolicitacaoImpressao(solicitacoes=solicitacoes).executar(
        tenant_id=tenant_id, solicitacao_id=solicitacao_id
    )
    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Solicitação não encontrada"
        )
