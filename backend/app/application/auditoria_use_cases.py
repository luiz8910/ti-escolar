"""Casos de uso da auditoria de ações (usuários logados no admin e ações da LLM).

Registrar é deliberadamente tolerante a falhas: auditar nunca deve derrubar a ação de
negócio que está sendo auditada. A consulta é escopada por ``tenant_id`` (a escola).
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.domain.entities import AtorAuditoria, RegistroAuditoria
from app.domain.ports import AuditLogRepository

logger = logging.getLogger("auditoria")


class RegistrarAuditoria:
    """Grava uma ação no log de auditoria.

    Falhas ao auditar são apenas logadas (não propagadas): o registro de auditoria é
    secundário em relação à ação de negócio.
    """

    def __init__(self, *, auditoria: AuditLogRepository) -> None:
        self._auditoria = auditoria

    async def executar(
        self,
        *,
        ator: AtorAuditoria,
        acao: str,
        tenant_id: UUID | None = None,
        ator_id: str = "",
        ator_nome: str = "",
        descricao: str = "",
        metadados: dict | None = None,
    ) -> RegistroAuditoria | None:
        registro = RegistroAuditoria(
            ator=ator,
            acao=acao,
            tenant_id=tenant_id,
            ator_id=ator_id,
            ator_nome=ator_nome,
            descricao=descricao,
            metadados=metadados or {},
        )
        try:
            return await self._auditoria.registrar(registro)
        except Exception:  # noqa: BLE001 — auditar não pode quebrar a ação auditada
            logger.exception("Falha ao registrar auditoria (acao=%s)", acao)
            return None


class ListarAuditoria:
    def __init__(self, *, auditoria: AuditLogRepository) -> None:
        self._auditoria = auditoria

    async def executar(
        self, *, tenant_id: UUID, limite: int = 200
    ) -> list[RegistroAuditoria]:
        return await self._auditoria.listar(tenant_id=tenant_id, limite=limite)
