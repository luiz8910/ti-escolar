"""Rotas da fila de atendimento humano (§6j).

Visão da **secretaria**: o que o assistente não resolveu e o responsável aceitou levar a
uma pessoa. Escopada por tenant e protegida pelo JWT do módulo ``admin``.

Responder consome o canal de mensagens da escola, então a rota de resposta exige também
``_exige_tenant_ativo`` — escola bloqueada ou cancelada não dispara WhatsApp (§6e).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.atendimento_humano_use_cases import (
    AssumirAtendimento,
    ContarAtendimentosPendentes,
    ListarAtendimentos,
    ObterAtendimento,
    ReabrirAtendimento,
    ResolverAtendimento,
    ResponderAtendimento,
)
from app.application.paginacao import POR_PAGINA_PADRAO
from app.domain.entities import (
    AtendimentoHumano,
    Mensagem,
    StatusAtendimentoHumano,
    Usuario,
)
from app.infrastructure.db.repositories import SqlConversaRepository
from app.infrastructure.db.repositories_admin import (
    SqlAuditLogRepository,
    SqlContatoRepository,
    SqlTenantRepository,
)
from app.infrastructure.db.repositories_comunicacao import (
    SqlAtendimentoHumanoRepository,
)
from app.interfaces.api.admin import (
    _auditar_usuario,
    _exige_acesso_tenant,
    _exige_tenant_ativo,
    usuario_autenticado,
)
from app.interfaces.deps import (
    get_atendimento_humano_repo,
    get_audit_repo,
    get_contato_repo,
    get_conversa_repo,
    get_responder_atendimento,
    get_tenant_repo,
)
from app.interfaces.dto import (
    AtendimentoDetalheSaida,
    AtendimentoPendentesSaida,
    AtendimentoRespostaEntrada,
    AtendimentosPaginaSaida,
    AtendimentoSaida,
    MensagemAtendimentoSaida,
    PaginaMeta,
)

router = APIRouter(prefix="/api/admin/atendimentos", tags=["atendimento-humano"])


def _saida(a: AtendimentoHumano) -> AtendimentoSaida:
    return AtendimentoSaida(
        id=a.id,
        conversa_id=a.conversa_id,
        contato=a.contato,
        contato_nome=a.contato_nome,
        motivo=a.motivo,
        status=a.status.value,
        fora_expediente=a.fora_expediente,
        atendente_id=a.atendente_id,
        atendente_nome=a.atendente_nome,
        minutos_de_espera=a.minutos_de_espera(),
        janela_aberta=a.janela_aberta(),
        janela_expira_em=a.janela_expira_em,
        ofereceu_em=a.ofereceu_em,
        confirmado_em=a.confirmado_em,
        assumido_em=a.assumido_em,
        resolvido_em=a.resolvido_em,
        criado_em=a.criado_em,
        atualizado_em=a.atualizado_em,
    )


def _mensagem_saida(m: Mensagem) -> MensagemAtendimentoSaida:
    return MensagemAtendimentoSaida(
        autor=m.autor.value,
        autor_nome=m.autor_nome,
        texto=m.texto,
        fontes=m.fontes,
        criado_em=m.criado_em,
    )


def _status_do_filtro(bruto: str) -> list[StatusAtendimentoHumano] | None:
    """``?status=aberto,em_atendimento`` → enums; vazio/"fila" cai no padrão da fila."""
    bruto = (bruto or "").strip().lower()
    if not bruto or bruto == "fila":
        return None
    try:
        return [StatusAtendimentoHumano(p.strip()) for p in bruto.split(",") if p.strip()]
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Status inválido: {e}"
        ) from e


async def _carregar_ou_404(
    repo: SqlAtendimentoHumanoRepository,
    *,
    tenant_id: UUID,
    atendimento_id: UUID,
    contatos: SqlContatoRepository | None = None,
) -> AtendimentoHumano:
    atendimento = await ObterAtendimento(atendimentos=repo, contatos=contatos).executar(
        tenant_id=tenant_id, atendimento_id=atendimento_id
    )
    if atendimento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Atendimento não encontrado"
        )
    return atendimento


@router.get("/tenant/{tenant_id}", response_model=AtendimentosPaginaSaida)
async def listar(
    tenant_id: UUID,
    status_filtro: str = Query("", alias="status"),
    # "meus" filtra pelo atendente logado — o recorte que a pessoa usa o dia inteiro.
    meus: bool = False,
    pagina: int = 1,
    por_pagina: int = POR_PAGINA_PADRAO,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlAtendimentoHumanoRepository = Depends(get_atendimento_humano_repo),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> AtendimentosPaginaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    resultado = await ListarAtendimentos(atendimentos=repo, contatos=contatos).executar(
        tenant_id=tenant_id,
        status=_status_do_filtro(status_filtro),
        atendente_id=usuario.id if meus else None,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return AtendimentosPaginaSaida(
        itens=[_saida(a) for a in resultado.itens],
        meta=PaginaMeta(
            pagina=resultado.pagina,
            por_pagina=resultado.por_pagina,
            total=resultado.total,
            total_paginas=resultado.total_paginas,
        ),
    )


@router.get("/tenant/{tenant_id}/pendentes", response_model=AtendimentoPendentesSaida)
async def pendentes(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlAtendimentoHumanoRepository = Depends(get_atendimento_humano_repo),
) -> AtendimentoPendentesSaida:
    """Contador do badge — consultado em polling, por isso devolve só o número."""
    _exige_acesso_tenant(usuario, tenant_id)
    total = await ContarAtendimentosPendentes(atendimentos=repo).executar(tenant_id=tenant_id)
    return AtendimentoPendentesSaida(pendentes=total)


@router.get("/{atendimento_id}", response_model=AtendimentoDetalheSaida)
async def detalhar(
    atendimento_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlAtendimentoHumanoRepository = Depends(get_atendimento_humano_repo),
    conversas: SqlConversaRepository = Depends(get_conversa_repo),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> AtendimentoDetalheSaida:
    """O card + a conversa inteira: quem atende precisa ler o que já foi dito."""
    _exige_acesso_tenant(usuario, tenant_id)
    atendimento = await _carregar_ou_404(
        repo, tenant_id=tenant_id, atendimento_id=atendimento_id, contatos=contatos
    )
    mensagens = await conversas.mensagens(conversa_id=atendimento.conversa_id)
    return AtendimentoDetalheSaida(
        atendimento=_saida(atendimento),
        mensagens=[_mensagem_saida(m) for m in mensagens],
    )


@router.post("/{atendimento_id}/assumir", response_model=AtendimentoSaida)
async def assumir(
    atendimento_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlAtendimentoHumanoRepository = Depends(get_atendimento_humano_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> AtendimentoSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        atendimento = await AssumirAtendimento(atendimentos=repo).executar(
            tenant_id=tenant_id, atendimento_id=atendimento_id, usuario=usuario
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="atendimento.assumir",
        tenant_id=tenant_id,
        descricao=f"Assumiu o atendimento de {atendimento.contato}",
        metadados={"atendimento_id": str(atendimento.id)},
    )
    return _saida(atendimento)


@router.post("/{atendimento_id}/responder", response_model=AtendimentoSaida)
async def responder(
    atendimento_id: UUID,
    tenant_id: UUID,
    payload: AtendimentoRespostaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    uc: ResponderAtendimento = Depends(get_responder_atendimento),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> AtendimentoSaida:
    """Resposta da secretaria, entregue no mesmo fio de WhatsApp do responsável."""
    _exige_acesso_tenant(usuario, tenant_id)
    await _exige_tenant_ativo(tenant_id, tenants)
    try:
        atendimento = await uc.executar(
            tenant_id=tenant_id,
            atendimento_id=atendimento_id,
            usuario=usuario,
            texto=payload.texto,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="atendimento.responder",
        tenant_id=tenant_id,
        descricao=f"Respondeu ao responsável {atendimento.contato}",
        metadados={
            "atendimento_id": str(atendimento.id),
            "caracteres": len(payload.texto),
        },
    )
    return _saida(atendimento)


@router.post("/{atendimento_id}/resolver", response_model=AtendimentoSaida)
async def resolver(
    atendimento_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlAtendimentoHumanoRepository = Depends(get_atendimento_humano_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> AtendimentoSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        atendimento = await ResolverAtendimento(atendimentos=repo).executar(
            tenant_id=tenant_id, atendimento_id=atendimento_id, usuario=usuario
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="atendimento.resolver",
        tenant_id=tenant_id,
        descricao=f"Resolveu o atendimento de {atendimento.contato}",
        metadados={"atendimento_id": str(atendimento.id)},
    )
    return _saida(atendimento)


@router.post("/{atendimento_id}/reabrir", response_model=AtendimentoSaida)
async def reabrir(
    atendimento_id: UUID,
    tenant_id: UUID,
    liberar: bool = False,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlAtendimentoHumanoRepository = Depends(get_atendimento_humano_repo),
) -> AtendimentoSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        atendimento = await ReabrirAtendimento(atendimentos=repo).executar(
            tenant_id=tenant_id, atendimento_id=atendimento_id, liberar=liberar
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _saida(atendimento)
