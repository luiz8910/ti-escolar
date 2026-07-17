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
    DefinirCotaImpressao,
    ListarCotasImpressao,
    ListarFilaImpressao,
    ObterSolicitacaoImpressao,
    RelatorioImpressaoMensal,
    RemoverCotaImpressao,
    RemoverSolicitacaoImpressao,
    SolicitarImpressao,
)
from app.domain.entities import (
    CotaImpressao,
    RelatorioImpressao,
    SolicitacaoImpressao,
    StatusImpressao,
    Usuario,
)
from app.infrastructure.db.repositories_admin import SqlProfessorRepository
from app.infrastructure.db.repositories_comunicacao import (
    SqlCotaImpressaoRepository,
    SqlSolicitacaoImpressaoRepository,
)
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import (
    get_cota_impressao_repo,
    get_impressao_repo,
    get_professor_repo,
)
from app.interfaces.dto import (
    CotaImpressaoEntrada,
    CotaImpressaoSaida,
    ImpressaoEntrada,
    ImpressaoSaida,
    ImpressaoStatusEntrada,
    LinhaRelatorioImpressaoSaida,
    RelatorioImpressaoSaida,
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


# --------------------------------------------------------------------------- #
# B2 · Cota (franquia mensal) e relatório de impressões por professor
# --------------------------------------------------------------------------- #
def _cota_saida(c: CotaImpressao) -> CotaImpressaoSaida:
    return CotaImpressaoSaida(
        id=c.id,
        professor_id=c.professor_id,
        professor_nome=c.professor_nome,
        limite_mensal=c.limite_mensal,
        ilimitado=c.ilimitado,
    )


def _relatorio_saida(r: RelatorioImpressao) -> RelatorioImpressaoSaida:
    return RelatorioImpressaoSaida(
        competencia=r.competencia,
        total_copias=r.total_copias,
        total_solicitacoes=r.total_solicitacoes,
        linhas=[
            LinhaRelatorioImpressaoSaida(
                professor_id=linha.professor_id,
                professor_nome=linha.professor_nome,
                total_solicitacoes=linha.total_solicitacoes,
                total_copias=linha.total_copias,
                limite_mensal=linha.limite_mensal,
                ilimitado=linha.ilimitado,
                excedeu=linha.excedeu,
                restante=linha.restante,
            )
            for linha in r.linhas
        ],
    )


@router.put("/impressao/cotas", response_model=CotaImpressaoSaida)
async def definir_cota_impressao(
    payload: CotaImpressaoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    cotas: SqlCotaImpressaoRepository = Depends(get_cota_impressao_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> CotaImpressaoSaida:
    """Define/atualiza a franquia mensal de cópias de um professor (0 = sem limite)."""
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        cota = await DefinirCotaImpressao(
            cotas=cotas, professores=professores
        ).executar(
            tenant_id=payload.tenant_id,
            professor_id=payload.professor_id,
            limite_mensal=payload.limite_mensal,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _cota_saida(cota)


@router.get("/impressao/cotas/tenant/{tenant_id}", response_model=list[CotaImpressaoSaida])
async def listar_cotas_impressao(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    cotas: SqlCotaImpressaoRepository = Depends(get_cota_impressao_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> list[CotaImpressaoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    itens = await ListarCotasImpressao(cotas=cotas, professores=professores).executar(
        tenant_id=tenant_id
    )
    return [_cota_saida(c) for c in itens]


@router.delete(
    "/impressao/cotas/{professor_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def remover_cota_impressao(
    professor_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    cotas: SqlCotaImpressaoRepository = Depends(get_cota_impressao_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverCotaImpressao(cotas=cotas).executar(
        tenant_id=tenant_id, professor_id=professor_id
    )
    if not removido:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Cota não encontrada"
        )


@router.get(
    "/impressao/relatorio/tenant/{tenant_id}", response_model=RelatorioImpressaoSaida
)
async def relatorio_impressao(
    tenant_id: UUID,
    competencia: str,
    usuario: Usuario = Depends(usuario_autenticado),
    solicitacoes: SqlSolicitacaoImpressaoRepository = Depends(get_impressao_repo),
    cotas: SqlCotaImpressaoRepository = Depends(get_cota_impressao_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> RelatorioImpressaoSaida:
    """Relatório mensal de impressões (``?competencia=YYYY-MM``), agregado por professor."""
    _exige_acesso_tenant(usuario, tenant_id)
    relatorio = await RelatorioImpressaoMensal(
        solicitacoes=solicitacoes, cotas=cotas, professores=professores
    ).executar(tenant_id=tenant_id, competencia=competencia)
    return _relatorio_saida(relatorio)


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
