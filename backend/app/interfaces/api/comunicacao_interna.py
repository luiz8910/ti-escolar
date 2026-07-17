"""Rotas do canal interno professor → secretaria/gestão/pedagógico (§A2/A4).

Visão da **escola** (secretaria/gestão), escopada por tenant e protegida pela
autenticação por JWT do módulo ``admin``. A abertura e o acompanhamento pelo próprio
professor autenticado ficam em ``professor.py``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.comunicacao_interna_use_cases import (
    AbrirSolicitacaoInterna,
    AtualizarStatusSolicitacaoInterna,
    ListarSolicitacoesInternas,
    ObterSolicitacaoInterna,
    RemoverSolicitacaoInterna,
    ResponderSolicitacaoInterna,
)
from app.domain.entities import (
    CategoriaSolicitacao,
    SolicitacaoInterna,
    StatusSolicitacaoInterna,
    Usuario,
)
from app.domain.ports import MessageChannel
from app.infrastructure.db.repositories_admin import SqlProfessorRepository
from app.infrastructure.db.repositories_comunicacao import (
    SqlSolicitacaoInternaRepository,
)
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import (
    get_canal,
    get_professor_repo,
    get_solicitacao_interna_repo,
)
from app.interfaces.dto import (
    SolicitacaoInternaEntrada,
    SolicitacaoInternaRespostaEntrada,
    SolicitacaoInternaSaida,
    SolicitacaoInternaStatusEntrada,
)

router = APIRouter(prefix="/api/admin", tags=["comunicacao-interna"])


def _saida(s: SolicitacaoInterna) -> SolicitacaoInternaSaida:
    return SolicitacaoInternaSaida(
        id=s.id,
        professor_id=s.professor_id,
        professor_nome=s.professor_nome,
        assunto=s.assunto,
        corpo=s.corpo,
        categoria=s.categoria.value,
        status=s.status.value,
        resposta=s.resposta,
        respondido_em=s.respondido_em,
        criado_em=s.criado_em,
        atualizado_em=s.atualizado_em,
    )


def _parse_categoria(bruto: str | None) -> CategoriaSolicitacao | None:
    if bruto is None:
        return None
    try:
        return CategoriaSolicitacao(bruto)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Categoria inválida. Use secretaria, gestao ou pedagogico.",
        ) from e


def _parse_status(bruto: str | None) -> StatusSolicitacaoInterna | None:
    if bruto is None:
        return None
    try:
        return StatusSolicitacaoInterna(bruto)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Status inválido. Use aberta, em_andamento, resolvida ou cancelada.",
        ) from e


@router.post(
    "/solicitacoes-internas",
    response_model=SolicitacaoInternaSaida,
    status_code=status.HTTP_201_CREATED,
)
async def abrir_solicitacao(
    payload: SolicitacaoInternaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoInternaRepository = Depends(get_solicitacao_interna_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> SolicitacaoInternaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    categoria = _parse_categoria(payload.categoria) or CategoriaSolicitacao.SECRETARIA
    try:
        solicitacao = await AbrirSolicitacaoInterna(
            solicitacoes=solicitacoes, professores=professores
        ).executar(
            tenant_id=payload.tenant_id,
            assunto=payload.assunto,
            corpo=payload.corpo,
            professor_id=payload.professor_id,
            categoria=categoria,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(solicitacao)


@router.get(
    "/solicitacoes-internas/tenant/{tenant_id}",
    response_model=list[SolicitacaoInternaSaida],
)
async def listar_solicitacoes(
    tenant_id: UUID,
    categoria: str | None = None,
    status_filtro: str | None = None,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoInternaRepository = Depends(get_solicitacao_interna_repo),
) -> list[SolicitacaoInternaSaida]:
    """Canal interno do tenant. ``?categoria=`` e ``?status_filtro=`` são opcionais."""
    _exige_acesso_tenant(usuario, tenant_id)
    itens = await ListarSolicitacoesInternas(solicitacoes=solicitacoes).executar(
        tenant_id=tenant_id,
        categoria=_parse_categoria(categoria),
        status=_parse_status(status_filtro),
    )
    return [_saida(s) for s in itens]


@router.get(
    "/solicitacoes-internas/{solicitacao_id}",
    response_model=SolicitacaoInternaSaida,
)
async def obter_solicitacao(
    solicitacao_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoInternaRepository = Depends(get_solicitacao_interna_repo),
) -> SolicitacaoInternaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        solicitacao = await ObterSolicitacaoInterna(solicitacoes=solicitacoes).executar(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _saida(solicitacao)


@router.put(
    "/solicitacoes-internas/{solicitacao_id}/status",
    response_model=SolicitacaoInternaSaida,
)
async def atualizar_status(
    solicitacao_id: UUID,
    payload: SolicitacaoInternaStatusEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoInternaRepository = Depends(get_solicitacao_interna_repo),
) -> SolicitacaoInternaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    novo_status = _parse_status(payload.status)
    if novo_status is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Status obrigatório.")
    try:
        solicitacao = await AtualizarStatusSolicitacaoInterna(
            solicitacoes=solicitacoes
        ).executar(
            tenant_id=payload.tenant_id,
            solicitacao_id=solicitacao_id,
            status=novo_status,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _saida(solicitacao)


@router.post(
    "/solicitacoes-internas/{solicitacao_id}/responder",
    response_model=SolicitacaoInternaSaida,
)
async def responder_solicitacao(
    solicitacao_id: UUID,
    payload: SolicitacaoInternaRespostaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoInternaRepository = Depends(get_solicitacao_interna_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
    canal: MessageChannel = Depends(get_canal),
) -> SolicitacaoInternaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        solicitacao = await ResponderSolicitacaoInterna(
            solicitacoes=solicitacoes, professores=professores, canal=canal
        ).executar(
            tenant_id=payload.tenant_id,
            solicitacao_id=solicitacao_id,
            resposta=payload.resposta,
            notificar=payload.notificar,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(solicitacao)


@router.delete(
    "/solicitacoes-internas/{solicitacao_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remover_solicitacao(
    solicitacao_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoInternaRepository = Depends(get_solicitacao_interna_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverSolicitacaoInterna(solicitacoes=solicitacoes).executar(
        tenant_id=tenant_id, solicitacao_id=solicitacao_id
    )
    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Solicitação não encontrada"
        )
