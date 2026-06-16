"""Adaptadores de persistência (implementam as portas de repositório do domínio)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities import (
    Autor,
    Broadcast,
    CategoriaTemplate,
    Conversa,
    DestinatarioBroadcast,
    Mensagem,
    MessageTemplate,
    ResumoConversa,
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


def _to_mensagem(row: MensagemORM) -> Mensagem:
    return Mensagem(
        id=row.id,
        conversa_id=row.conversa_id,
        autor=Autor.BOT if row.autor == "bot" else Autor.USUARIO,
        texto=row.texto,
        fontes=[f for f in row.fontes.split("|") if f],
        criado_em=row.criado_em,
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

    async def listar_resumos(self, *, tenant_id: uuid.UUID) -> list[ResumoConversa]:
        stmt = (
            select(ConversaORM)
            .where(ConversaORM.tenant_id == tenant_id)
            .options(selectinload(ConversaORM.mensagens))
            .order_by(ConversaORM.criado_em.desc())
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        resumos: list[ResumoConversa] = []
        for r in rows:
            ultima = r.mensagens[-1] if r.mensagens else None
            resumos.append(
                ResumoConversa(
                    conversa=Conversa(
                        id=r.id,
                        tenant_id=r.tenant_id,
                        contato=r.contato,
                        criado_em=r.criado_em,
                    ),
                    total_mensagens=len(r.mensagens),
                    ultima_mensagem=ultima.texto if ultima else "",
                    ultima_em=ultima.criado_em if ultima else None,
                )
            )
        # Conversas com atividade mais recente primeiro.
        resumos.sort(key=lambda x: x.ultima_em or x.conversa.criado_em, reverse=True)
        return resumos

    async def obter_conversa(
        self, *, tenant_id: uuid.UUID, conversa_id: uuid.UUID
    ) -> Conversa | None:
        row = await self._s.get(ConversaORM, conversa_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return Conversa(
            id=row.id, tenant_id=row.tenant_id, contato=row.contato, criado_em=row.criado_em
        )

    async def mensagens(self, *, conversa_id: uuid.UUID) -> list[Mensagem]:
        stmt = (
            select(MensagemORM)
            .where(MensagemORM.conversa_id == conversa_id)
            .order_by(MensagemORM.criado_em)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_mensagem(m) for m in rows]


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

    @staticmethod
    def _to_broadcast(row: BroadcastORM) -> Broadcast:
        dests = [
            DestinatarioBroadcast(
                id=d.id,
                contato=d.contato,
                parametros=[p for p in d.parametros.split("|") if p],
                status=StatusEntrega(d.status),
            )
            for d in row.destinatarios
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

    async def obter(self, broadcast_id: uuid.UUID) -> Broadcast | None:
        stmt = (
            select(BroadcastORM)
            .where(BroadcastORM.id == broadcast_id)
            .options(selectinload(BroadcastORM.destinatarios))
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return self._to_broadcast(row) if row else None

    async def listar(self, *, tenant_id: uuid.UUID) -> list[Broadcast]:
        stmt = (
            select(BroadcastORM)
            .where(BroadcastORM.tenant_id == tenant_id)
            .options(selectinload(BroadcastORM.destinatarios))
            .order_by(BroadcastORM.criado_em.desc())
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [self._to_broadcast(r) for r in rows]
