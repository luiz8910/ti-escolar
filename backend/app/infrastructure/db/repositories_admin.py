"""Repositórios de administração: usuários, contatos e grupos."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities import Contato, Grupo, Papel, Sala, Usuario
from app.infrastructure.db.models import (
    ContatoORM,
    GrupoORM,
    SalaORM,
    UsuarioORM,
    sala_contatos,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_usuario(row: UsuarioORM) -> Usuario:
    return Usuario(
        id=row.id,
        nome=row.nome,
        email=row.email,
        senha_hash=row.senha_hash,
        papel=Papel(row.papel),
        tenant_id=row.tenant_id,
        ativo=row.ativo,
        criado_em=row.criado_em,
    )


def _to_contato(row: ContatoORM) -> Contato:
    return Contato(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        telefone=row.telefone,
        criado_em=row.criado_em,
    )


class SqlUsuarioRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def por_email(self, email: str) -> Usuario | None:
        stmt = select(UsuarioORM).where(UsuarioORM.email == email.lower())
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return _to_usuario(row) if row else None

    async def criar(self, usuario: Usuario) -> Usuario:
        self._s.add(
            UsuarioORM(
                id=usuario.id,
                nome=usuario.nome,
                email=usuario.email.lower(),
                senha_hash=usuario.senha_hash,
                papel=usuario.papel.value,
                tenant_id=usuario.tenant_id,
                ativo=usuario.ativo,
                criado_em=usuario.criado_em,
            )
        )
        await self._s.flush()
        return usuario

    async def listar(self, *, tenant_id: uuid.UUID | None = None) -> list[Usuario]:
        stmt = select(UsuarioORM)
        if tenant_id is not None:
            stmt = stmt.where(UsuarioORM.tenant_id == tenant_id)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_usuario(r) for r in rows]


class SqlGrupoRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, grupo: Grupo) -> Grupo:
        self._s.add(
            GrupoORM(
                id=grupo.id,
                tenant_id=grupo.tenant_id,
                nome=grupo.nome,
                descricao=grupo.descricao,
                criado_em=grupo.criado_em,
            )
        )
        await self._s.flush()
        return grupo

    async def _orm(self, *, tenant_id: uuid.UUID, grupo_id: uuid.UUID) -> GrupoORM | None:
        stmt = (
            select(GrupoORM)
            .where(GrupoORM.id == grupo_id, GrupoORM.tenant_id == tenant_id)
            .options(selectinload(GrupoORM.membros))
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(self, *, tenant_id: uuid.UUID, grupo_id: uuid.UUID) -> Grupo | None:
        row = await self._orm(tenant_id=tenant_id, grupo_id=grupo_id)
        if row is None:
            return None
        return Grupo(
            id=row.id,
            tenant_id=row.tenant_id,
            nome=row.nome,
            descricao=row.descricao,
            criado_em=row.criado_em,
            membros=[_to_contato(c) for c in row.membros],
        )

    async def listar(self, *, tenant_id: uuid.UUID) -> list[Grupo]:
        stmt = (
            select(GrupoORM)
            .where(GrupoORM.tenant_id == tenant_id)
            .options(selectinload(GrupoORM.membros))
            .order_by(GrupoORM.nome)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [
            Grupo(
                id=r.id,
                tenant_id=r.tenant_id,
                nome=r.nome,
                descricao=r.descricao,
                criado_em=r.criado_em,
                membros=[_to_contato(c) for c in r.membros],
            )
            for r in rows
        ]

    async def _contato_por_telefone(
        self, *, tenant_id: uuid.UUID, telefone: str
    ) -> ContatoORM | None:
        stmt = select(ContatoORM).where(
            ContatoORM.tenant_id == tenant_id, ContatoORM.telefone == telefone
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def adicionar_contato(
        self, *, tenant_id: uuid.UUID, grupo_id: uuid.UUID, nome: str, telefone: str
    ) -> Contato:
        grupo = await self._orm(tenant_id=tenant_id, grupo_id=grupo_id)
        if grupo is None:
            raise ValueError("Grupo não encontrado para o tenant.")

        contato = await self._contato_por_telefone(tenant_id=tenant_id, telefone=telefone)
        if contato is None:
            contato = ContatoORM(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                nome=nome,
                telefone=telefone,
                criado_em=_now(),
            )
            self._s.add(contato)
            await self._s.flush()

        if contato not in grupo.membros:
            grupo.membros.append(contato)
            await self._s.flush()
        return _to_contato(contato)

    async def membros(self, *, tenant_id: uuid.UUID, grupo_id: uuid.UUID) -> list[Contato]:
        row = await self._orm(tenant_id=tenant_id, grupo_id=grupo_id)
        if row is None:
            return []
        return [_to_contato(c) for c in row.membros]


def _to_sala(row: SalaORM) -> Sala:
    return Sala(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        descricao=row.descricao,
        criado_em=row.criado_em,
        pais=[_to_contato(c) for c in row.pais],
    )


class SqlContatoRepository:
    """CRUD de pais/responsáveis (contatos), escopado por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, contato: Contato) -> Contato:
        self._s.add(
            ContatoORM(
                id=contato.id,
                tenant_id=contato.tenant_id,
                nome=contato.nome,
                telefone=contato.telefone,
                criado_em=contato.criado_em,
            )
        )
        await self._s.flush()
        return contato

    async def _orm(self, *, tenant_id: uuid.UUID, contato_id: uuid.UUID) -> ContatoORM | None:
        stmt = select(ContatoORM).where(
            ContatoORM.id == contato_id, ContatoORM.tenant_id == tenant_id
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(self, *, tenant_id: uuid.UUID, contato_id: uuid.UUID) -> Contato | None:
        row = await self._orm(tenant_id=tenant_id, contato_id=contato_id)
        return _to_contato(row) if row else None

    async def por_telefone(self, *, tenant_id: uuid.UUID, telefone: str) -> Contato | None:
        stmt = select(ContatoORM).where(
            ContatoORM.tenant_id == tenant_id, ContatoORM.telefone == telefone
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return _to_contato(row) if row else None

    async def listar(self, *, tenant_id: uuid.UUID) -> list[Contato]:
        stmt = (
            select(ContatoORM)
            .where(ContatoORM.tenant_id == tenant_id)
            .order_by(ContatoORM.nome)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_contato(r) for r in rows]

    async def atualizar(self, contato: Contato) -> Contato:
        row = await self._orm(tenant_id=contato.tenant_id, contato_id=contato.id)
        if row is None:
            raise ValueError("Contato não encontrado para o tenant.")
        row.nome = contato.nome
        row.telefone = contato.telefone
        await self._s.flush()
        return _to_contato(row)

    async def remover(self, *, tenant_id: uuid.UUID, contato_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, contato_id=contato_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


class SqlSalaRepository:
    """CRUD de salas (turmas) e vínculo N:N com pais, escopado por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, sala: Sala) -> Sala:
        self._s.add(
            SalaORM(
                id=sala.id,
                tenant_id=sala.tenant_id,
                nome=sala.nome,
                descricao=sala.descricao,
                criado_em=sala.criado_em,
            )
        )
        await self._s.flush()
        return sala

    async def _orm(self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID) -> SalaORM | None:
        stmt = (
            select(SalaORM)
            .where(SalaORM.id == sala_id, SalaORM.tenant_id == tenant_id)
            .options(selectinload(SalaORM.pais))
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID) -> Sala | None:
        row = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        return _to_sala(row) if row else None

    async def listar(self, *, tenant_id: uuid.UUID) -> list[Sala]:
        stmt = (
            select(SalaORM)
            .where(SalaORM.tenant_id == tenant_id)
            .options(selectinload(SalaORM.pais))
            .order_by(SalaORM.nome)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_sala(r) for r in rows]

    async def atualizar(
        self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID, nome: str, descricao: str
    ) -> Sala:
        row = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        if row is None:
            raise ValueError("Sala não encontrada para o tenant.")
        row.nome = nome
        row.descricao = descricao
        await self._s.flush()
        return _to_sala(row)

    async def remover(self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        if row is None:
            return False
        # Remove os vínculos antes (os pais em si permanecem cadastrados).
        await self._s.execute(delete(sala_contatos).where(sala_contatos.c.sala_id == sala_id))
        await self._s.delete(row)
        await self._s.flush()
        return True

    async def _contato_do_tenant(
        self, *, tenant_id: uuid.UUID, contato_id: uuid.UUID
    ) -> ContatoORM | None:
        stmt = select(ContatoORM).where(
            ContatoORM.id == contato_id, ContatoORM.tenant_id == tenant_id
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def vincular_pai(
        self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID, contato_id: uuid.UUID
    ) -> None:
        sala = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        if sala is None:
            raise ValueError("Sala não encontrada para o tenant.")
        contato = await self._contato_do_tenant(tenant_id=tenant_id, contato_id=contato_id)
        if contato is None:
            raise ValueError("Pai/responsável não encontrado para o tenant.")
        if contato not in sala.pais:
            sala.pais.append(contato)
            await self._s.flush()

    async def desvincular_pai(
        self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID, contato_id: uuid.UUID
    ) -> None:
        sala = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        if sala is None:
            raise ValueError("Sala não encontrada para o tenant.")
        sala.pais = [c for c in sala.pais if c.id != contato_id]
        await self._s.flush()

    async def pais(self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID) -> list[Contato]:
        row = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        if row is None:
            raise ValueError("Sala não encontrada para o tenant.")
        return [_to_contato(c) for c in row.pais]
