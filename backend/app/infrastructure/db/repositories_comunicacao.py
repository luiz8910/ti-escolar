"""Repositórios de comunicação interna: avisos temporizados, fila de impressão e mural.

Cobre as features da Onda 1 (Rosa Cury): C2 (aviso temporizado), B1 (solicitação de
impressão) e A1 (mural do professor + confirmação de leitura). Tudo escopado por tenant.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import (
    SugestaoBloqueio,
    NumeroBloqueado,
    AtendimentoHumano,
    CategoriaDocumento,
    AvisoTemporizado,
    CategoriaSolicitacao,
    CotaImpressao,
    DirecaoMensagem,
    DocumentoRecebido,
    LeituraRecado,
    MensagemMediada,
    Recado,
    SolicitacaoImpressao,
    SolicitacaoInterna,
    StatusAtendimentoHumano,
    StatusDocumento,
    StatusImpressao,
    StatusSolicitacaoInterna,
)
from app.infrastructure.db.models import (
    NumeroBloqueadoORM,
    AtendimentoHumanoORM,
    AvisoTemporizadoORM,
    CotaImpressaoORM,
    DocumentoRecebidoORM,
    LeituraRecadoORM,
    MensagemMediadaORM,
    RecadoORM,
    SolicitacaoImpressaoORM,
    SolicitacaoInternaORM,
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


# --------------------------------------------------------------------------- #
# Onda 2 · A2/A4 — Canal interno professor → secretaria/gestão/pedagógico
# --------------------------------------------------------------------------- #
def _to_solicitacao_interna(row: SolicitacaoInternaORM) -> SolicitacaoInterna:
    return SolicitacaoInterna(
        id=row.id,
        tenant_id=row.tenant_id,
        professor_id=row.professor_id,
        professor_nome=row.professor_nome,
        assunto=row.assunto,
        corpo=row.corpo,
        categoria=CategoriaSolicitacao(row.categoria),
        status=StatusSolicitacaoInterna(row.status),
        resposta=row.resposta,
        respondido_em=row.respondido_em,
        criado_em=row.criado_em,
        atualizado_em=row.atualizado_em,
    )


class SqlSolicitacaoInternaRepository:
    """Canal interno professor → secretaria/gestão/pedagógico, escopado por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, solicitacao: SolicitacaoInterna) -> SolicitacaoInterna:
        self._s.add(
            SolicitacaoInternaORM(
                id=solicitacao.id,
                tenant_id=solicitacao.tenant_id,
                professor_id=solicitacao.professor_id,
                professor_nome=solicitacao.professor_nome,
                assunto=solicitacao.assunto,
                corpo=solicitacao.corpo,
                categoria=solicitacao.categoria.value,
                status=solicitacao.status.value,
                resposta=solicitacao.resposta,
                respondido_em=solicitacao.respondido_em,
                criado_em=solicitacao.criado_em,
                atualizado_em=solicitacao.atualizado_em,
            )
        )
        await self._s.flush()
        return solicitacao

    async def _orm(
        self, *, tenant_id: uuid.UUID, solicitacao_id: uuid.UUID
    ) -> SolicitacaoInternaORM | None:
        stmt = select(SolicitacaoInternaORM).where(
            SolicitacaoInternaORM.id == solicitacao_id,
            SolicitacaoInternaORM.tenant_id == tenant_id,
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(
        self, *, tenant_id: uuid.UUID, solicitacao_id: uuid.UUID
    ) -> SolicitacaoInterna | None:
        row = await self._orm(tenant_id=tenant_id, solicitacao_id=solicitacao_id)
        return _to_solicitacao_interna(row) if row else None

    async def listar(
        self,
        *,
        tenant_id: uuid.UUID,
        categoria: str | None = None,
        status: StatusSolicitacaoInterna | None = None,
        professor_id: uuid.UUID | None = None,
    ) -> list[SolicitacaoInterna]:
        stmt = select(SolicitacaoInternaORM).where(
            SolicitacaoInternaORM.tenant_id == tenant_id
        )
        if categoria is not None:
            stmt = stmt.where(SolicitacaoInternaORM.categoria == categoria)
        if status is not None:
            stmt = stmt.where(SolicitacaoInternaORM.status == status.value)
        if professor_id is not None:
            stmt = stmt.where(SolicitacaoInternaORM.professor_id == professor_id)
        stmt = stmt.order_by(SolicitacaoInternaORM.criado_em.desc())
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_solicitacao_interna(r) for r in rows]

    async def atualizar(self, solicitacao: SolicitacaoInterna) -> SolicitacaoInterna:
        row = await self._orm(
            tenant_id=solicitacao.tenant_id, solicitacao_id=solicitacao.id
        )
        if row is None:
            raise ValueError("Solicitação interna não encontrada para o tenant.")
        row.assunto = solicitacao.assunto
        row.corpo = solicitacao.corpo
        row.categoria = solicitacao.categoria.value
        row.status = solicitacao.status.value
        row.resposta = solicitacao.resposta
        row.respondido_em = solicitacao.respondido_em
        row.atualizado_em = solicitacao.atualizado_em
        await self._s.flush()
        return _to_solicitacao_interna(row)

    async def remover(self, *, tenant_id: uuid.UUID, solicitacao_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, solicitacao_id=solicitacao_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


# --------------------------------------------------------------------------- #
# Onda 2 · A3 — Canal pai ↔ professor mediado (sem expor o número do professor)
# --------------------------------------------------------------------------- #
def _to_mensagem_mediada(row: MensagemMediadaORM) -> MensagemMediada:
    return MensagemMediada(
        id=row.id,
        tenant_id=row.tenant_id,
        professor_id=row.professor_id,
        contato_telefone=row.contato_telefone,
        contato_nome=row.contato_nome,
        professor_nome=row.professor_nome,
        direcao=DirecaoMensagem(row.direcao),
        corpo=row.corpo,
        criado_em=row.criado_em,
    )


class SqlMediacaoRepository:
    """Conversas mediadas pai ↔ professor, escopadas por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def registrar(self, mensagem: MensagemMediada) -> MensagemMediada:
        self._s.add(
            MensagemMediadaORM(
                id=mensagem.id,
                tenant_id=mensagem.tenant_id,
                professor_id=mensagem.professor_id,
                contato_telefone=mensagem.contato_telefone,
                contato_nome=mensagem.contato_nome,
                professor_nome=mensagem.professor_nome,
                direcao=mensagem.direcao.value,
                corpo=mensagem.corpo,
                criado_em=mensagem.criado_em,
            )
        )
        await self._s.flush()
        return mensagem

    async def conversa(
        self, *, tenant_id: uuid.UUID, professor_id: uuid.UUID, contato_telefone: str
    ) -> list[MensagemMediada]:
        stmt = (
            select(MensagemMediadaORM)
            .where(
                MensagemMediadaORM.tenant_id == tenant_id,
                MensagemMediadaORM.professor_id == professor_id,
                MensagemMediadaORM.contato_telefone == contato_telefone,
            )
            .order_by(MensagemMediadaORM.criado_em.asc())
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_mensagem_mediada(r) for r in rows]

    async def interlocutores(
        self, *, tenant_id: uuid.UUID, professor_id: uuid.UUID
    ) -> list[MensagemMediada]:
        stmt = (
            select(MensagemMediadaORM)
            .where(
                MensagemMediadaORM.tenant_id == tenant_id,
                MensagemMediadaORM.professor_id == professor_id,
            )
            .order_by(MensagemMediadaORM.criado_em.asc())
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_mensagem_mediada(r) for r in rows]


# --------------------------------------------------------------------------- #
# Onda 2 · B2 — Cota de impressão por professor
# --------------------------------------------------------------------------- #
def _to_cota(row: CotaImpressaoORM) -> CotaImpressao:
    return CotaImpressao(
        id=row.id,
        tenant_id=row.tenant_id,
        professor_id=row.professor_id,
        limite_mensal=row.limite_mensal,
        criado_em=row.criado_em,
        atualizado_em=row.atualizado_em,
    )


class SqlCotaImpressaoRepository:
    """Franquia mensal de impressão por professor, escopada por tenant (upsert)."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _orm(
        self, *, tenant_id: uuid.UUID, professor_id: uuid.UUID
    ) -> CotaImpressaoORM | None:
        stmt = select(CotaImpressaoORM).where(
            CotaImpressaoORM.tenant_id == tenant_id,
            CotaImpressaoORM.professor_id == professor_id,
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def definir(self, cota: CotaImpressao) -> CotaImpressao:
        row = await self._orm(
            tenant_id=cota.tenant_id, professor_id=cota.professor_id
        )
        if row is None:
            row = CotaImpressaoORM(
                id=cota.id,
                tenant_id=cota.tenant_id,
                professor_id=cota.professor_id,
                limite_mensal=cota.limite_mensal,
                criado_em=cota.criado_em,
                atualizado_em=cota.atualizado_em,
            )
            self._s.add(row)
        else:
            row.limite_mensal = cota.limite_mensal
            row.atualizado_em = cota.atualizado_em
        await self._s.flush()
        return _to_cota(row)

    async def por_professor(
        self, *, tenant_id: uuid.UUID, professor_id: uuid.UUID
    ) -> CotaImpressao | None:
        row = await self._orm(tenant_id=tenant_id, professor_id=professor_id)
        return _to_cota(row) if row else None

    async def listar(self, *, tenant_id: uuid.UUID) -> list[CotaImpressao]:
        stmt = select(CotaImpressaoORM).where(CotaImpressaoORM.tenant_id == tenant_id)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_cota(r) for r in rows]

    async def remover(self, *, tenant_id: uuid.UUID, professor_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, professor_id=professor_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


# --------------------------------------------------------------------------- #
# Atendimento humano — fila da secretaria (§6j)
# --------------------------------------------------------------------------- #
def _to_atendimento(row: AtendimentoHumanoORM) -> AtendimentoHumano:
    return AtendimentoHumano(
        id=row.id,
        tenant_id=row.tenant_id,
        conversa_id=row.conversa_id,
        contato=row.contato,
        contato_nome=row.contato_nome,
        motivo=row.motivo,
        status=StatusAtendimentoHumano(row.status),
        ofereceu_em=row.ofereceu_em,
        confirmado_em=row.confirmado_em,
        fora_expediente=row.fora_expediente,
        atendente_id=row.atendente_id,
        atendente_nome=row.atendente_nome,
        ultima_mensagem_responsavel_em=row.ultima_mensagem_responsavel_em,
        assumido_em=row.assumido_em,
        resolvido_em=row.resolvido_em,
        criado_em=row.criado_em,
        atualizado_em=row.atualizado_em,
    )


class SqlAtendimentoHumanoRepository:
    """Fila de atendimentos encaminhados pelo assistente à secretaria."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, atendimento: AtendimentoHumano) -> AtendimentoHumano:
        self._s.add(
            AtendimentoHumanoORM(
                id=atendimento.id,
                tenant_id=atendimento.tenant_id,
                conversa_id=atendimento.conversa_id,
                contato=atendimento.contato,
                contato_nome=atendimento.contato_nome,
                motivo=atendimento.motivo,
                status=atendimento.status.value,
                ofereceu_em=atendimento.ofereceu_em,
                confirmado_em=atendimento.confirmado_em,
                fora_expediente=atendimento.fora_expediente,
                atendente_id=atendimento.atendente_id,
                atendente_nome=atendimento.atendente_nome,
                ultima_mensagem_responsavel_em=atendimento.ultima_mensagem_responsavel_em,
                assumido_em=atendimento.assumido_em,
                resolvido_em=atendimento.resolvido_em,
                criado_em=atendimento.criado_em,
                atualizado_em=atendimento.atualizado_em,
            )
        )
        await self._s.flush()
        return atendimento

    async def obter(
        self, *, tenant_id: uuid.UUID, atendimento_id: uuid.UUID
    ) -> AtendimentoHumano | None:
        row = await self._s.get(AtendimentoHumanoORM, atendimento_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _to_atendimento(row)

    async def em_aberto_por_conversa(
        self, *, conversa_id: uuid.UUID
    ) -> AtendimentoHumano | None:
        """O atendimento vivo da conversa (na fila ou apenas oferecido), se houver.

        Mais recente primeiro: uma conversa pode acumular ofertas recusadas ao longo do
        ano, e o que importa é o estado atual.
        """
        stmt = (
            select(AtendimentoHumanoORM)
            .where(
                AtendimentoHumanoORM.conversa_id == conversa_id,
                AtendimentoHumanoORM.status.in_(
                    [
                        StatusAtendimentoHumano.OFERECIDO.value,
                        StatusAtendimentoHumano.ABERTO.value,
                        StatusAtendimentoHumano.EM_ATENDIMENTO.value,
                    ]
                ),
            )
            .order_by(AtendimentoHumanoORM.criado_em.desc())
        )
        row = (await self._s.execute(stmt)).scalars().first()
        return _to_atendimento(row) if row else None

    def _filtrar(self, stmt, *, tenant_id, status, atendente_id):
        stmt = stmt.where(AtendimentoHumanoORM.tenant_id == tenant_id)
        if status:
            stmt = stmt.where(
                AtendimentoHumanoORM.status.in_([s.value for s in status])
            )
        if atendente_id is not None:
            stmt = stmt.where(AtendimentoHumanoORM.atendente_id == atendente_id)
        return stmt

    async def listar(
        self,
        *,
        tenant_id: uuid.UUID,
        status: Sequence[StatusAtendimentoHumano] | None = None,
        atendente_id: uuid.UUID | None = None,
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[AtendimentoHumano]:
        # Mais antigos primeiro: a fila da secretaria é por tempo de espera, não por
        # novidade — quem está aguardando há mais tempo aparece no topo.
        stmt = self._filtrar(
            select(AtendimentoHumanoORM),
            tenant_id=tenant_id,
            status=status,
            atendente_id=atendente_id,
        ).order_by(AtendimentoHumanoORM.criado_em)
        if pagina is not None and por_pagina is not None:
            stmt = stmt.offset((pagina - 1) * por_pagina).limit(por_pagina)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_atendimento(r) for r in rows]

    async def contar(
        self,
        *,
        tenant_id: uuid.UUID,
        status: Sequence[StatusAtendimentoHumano] | None = None,
        atendente_id: uuid.UUID | None = None,
    ) -> int:
        stmt = self._filtrar(
            select(func.count()).select_from(AtendimentoHumanoORM),
            tenant_id=tenant_id,
            status=status,
            atendente_id=atendente_id,
        )
        return int((await self._s.execute(stmt)).scalar_one() or 0)

    async def atualizar(self, atendimento: AtendimentoHumano) -> AtendimentoHumano:
        row = await self._s.get(AtendimentoHumanoORM, atendimento.id)
        if row is None or row.tenant_id != atendimento.tenant_id:
            raise ValueError("Atendimento não encontrado.")
        row.contato_nome = atendimento.contato_nome
        row.motivo = atendimento.motivo
        row.status = atendimento.status.value
        row.ofereceu_em = atendimento.ofereceu_em
        row.confirmado_em = atendimento.confirmado_em
        row.fora_expediente = atendimento.fora_expediente
        row.atendente_id = atendimento.atendente_id
        row.atendente_nome = atendimento.atendente_nome
        row.ultima_mensagem_responsavel_em = atendimento.ultima_mensagem_responsavel_em
        row.assumido_em = atendimento.assumido_em
        row.resolvido_em = atendimento.resolvido_em
        row.atualizado_em = _now()
        await self._s.flush()
        return _to_atendimento(row)


# --------------------------------------------------------------------------- #
# Documentos recebidos dos responsáveis (§6k)
# --------------------------------------------------------------------------- #
def _to_documento(row: DocumentoRecebidoORM) -> DocumentoRecebido:
    return DocumentoRecebido(
        id=row.id,
        tenant_id=row.tenant_id,
        conversa_id=row.conversa_id,
        contato=row.contato,
        contato_nome=row.contato_nome,
        chave_storage=row.chave_storage,
        mime=row.mime,
        tamanho=row.tamanho,
        nome_arquivo=row.nome_arquivo,
        observacao=row.observacao,
        categoria=CategoriaDocumento(row.categoria),
        categoria_sugerida=(
            CategoriaDocumento(row.categoria_sugerida) if row.categoria_sugerida else None
        ),
        status=StatusDocumento(row.status),
        aluno_id=row.aluno_id,
        aluno_nome=row.aluno_nome,
        atendimento_id=row.atendimento_id,
        media_id=row.media_id,
        expira_em=row.expira_em,
        processado_em=row.processado_em,
        criado_em=row.criado_em,
    )


class SqlDocumentoRecebidoRepository:
    """Metadados dos arquivos enviados pelos responsáveis. Os bytes ficam no storage."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, documento: DocumentoRecebido) -> DocumentoRecebido:
        self._s.add(
            DocumentoRecebidoORM(
                id=documento.id,
                tenant_id=documento.tenant_id,
                conversa_id=documento.conversa_id,
                contato=documento.contato,
                contato_nome=documento.contato_nome,
                chave_storage=documento.chave_storage,
                mime=documento.mime,
                tamanho=documento.tamanho,
                nome_arquivo=documento.nome_arquivo,
                observacao=documento.observacao,
                categoria=documento.categoria.value,
                categoria_sugerida=(
                    documento.categoria_sugerida.value
                    if documento.categoria_sugerida
                    else ""
                ),
                status=documento.status.value,
                aluno_id=documento.aluno_id,
                aluno_nome=documento.aluno_nome,
                atendimento_id=documento.atendimento_id,
                media_id=documento.media_id,
                expira_em=documento.expira_em,
                processado_em=documento.processado_em,
                criado_em=documento.criado_em,
            )
        )
        await self._s.flush()
        return documento

    async def obter(
        self, *, tenant_id: uuid.UUID, documento_id: uuid.UUID
    ) -> DocumentoRecebido | None:
        row = await self._s.get(DocumentoRecebidoORM, documento_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _to_documento(row)

    async def descartados_por_numero(
        self, *, tenant_id: uuid.UUID, desde, minimo: int
    ) -> list[SugestaoBloqueio]:
        """Números com ao menos ``minimo`` descartes desde ``desde`` (§4.5).

        Agrega no banco em vez de carregar os documentos: a janela é curta, mas em época de
        matrícula o volume não é.
        """
        stmt = (
            select(
                DocumentoRecebidoORM.contato,
                func.count().label("total"),
                func.max(DocumentoRecebidoORM.contato_nome).label("nome"),
                func.max(DocumentoRecebidoORM.criado_em).label("ultimo"),
            )
            .where(
                DocumentoRecebidoORM.tenant_id == tenant_id,
                DocumentoRecebidoORM.status == StatusDocumento.DESCARTADO.value,
                DocumentoRecebidoORM.criado_em >= desde,
            )
            .group_by(DocumentoRecebidoORM.contato)
            .having(func.count() >= minimo)
            .order_by(func.count().desc())
        )
        return [
            SugestaoBloqueio(
                telefone=r.contato,
                descartados=int(r.total),
                contato_nome=r.nome or "",
                ultimo_em=r.ultimo,
            )
            for r in (await self._s.execute(stmt)).all()
        ]

    async def por_media_id(
        self, *, tenant_id: uuid.UUID, media_id: str
    ) -> DocumentoRecebido | None:
        media_id = (media_id or "").strip()
        if not media_id:  # o id vazio é o default: nunca casa
            return None
        stmt = select(DocumentoRecebidoORM).where(
            DocumentoRecebidoORM.tenant_id == tenant_id,
            DocumentoRecebidoORM.media_id == media_id,
        )
        row = (await self._s.execute(stmt)).scalars().first()
        return _to_documento(row) if row else None

    def _filtrar(self, stmt, *, tenant_id, categoria, status, aluno_id):
        stmt = stmt.where(DocumentoRecebidoORM.tenant_id == tenant_id)
        if categoria is not None:
            stmt = stmt.where(DocumentoRecebidoORM.categoria == categoria.value)
        if status is not None:
            stmt = stmt.where(DocumentoRecebidoORM.status == status.value)
        if aluno_id is not None:
            stmt = stmt.where(DocumentoRecebidoORM.aluno_id == aluno_id)
        return stmt

    async def listar(
        self,
        *,
        tenant_id: uuid.UUID,
        categoria: CategoriaDocumento | None = None,
        status: StatusDocumento | None = None,
        aluno_id: uuid.UUID | None = None,
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[DocumentoRecebido]:
        stmt = self._filtrar(
            select(DocumentoRecebidoORM),
            tenant_id=tenant_id,
            categoria=categoria,
            status=status,
            aluno_id=aluno_id,
        ).order_by(DocumentoRecebidoORM.criado_em.desc())
        if pagina is not None and por_pagina is not None:
            stmt = stmt.offset((pagina - 1) * por_pagina).limit(por_pagina)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_documento(r) for r in rows]

    async def contar(
        self,
        *,
        tenant_id: uuid.UUID,
        categoria: CategoriaDocumento | None = None,
        status: StatusDocumento | None = None,
        aluno_id: uuid.UUID | None = None,
    ) -> int:
        stmt = self._filtrar(
            select(func.count()).select_from(DocumentoRecebidoORM),
            tenant_id=tenant_id,
            categoria=categoria,
            status=status,
            aluno_id=aluno_id,
        )
        return int((await self._s.execute(stmt)).scalar_one() or 0)

    async def atualizar(self, documento: DocumentoRecebido) -> DocumentoRecebido:
        row = await self._s.get(DocumentoRecebidoORM, documento.id)
        if row is None or row.tenant_id != documento.tenant_id:
            raise ValueError("Documento não encontrado.")
        row.categoria = documento.categoria.value
        row.status = documento.status.value
        row.observacao = documento.observacao
        row.aluno_id = documento.aluno_id
        row.aluno_nome = documento.aluno_nome
        row.processado_em = documento.processado_em
        await self._s.flush()
        return _to_documento(row)

    async def expirados(self, *, limite: int = 500) -> list[DocumentoRecebido]:
        """Cross-tenant de propósito: o expurgo é rotina da plataforma, não de uma escola."""
        stmt = (
            select(DocumentoRecebidoORM)
            .where(
                DocumentoRecebidoORM.expira_em.is_not(None),
                DocumentoRecebidoORM.expira_em <= _now(),
            )
            .order_by(DocumentoRecebidoORM.expira_em)
            .limit(limite)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_documento(r) for r in rows]

    async def remover(self, *, tenant_id: uuid.UUID, documento_id: uuid.UUID) -> bool:
        row = await self._s.get(DocumentoRecebidoORM, documento_id)
        if row is None or row.tenant_id != tenant_id:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


class SqlNumeroBloqueadoRepository:
    """Números com envio de **mídia** recusado (§6k, anti-spam)."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def bloquear(self, bloqueio: NumeroBloqueado) -> NumeroBloqueado:
        # Idempotente: bloquear de novo atualiza o motivo em vez de estourar no UNIQUE —
        # a secretaria pode clicar duas vezes, ou revisar o motivo depois.
        stmt = select(NumeroBloqueadoORM).where(
            NumeroBloqueadoORM.tenant_id == bloqueio.tenant_id,
            NumeroBloqueadoORM.telefone == bloqueio.telefone,
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = NumeroBloqueadoORM(
                id=bloqueio.id,
                tenant_id=bloqueio.tenant_id,
                telefone=bloqueio.telefone,
                motivo=bloqueio.motivo,
                bloqueado_por=bloqueio.bloqueado_por,
                bloqueado_em=bloqueio.bloqueado_em,
            )
            self._s.add(row)
        else:
            row.motivo = bloqueio.motivo
            row.bloqueado_por = bloqueio.bloqueado_por
        await self._s.flush()
        return _to_bloqueio(row)

    async def desbloquear(self, *, tenant_id: uuid.UUID, telefone: str) -> bool:
        resultado = await self._s.execute(
            delete(NumeroBloqueadoORM).where(
                NumeroBloqueadoORM.tenant_id == tenant_id,
                NumeroBloqueadoORM.telefone == telefone,
            )
        )
        await self._s.flush()
        return bool(resultado.rowcount)

    async def bloqueado(self, *, tenant_id: uuid.UUID, telefone: str) -> bool:
        stmt = select(func.count()).select_from(NumeroBloqueadoORM).where(
            NumeroBloqueadoORM.tenant_id == tenant_id,
            NumeroBloqueadoORM.telefone == telefone,
        )
        return bool((await self._s.execute(stmt)).scalar_one())

    async def listar(self, *, tenant_id: uuid.UUID) -> list[NumeroBloqueado]:
        stmt = (
            select(NumeroBloqueadoORM)
            .where(NumeroBloqueadoORM.tenant_id == tenant_id)
            .order_by(NumeroBloqueadoORM.bloqueado_em.desc())
        )
        return [_to_bloqueio(r) for r in (await self._s.execute(stmt)).scalars().all()]


def _to_bloqueio(row: NumeroBloqueadoORM) -> NumeroBloqueado:
    return NumeroBloqueado(
        id=row.id,
        tenant_id=row.tenant_id,
        telefone=row.telefone,
        motivo=row.motivo,
        bloqueado_por=row.bloqueado_por,
        bloqueado_em=row.bloqueado_em,
    )
