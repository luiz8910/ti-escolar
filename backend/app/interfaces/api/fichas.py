"""Rotas administrativas da ficha de matrícula digital (§D1/D2/D3).

CRUD da ficha (frente + verso + campos sensíveis) por aluno e o fluxo de leitura por IA
(prévia → confirmação): o texto/OCR de uma foto/PDF é normalizado pela LLM, validado em
código e revisado antes de gravar. Guardadas por ``_exige_acesso_tenant``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.ficha_use_cases import (
    ConfirmarFichaMatricula,
    ObterFichaMatricula,
    PrevisualizarFichaMatricula,
    RemoverFichaMatricula,
    SalvarFichaMatricula,
)
from app.domain.entities import CAMPOS_FICHA_MATRICULA, FichaMatricula, Usuario
from app.domain.ports import LLMProvider
from app.infrastructure.db.repositories_admin import SqlAlunoRepository
from app.infrastructure.db.repositories_onda3 import SqlFichaMatriculaRepository
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import get_aluno_repo, get_ficha_repo, get_llm
from app.interfaces.dto import (
    FichaConfirmarEntrada,
    FichaEntrada,
    FichaPreviaEntrada,
    FichaPreviaSaida,
    FichaSaida,
)

router = APIRouter(prefix="/api/admin/fichas", tags=["fichas"])


def _campos(ficha: FichaMatricula) -> dict:
    return {campo: getattr(ficha, campo) for campo in CAMPOS_FICHA_MATRICULA}


def _saida(ficha: FichaMatricula) -> FichaSaida:
    return FichaSaida(
        aluno_id=ficha.aluno_id,
        aluno_nome=ficha.aluno_nome,
        campos=_campos(ficha),
        atualizado_em=ficha.atualizado_em,
    )


@router.post("", response_model=FichaSaida, status_code=status.HTTP_201_CREATED)
async def salvar(
    payload: FichaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    fichas: SqlFichaMatriculaRepository = Depends(get_ficha_repo),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> FichaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        ficha = await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
            tenant_id=payload.tenant_id, aluno_id=payload.aluno_id, campos=payload.campos
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(ficha)


@router.get("/aluno/{aluno_id}", response_model=FichaSaida)
async def obter(
    aluno_id: UUID,
    tenant_id: UUID = Query(...),
    usuario: Usuario = Depends(usuario_autenticado),
    fichas: SqlFichaMatriculaRepository = Depends(get_ficha_repo),
) -> FichaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    ficha = await ObterFichaMatricula(fichas=fichas).executar(
        tenant_id=tenant_id, aluno_id=aluno_id
    )
    if ficha is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ficha não encontrada."
        )
    return _saida(ficha)


@router.delete("/aluno/{aluno_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover(
    aluno_id: UUID,
    tenant_id: UUID = Query(...),
    usuario: Usuario = Depends(usuario_autenticado),
    fichas: SqlFichaMatriculaRepository = Depends(get_ficha_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removeu = await RemoverFichaMatricula(fichas=fichas).executar(
        tenant_id=tenant_id, aluno_id=aluno_id
    )
    if not removeu:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Ficha não encontrada."
        )


@router.post("/importar/previa", response_model=FichaPreviaSaida)
async def importar_previa(
    payload: FichaPreviaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    llm: LLMProvider = Depends(get_llm),
) -> FichaPreviaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        previa = await PrevisualizarFichaMatricula(llm=llm).executar(
            tenant_id=payload.tenant_id, conteudo=payload.conteudo
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return FichaPreviaSaida(
        campos=previa.campos,
        avisos=previa.avisos,
        erros=previa.erros,
        valido=previa.valido,
    )


@router.post("/importar/confirmar", response_model=FichaSaida)
async def importar_confirmar(
    payload: FichaConfirmarEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    fichas: SqlFichaMatriculaRepository = Depends(get_ficha_repo),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> FichaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        ficha = await ConfirmarFichaMatricula(fichas=fichas, alunos=alunos).executar(
            tenant_id=payload.tenant_id, aluno_id=payload.aluno_id, campos=payload.campos
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(ficha)
