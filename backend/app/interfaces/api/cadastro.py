"""Rotas de cadastro escolar: CRUD de pais/responsáveis e de salas (turmas),
vínculo pai↔sala e relatório de pais por sala.

Reaproveita a autenticação por JWT (``Authorization: Bearer``) e o controle de tenant
do módulo ``admin``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.cadastro_use_cases import (
    AtualizarPai,
    AtualizarSala,
    CadastrarPai,
    CriarSala,
    DesvincularPaiDaSala,
    ListarPais,
    ListarSalas,
    ObterSala,
    RelatorioPaisDaSala,
    RemoverPai,
    RemoverSala,
    VincularPaiASala,
)
from app.domain.entities import Contato, Sala, Usuario
from app.infrastructure.db.repositories_admin import SqlContatoRepository, SqlSalaRepository
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import get_contato_repo, get_sala_repo
from app.interfaces.dto import (
    PaiAtualizar,
    PaiEntrada,
    PaiSaida,
    SalaAtualizar,
    SalaEntrada,
    SalaSaida,
    VinculoPaiEntrada,
)

router = APIRouter(prefix="/api/admin", tags=["cadastro"])


def _pai_saida(c: Contato) -> PaiSaida:
    return PaiSaida(id=c.id, nome=c.nome, telefone=c.telefone)


def _sala_saida(s: Sala) -> SalaSaida:
    return SalaSaida(
        id=s.id,
        nome=s.nome,
        descricao=s.descricao,
        total_pais=len(s.pais),
        pais=[_pai_saida(c) for c in s.pais],
    )


# --------------------------------------------------------------------------- #
# Pais / responsáveis (CRUD)
# --------------------------------------------------------------------------- #
@router.post("/pais", response_model=PaiSaida, status_code=status.HTTP_201_CREATED)
async def cadastrar_pai(
    payload: PaiEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> PaiSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        contato = await CadastrarPai(contatos=contatos, salas=salas).executar(
            tenant_id=payload.tenant_id,
            nome=payload.nome,
            telefone=payload.telefone,
            sala_ids=payload.sala_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _pai_saida(contato)


@router.get("/pais/tenant/{tenant_id}", response_model=list[PaiSaida])
async def listar_pais(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> list[PaiSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    return [_pai_saida(c) for c in await ListarPais(contatos=contatos).executar(tenant_id=tenant_id)]


@router.put("/pais/{contato_id}", response_model=PaiSaida)
async def atualizar_pai(
    contato_id: UUID,
    payload: PaiAtualizar,
    usuario: Usuario = Depends(usuario_autenticado),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> PaiSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        contato = await AtualizarPai(contatos=contatos).executar(
            tenant_id=payload.tenant_id,
            contato_id=contato_id,
            nome=payload.nome,
            telefone=payload.telefone,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _pai_saida(contato)


@router.delete("/pais/{contato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_pai(
    contato_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverPai(contatos=contatos).executar(
        tenant_id=tenant_id, contato_id=contato_id
    )
    if not removido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Responsável não encontrado")


# --------------------------------------------------------------------------- #
# Salas / turmas (CRUD)
# --------------------------------------------------------------------------- #
@router.post("/salas", response_model=SalaSaida, status_code=status.HTTP_201_CREATED)
async def criar_sala(
    payload: SalaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> SalaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    sala = await CriarSala(salas=salas).executar(
        tenant_id=payload.tenant_id, nome=payload.nome, descricao=payload.descricao
    )
    return _sala_saida(sala)


@router.get("/salas/tenant/{tenant_id}", response_model=list[SalaSaida])
async def listar_salas(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> list[SalaSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    return [_sala_saida(s) for s in await ListarSalas(salas=salas).executar(tenant_id=tenant_id)]


@router.get("/salas/{sala_id}", response_model=SalaSaida)
async def obter_sala(
    sala_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> SalaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        sala = await ObterSala(salas=salas).executar(tenant_id=tenant_id, sala_id=sala_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _sala_saida(sala)


@router.put("/salas/{sala_id}", response_model=SalaSaida)
async def atualizar_sala(
    sala_id: UUID,
    payload: SalaAtualizar,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> SalaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        sala = await AtualizarSala(salas=salas).executar(
            tenant_id=payload.tenant_id,
            sala_id=sala_id,
            nome=payload.nome,
            descricao=payload.descricao,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _sala_saida(sala)


@router.delete("/salas/{sala_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_sala(
    sala_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverSala(salas=salas).executar(tenant_id=tenant_id, sala_id=sala_id)
    if not removido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sala não encontrada")


# --------------------------------------------------------------------------- #
# Vínculo pai ↔ sala e relatório de pais por sala
# --------------------------------------------------------------------------- #
@router.post("/salas/{sala_id}/pais", status_code=status.HTTP_204_NO_CONTENT)
async def vincular_pai(
    sala_id: UUID,
    payload: VinculoPaiEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> None:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        await VincularPaiASala(salas=salas).executar(
            tenant_id=payload.tenant_id, sala_id=sala_id, contato_id=payload.contato_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/salas/{sala_id}/pais/{contato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def desvincular_pai(
    sala_id: UUID,
    contato_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        await DesvincularPaiDaSala(salas=salas).executar(
            tenant_id=tenant_id, sala_id=sala_id, contato_id=contato_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/salas/{sala_id}/pais", response_model=list[PaiSaida])
async def relatorio_pais_da_sala(
    sala_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> list[PaiSaida]:
    """Relatório/lista dos pais/responsáveis vinculados a uma sala específica."""
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        pais = await RelatorioPaisDaSala(salas=salas).executar(tenant_id=tenant_id, sala_id=sala_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return [_pai_saida(c) for c in pais]
