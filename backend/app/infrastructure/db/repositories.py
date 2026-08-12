"""Adaptadores de persistência (implementam as portas de repositório do domínio)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
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
    try:
        autor = Autor(row.autor)
    except ValueError:  # autor gravado por uma versão futura/antiga: não quebra a leitura
        autor = Autor.USUARIO
    return Mensagem(
        id=row.id,
        conversa_id=row.conversa_id,
        autor=autor,
        texto=row.texto,
        fontes=[f for f in row.fontes.split("|") if f],
        criado_em=row.criado_em,
        autor_nome=row.autor_nome,
    )


def _to_template(row: TemplateORM) -> MessageTemplate:
    return MessageTemplate(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        categoria=CategoriaTemplate(row.categoria),
        idioma=row.idioma,
        corpo=row.corpo,
        status=StatusTemplate(row.status),
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _to_conversa(row: ConversaORM) -> Conversa:
    return Conversa(
        id=row.id,
        tenant_id=row.tenant_id,
        contato=row.contato,
        criado_em=row.criado_em,
        ultima_mensagem_em=row.ultima_mensagem_em or row.criado_em,
        encerrada_em=row.encerrada_em,
    )


class SqlConversaRepository:
    def __init__(self, session: AsyncSession, *, janela_horas: int = 24) -> None:
        self._s = session
        self._janela_horas = janela_horas

    async def obter_ou_criar(self, *, tenant_id: uuid.UUID, contato: str) -> Conversa:
        """A **sessão viva** do responsável — abrindo outra quando a anterior venceu.

        A sessão vencida é encerrada aqui, e não por um job: é o momento em que se sabe
        que ela acabou, e depender de agendador deixaria conversas mortas abertas até ele
        rodar (o projeto ainda não tem scheduler).
        """
        agora = _now()
        stmt = (
            select(ConversaORM)
            .where(
                ConversaORM.tenant_id == tenant_id,
                ConversaORM.contato == contato,
                ConversaORM.encerrada_em.is_(None),
            )
            # Defensivo: se por qualquer motivo houver duas vivas, a mais recente é a certa.
            .order_by(ConversaORM.criado_em.desc())
        )
        row = (await self._s.execute(stmt)).scalars().first()

        if row is not None:
            viva = _to_conversa(row)
            if not viva.vencida_em(agora, janela_horas=self._janela_horas):
                return viva
            # Passou da janela: fecha e abre outra. O histórico da antiga fica de pé.
            row.encerrada_em = agora
            await self._s.flush()

        nova = ConversaORM(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            contato=contato,
            criado_em=agora,
            ultima_mensagem_em=agora,
        )
        self._s.add(nova)
        await self._s.flush()
        return _to_conversa(nova)

    async def encerrar(self, *, conversa_id: uuid.UUID) -> None:
        """Fecha a sessão explicitamente (atendimento resolvido, §6j).

        Idempotente: encerrar duas vezes não reescreve a data — a primeira é a verdadeira.
        """
        row = await self._s.get(ConversaORM, conversa_id)
        if row is not None and row.encerrada_em is None:
            row.encerrada_em = _now()
            await self._s.flush()

    async def adicionar_mensagem(
        self,
        *,
        conversa_id: uuid.UUID,
        autor: str,
        texto: str,
        fontes: list[str] | None = None,
        autor_nome: str = "",
    ) -> None:
        # Renova a janela da sessão: sem isto, uma conversa ativa a tarde toda venceria às
        # 24h da PRIMEIRA mensagem, no meio do assunto.
        conversa = await self._s.get(ConversaORM, conversa_id)
        if conversa is not None:
            conversa.ultima_mensagem_em = _now()
        self._s.add(
            MensagemORM(
                id=uuid.uuid4(),
                conversa_id=conversa_id,
                autor=autor,
                texto=texto,
                fontes="|".join(fontes or []),
                criado_em=_now(),
                autor_nome=autor_nome,
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
        # A fala da secretaria ("atendente") é da escola, não do responsável: entra como
        # ``assistant``. Classificá-la como ``user`` faria o assistente ler a própria
        # escola como se fosse o pai perguntando.
        return [
            {
                "role": "assistant" if m.autor in ("bot", "atendente") else "user",
                "content": m.texto,
            }
            for m in rows
        ]

    async def contar_conversas(self, *, tenant_id: uuid.UUID) -> int:
        return int(
            (
                await self._s.execute(
                    select(func.count())
                    .select_from(ConversaORM)
                    .where(ConversaORM.tenant_id == tenant_id)
                )
            ).scalar_one()
        )

    async def listar_resumos(
        self,
        *,
        tenant_id: uuid.UUID,
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[ResumoConversa]:
        """Resumos das conversas, com atividade mais recente primeiro.

        Com ``pagina``/``por_pagina``, o recorte é feito **no banco**: sem isso, uma
        escola com um ano de uso carregaria todas as conversas — e todas as mensagens de
        cada uma, por causa do ``selectinload`` — só para exibir dez linhas.

        A ordenação por **última atividade** vive no ``ORDER BY``, não em memória: com
        ``OFFSET``/``LIMIT``, reordenar depois do recorte reordena apenas a página, e
        conversas passariam a pular ou repetir entre as páginas.
        """
        ultima_atividade = func.coalesce(
            select(func.max(MensagemORM.criado_em))
            .where(MensagemORM.conversa_id == ConversaORM.id)
            .correlate(ConversaORM)
            .scalar_subquery(),
            ConversaORM.criado_em,
        )
        stmt = (
            select(ConversaORM)
            .where(ConversaORM.tenant_id == tenant_id)
            .options(selectinload(ConversaORM.mensagens))
            .order_by(ultima_atividade.desc(), ConversaORM.id.desc())
        )
        if pagina is not None and por_pagina is not None:
            stmt = stmt.offset(max(0, (pagina - 1) * por_pagina)).limit(por_pagina)
        rows = (await self._s.execute(stmt)).scalars().all()
        resumos: list[ResumoConversa] = []
        for r in rows:
            ultima = r.mensagens[-1] if r.mensagens else None
            resumos.append(
                ResumoConversa(
                    conversa=_to_conversa(r),
                    total_mensagens=len(r.mensagens),
                    ultima_mensagem=ultima.texto if ultima else "",
                    ultima_em=ultima.criado_em if ultima else None,
                )
            )
        return resumos

    async def obter_conversa(
        self, *, tenant_id: uuid.UUID, conversa_id: uuid.UUID
    ) -> Conversa | None:
        row = await self._s.get(ConversaORM, conversa_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return _to_conversa(row)

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
        return _to_template(row)

    async def por_nome(self, *, tenant_id: uuid.UUID, nome: str) -> MessageTemplate | None:
        nome = (nome or "").strip()
        if not nome:
            return None
        stmt = select(TemplateORM).where(
            TemplateORM.tenant_id == tenant_id, TemplateORM.nome == nome
        )
        row = (await self._s.execute(stmt)).scalars().first()
        return _to_template(row) if row else None


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
                    mensagem_id_externo=dest.mensagem_id_externo,
                    atualizado_em=dest.atualizado_em,
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
                mensagem_id_externo=d.mensagem_id_externo or "",
                atualizado_em=d.atualizado_em,
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

    async def contar(self, *, tenant_id: uuid.UUID) -> int:
        return int(
            (
                await self._s.execute(
                    select(func.count())
                    .select_from(BroadcastORM)
                    .where(BroadcastORM.tenant_id == tenant_id)
                )
            ).scalar_one()
        )

    async def listar(
        self,
        *,
        tenant_id: uuid.UUID,
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[Broadcast]:
        stmt = (
            select(BroadcastORM)
            .where(BroadcastORM.tenant_id == tenant_id)
            .options(selectinload(BroadcastORM.destinatarios))
            .order_by(BroadcastORM.criado_em.desc())
        )
        if pagina is not None and por_pagina is not None:
            stmt = stmt.offset(max(0, (pagina - 1) * por_pagina)).limit(por_pagina)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [self._to_broadcast(r) for r in rows]

    async def registrar_status(
        self, *, mensagem_id_externo: str, status: StatusEntrega
    ) -> bool:
        if not mensagem_id_externo:
            return False
        stmt = select(DestinatarioORM).where(
            DestinatarioORM.mensagem_id_externo == mensagem_id_externo
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        for row in rows:
            row.status = status.value
            row.atualizado_em = _now()
        await self._s.flush()
        return bool(rows)
