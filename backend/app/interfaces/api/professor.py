"""Rotas do lado do **professor** (§A1): login próprio, mural de recados com
confirmação de leitura e solicitação de impressão.

Autenticação por JWT separada da do admin: o token carrega ``papel="professor"`` e o
id do professor. A dependência ``professor_autenticado`` revalida o professor no banco
(existência + senha definida) a cada requisição.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.impressao_use_cases import SolicitarImpressao
from app.application.mural_use_cases import (
    AutenticarProfessor,
    ConfirmarLeituraRecado,
    ListarRecadosDoProfessor,
)
from app.config import Settings
from app.domain.entities import Professor, RecadoDoProfessor
from app.infrastructure.db.repositories_admin import SqlProfessorRepository
from app.infrastructure.db.repositories_comunicacao import (
    SqlMuralRepository,
    SqlSolicitacaoImpressaoRepository,
)
from app.infrastructure.security import criar_token, decodificar_token
from app.interfaces.deps import (
    get_impressao_repo,
    get_mural_repo,
    get_professor_repo,
    get_settings_dep,
)
from app.interfaces.dto import (
    ImpressaoSaida,
    ProfessorImpressaoEntrada,
    ProfessorLoginEntrada,
    ProfessorLogadoSaida,
    ProfessorTokenSaida,
    RecadoDoProfessorSaida,
)

router = APIRouter(prefix="/api/professor", tags=["professor"])

_bearer = HTTPBearer(auto_error=False)

_NAO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Não autenticado",
    headers={"WWW-Authenticate": "Bearer"},
)


async def professor_autenticado(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
    settings: Settings = Depends(get_settings_dep),
) -> Professor:
    """Resolve o professor a partir do JWT ``papel=professor`` e revalida no banco."""
    if credenciais is None or not credenciais.credentials:
        raise _NAO_AUTENTICADO
    payload = decodificar_token(credenciais.credentials, segredo=settings.jwt_secret)
    if payload is None or payload.get("papel") != "professor":
        raise _NAO_AUTENTICADO
    tenant_id = payload.get("tenant_id")
    professor_id = payload.get("sub")
    if not tenant_id or not professor_id:
        raise _NAO_AUTENTICADO
    try:
        professor = await professores.obter(
            tenant_id=UUID(tenant_id), professor_id=UUID(professor_id)
        )
    except (ValueError, TypeError) as e:
        raise _NAO_AUTENTICADO from e
    if professor is None or not professor.senha_hash:
        raise _NAO_AUTENTICADO
    return professor


def _logado_saida(p: Professor) -> ProfessorLogadoSaida:
    return ProfessorLogadoSaida(
        id=p.id, nome=p.nome, telefone=p.telefone, tenant_id=p.tenant_id
    )


def _recado_saida(r: RecadoDoProfessor) -> RecadoDoProfessorSaida:
    return RecadoDoProfessorSaida(
        id=r.recado.id,
        titulo=r.recado.titulo,
        corpo=r.recado.corpo,
        autor_nome=r.recado.autor_nome,
        criado_em=r.recado.criado_em,
        lido=r.lido,
        lido_em=r.lido_em,
    )


def _impressao_saida(s) -> ImpressaoSaida:
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


@router.post("/login", response_model=ProfessorTokenSaida)
async def login_professor(
    payload: ProfessorLoginEntrada,
    professores: SqlProfessorRepository = Depends(get_professor_repo),
    settings: Settings = Depends(get_settings_dep),
) -> ProfessorTokenSaida:
    professor = await AutenticarProfessor(professores=professores).executar(
        tenant_id=payload.tenant_id, telefone=payload.telefone, senha=payload.senha
    )
    if professor is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas"
        )
    expira_em = settings.jwt_expira_minutos * 60
    token = criar_token(
        {
            "sub": str(professor.id),
            "papel": "professor",
            "tenant_id": str(professor.tenant_id),
            "telefone": professor.telefone,
        },
        segredo=settings.jwt_secret,
        expira_em_segundos=expira_em,
    )
    return ProfessorTokenSaida(
        access_token=token, expira_em=expira_em, professor=_logado_saida(professor)
    )


@router.get("/eu", response_model=ProfessorLogadoSaida)
async def eu(professor: Professor = Depends(professor_autenticado)) -> ProfessorLogadoSaida:
    return _logado_saida(professor)


@router.get("/recados", response_model=list[RecadoDoProfessorSaida])
async def meus_recados(
    professor: Professor = Depends(professor_autenticado),
    mural: SqlMuralRepository = Depends(get_mural_repo),
) -> list[RecadoDoProfessorSaida]:
    recados = await ListarRecadosDoProfessor(mural=mural).executar(
        tenant_id=professor.tenant_id, professor_id=professor.id
    )
    return [_recado_saida(r) for r in recados]


@router.post("/recados/{recado_id}/leitura", status_code=status.HTTP_204_NO_CONTENT)
async def confirmar_leitura(
    recado_id: UUID,
    professor: Professor = Depends(professor_autenticado),
    mural: SqlMuralRepository = Depends(get_mural_repo),
) -> None:
    """O professor confirma ("tica") a leitura de um recado."""
    try:
        await ConfirmarLeituraRecado(mural=mural).executar(
            tenant_id=professor.tenant_id, recado_id=recado_id, professor_id=professor.id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.post("/impressao", response_model=ImpressaoSaida, status_code=status.HTTP_201_CREATED)
async def solicitar_impressao(
    payload: ProfessorImpressaoEntrada,
    professor: Professor = Depends(professor_autenticado),
    solicitacoes: SqlSolicitacaoImpressaoRepository = Depends(get_impressao_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> ImpressaoSaida:
    """O professor envia um arquivo para a fila de impressão da secretaria."""
    try:
        solicitacao = await SolicitarImpressao(
            solicitacoes=solicitacoes, professores=professores
        ).executar(
            tenant_id=professor.tenant_id,
            arquivo_nome=payload.arquivo_nome,
            professor_id=professor.id,
            arquivo_url=payload.arquivo_url,
            copias=payload.copias,
            colorido=payload.colorido,
            frente_verso=payload.frente_verso,
            observacao=payload.observacao,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _impressao_saida(solicitacao)
