"""Rota de exportação de conversa para fins legais (§H1).

Gera o documento textual de uma conversa (opcionalmente por período) para arquivamento
legal (processo/prontuário). Guardada por ``_exige_acesso_tenant`` — a escola exporta as
suas conversas; o super admin também, via a mesma regra.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.application.exportacao_use_cases import ExportarConversaLegal
from app.domain.entities import Usuario
from app.infrastructure.db.repositories import SqlConversaRepository
from app.infrastructure.db.repositories_admin import SqlTenantRepository
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import get_conversa_repo, get_tenant_repo
from app.interfaces.dto import ConversaExportadaSaida

router = APIRouter(prefix="/api/admin/escolas", tags=["exportacao"])


@router.get(
    "/{tenant_id}/conversas/{conversa_id}/exportar",
    response_model=ConversaExportadaSaida,
)
async def exportar_conversa(
    tenant_id: UUID,
    conversa_id: UUID,
    inicio: datetime | None = Query(default=None),
    fim: datetime | None = Query(default=None),
    usuario: Usuario = Depends(usuario_autenticado),
    conversas: SqlConversaRepository = Depends(get_conversa_repo),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> ConversaExportadaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        exportada = await ExportarConversaLegal(
            conversas=conversas, tenants=tenants
        ).executar(
            tenant_id=tenant_id, conversa_id=conversa_id, inicio=inicio, fim=fim
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return ConversaExportadaSaida(
        conversa_id=exportada.conversa_id,
        escola_nome=exportada.escola_nome,
        contato=exportada.contato,
        documento=exportada.documento,
        total_mensagens=exportada.total_mensagens,
        inicio=exportada.inicio,
        fim=exportada.fim,
        gerado_em=exportada.gerado_em,
    )
