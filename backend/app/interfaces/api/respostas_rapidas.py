"""Rotas das respostas rápidas ("atalhos") da escola.

CRUD escopado por tenant; cada resposta rápida é ingerida no RAG (ver
``respostas_rapidas_use_cases``). Reaproveita a autenticação por JWT e o controle de
tenant do módulo ``admin``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.respostas_rapidas_use_cases import (
    AtualizarRespostaRapida,
    CriarRespostaRapida,
    ListarRespostasRapidas,
    ObterRespostaRapida,
    RemoverRespostaRapida,
)
from app.config import Settings
from app.domain.entities import RespostaRapida, Usuario
from app.infrastructure.db.pgvector_store import PgVectorStore
from app.infrastructure.db.repositories_conhecimento import (
    SqlFonteConhecimentoRepository,
    SqlRespostaRapidaRepository,
)
from app.infrastructure.factories import criar_embedder
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import (
    get_resposta_rapida_repo,
    get_session,
    get_settings_dep,
)
from app.interfaces.dto import (
    RespostaRapidaAtualizar,
    RespostaRapidaEntrada,
    RespostaRapidaSaida,
)

router = APIRouter(prefix="/api/admin", tags=["respostas-rapidas"])


def _saida(r: RespostaRapida) -> RespostaRapidaSaida:
    return RespostaRapidaSaida(
        id=r.id,
        chave=r.chave,
        conteudo=r.conteudo,
        ativo=r.ativo,
        fonte_id=r.fonte_id,
        atualizado_em=r.atualizado_em,
    )


def _rag_kwargs(session: AsyncSession, settings: Settings) -> dict:
    """Portas de RAG compartilhadas pelos casos de uso que indexam/removem."""
    return {
        "embedder": criar_embedder(settings),
        "store": PgVectorStore(session),
        "fontes": SqlFonteConhecimentoRepository(session),
    }


@router.post(
    "/respostas-rapidas",
    response_model=RespostaRapidaSaida,
    status_code=status.HTTP_201_CREATED,
)
async def criar_resposta_rapida(
    payload: RespostaRapidaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    respostas: SqlRespostaRapidaRepository = Depends(get_resposta_rapida_repo),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> RespostaRapidaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        resposta = await CriarRespostaRapida(
            respostas=respostas, **_rag_kwargs(session, settings)
        ).executar(
            tenant_id=payload.tenant_id,
            chave=payload.chave,
            conteudo=payload.conteudo,
            ativo=payload.ativo,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(resposta)


@router.get(
    "/respostas-rapidas/tenant/{tenant_id}", response_model=list[RespostaRapidaSaida]
)
async def listar_respostas_rapidas(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    respostas: SqlRespostaRapidaRepository = Depends(get_resposta_rapida_repo),
) -> list[RespostaRapidaSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    return [
        _saida(r)
        for r in await ListarRespostasRapidas(respostas=respostas).executar(
            tenant_id=tenant_id
        )
    ]


@router.get("/respostas-rapidas/{resposta_id}", response_model=RespostaRapidaSaida)
async def obter_resposta_rapida(
    resposta_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    respostas: SqlRespostaRapidaRepository = Depends(get_resposta_rapida_repo),
) -> RespostaRapidaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        resposta = await ObterRespostaRapida(respostas=respostas).executar(
            tenant_id=tenant_id, resposta_id=resposta_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _saida(resposta)


@router.put("/respostas-rapidas/{resposta_id}", response_model=RespostaRapidaSaida)
async def atualizar_resposta_rapida(
    resposta_id: UUID,
    payload: RespostaRapidaAtualizar,
    usuario: Usuario = Depends(usuario_autenticado),
    respostas: SqlRespostaRapidaRepository = Depends(get_resposta_rapida_repo),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> RespostaRapidaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        resposta = await AtualizarRespostaRapida(
            respostas=respostas, **_rag_kwargs(session, settings)
        ).executar(
            tenant_id=payload.tenant_id,
            resposta_id=resposta_id,
            chave=payload.chave,
            conteudo=payload.conteudo,
            ativo=payload.ativo,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(resposta)


@router.delete("/respostas-rapidas/{resposta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_resposta_rapida(
    resposta_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    respostas: SqlRespostaRapidaRepository = Depends(get_resposta_rapida_repo),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings_dep),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverRespostaRapida(
        respostas=respostas, **_rag_kwargs(session, settings)
    ).executar(tenant_id=tenant_id, resposta_id=resposta_id)
    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Resposta rápida não encontrada"
        )
