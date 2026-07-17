"""Repositórios de comunicação interna: avisos temporizados, fila de impressão e mural.

Cobre as features da Onda 1 (Rosa Cury): C2 (aviso temporizado), B1 (solicitação de
impressão) e A1 (mural do professor + confirmação de leitura). Tudo escopado por tenant.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import (
    AvisoTemporizado,
    LeituraRecado,
    Recado,
    SolicitacaoImpressao,
    StatusImpressao,
)
from app.infrastructure.db.models import (
    AvisoTemporizadoORM,
    LeituraRecadoORM,
    RecadoORM,
    SolicitacaoImpressaoORM,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_aviso(row: AvisoTemporizadoORM) -> AvisoTemporizado:
    return AvisoTemporizado(
        id=row.id,
        tenant_id=row.tenant_id,
        mensagem=row.mensagem,
        ativo=row.ativo,
        inicia_em=row.inicia_em,
        expira_em=row.expira_em,
        criado_em=row.criado_em,
        atualizado_em=row.atualizado_em,
    )


class SqlAvisoTemporizadoRepository:
    """CRUD dos avisos temporizados, escopado por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, aviso: AvisoTemporizado) -> AvisoTemporizado:
        self._s.add(
            AvisoTemporizadoORM(
                id=aviso.id,
                tenant_id=aviso.tenant_id,
                mensagem=aviso.mensagem,
                ativo=aviso.ativo,
                inicia_em=aviso.inicia_em,
                expira_em=aviso.expira_em,
                criado_em=aviso.criado_em,
                atualizado_em=aviso.atualizado_em,
            )
        )
        await self._s.flush()
        return aviso

    async def _orm(
        self, *, tenant_id: uuid.UUID, aviso_id: uuid.UUID
    ) -> AvisoTemporizadoORM | None:
        stmt = select(AvisoTemporizadoORM).where(
            AvisoTemporizadoORM.id == aviso_id,
            AvisoTemporizadoORM.tenant_id == tenant_id,
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(
        self, *, tenant_id: uuid.UUID, aviso_id: uuid.UUID
    ) -> AvisoTemporizado | None:
        row = await self._orm(tenant_id=tenant_id, aviso_id=aviso_id)
        return _to_aviso(row) if row else None

    async def listar(self, *, tenant_id: uuid.UUID) -> list[AvisoTemporizado]:
        stmt = (
            select(AvisoTemporizadoORM)
            .where(AvisoTemporizadoORM.tenant_id == tenant_id)
            .order_by(AvisoTemporizadoORM.criado_em.desc())
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_aviso(r) for r in rows]

    async def vigente(self, *, tenant_id: uuid.UUID) -> AvisoTemporizado | None:
        """Aviso ativo e dentro da janela de vigência (o mais recente, se houver vários)."""
        stmt = (
            select(AvisoTemporizadoORM)
            .where(
                AvisoTemporizadoORM.tenant_id == tenant_id,
                AvisoTemporizadoORM.ativo.is_(True),
            )
            .order_by(AvisoTemporizadoORM.criado_em.desc())
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        agora = _now()
        for row in rows:
            aviso = _to_aviso(row)
            if aviso.vigente_em(agora):
                return aviso
        return None

    async def atualizar(self, aviso: AvisoTemporizado) -> AvisoTemporizado:
        row = await self._orm(tenant_id=aviso.tenant_id, aviso_id=aviso.id)
        if row is None:
            raise ValueError("Aviso não encontrado para o tenant.")
        row.mensagem = aviso.mensagem
        row.ativo = aviso.ativo
        row.inicia_em = aviso.inicia_em
        row.expira_em = aviso.expira_em
        row.atualizado_em = aviso.atualizado_em
        await self._s.flush()
        return _to_aviso(row)

    async def remover(self, *, tenant_id: uuid.UUID, aviso_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, aviso_id=aviso_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


def _to_impressao(row: SolicitacaoImpressaoORM) -> SolicitacaoImpressao:
    return SolicitacaoImpressao(
        id=row.id,
        tenant_id=row.tenant_id,
        professor_id=row.professor_id,
        professor_nome=row.professor_nome,
        arquivo_nome=row.arquivo_nome,
        arquivo_url=row.arquivo_url,
        copias=row.copias,
        colorido=row.colorido,
        frente_verso=row.frente_verso,
        observacao=row.observacao,
        status=StatusImpressao(row.status),
        criado_em=row.criado_em,
        atualizado_em=row.atualizado_em,
    )


class SqlSolicitacaoImpressaoRepository:
    """Fila de solicitações de impressão, escopada por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, solicitacao: SolicitacaoImpressao) -> SolicitacaoImpressao:
        self._s.add(
            SolicitacaoImpressaoORM(
                id=solicitacao.id,
                tenant_id=solicitacao.tenant_id,
                professor_id=solicitacao.professor_id,
                professor_nome=solicitacao.professor_nome,
                arquivo_nome=solicitacao.arquivo_nome,
                arquivo_url=solicitacao.arquivo_url,
                copias=solicitacao.copias,
                colorido=solicitacao.colorido,
                frente_verso=solicitacao.frente_verso,
                observacao=solicitacao.observacao,
                status=solicitacao.status.value,
                criado_em=solicitacao.criado_em,
                atualizado_em=solicitacao.atualizado_em,
            )
        )
        await self._s.flush()
        return solicitacao

    async def _orm(
        self, *, tenant_id: uuid.UUID, solicitacao_id: uuid.UUID
    ) -> SolicitacaoImpressaoORM | None:
        stmt = select(SolicitacaoImpressaoORM).where(
            SolicitacaoImpressaoORM.id == solicitacao_id,
            SolicitacaoImpressaoORM.tenant_id == tenant_id,
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(
        self, *, tenant_id: uuid.UUID, solicitacao_id: uuid.UUID
    ) -> SolicitacaoImpressao | None:
        row = await self._orm(tenant_id=tenant_id, solicitacao_id=solicitacao_id)
        return _to_impressao(row) if row else None

    async def listar(
        self, *, tenant_id: uuid.UUID, status: StatusImpressao | None = None
    ) -> list[SolicitacaoImpressao]:
        stmt = select(SolicitacaoImpressaoORM).where(
            SolicitacaoImpressaoORM.tenant_id == tenant_id
        )
        if status is not None:
            stmt = stmt.where(SolicitacaoImpressaoORM.status == status.value)
        stmt = stmt.order_by(SolicitacaoImpressaoORM.criado_em.desc())
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_impressao(r) for r in rows]

    async def atualizar(self, solicitacao: SolicitacaoImpressao) -> SolicitacaoImpressao:
        row = await self._orm(
            tenant_id=solicitacao.tenant_id, solicitacao_id=solicitacao.id
        )
        if row is None:
            raise ValueError("Solicitação de impressão não encontrada para o tenant.")
        row.status = solicitacao.status.value
        row.observacao = solicitacao.observacao
        row.copias = solicitacao.copias
        row.colorido = solicitacao.colorido
        row.frente_verso = solicitacao.frente_verso
        row.atualizado_em = solicitacao.atualizado_em
        await self._s.flush()
        return _to_impressao(row)

    async def remover(self, *, tenant_id: uuid.UUID, solicitacao_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, solicitacao_id=solicitacao_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


def _to_recado(row: RecadoORM) -> Recado:
    return Recado(
        id=row.id,
        tenant_id=row.tenant_id,
        titulo=row.titulo,
        corpo=row.corpo,
        autor_id=row.autor_id,
        autor_nome=row.autor_nome,
        criado_em=row.criado_em,
    )


def _to_leitura(row: LeituraRecadoORM) -> LeituraRecado:
    return LeituraRecado(
        recado_id=row.recado_id,
        professor_id=row.professor_id,
        lido_em=row.lido_em,
    )


class SqlMuralRepository:
    """Mural de recados aos professores + confirmação de leitura, escopado por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, recado: Recado) -> Recado:
        self._s.add(
            RecadoORM(
                id=recado.id,
                tenant_id=recado.tenant_id,
                titulo=recado.titulo,
                corpo=recado.corpo,
                autor_id=recado.autor_id,
                autor_nome=recado.autor_nome,
                criado_em=recado.criado_em,
            )
        )
        await self._s.flush()
        return recado

    async def _orm(
        self, *, tenant_id: uuid.UUID, recado_id: uuid.UUID
    ) -> RecadoORM | None:
        stmt = select(RecadoORM).where(
            RecadoORM.id == recado_id, RecadoORM.tenant_id == tenant_id
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(self, *, tenant_id: uuid.UUID, recado_id: uuid.UUID) -> Recado | None:
        row = await self._orm(tenant_id=tenant_id, recado_id=recado_id)
        return _to_recado(row) if row else None

    async def listar(self, *, tenant_id: uuid.UUID) -> list[Recado]:
        stmt = (
            select(RecadoORM)
            .where(RecadoORM.tenant_id == tenant_id)
            .order_by(RecadoORM.criado_em.desc())
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_recado(r) for r in rows]

    async def remover(self, *, tenant_id: uuid.UUID, recado_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, recado_id=recado_id)
        if row is None:
            return False
        await self._s.delete(row)  # leituras somem por ON DELETE CASCADE
        await self._s.flush()
        return True

    async def marcar_leitura(
        self, *, tenant_id: uuid.UUID, recado_id: uuid.UUID, professor_id: uuid.UUID
    ) -> LeituraRecado:
        stmt = select(LeituraRecadoORM).where(
            LeituraRecadoORM.recado_id == recado_id,
            LeituraRecadoORM.professor_id == professor_id,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None:  # idempotente: não re-registra se já leu
            row = LeituraRecadoORM(
                recado_id=recado_id, professor_id=professor_id, lido_em=_now()
            )
            self._s.add(row)
            await self._s.flush()
        return _to_leitura(row)

    async def leituras(self, *, recado_id: uuid.UUID) -> list[LeituraRecado]:
        stmt = select(LeituraRecadoORM).where(LeituraRecadoORM.recado_id == recado_id)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_leitura(r) for r in rows]

    async def leituras_do_professor(
        self, *, tenant_id: uuid.UUID, professor_id: uuid.UUID
    ) -> list[LeituraRecado]:
        stmt = (
            select(LeituraRecadoORM)
            .join(RecadoORM, RecadoORM.id == LeituraRecadoORM.recado_id)
            .where(
                RecadoORM.tenant_id == tenant_id,
                LeituraRecadoORM.professor_id == professor_id,
            )
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_leitura(r) for r in rows]
