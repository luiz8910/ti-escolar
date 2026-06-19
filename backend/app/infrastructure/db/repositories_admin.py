"""Repositórios de administração: usuários, contatos e grupos."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities import Aluno, Contato, Grupo, Papel, ResumoEscola, Sala, Tenant, Usuario
from app.infrastructure.db.models import (
    AlunoORM,
    BroadcastORM,
    ConhecimentoORM,
    ContatoORM,
    ConversaORM,
    DestinatarioORM,
    DocumentoORM,
    GrupoORM,
    MensagemORM,
    QuotaORM,
    SalaORM,
    TemplateORM,
    TenantORM,
    UsuarioORM,
    aluno_responsaveis,
    grupo_contatos,
    sala_contatos,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_tenant(row: TenantORM) -> Tenant:
    return Tenant(id=row.id, nome=row.nome, slug=row.slug, criado_em=row.criado_em)


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


class SqlTenantRepository:
    """Persistência das escolas (tenants), com remoção em cascata explícita.

    O esquema usa FKs sem ``ON DELETE CASCADE``, então a remoção apaga os dados
    dependentes em ordem (mensagens → conversas → ... → tenant) na mesma transação.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, tenant: Tenant) -> Tenant:
        self._s.add(
            TenantORM(
                id=tenant.id,
                nome=tenant.nome,
                slug=tenant.slug,
                criado_em=tenant.criado_em,
            )
        )
        try:
            await self._s.flush()
        except IntegrityError as e:
            await self._s.rollback()
            raise ValueError("Já existe uma escola com este slug.") from e
        return tenant

    async def obter(self, tenant_id: uuid.UUID) -> Tenant | None:
        row = await self._s.get(TenantORM, tenant_id)
        return _to_tenant(row) if row else None

    async def por_slug(self, slug: str) -> Tenant | None:
        stmt = select(TenantORM).where(TenantORM.slug == slug)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return _to_tenant(row) if row else None

    async def listar(self) -> list[Tenant]:
        stmt = select(TenantORM).order_by(TenantORM.nome)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_tenant(r) for r in rows]

    async def listar_resumos(self) -> list[ResumoEscola]:
        tenants = await self.listar()

        async def _contagem(coluna) -> dict[uuid.UUID, int]:
            stmt = select(coluna, func.count()).group_by(coluna)
            return {tid: n for tid, n in (await self._s.execute(stmt)).all()}

        conversas = await _contagem(ConversaORM.tenant_id)
        contatos = await _contagem(ContatoORM.tenant_id)
        broadcasts = await _contagem(BroadcastORM.tenant_id)
        return [
            ResumoEscola(
                tenant=t,
                total_conversas=conversas.get(t.id, 0),
                total_contatos=contatos.get(t.id, 0),
                total_broadcasts=broadcasts.get(t.id, 0),
            )
            for t in tenants
        ]

    async def atualizar(self, tenant: Tenant) -> Tenant:
        row = await self._s.get(TenantORM, tenant.id)
        if row is None:
            raise ValueError("Escola não encontrada.")
        row.nome = tenant.nome
        row.slug = tenant.slug
        try:
            await self._s.flush()
        except IntegrityError as e:
            await self._s.rollback()
            raise ValueError("Já existe uma escola com este slug.") from e
        return _to_tenant(row)

    async def remover(self, tenant_id: uuid.UUID) -> bool:
        row = await self._s.get(TenantORM, tenant_id)
        if row is None:
            return False

        conversas_do_tenant = select(ConversaORM.id).where(ConversaORM.tenant_id == tenant_id)
        broadcasts_do_tenant = select(BroadcastORM.id).where(BroadcastORM.tenant_id == tenant_id)
        grupos_do_tenant = select(GrupoORM.id).where(GrupoORM.tenant_id == tenant_id)
        contatos_do_tenant = select(ContatoORM.id).where(ContatoORM.tenant_id == tenant_id)
        alunos_do_tenant = select(AlunoORM.id).where(AlunoORM.tenant_id == tenant_id)

        # Filhos primeiro, respeitando as FKs.
        await self._s.execute(
            delete(MensagemORM).where(MensagemORM.conversa_id.in_(conversas_do_tenant))
        )
        await self._s.execute(
            delete(aluno_responsaveis).where(
                aluno_responsaveis.c.aluno_id.in_(alunos_do_tenant)
                | aluno_responsaveis.c.contato_id.in_(contatos_do_tenant)
            )
        )
        await self._s.execute(delete(AlunoORM).where(AlunoORM.tenant_id == tenant_id))
        await self._s.execute(delete(ConversaORM).where(ConversaORM.tenant_id == tenant_id))
        await self._s.execute(delete(ConhecimentoORM).where(ConhecimentoORM.tenant_id == tenant_id))
        await self._s.execute(delete(DocumentoORM).where(DocumentoORM.tenant_id == tenant_id))
        await self._s.execute(
            delete(DestinatarioORM).where(DestinatarioORM.broadcast_id.in_(broadcasts_do_tenant))
        )
        await self._s.execute(delete(BroadcastORM).where(BroadcastORM.tenant_id == tenant_id))
        await self._s.execute(delete(TemplateORM).where(TemplateORM.tenant_id == tenant_id))
        await self._s.execute(delete(QuotaORM).where(QuotaORM.tenant_id == tenant_id))
        await self._s.execute(
            delete(grupo_contatos).where(
                grupo_contatos.c.grupo_id.in_(grupos_do_tenant)
                | grupo_contatos.c.contato_id.in_(contatos_do_tenant)
            )
        )
        await self._s.execute(delete(GrupoORM).where(GrupoORM.tenant_id == tenant_id))
        await self._s.execute(delete(ContatoORM).where(ContatoORM.tenant_id == tenant_id))
        await self._s.execute(delete(UsuarioORM).where(UsuarioORM.tenant_id == tenant_id))
        await self._s.delete(row)
        await self._s.flush()
        return True


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


def _to_aluno(row: AlunoORM) -> Aluno:
    return Aluno(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        matricula=row.matricula,
        sala_id=row.sala_id,
        ativo=row.ativo,
        criado_em=row.criado_em,
        responsaveis=[_to_contato(c) for c in row.responsaveis],
        sala_nome=row.sala.nome if row.sala else "",
    )


class SqlAlunoRepository:
    """CRUD de alunos, vínculo N:N com responsáveis e série 1:1, escopado por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _orm(self, *, tenant_id: uuid.UUID, aluno_id: uuid.UUID) -> AlunoORM | None:
        stmt = (
            select(AlunoORM)
            .where(AlunoORM.id == aluno_id, AlunoORM.tenant_id == tenant_id)
            .options(selectinload(AlunoORM.responsaveis), selectinload(AlunoORM.sala))
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def criar(self, aluno: Aluno) -> Aluno:
        self._s.add(
            AlunoORM(
                id=aluno.id,
                tenant_id=aluno.tenant_id,
                nome=aluno.nome,
                matricula=aluno.matricula,
                sala_id=aluno.sala_id,
                ativo=aluno.ativo,
                criado_em=aluno.criado_em,
            )
        )
        await self._s.flush()
        # Recarrega com os relacionamentos para devolver sala_nome/responsáveis.
        row = await self._orm(tenant_id=aluno.tenant_id, aluno_id=aluno.id)
        return _to_aluno(row)

    async def obter(self, *, tenant_id: uuid.UUID, aluno_id: uuid.UUID) -> Aluno | None:
        row = await self._orm(tenant_id=tenant_id, aluno_id=aluno_id)
        return _to_aluno(row) if row else None

    async def listar(
        self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID | None = None
    ) -> list[Aluno]:
        stmt = (
            select(AlunoORM)
            .where(AlunoORM.tenant_id == tenant_id)
            .options(selectinload(AlunoORM.responsaveis), selectinload(AlunoORM.sala))
            .order_by(AlunoORM.nome)
        )
        if sala_id is not None:
            stmt = stmt.where(AlunoORM.sala_id == sala_id)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_aluno(r) for r in rows]

    async def atualizar(self, aluno: Aluno) -> Aluno:
        row = await self._orm(tenant_id=aluno.tenant_id, aluno_id=aluno.id)
        if row is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        row.nome = aluno.nome
        row.matricula = aluno.matricula
        row.sala_id = aluno.sala_id
        row.ativo = aluno.ativo
        await self._s.flush()
        await self._s.refresh(row, attribute_names=["sala"])
        return _to_aluno(row)

    async def remover(self, *, tenant_id: uuid.UUID, aluno_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, aluno_id=aluno_id)
        if row is None:
            return False
        # Os vínculos com responsáveis somem por ON DELETE CASCADE; o aluno some daqui.
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

    async def vincular_responsavel(
        self, *, tenant_id: uuid.UUID, aluno_id: uuid.UUID, contato_id: uuid.UUID
    ) -> None:
        aluno = await self._orm(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        contato = await self._contato_do_tenant(tenant_id=tenant_id, contato_id=contato_id)
        if contato is None:
            raise ValueError("Responsável não encontrado para o tenant.")
        if all(c.id != contato_id for c in aluno.responsaveis):
            aluno.responsaveis.append(contato)
            await self._s.flush()

    async def desvincular_responsavel(
        self, *, tenant_id: uuid.UUID, aluno_id: uuid.UUID, contato_id: uuid.UUID
    ) -> None:
        aluno = await self._orm(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        aluno.responsaveis = [c for c in aluno.responsaveis if c.id != contato_id]
        await self._s.flush()
