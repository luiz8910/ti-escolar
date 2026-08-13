"""Adaptadores de persistência (implementam as portas de repositório do domínio)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, or_, select
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
    TemplateNaWaba,
    Waba,
)
from app.infrastructure.db.models import (
    BroadcastORM,
    ConversaORM,
    DestinatarioORM,
    MensagemORM,
    TemplateORM,
    TemplateWabaORM,
    TenantORM,
    WabaORM,
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


def _to_template(
    row: TemplateORM, entradas: list[TemplateWabaORM] | None = None
) -> MessageTemplate:
    return MessageTemplate(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        categoria=CategoriaTemplate(row.categoria),
        idioma=row.idioma,
        corpo=row.corpo,
        wabas=[_to_template_waba(e) for e in (entradas or [])],
        exemplos=list(row.exemplos or []),
        criado_em=row.criado_em or _now(),
        atualizado_em=row.atualizado_em,
    )


def _to_template_waba(row: TemplateWabaORM) -> TemplateNaWaba:
    return TemplateNaWaba(
        waba_id=row.waba_id,
        status=StatusTemplate(row.status),
        meta_template_id=row.meta_template_id or "",
        motivo_rejeicao=row.motivo_rejeicao or "",
        atualizado_em=row.atualizado_em,
    )


def _to_waba(row: WabaORM) -> Waba:
    return Waba(
        id=row.id,
        meta_waba_id=row.meta_waba_id or "",
        nome=row.nome,
        meta_business_id=row.meta_business_id or "",
        ativo=bool(row.ativo),
        criado_em=row.criado_em or _now(),
        atualizado_em=row.atualizado_em,
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
    """Catálogo de templates + o status de cada um **em cada WABA**.

    As entradas por conta são carregadas **em lote** (uma consulta por página, não uma por
    template): a listagem do painel percorre o catálogo inteiro, e um SELECT por linha ali
    é o N+1 clássico.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def _entradas(
        self, template_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[TemplateWabaORM]]:
        if not template_ids:
            return {}
        stmt = select(TemplateWabaORM).where(
            TemplateWabaORM.template_id.in_(template_ids)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        agrupado: dict[uuid.UUID, list[TemplateWabaORM]] = {}
        for r in rows:
            agrupado.setdefault(r.template_id, []).append(r)
        return agrupado

    async def _montar(self, row: TemplateORM | None) -> MessageTemplate | None:
        if row is None:
            return None
        entradas = await self._entradas([row.id])
        return _to_template(row, entradas.get(row.id, []))

    async def _montar_muitos(self, rows: list[TemplateORM]) -> list[MessageTemplate]:
        entradas = await self._entradas([r.id for r in rows])
        return [_to_template(r, entradas.get(r.id, [])) for r in rows]

    async def obter(
        self, *, tenant_id: uuid.UUID, template_id: uuid.UUID
    ) -> MessageTemplate | None:
        row = await self._s.get(TemplateORM, template_id)
        # ``tenant_id IS NULL`` é template global: visível para toda escola.
        if row is None or (row.tenant_id is not None and row.tenant_id != tenant_id):
            return None
        return await self._montar(row)

    async def por_nome(self, *, tenant_id: uuid.UUID, nome: str) -> MessageTemplate | None:
        nome = (nome or "").strip()
        if not nome:
            return None
        stmt = select(TemplateORM).where(
            TemplateORM.nome == nome,
            or_(TemplateORM.tenant_id == tenant_id, TemplateORM.tenant_id.is_(None)),
            # O da própria escola primeiro: quem personalizou espera a versão dela.
            # ``NULLS LAST`` ordena o global depois do específico.
        ).order_by(TemplateORM.tenant_id.desc().nullslast())
        row = (await self._s.execute(stmt)).scalars().first()
        return await self._montar(row)

    async def listar(self, *, tenant_id: uuid.UUID) -> list[MessageTemplate]:
        stmt = (
            select(TemplateORM)
            .where(or_(TemplateORM.tenant_id == tenant_id, TemplateORM.tenant_id.is_(None)))
            .order_by(TemplateORM.nome)
        )
        rows = list((await self._s.execute(stmt)).scalars().all())
        return await self._montar_muitos(rows)

    async def listar_todos(self) -> list[MessageTemplate]:
        rows = list((await self._s.execute(select(TemplateORM))).scalars().all())
        return await self._montar_muitos(rows)

    async def por_meta_id(self, meta_template_id: str) -> MessageTemplate | None:
        meta_template_id = (meta_template_id or "").strip()
        if not meta_template_id:
            return None
        # O id da Meta mora na entrada por conta: o mesmo texto tem um id em cada WABA.
        stmt = select(TemplateWabaORM).where(
            TemplateWabaORM.meta_template_id == meta_template_id
        )
        entrada = (await self._s.execute(stmt)).scalars().first()
        if entrada is None:
            return None
        return await self._montar(await self._s.get(TemplateORM, entrada.template_id))

    async def por_nome_e_idioma(self, *, nome: str, idioma: str) -> MessageTemplate | None:
        nome = (nome or "").strip()
        if not nome:
            return None
        stmt = select(TemplateORM).where(
            TemplateORM.nome == nome, TemplateORM.idioma == idioma
        )
        row = (await self._s.execute(stmt)).scalars().first()
        return await self._montar(row)

    async def salvar(self, template: MessageTemplate) -> MessageTemplate:
        row = await self._s.get(TemplateORM, template.id)
        if row is None:
            row = TemplateORM(id=template.id, criado_em=template.criado_em)
            self._s.add(row)
        row.tenant_id = template.tenant_id
        row.nome = template.nome
        row.categoria = template.categoria.value
        row.idioma = template.idioma
        row.corpo = template.corpo
        row.exemplos = list(template.exemplos)
        row.atualizado_em = _now()
        await self._s.flush()

        existentes = {
            e.waba_id: e for e in (await self._entradas([template.id])).get(template.id, [])
        }
        for entrada in template.wabas:
            alvo = existentes.pop(entrada.waba_id, None)
            if alvo is None:
                alvo = TemplateWabaORM(
                    id=uuid.uuid4(),
                    template_id=template.id,
                    waba_id=entrada.waba_id,
                )
                self._s.add(alvo)
            alvo.status = entrada.status.value
            alvo.meta_template_id = entrada.meta_template_id
            alvo.motivo_rejeicao = entrada.motivo_rejeicao
            alvo.atualizado_em = _now()
        # Entrada que sumiu da entidade é submissão desfeita (conta removida do catálogo);
        # deixá-la para trás faria o status agregado considerar uma conta que já não vale.
        for sobra in existentes.values():
            await self._s.delete(sobra)

        await self._s.flush()
        return (await self._montar(row)) or template

    async def remover(self, template_id: uuid.UUID) -> bool:
        row = await self._s.get(TemplateORM, template_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True


class SqlWabaRepository:
    """Contas do WhatsApp Business. Ver `Waba`."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def listar(self, *, apenas_ativas: bool = False) -> list[Waba]:
        stmt = select(WabaORM).order_by(WabaORM.criado_em)
        if apenas_ativas:
            stmt = stmt.where(WabaORM.ativo.is_(True))
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_waba(r) for r in rows]

    async def obter(self, waba_id: uuid.UUID) -> Waba | None:
        row = await self._s.get(WabaORM, waba_id)
        return _to_waba(row) if row else None

    async def por_meta_id(self, meta_waba_id: str) -> Waba | None:
        meta_waba_id = (meta_waba_id or "").strip()
        if not meta_waba_id:
            return None
        stmt = select(WabaORM).where(WabaORM.meta_waba_id == meta_waba_id)
        row = (await self._s.execute(stmt)).scalars().first()
        return _to_waba(row) if row else None

    async def salvar(self, waba: Waba) -> Waba:
        row = await self._s.get(WabaORM, waba.id)
        if row is None:
            row = WabaORM(id=waba.id, criado_em=waba.criado_em)
            self._s.add(row)
        row.meta_waba_id = waba.meta_waba_id
        row.nome = waba.nome
        row.meta_business_id = waba.meta_business_id
        row.ativo = waba.ativo
        row.atualizado_em = _now()
        await self._s.flush()
        return _to_waba(row)

    async def remover(self, waba_id: uuid.UUID) -> bool:
        row = await self._s.get(WabaORM, waba_id)
        if row is None:
            return False
        await self._s.delete(row)
        await self._s.flush()
        return True

    async def total_escolas(self) -> dict[uuid.UUID, int]:
        stmt = (
            select(TenantORM.waba_id, func.count(TenantORM.id))
            .where(TenantORM.waba_id.is_not(None))
            .group_by(TenantORM.waba_id)
        )
        rows = (await self._s.execute(stmt)).all()
        return {linha[0]: int(linha[1]) for linha in rows}


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
