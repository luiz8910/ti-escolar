"""Rotas da matrícula self-service pelo WhatsApp (§E1).

A secretaria (ou um futuro webhook de inbound) inicia a matrícula de um responsável, que
recebe a lista de documentos e envia fotos/scan; a secretaria acompanha e conclui apenas
para a assinatura presencial. Guardadas por ``_exige_acesso_tenant``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.matricula_use_cases import (
    AnexarDocumentoMatricula,
    AtualizarStatusMatricula,
    IniciarMatricula,
    ListarMatriculas,
    montar_mensagem_documentos,
)
from app.domain.entities import SolicitacaoMatricula, StatusMatricula, Usuario
from app.infrastructure.db.repositories_onda3 import SqlSolicitacaoMatriculaRepository
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import get_matricula_repo
from app.interfaces.dto import (
    DocumentoMatriculaSaida,
    MatriculaDocumentoEntrada,
    MatriculaIniciarEntrada,
    MatriculaIniciarSaida,
    MatriculaSaida,
    MatriculaStatusEntrada,
)

router = APIRouter(prefix="/api/admin/matriculas", tags=["matricula"])


def _saida(s: SolicitacaoMatricula) -> MatriculaSaida:
    return MatriculaSaida(
        id=s.id,
        contato_telefone=s.contato_telefone,
        nome_responsavel=s.nome_responsavel,
        nome_aluno=s.nome_aluno,
        status=s.status.value,
        observacao=s.observacao,
        documentos=[
            DocumentoMatriculaSaida(nome=d.nome, url=d.url, recebido_em=d.recebido_em)
            for d in s.documentos
        ],
        criado_em=s.criado_em,
        atualizado_em=s.atualizado_em,
    )


@router.post("/iniciar", response_model=MatriculaIniciarSaida, status_code=status.HTTP_201_CREATED)
async def iniciar(
    payload: MatriculaIniciarEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    matriculas: SqlSolicitacaoMatriculaRepository = Depends(get_matricula_repo),
) -> MatriculaIniciarSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        solicitacao = await IniciarMatricula(matriculas=matriculas).executar(
            tenant_id=payload.tenant_id,
            contato_telefone=payload.contato_telefone,
            nome_responsavel=payload.nome_responsavel,
            nome_aluno=payload.nome_aluno,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return MatriculaIniciarSaida(
        solicitacao=_saida(solicitacao),
        mensagem=montar_mensagem_documentos(solicitacao.nome_responsavel),
    )


@router.get("/tenant/{tenant_id}", response_model=list[MatriculaSaida])
async def listar(
    tenant_id: UUID,
    status_filtro: str | None = Query(default=None, alias="status"),
    usuario: Usuario = Depends(usuario_autenticado),
    matriculas: SqlSolicitacaoMatriculaRepository = Depends(get_matricula_repo),
) -> list[MatriculaSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    filtro = StatusMatricula(status_filtro) if status_filtro else None
    itens = await ListarMatriculas(matriculas=matriculas).executar(
        tenant_id=tenant_id, status=filtro
    )
    return [_saida(s) for s in itens]


@router.post("/{solicitacao_id}/documentos", response_model=MatriculaSaida)
async def anexar_documento(
    solicitacao_id: UUID,
    payload: MatriculaDocumentoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    matriculas: SqlSolicitacaoMatriculaRepository = Depends(get_matricula_repo),
) -> MatriculaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        solicitacao = await AnexarDocumentoMatricula(matriculas=matriculas).executar(
            tenant_id=payload.tenant_id,
            solicitacao_id=solicitacao_id,
            nome=payload.nome,
            url=payload.url,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(solicitacao)


@router.put("/{solicitacao_id}/status", response_model=MatriculaSaida)
async def atualizar_status(
    solicitacao_id: UUID,
    payload: MatriculaStatusEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    matriculas: SqlSolicitacaoMatriculaRepository = Depends(get_matricula_repo),
) -> MatriculaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        novo_status = StatusMatricula(payload.status)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Status inválido."
        ) from e
    try:
        solicitacao = await AtualizarStatusMatricula(matriculas=matriculas).executar(
            tenant_id=payload.tenant_id,
            solicitacao_id=solicitacao_id,
            status=novo_status,
            observacao=payload.observacao,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(solicitacao)
