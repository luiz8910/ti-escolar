"""Rotas do mural do professor — lado da secretaria/gestão (§A1).

Publica recados aos professores e acompanha a **confirmação de leitura** (quem viu /
quem não viu), com a opção de **re-notificar** por WhatsApp quem ainda não leu.
Protegido pela autenticação por JWT do módulo ``admin``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.mural_use_cases import (
    ListarRecados,
    ObterStatusLeitura,
    PublicarRecado,
    RemoverRecado,
    ReNotificarRecadoNaoLido,
)
from app.domain.entities import RecadoResumo, StatusLeituraRecado, Usuario
from app.domain.ports import MessageChannel
from app.infrastructure.db.repositories_admin import SqlProfessorRepository
from app.infrastructure.db.repositories_comunicacao import SqlMuralRepository
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import get_canal, get_mural_repo, get_professor_repo
from app.interfaces.dto import (
    LeitorRecadoSaida,
    RecadoEntrada,
    RecadoResumoSaida,
    RecadoStatusLeituraSaida,
    ReNotificarRecadoSaida,
)

router = APIRouter(prefix="/api/admin", tags=["mural"])


def _resumo_saida(r: RecadoResumo) -> RecadoResumoSaida:
    return RecadoResumoSaida(
        id=r.recado.id,
        titulo=r.recado.titulo,
        corpo=r.recado.corpo,
        autor_nome=r.recado.autor_nome,
        criado_em=r.recado.criado_em,
        total_professores=r.total_professores,
        total_lidos=r.total_lidos,
        total_nao_lidos=r.total_nao_lidos,
    )


def _status_saida(s: StatusLeituraRecado) -> RecadoStatusLeituraSaida:
    return RecadoStatusLeituraSaida(
        id=s.recado.id,
        titulo=s.recado.titulo,
        corpo=s.recado.corpo,
        criado_em=s.recado.criado_em,
        lidos=[
            LeitorRecadoSaida(
                professor_id=p.id, nome=p.nome, telefone=p.telefone, lido_em=lido_em
            )
            for p, lido_em in s.lidos
        ],
        nao_lidos=[
            LeitorRecadoSaida(professor_id=p.id, nome=p.nome, telefone=p.telefone)
            for p in s.nao_lidos
        ],
    )


@router.post("/recados", response_model=RecadoResumoSaida, status_code=status.HTTP_201_CREATED)
async def publicar_recado(
    payload: RecadoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    mural: SqlMuralRepository = Depends(get_mural_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> RecadoResumoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        recado = await PublicarRecado(mural=mural).executar(
            tenant_id=payload.tenant_id,
            titulo=payload.titulo,
            corpo=payload.corpo,
            autor_id=str(usuario.id),
            autor_nome=usuario.nome,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    total = len(await professores.listar(tenant_id=payload.tenant_id))
    return _resumo_saida(RecadoResumo(recado=recado, total_professores=total, total_lidos=0))


@router.get("/recados/tenant/{tenant_id}", response_model=list[RecadoResumoSaida])
async def listar_recados(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    mural: SqlMuralRepository = Depends(get_mural_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> list[RecadoResumoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    resumos = await ListarRecados(mural=mural, professores=professores).executar(
        tenant_id=tenant_id
    )
    return [_resumo_saida(r) for r in resumos]


@router.get("/recados/{recado_id}/leitura", response_model=RecadoStatusLeituraSaida)
async def status_leitura_recado(
    recado_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    mural: SqlMuralRepository = Depends(get_mural_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> RecadoStatusLeituraSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        status_leitura = await ObterStatusLeitura(
            mural=mural, professores=professores
        ).executar(tenant_id=tenant_id, recado_id=recado_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _status_saida(status_leitura)


@router.post("/recados/{recado_id}/renotificar", response_model=ReNotificarRecadoSaida)
async def renotificar_recado(
    recado_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    mural: SqlMuralRepository = Depends(get_mural_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
    canal: MessageChannel = Depends(get_canal),
) -> ReNotificarRecadoSaida:
    """Re-notifica por WhatsApp os professores que ainda não confirmaram a leitura."""
    _exige_acesso_tenant(usuario, tenant_id)
    avisados = await ReNotificarRecadoNaoLido(
        mural=mural, professores=professores, canal=canal
    ).executar(tenant_id=tenant_id, recado_id=recado_id)
    return ReNotificarRecadoSaida(avisados=avisados)


@router.delete("/recados/{recado_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_recado(
    recado_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    mural: SqlMuralRepository = Depends(get_mural_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverRecado(mural=mural).executar(
        tenant_id=tenant_id, recado_id=recado_id
    )
    if not removido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recado não encontrado")
