"""Adaptadores de persistência (implementam as portas de repositório do domínio)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import (
    Broadcast,
    CategoriaTemplate,
    Conversa,
    DestinatarioBroadcast,
    MessageTemplate,
    StatusBroadcast,
    StatusEntrega,
    StatusTemplate,
)
from app.infrastructure.db.models import (
    BroadcastORM,
    ConversaORM,
    DestinatarioORM,
    MensagemORM,
    TemplateORM,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SqlConversaRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def obter_ou_criar(self, *, tenant_id: uuid.UUID, contato: str) -> Conversa:
        stmt = select(ConversaORM).where(
            ConversaORM.tenant_id == tenant_id, ConversaORM.contato == contato
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ConversaORM(
                id=uuid.uuid4(), tenant_id=tenant_id, contato=contato, criado_em=_now()
            )
            self._s.add(row)
            await self._s.flush()
        return Conversa(
            id=row.id, tenant_id=row.tenant_id, contato=row.contato, criado_em=row.criado_em
        )

    async def adicionar_mensagem(
        self, *, conversa_id: uuid.UUID, autor: str, texto: str, fontes: list[str] | None = None
    ) -> None:
        self._s.add(
            MensagemORM(
                id=uuid.uuid4(),
                conversa_id=conversa_id,
                autor=autor,
                texto=texto,
                fontes="|".join(fontes or []),
                criado_em=_now(),
            )
        )
        await self._s.flush()

    async def historico(
        self, *, conversa_id: uuid.UUID, limite: int = 20
    ) -> list[dict[str, str]]:
        stmt = (
            select(MensagemORM)
            .where(MensagemORM.conversa_id == conversa_id)
            .order_by(MensagemORM.criado_em)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        rows = rows[-limite:]
        return [
            {"role": "assistant" if m.autor == "bot" else "user", "content": m.texto}
            for m in rows
        ]


class SqlTemplateRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def obter(
        self, *, tenant_id: uuid.UUID, template_id: uuid.UUID
    ) -> MessageTemplate | None:
        row = await self._s.get(TemplateORM, template_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return MessageTemplate(
            id=row.id,
            tenant_id=row.tenant_id,
            nome=row.nome,
            categoria=CategoriaTemplate(row.categoria),
            idioma=row.idioma,
            corpo=row.corpo,
            status=StatusTemplate(row.status),
        )


class SqlBroadcastRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def salvar(self, broadcast: Broadcast) -> None:
        row = await self._s.get(BroadcastORM, broadcast.id)
        if row is None:
            row = BroadcastORM(id=broadcast.id, criado_em=broadcast.criado_em)
            self._s.add(row)
        row.tenant_id = broadcast.tenant_id
        row.template_id = broadcast.template_id
        row.titulo = broadcast.titulo
        row.status = broadcast.status.value
        row.agendado_para = broadcast.agendado_para

        await self._s.flush()
        # Reescreve destinatários (simples para o scaffold).
        for d in list(await self._dest_existentes(broadcast.id)):
            await self._s.delete(d)
        await self._s.flush()
        for dest in broadcast.destinatarios:
            self._s.add(
                DestinatarioORM(
                    id=dest.id,
                    broadcast_id=broadcast.id,
                    contato=dest.contato,
                    parametros="|".join(dest.parametros),
                    status=dest.status.value,
                )
            )
        await self._s.flush()

    async def _dest_existentes(self, broadcast_id: uuid.UUID) -> list[DestinatarioORM]:
        stmt = select(DestinatarioORM).where(DestinatarioORM.broadcast_id == broadcast_id)
        return list((await self._s.execute(stmt)).scalars().all())

    async def obter(self, broadcast_id: uuid.UUID) -> Broadcast | None:
        row = await self._s.get(BroadcastORM, broadcast_id)
        if row is None:
            return None
        dests = [
            DestinatarioBroadcast(
                id=d.id,
                contato=d.contato,
                parametros=[p for p in d.parametros.split("|") if p],
                status=StatusEntrega(d.status),
            )
            for d in await self._dest_existentes(broadcast_id)
        ]
        return Broadcast(
            id=row.id,
            tenant_id=row.tenant_id,
            template_id=row.template_id,
            titulo=row.titulo,
            destinatarios=dests,
            status=StatusBroadcast(row.status),
            agendado_para=row.agendado_para,
            criado_em=row.criado_em,
        )
