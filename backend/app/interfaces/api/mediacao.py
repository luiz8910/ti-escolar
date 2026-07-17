"""Rotas administrativas do canal pai ↔ professor mediado (§A3).

Ponto de entrada para a secretaria (ou um futuro webhook de inbound roteado) registrar
uma mensagem recebida de um responsável, direcionada a um professor, e para acompanhar
a conversa. O envio (professor → responsável) fica no portal do professor.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.mediacao_use_cases import (
    ListarConversaMediada,
    RegistrarMensagemDoResponsavel,
)
from app.domain.entities import MensagemMediada, Usuario
from app.infrastructure.db.repositories_admin import (
    SqlContatoRepository,
    SqlProfessorRepository,
)
from app.infrastructure.db.repositories_comunicacao import SqlMediacaoRepository
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import (
    get_contato_repo,
    get_mediacao_repo,
    get_professor_repo,
)
from app.interfaces.dto import MediacaoRecebidaEntrada, MensagemMediadaSaida

router = APIRouter(prefix="/api/admin/mediacao", tags=["mediacao"])


def _saida(m: MensagemMediada) -> MensagemMediadaSaida:
    return MensagemMediadaSaida(
        id=m.id,
        professor_id=m.professor_id,
        contato_telefone=m.contato_telefone,
        contato_nome=m.contato_nome,
        professor_nome=m.professor_nome,
        direcao=m.direcao.value,
        corpo=m.corpo,
        criado_em=m.criado_em,
    )


@router.post(
    "/receber", response_model=MensagemMediadaSaida, status_code=status.HTTP_201_CREATED
)
async def registrar_recebida(
    payload: MediacaoRecebidaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    mediacao: SqlMediacaoRepository = Depends(get_mediacao_repo),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> MensagemMediadaSaida:
    """Registra uma mensagem de um responsável direcionada a um professor."""
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        mensagem = await RegistrarMensagemDoResponsavel(
            mediacao=mediacao, professores=professores, contatos=contatos
        ).executar(
            tenant_id=payload.tenant_id,
            professor_id=payload.professor_id,
            contato_telefone=payload.contato_telefone,
            corpo=payload.corpo,
            contato_nome=payload.contato_nome,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _saida(mensagem)


@router.get(
    "/tenant/{tenant_id}/professor/{professor_id}/{contato_telefone}",
    response_model=list[MensagemMediadaSaida],
)
async def conversa(
    tenant_id: UUID,
    professor_id: UUID,
    contato_telefone: str,
    usuario: Usuario = Depends(usuario_autenticado),
    mediacao: SqlMediacaoRepository = Depends(get_mediacao_repo),
) -> list[MensagemMediadaSaida]:
    """Acompanhamento (secretaria/gestão) de uma conversa mediada."""
    _exige_acesso_tenant(usuario, tenant_id)
    mensagens = await ListarConversaMediada(mediacao=mediacao).executar(
        tenant_id=tenant_id,
        professor_id=professor_id,
        contato_telefone=contato_telefone,
    )
    return [_saida(m) for m in mensagens]
