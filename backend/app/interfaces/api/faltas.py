"""Rotas administrativas de aviso de falta e chamada de eventual (§I1).

A secretaria registra a falta, dispara o pedido de eventual (substituto) para uma lista
de candidatos, confirma quem cobre e pode cancelar. O professor também pode registrar a
própria falta pelo portal (ver ``professor.py``).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.falta_use_cases import (
    CancelarFalta,
    ChamarEventual,
    ConfirmarEventual,
    ListarFaltas,
    RegistrarFaltaProfessor,
)
from app.domain.entities import AvisoFalta, StatusFalta, Usuario
from app.domain.ports import MessageChannel
from app.infrastructure.db.repositories_admin import (
    SqlProfessorRepository,
    SqlTenantRepository,
)
from app.infrastructure.db.repositories_onda3 import SqlAvisoFaltaRepository
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import (
    get_canal,
    get_falta_repo,
    get_professor_repo,
    get_tenant_repo,
)
from app.interfaces.dto import (
    ChamarEventualEntrada,
    ConfirmarEventualEntrada,
    FaltaAcaoEntrada,
    FaltaEntrada,
    FaltaSaida,
)

router = APIRouter(prefix="/api/admin/faltas", tags=["faltas"])


def _saida(a: AvisoFalta) -> FaltaSaida:
    return FaltaSaida(
        id=a.id,
        data=a.data,
        motivo=a.motivo,
        professor_id=a.professor_id,
        professor_nome=a.professor_nome,
        status=a.status.value,
        eventual_nome=a.eventual_nome,
        eventual_telefone=a.eventual_telefone,
        eventuais_chamados=list(a.eventuais_chamados),
        criado_em=a.criado_em,
        atualizado_em=a.atualizado_em,
    )


@router.post("", response_model=FaltaSaida, status_code=status.HTTP_201_CREATED)
async def registrar(
    payload: FaltaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    faltas: SqlAvisoFaltaRepository = Depends(get_falta_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> FaltaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        aviso = await RegistrarFaltaProfessor(
            faltas=faltas, professores=professores
        ).executar(
            tenant_id=payload.tenant_id,
            data=payload.data,
            motivo=payload.motivo,
            professor_id=payload.professor_id,
            professor_nome=payload.professor_nome,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(aviso)


@router.get("/tenant/{tenant_id}", response_model=list[FaltaSaida])
async def listar(
    tenant_id: UUID,
    status_filtro: str | None = Query(default=None, alias="status"),
    usuario: Usuario = Depends(usuario_autenticado),
    faltas: SqlAvisoFaltaRepository = Depends(get_falta_repo),
) -> list[FaltaSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    filtro = StatusFalta(status_filtro) if status_filtro else None
    avisos = await ListarFaltas(faltas=faltas).executar(tenant_id=tenant_id, status=filtro)
    return [_saida(a) for a in avisos]


@router.post("/{aviso_id}/chamar-eventual", response_model=FaltaSaida)
async def chamar_eventual(
    aviso_id: UUID,
    payload: ChamarEventualEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    faltas: SqlAvisoFaltaRepository = Depends(get_falta_repo),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
    canal: MessageChannel = Depends(get_canal),
) -> FaltaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        aviso = await ChamarEventual(faltas=faltas, canal=canal, tenants=tenants).executar(
            tenant_id=payload.tenant_id,
            aviso_id=aviso_id,
            telefones=payload.telefones,
            mensagem=payload.mensagem,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(aviso)


@router.post("/{aviso_id}/confirmar", response_model=FaltaSaida)
async def confirmar(
    aviso_id: UUID,
    payload: ConfirmarEventualEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    faltas: SqlAvisoFaltaRepository = Depends(get_falta_repo),
) -> FaltaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        aviso = await ConfirmarEventual(faltas=faltas).executar(
            tenant_id=payload.tenant_id,
            aviso_id=aviso_id,
            eventual_nome=payload.eventual_nome,
            eventual_telefone=payload.eventual_telefone,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(aviso)


@router.post("/{aviso_id}/cancelar", response_model=FaltaSaida)
async def cancelar(
    aviso_id: UUID,
    payload: FaltaAcaoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    faltas: SqlAvisoFaltaRepository = Depends(get_falta_repo),
) -> FaltaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        aviso = await CancelarFalta(faltas=faltas).executar(
            tenant_id=payload.tenant_id, aviso_id=aviso_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(aviso)
