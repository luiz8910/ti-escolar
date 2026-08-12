"""Repositórios de administração: usuários, contatos e grupos."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.entities import (
    Aluno,
    AtorAuditoria,
    Cargo,
    Contato,
    Grupo,
    MetricasUsoEscola,
    Papel,
    PlanoTenant,
    Professor,
    RegistroAuditoria,
    ResumoEscola,
    Sala,
    StatusTenant,
    Tenant,
    TipoFiliacao,
    Turno,
    Usuario,
)
from app.infrastructure.db.models import (
    AlunoORM,
    AuditoriaORM,
    AvisoFaltaORM,
    AvisoTemporizadoORM,
    BroadcastORM,
    ConhecimentoORM,
    ContatoORM,
    ConversaORM,
    DestinatarioORM,
    DocumentoORM,
    FichaMatriculaORM,
    FonteConhecimentoORM,
    GrupoORM,
    MensagemORM,
    ProfessorORM,
    QuotaORM,
    RecadoORM,
    RespostaRapidaORM,
    SolicitacaoImpressaoORM,
    SolicitacaoMatriculaORM,
    SalaORM,
    TemplateORM,
    TenantORM,
    UsuarioORM,
    aluno_responsaveis,
    grupo_contatos,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dias_do_csv(bruto: str) -> tuple[int, ...]:
    """``"1,2,3,4,5"`` → ``(1, 2, 3, 4, 5)``, ignorando lixo em vez de estourar.

    Um dia inválido gravado por engano viraria exceção em **todo** carregamento da escola,
    inclusive no login — caro demais para um campo de conveniência.
    """
    dias = []
    for parte in (bruto or "").split(","):
        parte = parte.strip()
        if parte.isdigit() and 1 <= int(parte) <= 7 and int(parte) not in dias:
            dias.append(int(parte))
    return tuple(sorted(dias))


def _dias_para_csv(dias: tuple[int, ...]) -> str:
    return ",".join(str(d) for d in sorted(set(dias)))


def _to_tenant(row: TenantORM) -> Tenant:
    return Tenant(
        id=row.id,
        nome=row.nome,
        slug=row.slug,
        criado_em=row.criado_em,
        expediente_dias=_dias_do_csv(row.expediente_dias),
        expediente_inicio=row.expediente_inicio,
        expediente_fim=row.expediente_fim,
        expediente_timezone=row.expediente_timezone,
        whatsapp_numero=row.whatsapp_numero,
        meta_phone_number_id=row.meta_phone_number_id,
        telefone_contato=row.telefone_contato,
        status=StatusTenant(row.status),
        motivo_bloqueio=row.motivo_bloqueio,
        bloqueado_em=row.bloqueado_em,
        plano=PlanoTenant(row.plano),
        licenca_expira_em=row.licenca_expira_em,
        valor_mensal_centavos=row.valor_mensal_centavos,
        valor_anual_centavos=row.valor_anual_centavos,
        cancelado_em=row.cancelado_em,
        motivo_cancelamento=row.motivo_cancelamento,
    )


def _to_usuario(row: UsuarioORM) -> Usuario:
    return Usuario(
        id=row.id,
        nome=row.nome,
        email=row.email,
        senha_hash=row.senha_hash,
        papel=Papel(row.papel),
        tenant_id=row.tenant_id,
        cargo=Cargo(row.cargo) if row.cargo else None,
        telefone=row.telefone,
        endereco=row.endereco,
        turno=Turno(row.turno) if row.turno else None,
        ativo=row.ativo,
        criado_em=row.criado_em,
    )


def _to_contato(row: ContatoORM) -> Contato:
    return Contato(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        telefone=row.telefone,
        ativo=row.ativo,
        cpf=row.cpf,
        tipo_filiacao=TipoFiliacao(row.tipo_filiacao) if row.tipo_filiacao else None,
        data_nascimento=row.data_nascimento,
        telefone_2=row.telefone_2,
        local_trabalho=row.local_trabalho,
        telefone_trabalho=row.telefone_trabalho,
        email=row.email,
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
                whatsapp_numero=tenant.whatsapp_numero,
                meta_phone_number_id=tenant.meta_phone_number_id,
                telefone_contato=tenant.telefone_contato,
                status=tenant.status.value,
                motivo_bloqueio=tenant.motivo_bloqueio,
                bloqueado_em=tenant.bloqueado_em,
                plano=tenant.plano.value,
                licenca_expira_em=tenant.licenca_expira_em,
                valor_mensal_centavos=tenant.valor_mensal_centavos,
                valor_anual_centavos=tenant.valor_anual_centavos,
                cancelado_em=tenant.cancelado_em,
                motivo_cancelamento=tenant.motivo_cancelamento,
                expediente_dias=_dias_para_csv(tenant.expediente_dias),
                expediente_inicio=tenant.expediente_inicio,
                expediente_fim=tenant.expediente_fim,
                expediente_timezone=tenant.expediente_timezone,
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

    async def por_whatsapp(self, numero: str) -> Tenant | None:
        numero = (numero or "").strip()
        if not numero:  # nunca casar pelo número vazio (padrão das escolas sem número)
            return None
        stmt = select(TenantORM).where(TenantORM.whatsapp_numero == numero)
        row = (await self._s.execute(stmt)).scalars().first()
        return _to_tenant(row) if row else None

    async def por_meta_phone_number_id(self, phone_number_id: str) -> Tenant | None:
        """Escola dona do ``phone_number_id`` da Meta — roteamento do inbound (§9e.1)."""
        pid = (phone_number_id or "").strip()
        if not pid:  # o id vazio é o default das escolas sem número na Meta: nunca casa
            return None
        stmt = select(TenantORM).where(TenantORM.meta_phone_number_id == pid)
        row = (await self._s.execute(stmt)).scalars().first()
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

    async def metricas_uso(self, tenant_id: uuid.UUID) -> MetricasUsoEscola:
        async def _contar(stmt) -> int:
            return (await self._s.execute(stmt)).scalar_one() or 0

        usuarios_ativos = await _contar(
            select(func.count())
            .select_from(UsuarioORM)
            .where(UsuarioORM.tenant_id == tenant_id, UsuarioORM.ativo.is_(True))
        )
        contatos = await _contar(
            select(func.count()).select_from(ContatoORM).where(ContatoORM.tenant_id == tenant_id)
        )
        alunos = await _contar(
            select(func.count()).select_from(AlunoORM).where(AlunoORM.tenant_id == tenant_id)
        )
        conversas = await _contar(
            select(func.count()).select_from(ConversaORM).where(ConversaORM.tenant_id == tenant_id)
        )
        broadcasts = await _contar(
            select(func.count())
            .select_from(BroadcastORM)
            .where(BroadcastORM.tenant_id == tenant_id)
        )
        return MetricasUsoEscola(
            total_usuarios_ativos=usuarios_ativos,
            total_contatos=contatos,
            total_alunos=alunos,
            total_conversas=conversas,
            total_broadcasts=broadcasts,
        )

    async def atualizar(self, tenant: Tenant) -> Tenant:
        row = await self._s.get(TenantORM, tenant.id)
        if row is None:
            raise ValueError("Escola não encontrada.")
        row.nome = tenant.nome
        row.slug = tenant.slug
        row.whatsapp_numero = tenant.whatsapp_numero
        row.meta_phone_number_id = tenant.meta_phone_number_id
        row.telefone_contato = tenant.telefone_contato
        row.status = tenant.status.value
        row.motivo_bloqueio = tenant.motivo_bloqueio
        row.bloqueado_em = tenant.bloqueado_em
        row.plano = tenant.plano.value
        row.licenca_expira_em = tenant.licenca_expira_em
        row.valor_mensal_centavos = tenant.valor_mensal_centavos
        row.valor_anual_centavos = tenant.valor_anual_centavos
        row.cancelado_em = tenant.cancelado_em
        row.motivo_cancelamento = tenant.motivo_cancelamento
        row.expediente_dias = _dias_para_csv(tenant.expediente_dias)
        row.expediente_inicio = tenant.expediente_inicio
        row.expediente_fim = tenant.expediente_fim
        row.expediente_timezone = tenant.expediente_timezone
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
        # Onda 3 — fichas de matrícula (FK ao aluno CASCADE, mas removemos antes para não
        # depender da ordem) e matrículas self-service (FK só a tenants, sem cascade).
        await self._s.execute(
            delete(FichaMatriculaORM).where(FichaMatriculaORM.tenant_id == tenant_id)
        )
        await self._s.execute(
            delete(SolicitacaoMatriculaORM).where(
                SolicitacaoMatriculaORM.tenant_id == tenant_id
            )
        )
        await self._s.execute(delete(AlunoORM).where(AlunoORM.tenant_id == tenant_id))
        # Séries (turmas); depois os professores que elas referenciam. O vínculo manual
        # pai↔turma não existe mais — ele é derivado dos alunos, já apagados acima.
        await self._s.execute(delete(SalaORM).where(SalaORM.tenant_id == tenant_id))
        # Fila de impressão (FK a professores SET NULL) antes de remover os professores.
        await self._s.execute(
            delete(SolicitacaoImpressaoORM).where(
                SolicitacaoImpressaoORM.tenant_id == tenant_id
            )
        )
        # Recados do mural (as leituras somem por ON DELETE CASCADE).
        await self._s.execute(delete(RecadoORM).where(RecadoORM.tenant_id == tenant_id))
        # Avisos de falta (FK a professores SET NULL) antes de remover os professores.
        await self._s.execute(
            delete(AvisoFaltaORM).where(AvisoFaltaORM.tenant_id == tenant_id)
        )
        await self._s.execute(delete(ProfessorORM).where(ProfessorORM.tenant_id == tenant_id))
        await self._s.execute(delete(ConversaORM).where(ConversaORM.tenant_id == tenant_id))
        # Respostas rápidas (FK a fontes SET NULL) antes das fontes; depois os trechos e fontes.
        await self._s.execute(
            delete(RespostaRapidaORM).where(RespostaRapidaORM.tenant_id == tenant_id)
        )
        await self._s.execute(delete(ConhecimentoORM).where(ConhecimentoORM.tenant_id == tenant_id))
        await self._s.execute(
            delete(FonteConhecimentoORM).where(FonteConhecimentoORM.tenant_id == tenant_id)
        )
        await self._s.execute(
            delete(AvisoTemporizadoORM).where(AvisoTemporizadoORM.tenant_id == tenant_id)
        )
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
        await self._s.execute(delete(AuditoriaORM).where(AuditoriaORM.tenant_id == tenant_id))
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
                cargo=usuario.cargo.value if usuario.cargo else "",
                telefone=usuario.telefone,
                endereco=usuario.endereco,
                turno=usuario.turno.value if usuario.turno else "",
                ativo=usuario.ativo,
                criado_em=usuario.criado_em,
            )
        )
        await self._s.flush()
        return usuario

    async def obter(self, usuario_id: uuid.UUID) -> Usuario | None:
        row = await self._s.get(UsuarioORM, usuario_id)
        return _to_usuario(row) if row else None

    async def listar(self, *, tenant_id: uuid.UUID | None = None) -> list[Usuario]:
        stmt = select(UsuarioORM).order_by(UsuarioORM.nome)
        if tenant_id is not None:
            stmt = stmt.where(UsuarioORM.tenant_id == tenant_id)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_usuario(r) for r in rows]

    async def atualizar(self, usuario: Usuario) -> Usuario:
        row = await self._s.get(UsuarioORM, usuario.id)
        if row is None:
            raise ValueError("Usuário não encontrado.")
        row.nome = usuario.nome
        row.senha_hash = usuario.senha_hash
        row.ativo = usuario.ativo
        # `papel` acompanha o cargo: quem vira secretaria perde a gestão de usuários na
        # requisição seguinte, e quem sai de secretaria a ganha. Manter os dois em sincronia
        # aqui evita o estado impossível "cargo de diretor, papel de secretaria".
        row.papel = usuario.papel.value
        row.cargo = usuario.cargo.value if usuario.cargo else ""
        row.telefone = usuario.telefone
        row.endereco = usuario.endereco
        row.turno = usuario.turno.value if usuario.turno else ""
        await self._s.flush()
        return _to_usuario(row)


def _to_auditoria(row: AuditoriaORM) -> RegistroAuditoria:
    return RegistroAuditoria(
        id=row.id,
        tenant_id=row.tenant_id,
        ator=AtorAuditoria(row.ator),
        ator_id=row.ator_id,
        ator_nome=row.ator_nome,
        acao=row.acao,
        descricao=row.descricao,
        metadados=row.metadados or {},
        criado_em=row.criado_em,
    )


class SqlAuditLogRepository:
    """Persistência do log de auditoria (ações de usuários e da LLM)."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def registrar(self, registro: RegistroAuditoria) -> RegistroAuditoria:
        self._s.add(
            AuditoriaORM(
                id=registro.id,
                tenant_id=registro.tenant_id,
                ator=registro.ator.value,
                ator_id=registro.ator_id,
                ator_nome=registro.ator_nome,
                acao=registro.acao,
                descricao=registro.descricao,
                metadados=registro.metadados,
                criado_em=registro.criado_em,
            )
        )
        await self._s.flush()
        return registro

    async def contar(self, *, tenant_id: uuid.UUID) -> int:
        return int(
            (
                await self._s.execute(
                    select(func.count())
                    .select_from(AuditoriaORM)
                    .where(AuditoriaORM.tenant_id == tenant_id)
                )
            ).scalar_one()
        )

    async def listar(
        self,
        *,
        tenant_id: uuid.UUID,
        limite: int = 200,
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[RegistroAuditoria]:
        stmt = (
            select(AuditoriaORM)
            .where(AuditoriaORM.tenant_id == tenant_id)
            .order_by(AuditoriaORM.criado_em.desc())
        )
        if pagina is not None and por_pagina is not None:
            stmt = stmt.offset(max(0, (pagina - 1) * por_pagina)).limit(por_pagina)
        else:
            stmt = stmt.limit(limite)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_auditoria(r) for r in rows]


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


def _to_professor(row: ProfessorORM) -> Professor:
    return Professor(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        telefone=row.telefone,
        cpf=row.cpf,
        data_nascimento=row.data_nascimento,
        matricula=row.matricula,
        endereco=row.endereco,
        telefone_2=row.telefone_2,
        email=row.email,
        educacao_fisica=row.educacao_fisica,
        titular=row.titular,
        senha_hash=row.senha_hash,
        criado_em=row.criado_em,
    )


def _to_sala(row: SalaORM, *, pais: list[Contato] | None = None) -> Sala:
    """``pais`` vem de fora porque **é derivado dos alunos** (ver `_pais_das_salas`), e
    não de um vínculo próprio da turma."""
    return Sala(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        descricao=row.descricao,
        ano_letivo=row.ano_letivo,
        etapa=row.etapa,
        turma=row.turma,
        numero_sala=row.numero_sala,
        periodo=Turno(row.periodo) if row.periodo else None,
        grade_horario=dict(row.grade_horario or {}),
        criado_em=row.criado_em,
        pais=list(pais or []),
        professor_id=row.professor_id,
        professor_nome=row.professor.nome if row.professor else "",
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
                ativo=contato.ativo,
                cpf=contato.cpf,
                tipo_filiacao=(
                    contato.tipo_filiacao.value if contato.tipo_filiacao else ""
                ),
                data_nascimento=contato.data_nascimento,
                telefone_2=contato.telefone_2,
                local_trabalho=contato.local_trabalho,
                telefone_trabalho=contato.telefone_trabalho,
                email=contato.email,
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

    async def por_cpf(self, *, tenant_id: uuid.UUID, cpf: str) -> Contato | None:
        # CPF vazio não identifica ninguém: devolver "o primeiro sem CPF" faria o cadastro
        # recusar todo responsável novo por falso duplicado.
        if not cpf:
            return None
        stmt = select(ContatoORM).where(
            ContatoORM.tenant_id == tenant_id, ContatoORM.cpf == cpf
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return _to_contato(row) if row else None

    async def por_telefones(
        self, *, tenant_id: uuid.UUID, telefones: Sequence[str]
    ) -> dict[str, Contato]:
        """Contatos de vários telefones de uma vez, indexados pelo telefone.

        Nomear uma página de atendimentos card a card seria um SELECT por card.
        """
        alvo = {t for t in telefones if t}
        if not alvo:
            return {}
        stmt = select(ContatoORM).where(
            ContatoORM.tenant_id == tenant_id, ContatoORM.telefone.in_(alvo)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        return {r.telefone: _to_contato(r) for r in rows}

    async def contar(self, *, tenant_id: uuid.UUID) -> int:
        return int(
            (
                await self._s.execute(
                    select(func.count())
                    .select_from(ContatoORM)
                    .where(ContatoORM.tenant_id == tenant_id)
                )
            ).scalar_one()
        )

    async def listar(
        self,
        *,
        tenant_id: uuid.UUID,
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[Contato]:
        """Sem paginação, devolve todos — os casos de uso internos (grupos, cobertura,
        progressão) precisam do conjunto completo. A borda HTTP é que pagina."""
        stmt = (
            select(ContatoORM)
            .where(ContatoORM.tenant_id == tenant_id)
            .order_by(ContatoORM.criado_em.desc())
        )
        if pagina is not None and por_pagina is not None:
            stmt = stmt.offset(max(0, (pagina - 1) * por_pagina)).limit(por_pagina)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_contato(r) for r in rows]

    async def atualizar(self, contato: Contato) -> Contato:
        row = await self._orm(tenant_id=contato.tenant_id, contato_id=contato.id)
        if row is None:
            raise ValueError("Contato não encontrado para o tenant.")
        row.nome = contato.nome
        row.telefone = contato.telefone
        row.ativo = contato.ativo
        row.cpf = contato.cpf
        row.tipo_filiacao = contato.tipo_filiacao.value if contato.tipo_filiacao else ""
        row.data_nascimento = contato.data_nascimento
        row.telefone_2 = contato.telefone_2
        row.local_trabalho = contato.local_trabalho
        row.telefone_trabalho = contato.telefone_trabalho
        row.email = contato.email
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
                ano_letivo=sala.ano_letivo,
                etapa=sala.etapa,
                turma=sala.turma,
                numero_sala=sala.numero_sala,
                periodo=sala.periodo.value if sala.periodo else "",
                grade_horario=dict(sala.grade_horario or {}),
                criado_em=sala.criado_em,
            )
        )
        await self._s.flush()
        return sala

    async def _orm(self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID) -> SalaORM | None:
        stmt = (
            select(SalaORM)
            .where(SalaORM.id == sala_id, SalaORM.tenant_id == tenant_id)
            .options(selectinload(SalaORM.professor))
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID) -> Sala | None:
        row = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        if row is None:
            return None
        pais = await self._pais_das_salas(tenant_id=tenant_id, sala_ids=[sala_id])
        return _to_sala(row, pais=pais.get(sala_id, []))

    async def _pais_das_salas(
        self, *, tenant_id: uuid.UUID, sala_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[Contato]]:
        """Responsáveis por turma, **derivados dos alunos ativos**.

        Antes existia um vínculo próprio (``sala_contatos``), mantido à mão. Ele permitia
        um pai ligado a uma turma **sem nenhum filho nela** — e era o que fazia a cobertura
        de contatos contar errado. Agora o pai pertence à turma porque tem aluno ativo lá.

        Ex-aluno não conta: a família de quem já saiu não deve continuar recebendo o aviso
        da turma. Uma consulta só para todas as turmas — a lista de turmas é a tela mais
        aberta do painel.
        """
        if not sala_ids:
            return {}
        stmt = (
            select(AlunoORM)
            .where(
                AlunoORM.tenant_id == tenant_id,
                AlunoORM.sala_id.in_(list(sala_ids)),
                AlunoORM.ativo.is_(True),
            )
            .options(selectinload(AlunoORM.responsaveis))
        )
        alunos = (await self._s.execute(stmt)).scalars().all()

        por_sala: dict[uuid.UUID, list[Contato]] = {}
        vistos: dict[uuid.UUID, set[uuid.UUID]] = {}
        for aluno in alunos:
            ids = vistos.setdefault(aluno.sala_id, set())
            for contato in aluno.responsaveis:
                # Irmãos na mesma turma não duplicam o responsável no relatório.
                if contato.id in ids:
                    continue
                ids.add(contato.id)
                por_sala.setdefault(aluno.sala_id, []).append(_to_contato(contato))
        for lista in por_sala.values():
            lista.sort(key=lambda c: c.nome)
        return por_sala

    async def listar(self, *, tenant_id: uuid.UUID) -> list[Sala]:
        stmt = (
            select(SalaORM)
            .where(SalaORM.tenant_id == tenant_id)
            .options(selectinload(SalaORM.professor))
            # Ordena pela identificação estruturada; `nome` desempata as turmas antigas.
            .order_by(SalaORM.ano_letivo.desc(), SalaORM.etapa, SalaORM.turma, SalaORM.nome)
        )
        rows = (await self._s.execute(stmt)).scalars().all()
        pais = await self._pais_das_salas(
            tenant_id=tenant_id, sala_ids=[r.id for r in rows]
        )
        return [_to_sala(r, pais=pais.get(r.id, [])) for r in rows]

    async def atualizar(self, sala: Sala) -> Sala:
        row = await self._orm(tenant_id=sala.tenant_id, sala_id=sala.id)
        if row is None:
            raise ValueError("Sala não encontrada para o tenant.")
        row.nome = sala.nome
        row.descricao = sala.descricao
        row.ano_letivo = sala.ano_letivo
        row.etapa = sala.etapa
        row.turma = sala.turma
        row.numero_sala = sala.numero_sala
        row.periodo = sala.periodo.value if sala.periodo else ""
        row.grade_horario = dict(sala.grade_horario or {})
        await self._s.flush()
        return await self.obter(tenant_id=sala.tenant_id, sala_id=sala.id)

    async def remover(self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        if row is None:
            return False
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

    async def pais(self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID) -> list[Contato]:
        """Responsáveis da turma — **derivados dos alunos ativos** (ver `_pais_das_salas`).

        Os métodos ``vincular_pai``/``desvincular_pai`` sumiram junto com a tabela
        ``sala_contatos``: não há mais o que vincular à mão.
        """
        row = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        if row is None:
            raise ValueError("Sala não encontrada para o tenant.")
        pais = await self._pais_das_salas(tenant_id=tenant_id, sala_ids=[sala_id])
        return pais.get(sala_id, [])

    async def definir_professor(
        self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID, professor_id: uuid.UUID | None
    ) -> Sala:
        sala = await self._orm(tenant_id=tenant_id, sala_id=sala_id)
        if sala is None:
            raise ValueError("Sala não encontrada para o tenant.")
        if professor_id is not None:
            stmt = select(ProfessorORM).where(
                ProfessorORM.id == professor_id, ProfessorORM.tenant_id == tenant_id
            )
            professor = (await self._s.execute(stmt)).scalar_one_or_none()
            if professor is None:
                raise ValueError("Professor não encontrado para o tenant.")
        sala.professor_id = professor_id
        await self._s.flush()
        await self._s.refresh(sala, attribute_names=["professor"])
        return _to_sala(sala)


class SqlProfessorRepository:
    """CRUD de professores (nome + telefone), escopado por tenant."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def criar(self, professor: Professor) -> Professor:
        self._s.add(
            ProfessorORM(
                id=professor.id,
                tenant_id=professor.tenant_id,
                nome=professor.nome,
                telefone=professor.telefone,
                cpf=professor.cpf,
                data_nascimento=professor.data_nascimento,
                matricula=professor.matricula,
                endereco=professor.endereco,
                telefone_2=professor.telefone_2,
                email=professor.email,
                educacao_fisica=professor.educacao_fisica,
                titular=professor.titular,
                senha_hash=professor.senha_hash,
                criado_em=professor.criado_em,
            )
        )
        await self._s.flush()
        return professor

    async def _orm(self, *, tenant_id: uuid.UUID, professor_id: uuid.UUID) -> ProfessorORM | None:
        stmt = select(ProfessorORM).where(
            ProfessorORM.id == professor_id, ProfessorORM.tenant_id == tenant_id
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def obter(self, *, tenant_id: uuid.UUID, professor_id: uuid.UUID) -> Professor | None:
        row = await self._orm(tenant_id=tenant_id, professor_id=professor_id)
        return _to_professor(row) if row else None

    async def por_telefone(self, *, tenant_id: uuid.UUID, telefone: str) -> Professor | None:
        stmt = select(ProfessorORM).where(
            ProfessorORM.tenant_id == tenant_id, ProfessorORM.telefone == telefone
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return _to_professor(row) if row else None

    async def por_cpf(self, *, tenant_id: uuid.UUID, cpf: str) -> Professor | None:
        # CPF vazio não identifica ninguém: devolver "o primeiro sem CPF" faria o cadastro
        # recusar todo professor novo por falso duplicado.
        if not cpf:
            return None
        stmt = select(ProfessorORM).where(
            ProfessorORM.tenant_id == tenant_id, ProfessorORM.cpf == cpf
        )
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return _to_professor(row) if row else None

    async def listar(
        self, *, tenant_id: uuid.UUID, apenas_eventuais: bool = False
    ) -> list[Professor]:
        stmt = select(ProfessorORM).where(ProfessorORM.tenant_id == tenant_id)
        if apenas_eventuais:
            # A lista de quem cobre falta (§I1). Sem telefone o eventual não é chamável,
            # então nem entra na lista — evita a secretaria "convocar" quem não recebe.
            stmt = stmt.where(
                ProfessorORM.titular.is_(False), ProfessorORM.telefone != ""
            )
        rows = (await self._s.execute(stmt.order_by(ProfessorORM.nome))).scalars().all()
        return [_to_professor(r) for r in rows]

    async def atualizar(self, professor: Professor) -> Professor:
        row = await self._orm(tenant_id=professor.tenant_id, professor_id=professor.id)
        if row is None:
            raise ValueError("Professor não encontrado para o tenant.")
        row.nome = professor.nome
        row.telefone = professor.telefone
        row.cpf = professor.cpf
        row.data_nascimento = professor.data_nascimento
        row.matricula = professor.matricula
        row.endereco = professor.endereco
        row.telefone_2 = professor.telefone_2
        row.email = professor.email
        row.educacao_fisica = professor.educacao_fisica
        row.titular = professor.titular
        row.senha_hash = professor.senha_hash
        await self._s.flush()
        return _to_professor(row)

    async def remover(self, *, tenant_id: uuid.UUID, professor_id: uuid.UUID) -> bool:
        row = await self._orm(tenant_id=tenant_id, professor_id=professor_id)
        if row is None:
            return False
        # As séries que apontavam para este professor são desvinculadas (ON DELETE SET NULL).
        await self._s.delete(row)
        await self._s.flush()
        return True


def _to_aluno(row: AlunoORM) -> Aluno:
    return Aluno(
        id=row.id,
        tenant_id=row.tenant_id,
        nome=row.nome,
        matricula=row.matricula,
        sala_id=row.sala_id,
        ativo=row.ativo,
        foto_chave=row.foto_chave,
        desativado_em=row.desativado_em,
        motivo_desativacao=row.motivo_desativacao,
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
                foto_chave=aluno.foto_chave,
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
        self, *, tenant_id: uuid.UUID, sala_id: uuid.UUID | None = None,
        apenas_ativos: bool | None = None,
        pagina: int | None = None,
        por_pagina: int | None = None,
    ) -> list[Aluno]:
        """``apenas_ativos=None`` traz todos; ``True`` só os matriculados; ``False`` só
        os ex-alunos (a lista de quem já passou pela escola)."""
        stmt = (
            select(AlunoORM)
            .where(AlunoORM.tenant_id == tenant_id)
            .options(selectinload(AlunoORM.responsaveis), selectinload(AlunoORM.sala))
            .order_by(AlunoORM.criado_em.desc())
        )
        if sala_id is not None:
            stmt = stmt.where(AlunoORM.sala_id == sala_id)
        if apenas_ativos is not None:
            stmt = stmt.where(AlunoORM.ativo.is_(apenas_ativos))
        if pagina is not None and por_pagina is not None:
            stmt = stmt.offset(max(0, (pagina - 1) * por_pagina)).limit(por_pagina)
        rows = (await self._s.execute(stmt)).scalars().all()
        return [_to_aluno(r) for r in rows]

    async def contar(
        self,
        *,
        tenant_id: uuid.UUID,
        sala_id: uuid.UUID | None = None,
        apenas_ativos: bool | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(AlunoORM).where(AlunoORM.tenant_id == tenant_id)
        if sala_id is not None:
            stmt = stmt.where(AlunoORM.sala_id == sala_id)
        if apenas_ativos is not None:
            stmt = stmt.where(AlunoORM.ativo.is_(apenas_ativos))
        return int((await self._s.execute(stmt)).scalar_one())

    async def atualizar(self, aluno: Aluno) -> Aluno:
        row = await self._orm(tenant_id=aluno.tenant_id, aluno_id=aluno.id)
        if row is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        row.nome = aluno.nome
        row.matricula = aluno.matricula
        row.sala_id = aluno.sala_id
        row.ativo = aluno.ativo
        row.foto_chave = aluno.foto_chave
        row.desativado_em = aluno.desativado_em
        row.motivo_desativacao = aluno.motivo_desativacao
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
