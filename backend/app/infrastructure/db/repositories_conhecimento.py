"""Repositórios da base de conhecimento enriquecida pela escola.

- ``SqlFonteConhecimentoRepository``: metadados dos documentos enviados (RAG).
- ``SqlPromptTenantRepository``: system prompt personalizado por tenant.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import FonteConhecimento, PromptTenant, TipoConhecimento
from app.infrastructure.db.models import FonteConhecimentoORM, PromptTenantORM


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_fonte(row: FonteConhecimentoORM) -> FonteConhecimento:
    return FonteConhecimento(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        tipo=TipoConhecimento(row.tipo),
        total_trechos=row.total_trechos,
        criado_em=row.criado_em,
    )


class SqlFonteConhecimentoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, fonte: FonteConhecimento) -> FonteConhecimento:
        self._s.add(
            FonteConhecimentoORM(
                id=fonte.id,
                tenant_id=fonte.tenant_id,
                nome=fonte.nome,
                tipo=fonte.tipo.value,
                total_trechos=fonte.total_trechos,
                criado_em=fonte.criado_em,
            )
        )
        await self._s.flush()
        return fonte

    async def obter(
        self, *, tenant_id: uuid.UUID, fonte_id: uuid.UUID
    ) -> FonteConhecimento | None:
        stmt = select(FonteConhecimentoORM).where(
            FonteConhecimentoORM.id == fonte_id,
            FonteConhecimentoORM.tenant_id == tenant_id,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return _to_fonte(row) if row else None

    async def listar(self, *, tenant_id: uuid.UUID) -> list[FonteConhecimento]:
        stmt = (
            select(FonteConhecimentoORM)
            .where(FonteConhecimentoORM.tenant_id == tenant_id)
            .order_by(FonteConhecimentoORM.criado_em.desc())
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_fonte(r) for r in rows]

    async def remover(self, *, tenant_id: uuid.UUID, fonte_id: uuid.UUID) -> bool:
        stmt = select(FonteConhecimentoORM).where(
            FonteConhecimentoORM.id == fonte_id,
            FonteConhecimentoORM.tenant_id == tenant_id,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


class SqlPromptTenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def obter(self, *, tenant_id: uuid.UUID) -> PromptTenant | None:
        stmt = select(PromptTenantORM).where(PromptTenantORM.tenant_id == tenant_id)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return PromptTenant(
            id=row.id,
            tenant_id=row.tenant_id,
            conteudo=row.conteudo,
            atualizado_em=row.atualizado_em,
        )

    async def salvar(self, *, tenant_id: uuid.UUID, conteudo: str) -> PromptTenant:
        stmt = select(PromptTenantORM).where(PromptTenantORM.tenant_id == tenant_id)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = PromptTenantORM(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                conteudo=conteudo,
                atualizado_em=_now(),
            )
            self._s.add(row)
        else:
            row.conteudo = conteudo
            row.atualizado_em = _now()
        await self._s.flush()
        return PromptTenant(
            id=row.id,
            tenant_id=row.tenant_id,
            conteudo=row.conteudo,
            atualizado_em=row.atualizado_em,
        )
