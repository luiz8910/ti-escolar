"""Rotas dos avisos temporizados da escola (resposta automática do bot).

CRUD escopado por tenant; um aviso vigente é anexado à resposta do bot ao inbound.
Reaproveita a autenticação por JWT e o controle de tenant do módulo ``admin``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.avisos_use_cases import (
    AtualizarAvisoTemporizado,
    CriarAvisoTemporizado,
    ListarAvisosTemporizados,
    ObterAvisoTemporizado,
    RemoverAvisoTemporizado,
)
from app.domain.entities import AvisoTemporizado, Usuario
from app.infrastructure.db.repositories_comunicacao import SqlAvisoTemporizadoRepository
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import get_aviso_repo
from app.interfaces.dto import (
    AvisoTemporizadoAtualizar,
    AvisoTemporizadoEntrada,
    AvisoTemporizadoSaida,
)

router = APIRouter(prefix="/api/admin", tags=["avisos"])


def _saida(a: AvisoTemporizado) -> AvisoTemporizadoSaida:
    return AvisoTemporizadoSaida(
        id=a.id,
        mensagem=a.mensagem,
        ativo=a.ativo,
        inicia_em=a.inicia_em,
        expira_em=a.expira_em,
        vigente=a.vigente_em(),
        atualizado_em=a.atualizado_em,
    )


@router.post(
    "/avisos", response_model=AvisoTemporizadoSaida, status_code=status.HTTP_201_CREATED
)
async def criar_aviso(
    payload: AvisoTemporizadoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    avisos: SqlAvisoTemporizadoRepository = Depends(get_aviso_repo),
) -> AvisoTemporizadoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        aviso = await CriarAvisoTemporizado(avisos=avisos).executar(
            tenant_id=payload.tenant_id,
            mensagem=payload.mensagem,
            ativo=payload.ativo,
            inicia_em=payload.inicia_em,
            expira_em=payload.expira_em,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(aviso)


@router.get("/avisos/tenant/{tenant_id}", response_model=list[AvisoTemporizadoSaida])
async def listar_avisos(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    avisos: SqlAvisoTemporizadoRepository = Depends(get_aviso_repo),
) -> list[AvisoTemporizadoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    return [
        _saida(a)
        for a in await ListarAvisosTemporizados(avisos=avisos).executar(tenant_id=tenant_id)
    ]


@router.get("/avisos/{aviso_id}", response_model=AvisoTemporizadoSaida)
async def obter_aviso(
    aviso_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    avisos: SqlAvisoTemporizadoRepository = Depends(get_aviso_repo),
) -> AvisoTemporizadoSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        aviso = await ObterAvisoTemporizado(avisos=avisos).executar(
            tenant_id=tenant_id, aviso_id=aviso_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _saida(aviso)


@router.put("/avisos/{aviso_id}", response_model=AvisoTemporizadoSaida)
async def atualizar_aviso(
    aviso_id: UUID,
    payload: AvisoTemporizadoAtualizar,
    usuario: Usuario = Depends(usuario_autenticado),
    avisos: SqlAvisoTemporizadoRepository = Depends(get_aviso_repo),
) -> AvisoTemporizadoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        aviso = await AtualizarAvisoTemporizado(avisos=avisos).executar(
            tenant_id=payload.tenant_id,
            aviso_id=aviso_id,
            mensagem=payload.mensagem,
            ativo=payload.ativo,
            inicia_em=payload.inicia_em,
            expira_em=payload.expira_em,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(aviso)


@router.delete("/avisos/{aviso_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_aviso(
    aviso_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    avisos: SqlAvisoTemporizadoRepository = Depends(get_aviso_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverAvisoTemporizado(avisos=avisos).executar(
        tenant_id=tenant_id, aviso_id=aviso_id
    )
    if not removido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aviso não encontrado")
