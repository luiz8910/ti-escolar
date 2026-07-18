"""Repositórios da Onda 3 (digitalização documental).

- ``SqlAvisoFaltaRepository`` — avisos de falta + chamada de eventual (§I1).
- ``SqlFichaMatriculaRepository`` — ficha de matrícula digital por aluno (§D1/D2/D3).
- ``SqlSolicitacaoMatriculaRepository`` — matrícula self-service pelo WhatsApp (§E1).

Tudo escopado por ``tenant_id``. Os campos ricos (ficha) e as listas (documentos,
eventuais chamados) são serializados em colunas JSON.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import (
    CAMPOS_FICHA_MATRICULA,
    AvisoFalta,
    DocumentoMatricula,
    FichaMatricula,
    SolicitacaoMatricula,
    StatusFalta,
    StatusMatricula,
)
from app.infrastructure.db.models import (
    AvisoFaltaORM,
    FichaMatriculaORM,
    SolicitacaoMatriculaORM,
)


# --------------------------------------------------------------------------- #
# I1 — Avisos de falta de professor
# --------------------------------------------------------------------------- #
def _to_falta(row: AvisoFaltaORM) -> AvisoFalta:
    return AvisoFalta(
        id=row.id,
        tenant_id=row.tenant_id,
        professor_id=row.professor_id,
        professor_nome=row.professor_nome,
        data=row.data,
        motivo=row.motivo,
        status=StatusFalta(row.status),
        eventual_nome=row.eventual_nome,
        eventual_telefone=row.eventual_telefone,
        eventuais_chamados=list(row.eventuais_chamados or []),
        criado_em=row.criado_em,
        atualizado_em=row.atualizado_em,
    )


class SqlAvisoFaltaRepository:
    """Avisos de falta de professor + chamada de eventual, escopado por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, aviso: AvisoFalta) -> AvisoFalta:
        self._s.add(
            AvisoFaltaORM(
                id=aviso.id,
                tenant_id=aviso.tenant_id,
                professor_id=aviso.professor_id,
                professor_nome=aviso.professor_nome,
                data=aviso.data,
                motivo=aviso.motivo,
                status=aviso.status.value,
                eventual_nome=aviso.eventual_nome,
                eventual_telefone=aviso.eventual_telefone,
                eventuais_chamados=list(aviso.eventuais_chamados),
                criado_em=aviso.criado_em,
                atualizado_em=aviso.atualizado_em,
            )
        )
        await self._s.flush()
        return aviso

    async def _orm(
        self, *, tenant_id: uuid.UUID, aviso_id: uuid.UUID
    ) -> AvisoFaltaORM | None:
        stmt = select(AvisoFaltaORM).where(
            AvisoFaltaORM.id == aviso_id, AvisoFaltaORM.tenant_id == tenant_id
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(
        self, *, tenant_id: uuid.UUID, aviso_id: uuid.UUID
    ) -> AvisoFalta | None:
        row = await self._orm(tenant_id=tenant_id, aviso_id=aviso_id)
        return _to_falta(row) if row else None

    async def listar(
        self, *, tenant_id: uuid.UUID, status: StatusFalta | None = None
    ) -> list[AvisoFalta]:
        stmt = select(AvisoFaltaORM).where(AvisoFaltaORM.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(AvisoFaltaORM.status == status.value)
        stmt = stmt.order_by(AvisoFaltaORM.criado_em.desc())
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_falta(r) for r in rows]

    async def atualizar(self, aviso: AvisoFalta) -> AvisoFalta:
        row = await self._orm(tenant_id=aviso.tenant_id, aviso_id=aviso.id)
        if row is None:
            raise ValueError("Aviso de falta não encontrado para o tenant.")
        row.professor_id = aviso.professor_id
        row.professor_nome = aviso.professor_nome
        row.data = aviso.data
        row.motivo = aviso.motivo
        row.status = aviso.status.value
        row.eventual_nome = aviso.eventual_nome
        row.eventual_telefone = aviso.eventual_telefone
        row.eventuais_chamados = list(aviso.eventuais_chamados)
        row.atualizado_em = aviso.atualizado_em
        await self._s.flush()
        return _to_falta(row)

    async def remover(self, *, tenant_id: uuid.UUID, aviso_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, aviso_id=aviso_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


# --------------------------------------------------------------------------- #
# D1/D2/D3 — Ficha de matrícula
# --------------------------------------------------------------------------- #
def _to_ficha(row: FichaMatriculaORM) -> FichaMatricula:
    dados = dict(row.conteudo or {})
    ficha = FichaMatricula(
        id=row.id,
        tenant_id=row.tenant_id,
        aluno_id=row.aluno_id,
        criado_em=row.criado_em,
        atualizado_em=row.atualizado_em,
    )
    for campo in CAMPOS_FICHA_MATRICULA:
        if campo in dados:
            setattr(ficha, campo, dados[campo])
    ficha.aluno_nome = dados.get("aluno_nome", "")
    return ficha


def _conteudo_ficha(ficha: FichaMatricula) -> dict:
    conteudo = {campo: getattr(ficha, campo) for campo in CAMPOS_FICHA_MATRICULA}
    conteudo["aluno_nome"] = ficha.aluno_nome
    return conteudo


class SqlFichaMatriculaRepository:
    """Ficha de matrícula digital por aluno (upsert 1:1), escopada por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _orm(
        self, *, tenant_id: uuid.UUID, aluno_id: uuid.UUID
    ) -> FichaMatriculaORM | None:
        stmt = select(FichaMatriculaORM).where(
            FichaMatriculaORM.tenant_id == tenant_id,
            FichaMatriculaORM.aluno_id == aluno_id,
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def salvar(self, ficha: FichaMatricula) -> FichaMatricula:
        row = await self._orm(tenant_id=ficha.tenant_id, aluno_id=ficha.aluno_id)
        if row is None:
            row = FichaMatriculaORM(
                id=ficha.id,
                tenant_id=ficha.tenant_id,
                aluno_id=ficha.aluno_id,
                conteudo=_conteudo_ficha(ficha),
                criado_em=ficha.criado_em,
                atualizado_em=ficha.atualizado_em,
            )
            self._s.add(row)
        else:
            row.conteudo = _conteudo_ficha(ficha)
            row.atualizado_em = ficha.atualizado_em
        await self._s.flush()
        return _to_ficha(row)

    async def por_aluno(
        self, *, tenant_id: uuid.UUID, aluno_id: uuid.UUID
    ) -> FichaMatricula | None:
        row = await self._orm(tenant_id=tenant_id, aluno_id=aluno_id)
        return _to_ficha(row) if row else None

    async def remover(self, *, tenant_id: uuid.UUID, aluno_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, aluno_id=aluno_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


# --------------------------------------------------------------------------- #
# E1 — Matrícula self-service
# --------------------------------------------------------------------------- #
def _parse_dt(valor: str | None) -> datetime | None:
    if not valor:
        return None
    try:
        return datetime.fromisoformat(valor)
    except ValueError:
        return None


def _to_matricula(row: SolicitacaoMatriculaORM) -> SolicitacaoMatricula:
    documentos = []
    for d in row.documentos or []:
        if not isinstance(d, dict):
            continue
        recebido = _parse_dt(d.get("recebido_em"))
        doc = DocumentoMatricula(nome=d.get("nome", ""), url=d.get("url", ""))
        if recebido is not None:
            doc.recebido_em = recebido
        documentos.append(doc)
    return SolicitacaoMatricula(
        id=row.id,
        tenant_id=row.tenant_id,
        contato_telefone=row.contato_telefone,
        nome_responsavel=row.nome_responsavel,
        nome_aluno=row.nome_aluno,
        status=StatusMatricula(row.status),
        observacao=row.observacao,
        documentos=documentos,
        criado_em=row.criado_em,
        atualizado_em=row.atualizado_em,
    )


def _documentos_json(solicitacao: SolicitacaoMatricula) -> list[dict]:
    return [
        {
            "nome": d.nome,
            "url": d.url,
            "recebido_em": d.recebido_em.isoformat() if d.recebido_em else "",
        }
        for d in solicitacao.documentos
    ]


class SqlSolicitacaoMatriculaRepository:
    """Matrículas self-service iniciadas pelo responsável, escopadas por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, solicitacao: SolicitacaoMatricula) -> SolicitacaoMatricula:
        self._s.add(
            SolicitacaoMatriculaORM(
                id=solicitacao.id,
                tenant_id=solicitacao.tenant_id,
                contato_telefone=solicitacao.contato_telefone,
                nome_responsavel=solicitacao.nome_responsavel,
                nome_aluno=solicitacao.nome_aluno,
                status=solicitacao.status.value,
                observacao=solicitacao.observacao,
                documentos=_documentos_json(solicitacao),
                criado_em=solicitacao.criado_em,
                atualizado_em=solicitacao.atualizado_em,
            )
        )
        await self._s.flush()
        return solicitacao

    async def _orm(
        self, *, tenant_id: uuid.UUID, solicitacao_id: uuid.UUID
    ) -> SolicitacaoMatriculaORM | None:
        stmt = select(SolicitacaoMatriculaORM).where(
            SolicitacaoMatriculaORM.id == solicitacao_id,
            SolicitacaoMatriculaORM.tenant_id == tenant_id,
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(
        self, *, tenant_id: uuid.UUID, solicitacao_id: uuid.UUID
    ) -> SolicitacaoMatricula | None:
        row = await self._orm(tenant_id=tenant_id, solicitacao_id=solicitacao_id)
        return _to_matricula(row) if row else None

    async def por_telefone(
        self, *, tenant_id: uuid.UUID, telefone: str
    ) -> SolicitacaoMatricula | None:
        # Uma solicitação "em aberto" (não concluída/cancelada) do responsável.
        stmt = (
            select(SolicitacaoMatriculaORM)
            .where(
                SolicitacaoMatriculaORM.tenant_id == tenant_id,
                SolicitacaoMatriculaORM.contato_telefone == telefone,
                SolicitacaoMatriculaORM.status.notin_(("concluida", "cancelada")),
            )
            .order_by(SolicitacaoMatriculaORM.criado_em.desc())
        )
        row = (await self._s.execute(stmt)).scalars().first()
        return _to_matricula(row) if row else None

    async def listar(
        self, *, tenant_id: uuid.UUID, status: StatusMatricula | None = None
    ) -> list[SolicitacaoMatricula]:
        stmt = select(SolicitacaoMatriculaORM).where(
            SolicitacaoMatriculaORM.tenant_id == tenant_id
        )
        if status is not None:
            stmt = stmt.where(SolicitacaoMatriculaORM.status == status.value)
        stmt = stmt.order_by(SolicitacaoMatriculaORM.criado_em.desc())
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_matricula(r) for r in rows]

    async def atualizar(
        self, solicitacao: SolicitacaoMatricula
    ) -> SolicitacaoMatricula:
        row = await self._orm(
            tenant_id=solicitacao.tenant_id, solicitacao_id=solicitacao.id
        )
        if row is None:
            raise ValueError("Solicitação de matrícula não encontrada para o tenant.")
        row.nome_responsavel = solicitacao.nome_responsavel
        row.nome_aluno = solicitacao.nome_aluno
        row.status = solicitacao.status.value
        row.observacao = solicitacao.observacao
        row.documentos = _documentos_json(solicitacao)
        row.atualizado_em = solicitacao.atualizado_em
        await self._s.flush()
        return _to_matricula(row)
