"""Modelos ORM (SQLAlchemy 2.0). Camada de infraestrutura — não vaza para o domínio."""

from __future__ import annotations

import uuid
from datetime import datetime, time

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.config import get_settings

_DIM = get_settings().embedding_dim


class Base(DeclarativeBase):
    pass


class TenantORM(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    criado_em: Mapped[datetime] = mapped_column()
    # Número de WhatsApp (E.164) da escola; vazio = usa o número padrão do canal.
    whatsapp_numero: Mapped[str] = mapped_column(
        String(30), default="", server_default="", index=True
    )
    # ``phone_number_id`` do número da escola na Meta: origem do outbound (URL da Graph API)
    # e chave de roteamento do inbound (value.metadata.phone_number_id). Indexado e único
    # entre escolas — o índice parcial da migration 0024 permite várias escolas com "".
    # Conta do WhatsApp Business (WABA) onde o número desta escola está cadastrado — é
    # onde o template dela é criado e conferido. Nulo enquanto não atribuída.
    waba_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("wabas.id"), index=True, nullable=True
    )
    meta_phone_number_id: Mapped[str] = mapped_column(
        String(64), default="", server_default="", index=True
    )
    # Telefone de contato (E.164) público da escola — informativo (secretaria). Sem índice
    # nem unicidade: não roteia mensagens.
    telefone_contato: Mapped[str] = mapped_column(String(30), default="", server_default="")
    # Licenciamento / cobrança / bloqueio.
    status: Mapped[str] = mapped_column(String(20), default="ativo", server_default="ativo")
    motivo_bloqueio: Mapped[str] = mapped_column(Text, default="", server_default="")
    bloqueado_em: Mapped[datetime | None] = mapped_column(nullable=True)
    plano: Mapped[str] = mapped_column(String(20), default="mensal", server_default="mensal")
    licenca_expira_em: Mapped[datetime | None] = mapped_column(nullable=True)
    # Cobrança: preços por ciclo, em centavos.
    valor_mensal_centavos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    valor_anual_centavos: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # Cancelamento (churn): data e motivo da saída da plataforma.
    cancelado_em: Mapped[datetime | None] = mapped_column(nullable=True)
    motivo_cancelamento: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Expediente da secretaria (§6j). Os dias vão como CSV de inteiros ISO ("1,2,3,4,5"):
    # é lista curta e imutável, e uma tabela filha só para isso não pagaria a junção.
    expediente_dias: Mapped[str] = mapped_column(
        String(20), default="1,2,3,4,5", server_default="1,2,3,4,5"
    )
    expediente_inicio: Mapped[time] = mapped_column(
        Time, default=time(7, 30), server_default="07:30"
    )
    expediente_fim: Mapped[time] = mapped_column(Time, default=time(17, 0), server_default="17:00")
    expediente_timezone: Mapped[str] = mapped_column(
        String(64), default="America/Sao_Paulo", server_default="America/Sao_Paulo"
    )


class ConversaORM(Base):
    __tablename__ = "conversas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    contato: Mapped[str] = mapped_column(String(50), index=True)
    criado_em: Mapped[datetime] = mapped_column()
    # Base da janela de inatividade da sessão (ver `Conversa`).
    ultima_mensagem_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    # Sessão fechada por inatividade ou por atendimento resolvido. NULL = viva.
    encerrada_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    mensagens: Mapped[list["MensagemORM"]] = relationship(
        back_populates="conversa", cascade="all, delete-orphan", order_by="MensagemORM.criado_em"
    )

    __table_args__ = (
        # O UNIQUE (tenant, contato) saiu na 0037: **o mesmo responsável passa a ter várias
        # conversas**, uma por sessão. O índice abaixo é o que sustenta a busca da sessão
        # viva, que roda a cada mensagem recebida.
        Index("ix_conversa_sessao_viva", "tenant_id", "contato", "encerrada_em"),
    )


class MensagemORM(Base):
    __tablename__ = "mensagens"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    conversa_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversas.id"), index=True
    )
    # "usuario" (o responsável), "bot" (o assistente) ou "atendente" (a secretaria, §6j).
    autor: Mapped[str] = mapped_column(String(20))
    # Quem da secretaria respondeu — só preenchido quando ``autor == "atendente"``. Sem
    # isso o histórico mostra que uma pessoa respondeu, mas não qual.
    autor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    texto: Mapped[str] = mapped_column(Text)
    fontes: Mapped[str] = mapped_column(Text, default="")  # separadas por "|"
    criado_em: Mapped[datetime] = mapped_column()

    conversa: Mapped[ConversaORM] = relationship(back_populates="mensagens")


class FonteConhecimentoORM(Base):
    """Documento enviado pela escola, fragmentado em trechos de ``conhecimento``."""

    __tablename__ = "fontes_conhecimento"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(300))
    tipo: Mapped[str] = mapped_column(String(30))
    total_trechos: Mapped[int] = mapped_column(Integer, default=0)
    # Texto como foi enviado. Sem ele o documento só existia fragmentado no vector store:
    # dava para apagar, nunca para reler ou corrigir.
    conteudo: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Indexado no vector store? Desativar tira do RAG sem destruir o texto.
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column(nullable=True)


class ConhecimentoORM(Base):
    __tablename__ = "conhecimento"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Documento de origem (quando o trecho veio de um upload da escola).
    fonte_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fontes_conhecimento.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tipo: Mapped[str] = mapped_column(String(30))
    titulo: Mapped[str] = mapped_column(String(300))
    conteudo: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(_DIM))
    criado_em: Mapped[datetime] = mapped_column()


class DocumentoORM(Base):
    __tablename__ = "documentos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(300))
    categoria: Mapped[str] = mapped_column(String(100))
    url: Mapped[str] = mapped_column(Text)


class TemplateORM(Base):
    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    # NULO = template **global** (catálogo compartilhado entre as escolas). Ver
    # `MessageTemplate`: templates moram na WABA, que é uma só, então o caso comum é um
    # texto único com o nome da escola como parâmetro.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True, nullable=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    categoria: Mapped[str] = mapped_column(String(30))
    idioma: Mapped[str] = mapped_column(String(10))
    corpo: Mapped[str] = mapped_column(Text)
    # Amostras dos {{n}} exigidas na submissão; não vão ao responsável.
    exemplos: Mapped[list] = mapped_column(JSON, default=list)
    criado_em: Mapped[datetime] = mapped_column(nullable=True)
    atualizado_em: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        # (nome, idioma) é único **em cada WABA**. Mantemos o UNIQUE global aqui porque o
        # texto é um só no nosso catálogo, replicado nas contas: dois registros com o
        # mesmo nome seriam duas linhas disputando o mesmo nome em toda WABA.
        UniqueConstraint("nome", "idioma", name="uq_template_nome_idioma"),
    )


class WabaORM(Base):
    """Conta do WhatsApp Business. Ver `Waba` — o endereço de todo template."""

    __tablename__ = "wabas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    meta_waba_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(200))
    # Portfólio (Meta Business Account) dono da conta: onde o teto de números e o limite
    # diário de envio são de fato medidos.
    meta_business_id: Mapped[str] = mapped_column(
        String(64), default="", server_default=""
    )
    ativo: Mapped[bool] = mapped_column(default=True, server_default="true")
    criado_em: Mapped[datetime] = mapped_column(nullable=True)
    atualizado_em: Mapped[datetime | None] = mapped_column(nullable=True)


class TemplateWabaORM(Base):
    """Status de um template **em uma** WABA. Ver `TemplateNaWaba`.

    Uma linha por (template, conta). O ``meta_template_id`` é único na Meta inteira, o
    que faz dele a chave exata do webhook: ele identifica o texto **e** a conta.
    """

    __tablename__ = "template_wabas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("templates.id", ondelete="CASCADE"),
        index=True,
    )
    waba_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("wabas.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[str] = mapped_column(String(20))
    meta_template_id: Mapped[str] = mapped_column(
        String(64), default="", server_default="", index=True
    )
    motivo_rejeicao: Mapped[str] = mapped_column(Text, default="", server_default="")
    atualizado_em: Mapped[datetime | None] = mapped_column(nullable=True)

    __table_args__ = (
        UniqueConstraint("template_id", "waba_id", name="uq_template_waba"),
    )


class BroadcastORM(Base):
    __tablename__ = "broadcasts"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("templates.id"))
    titulo: Mapped[str] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(String(30))
    agendado_para: Mapped[datetime | None] = mapped_column(nullable=True)
    criado_em: Mapped[datetime] = mapped_column()

    destinatarios: Mapped[list["DestinatarioORM"]] = relationship(
        back_populates="broadcast", cascade="all, delete-orphan"
    )


class DestinatarioORM(Base):
    __tablename__ = "destinatarios_broadcast"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    broadcast_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("broadcasts.id"), index=True
    )
    contato: Mapped[str] = mapped_column(String(50))
    parametros: Mapped[str] = mapped_column(Text, default="")  # separados por "|"
    status: Mapped[str] = mapped_column(String(20))
    # Id externo da mensagem na Meta (``wamid``), para casar eventos de status do webhook.
    mensagem_id_externo: Mapped[str] = mapped_column(String(128), default="", index=True)
    # Última atualização de status (envio ou webhook).
    atualizado_em: Mapped[datetime | None] = mapped_column(nullable=True)
    # Motivo da falha, como a Meta o descreveu. Ver `DestinatarioBroadcast.erro`.
    erro: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Tentativas já feitas para este destinatário em falha TRANSITÓRIA (timeout, 5xx).
    # Falha definitiva não conta: vai direto para FALHOU, porque repetir dá o mesmo erro
    # e queima a qualidade do número.
    tentativas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    broadcast: Mapped[BroadcastORM] = relationship(back_populates="destinatarios")


class EnvioIniciadoORM(Base):
    """Uma conversa iniciada pelo negócio — a unidade que a Meta cobra na janela de 24h.

    Substitui o contador por dia de calendário (`message_quotas`), que não conseguia
    responder à única pergunta que importa: *quantos clientes distintos foram alcançados
    nas últimas 24 horas?* Um contador agregado perde o instante de cada envio, e sem o
    instante não há janela corrida nem previsão de quando a capacidade volta.

    Guardar o `contato` é o que permite contar **distintos**: a Meta cobra cliente único,
    então o mesmo responsável em dois avisos da mesma janela é uma conversa, não duas.

    Não é derivável de `destinatarios_broadcast`, e essa foi a razão de existir: aquela
    tabela só conhece broadcast (a retomada de atendimento fora das 24h consome teto e não
    passa por lá) e seu `atualizado_em` é remexido pelo webhook de status dias depois, o
    que faria um `delivered` atrasado reescrever a hora do envio.
    """

    __tablename__ = "envios_iniciados"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Portfólio (Meta Business Account) que carrega o teto. Vazio = escola ainda sem WABA:
    # conta num balde próprio, para não somar com quem tem portfólio conhecido nem sumir
    # da contagem.
    meta_business_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    contato: Mapped[str] = mapped_column(String(50))
    enviado_em: Mapped[datetime] = mapped_column()

    __table_args__ = (
        # A consulta quente é sempre "distintos deste portfólio depois de tal instante".
        Index("ix_envios_iniciados_janela", "meta_business_id", "enviado_em"),
    )


# --------------------------------------------------------------------------- #
# Administração e grupos
# --------------------------------------------------------------------------- #
class UsuarioORM(Base):
    __tablename__ = "usuarios"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    nome: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    senha_hash: Mapped[str] = mapped_column(Text)
    # Fronteira de autorização: "super_admin" | "tenant_admin" | "secretaria".
    papel: Mapped[str] = mapped_column(String(20))
    # NULL para super admin (cross-tenant).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    # Posto na escola — ordena a hierarquia de quem gere quem. NULL só para super admin.
    cargo: Mapped[str] = mapped_column(String(20), default="", server_default="")
    # Existe para a fila de atendimento (§6j) poder notificar por WhatsApp.
    telefone: Mapped[str] = mapped_column(String(30), default="", server_default="")
    endereco: Mapped[str] = mapped_column(Text, default="", server_default="")
    turno: Mapped[str] = mapped_column(String(20), default="", server_default="")
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column()


# Associação N:N entre grupos e contatos.
grupo_contatos = Table(
    "grupo_contatos",
    Base.metadata,
    Column("grupo_id", PGUUID(as_uuid=True), ForeignKey("grupos.id"), primary_key=True),
    Column("contato_id", PGUUID(as_uuid=True), ForeignKey("contatos.id"), primary_key=True),
)


# Associação N:N entre alunos e contatos (responsáveis).
aluno_responsaveis = Table(
    "aluno_responsaveis",
    Base.metadata,
    Column(
        "aluno_id",
        PGUUID(as_uuid=True),
        ForeignKey("alunos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "contato_id",
        PGUUID(as_uuid=True),
        ForeignKey("contatos.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


# Associação N:N entre salas (turmas) e contatos (pais/responsáveis).

class ContatoORM(Base):
    __tablename__ = "contatos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    # O número da CONVERSA: roteia o inbound e assina o outbound. Único por tenant.
    telefone: Mapped[str] = mapped_column(String(50))
    # Responsável inativo (todos os seus alunos já são ex-alunos, §F1). Mantido no cadastro.
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Cadastro do responsável. CPF em 11 dígitos sem pontuação; datas em ISO.
    cpf: Mapped[str] = mapped_column(String(11), default="", server_default="")
    # "mae" | "pai" | "responsavel_legal" (termo de guarda) | "outro".
    tipo_filiacao: Mapped[str] = mapped_column(String(20), default="", server_default="")
    data_nascimento: Mapped[str] = mapped_column(String(10), default="", server_default="")
    # Emergência — NÃO recebem disparo. Ver o docstring de `Contato`.
    telefone_2: Mapped[str] = mapped_column(String(50), default="", server_default="")
    local_trabalho: Mapped[str] = mapped_column(String(200), default="", server_default="")
    telefone_trabalho: Mapped[str] = mapped_column(String(50), default="", server_default="")
    email: Mapped[str] = mapped_column(String(200), default="", server_default="")
    criado_em: Mapped[datetime] = mapped_column()

    grupos: Mapped[list["GrupoORM"]] = relationship(
        secondary=grupo_contatos, back_populates="membros"
    )
    alunos: Mapped[list["AlunoORM"]] = relationship(
        secondary=aluno_responsaveis, back_populates="responsaveis"
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "telefone", name="uq_contato_tenant_telefone"),
        # UNIQUE parcial: CPF único por escola quando informado. O default é '' e um
        # UNIQUE simples deixaria só um responsável sem CPF — mesma razão do índice de
        # `professores.cpf` (0032) e de `meta_phone_number_id` (0024).
        Index(
            "uq_contato_tenant_cpf",
            "tenant_id",
            "cpf",
            unique=True,
            postgresql_where=text("cpf <> ''"),
        ),
    )


class GrupoORM(Base):
    __tablename__ = "grupos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, default="")
    criado_em: Mapped[datetime] = mapped_column()

    membros: Mapped[list[ContatoORM]] = relationship(
        secondary=grupo_contatos, back_populates="grupos"
    )

    __table_args__ = (UniqueConstraint("tenant_id", "nome", name="uq_grupo_tenant_nome"),)


class ProfessorORM(Base):
    __tablename__ = "professores"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    telefone: Mapped[str] = mapped_column(String(50))
    # Cadastro funcional. CPF em 11 dígitos sem pontuação; datas em ISO (AAAA-MM-DD).
    cpf: Mapped[str] = mapped_column(String(11), default="", server_default="")
    data_nascimento: Mapped[str] = mapped_column(String(10), default="", server_default="")
    matricula: Mapped[str] = mapped_column(String(50), default="", server_default="")
    endereco: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Emergência — não recebe disparo. Ver o docstring de `Professor`.
    telefone_2: Mapped[str] = mapped_column(String(50), default="", server_default="")
    email: Mapped[str] = mapped_column(String(200), default="", server_default="")
    educacao_fisica: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # `titular=False` = eventual: é a lista de quem cobre falta (§I1).
    titular: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Senha (hash PBKDF2) para o login do professor no mural (§A1); vazio = sem acesso.
    senha_hash: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Vínculo vivo com a escola: desligado, o número deixa de ser reconhecido no inbound.
    ativo: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
    )
    criado_em: Mapped[datetime] = mapped_column()

    __table_args__ = (
        UniqueConstraint("tenant_id", "telefone", name="uq_professor_tenant_telefone"),
        # UNIQUE parcial: o CPF é único por escola quando informado, mas o default é ''
        # e um UNIQUE simples permitiria **um só** professor sem CPF cadastrado.
        Index(
            "uq_professor_tenant_cpf",
            "tenant_id",
            "cpf",
            unique=True,
            postgresql_where=text("cpf <> ''"),
        ),
    )


class SolicitacaoImpressaoORM(Base):
    __tablename__ = "solicitacoes_impressao"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Professor solicitante; ON DELETE SET NULL preserva o histórico da fila.
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    professor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    arquivo_nome: Mapped[str] = mapped_column(String(300))
    arquivo_url: Mapped[str] = mapped_column(Text, default="", server_default="")
    copias: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    colorido: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    frente_verso: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    observacao: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(20), default="pendente", server_default="pendente", index=True
    )
    # Por onde entrou: "portal" (formulário) ou "whatsapp" (arquivo enviado ao número).
    origem: Mapped[str] = mapped_column(
        String(20), default="portal", server_default="portal"
    )
    # Bytes do arquivo, quando ele veio pelo WhatsApp. Ponteiro para o ArquivoStorage —
    # nunca o conteúdo, como em `documentos_recebidos`.
    chave_storage: Mapped[str] = mapped_column(String(64), default="", server_default="")
    mime: Mapped[str] = mapped_column(String(120), default="", server_default="")
    tamanho: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    # `media_id` da Meta: deduplica a reentrega do webhook.
    media_id: Mapped[str] = mapped_column(
        String(120), default="", server_default="", index=True
    )
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()


class SalaORM(Base):
    __tablename__ = "salas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Derivado de etapa + turma; mantido em coluna porque relatórios e telas já o exibem.
    nome: Mapped[str] = mapped_column(String(200))
    descricao: Mapped[str] = mapped_column(Text, default="")
    # Identificação estruturada (ficha física: ANO · ETAPA · TURMA · PERÍODO).
    ano_letivo: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    etapa: Mapped[str] = mapped_column(String(60), default="", server_default="")
    turma: Mapped[str] = mapped_column(String(10), default="", server_default="")
    numero_sala: Mapped[str] = mapped_column(String(30), default="", server_default="")
    periodo: Mapped[str] = mapped_column(String(20), default="", server_default="")
    # Grade de horário nos dois formatos da decisão B, sobre a mesma coluna.
    grade_horario: Mapped[dict] = mapped_column(JSON, default=dict, server_default="{}")
    # Professor responsável pela série (1:1; um professor pode ter várias séries).
    # ON DELETE SET NULL: remover o professor apenas desvincula as séries.
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    criado_em: Mapped[datetime] = mapped_column()

    professor: Mapped["ProfessorORM | None"] = relationship()

    __table_args__ = (
        # A turma é identificada por **ano + etapa + letra**. O UNIQUE antigo em `nome` foi
        # removido na 0036: `nome` é derivado de etapa + turma e **se repete legitimamente
        # entre anos letivos** — a "4ª série B" de 2026 e a de 2027 são turmas diferentes,
        # e o índice antigo recusava a segunda.
        UniqueConstraint(
            "tenant_id", "ano_letivo", "etapa", "turma", name="uq_sala_tenant_ano_turma"
        ),
    )


class AlunoORM(Base):
    __tablename__ = "alunos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    nome: Mapped[str] = mapped_column(String(200))
    matricula: Mapped[str] = mapped_column(String(50), default="")
    # Série/turma do aluno (1:1, obrigatória). A exclusão de uma série é mediada pelos
    # casos de uso (que exigem uma série destino para os alunos), por isso a FK é
    # restritiva: nenhum caminho pode deixar aluno órfão nem apagá-lo em cascata.
    sala_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("salas.id"), nullable=False, index=True
    )
    # Soft delete: o aluno nunca é apagado pelo painel — o registro de que ele estudou
    # aqui é o lastro da escola (histórico, declarações). ativo=False é a "exclusão".
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Chave da foto no `ArquivoStorage` (§6k). Vazio = sem foto — é opcional.
    foto_chave: Mapped[str] = mapped_column(String(120), default="", server_default="")
    desativado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    motivo_desativacao: Mapped[str] = mapped_column(
        String(200), default="", server_default=""
    )
    criado_em: Mapped[datetime] = mapped_column()

    sala: Mapped["SalaORM | None"] = relationship()
    responsaveis: Mapped[list[ContatoORM]] = relationship(
        secondary=aluno_responsaveis, back_populates="alunos"
    )


# --------------------------------------------------------------------------- #
# Mural do professor: recados + confirmação de leitura (§A1)
# --------------------------------------------------------------------------- #
class RecadoORM(Base):
    __tablename__ = "recados"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    titulo: Mapped[str] = mapped_column(String(300))
    corpo: Mapped[str] = mapped_column(Text)
    autor_id: Mapped[str] = mapped_column(String(64), default="", server_default="")
    autor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    criado_em: Mapped[datetime] = mapped_column(index=True)

    leituras: Mapped[list["LeituraRecadoORM"]] = relationship(
        back_populates="recado", cascade="all, delete-orphan"
    )


class LeituraRecadoORM(Base):
    __tablename__ = "leituras_recado"

    recado_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("recados.id", ondelete="CASCADE"),
        primary_key=True,
    )
    professor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="CASCADE"),
        primary_key=True,
    )
    lido_em: Mapped[datetime] = mapped_column()

    recado: Mapped[RecadoORM] = relationship(back_populates="leituras")


# --------------------------------------------------------------------------- #
# Auditoria de ações (usuários logados + LLM)
# --------------------------------------------------------------------------- #
class AuditoriaORM(Base):
    __tablename__ = "auditoria"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    # NULL para ações cross-tenant do super admin; index para a consulta por escola.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    ator: Mapped[str] = mapped_column(String(20))  # "usuario" | "llm" | "sistema"
    ator_id: Mapped[str] = mapped_column(String(128), default="")
    ator_nome: Mapped[str] = mapped_column(String(200), default="")
    acao: Mapped[str] = mapped_column(String(80), index=True)
    descricao: Mapped[str] = mapped_column(Text, default="")
    metadados: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(index=True)


# --------------------------------------------------------------------------- #
# Respostas rápidas ("atalhos") da escola — ingeridas no RAG
# --------------------------------------------------------------------------- #
class RespostaRapidaORM(Base):
    __tablename__ = "respostas_rapidas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    chave: Mapped[str] = mapped_column(String(200))
    conteudo: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Documento de RAG gerado por esta resposta rápida; SET NULL ao remover a fonte.
    fonte_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("fontes_conhecimento.id", ondelete="SET NULL"),
        nullable=True,
    )
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()

    __table_args__ = (
        UniqueConstraint("tenant_id", "chave", name="uq_resposta_rapida_tenant_chave"),
    )


# --------------------------------------------------------------------------- #
# Aviso geral temporizado (resposta automática do bot)
# --------------------------------------------------------------------------- #
class AvisoTemporizadoORM(Base):
    __tablename__ = "avisos_temporizados"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    mensagem: Mapped[str] = mapped_column(Text)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    inicia_em: Mapped[datetime | None] = mapped_column(nullable=True)
    expira_em: Mapped[datetime | None] = mapped_column(nullable=True)
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 2 · A2/A4 — Canal interno professor → secretaria (roteamento por assunto)
# --------------------------------------------------------------------------- #
class SolicitacaoInternaORM(Base):
    __tablename__ = "solicitacoes_internas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Professor solicitante; ON DELETE SET NULL preserva o histórico do canal.
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    professor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    assunto: Mapped[str] = mapped_column(String(300))
    corpo: Mapped[str] = mapped_column(Text)
    categoria: Mapped[str] = mapped_column(
        String(20), default="secretaria", server_default="secretaria", index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="aberta", server_default="aberta", index=True
    )
    resposta: Mapped[str] = mapped_column(Text, default="", server_default="")
    respondido_em: Mapped[datetime | None] = mapped_column(nullable=True)
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 2 · A3 — Canal pai ↔ professor mediado (sem expor o número do professor)
# --------------------------------------------------------------------------- #
class MensagemMediadaORM(Base):
    __tablename__ = "mensagens_mediadas"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    professor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="CASCADE"),
        index=True,
    )
    contato_telefone: Mapped[str] = mapped_column(String(50), index=True)
    contato_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    professor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    direcao: Mapped[str] = mapped_column(String(30))
    corpo: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(index=True)


# --------------------------------------------------------------------------- #
# Onda 2 · B2 — Cota de impressão por professor
# --------------------------------------------------------------------------- #
class CotaImpressaoORM(Base):
    __tablename__ = "cotas_impressao"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    professor_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="CASCADE"),
        index=True,
    )
    limite_mensal: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()

    __table_args__ = (
        UniqueConstraint("tenant_id", "professor_id", name="uq_cota_impressao_tenant_professor"),
    )


# --------------------------------------------------------------------------- #
# System prompt personalizado por tenant (o "CLAUDE.md" da escola)
# --------------------------------------------------------------------------- #
class PromptTenantORM(Base):
    __tablename__ = "prompts_tenant"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), unique=True, index=True
    )
    conteudo: Mapped[str] = mapped_column(Text, default="")
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 3 · I1 — Aviso de falta de professor e chamada de eventual
# --------------------------------------------------------------------------- #
class AvisoFaltaORM(Base):
    __tablename__ = "avisos_falta"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Professor ausente; ON DELETE SET NULL preserva o histórico de faltas.
    professor_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("professores.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    professor_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    data: Mapped[str] = mapped_column(String(10))  # "YYYY-MM-DD"
    motivo: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(20), default="aberta", server_default="aberta", index=True
    )
    eventual_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    eventual_telefone: Mapped[str] = mapped_column(String(50), default="", server_default="")
    eventuais_chamados: Mapped[list] = mapped_column(JSON, default=list)
    criado_em: Mapped[datetime] = mapped_column(index=True)
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 3 · D1/D2/D3 — Ficha de matrícula digital (1:1 com o aluno)
# --------------------------------------------------------------------------- #
class FichaMatriculaORM(Base):
    __tablename__ = "fichas_matricula"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    # Ficha 1:1 com o aluno; apaga junto com o aluno.
    aluno_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("alunos.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    # Todos os campos da ficha (frente, verso e sensíveis) serializados em JSON.
    conteudo: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Onda 3 · E1 — Matrícula self-service iniciada pelo responsável (WhatsApp)
# --------------------------------------------------------------------------- #
class SolicitacaoMatriculaORM(Base):
    __tablename__ = "solicitacoes_matricula"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    contato_telefone: Mapped[str] = mapped_column(String(50), index=True)
    nome_responsavel: Mapped[str] = mapped_column(String(200), default="", server_default="")
    nome_aluno: Mapped[str] = mapped_column(String(200), default="", server_default="")
    status: Mapped[str] = mapped_column(
        String(30), default="iniciada", server_default="iniciada", index=True
    )
    observacao: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Lista de documentos anexados (nome/url/recebido_em) serializada em JSON.
    documentos: Mapped[list] = mapped_column(JSON, default=list)
    criado_em: Mapped[datetime] = mapped_column(index=True)
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Infra de produção · rate limiting (item 5 do checklist de pré-deploy)
# --------------------------------------------------------------------------- #
class ControleTaxaORM(Base):
    """Contador de janela fixa por chave, para o limite de taxa de entrada.

    Mora no Postgres — e não em memória — porque o limite precisa valer para o
    **serviço inteiro**: com duas instâncias no Render, um contador de processo daria
    ao atacante o dobro das tentativas, e um restart zeraria a contagem.
    """

    __tablename__ = "controle_taxa"

    # Ex.: "login:ip:203.0.113.7", "login:email:diretor@escola.br", "inbound:+5511...".
    chave: Mapped[str] = mapped_column(String(200), primary_key=True)
    janela_inicio: Mapped[datetime] = mapped_column(index=True)
    contador: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------------------- #
# Infra de produção · atendimento do inbound (idempotência durável)
# --------------------------------------------------------------------------- #
class InboundAtendimentoORM(Base):
    """Estado do atendimento de cada mensagem recebida, chaveado pelo wamid da Meta.

    Existe para que a reentrega do webhook — que chega enquanto a primeira tentativa
    ainda está esperando a LLM — não vire uma segunda resposta ao responsável e uma
    segunda cobrança no provedor. Mora no banco, e não no processo, porque o duplicado
    frequentemente cai em **outra réplica**, onde um cache de memória nada sabe.
    """

    __tablename__ = "inbound_atendimento"

    # wamid da Meta (id da mensagem recebida).
    chave: Mapped[str] = mapped_column(String(200), primary_key=True)
    # Escola dona da conversa; nulo apenas se a mensagem foi reservada antes do roteamento.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True, index=True
    )
    # Telefone do responsável (E.164), para rastrear no painel de logs.
    origem: Mapped[str] = mapped_column(String(50), default="", server_default="")
    # em_atendimento | concluida | falhou
    status: Mapped[str] = mapped_column(
        String(20), default="em_atendimento", server_default="em_atendimento", index=True
    )
    # Primeiras palavras da resposta enviada — mostra no log o que foi respondido.
    resumo: Mapped[str] = mapped_column(Text, default="", server_default="")
    criado_em: Mapped[datetime] = mapped_column(index=True)
    atualizado_em: Mapped[datetime] = mapped_column()


# --------------------------------------------------------------------------- #
# Observabilidade · logs da aplicação (§16)
# --------------------------------------------------------------------------- #
class LogAplicacaoORM(Base):
    """Log operacional persistido, consultável pelo super admin.

    Separado de ``auditoria``: aquela registra decisões de negócio (evidência de
    compliance), esta registra o que o processo fez e onde quebrou. Guardar os dois na
    mesma tabela transformaria a auditoria em depósito de ruído técnico.
    """

    __tablename__ = "logs_aplicacao"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    criado_em: Mapped[datetime] = mapped_column(index=True)
    nivel: Mapped[str] = mapped_column(String(10), index=True)
    logger: Mapped[str] = mapped_column(String(120), default="", server_default="", index=True)
    mensagem: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Amarra todas as linhas de uma mesma requisição (e o código mostrado ao usuário).
    correlacao_id: Mapped[str] = mapped_column(
        String(40), default="", server_default="", index=True
    )
    rota: Mapped[str] = mapped_column(String(200), default="", server_default="")
    metodo: Mapped[str] = mapped_column(String(10), default="", server_default="")
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duracao_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Sem FK: um log pode nascer antes de sabermos a escola, ou de um tenant já removido —
    # e a FK faria a limpeza de escola falhar por causa de linha de log.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    excecao: Mapped[str] = mapped_column(Text, default="", server_default="")
    metadados: Mapped[dict] = mapped_column(JSON, default=dict)


# --------------------------------------------------------------------------- #
# Atendimento humano: o assistente passa a conversa para a secretaria (§6j)
# --------------------------------------------------------------------------- #
class AtendimentoHumanoORM(Base):
    __tablename__ = "atendimentos_humanos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    # Sem índice próprio em tenant_id/conversa_id/status: são prefixo dos índices
    # compostos declarados em __table_args__ (ver a migration 0029).
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"))
    conversa_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversas.id")
    )
    contato: Mapped[str] = mapped_column(String(50), index=True)
    contato_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    motivo: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[str] = mapped_column(String(20), default="oferecido", server_default="oferecido")
    ofereceu_em: Mapped[datetime | None] = mapped_column(nullable=True)
    confirmado_em: Mapped[datetime | None] = mapped_column(nullable=True)
    fora_expediente: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    # Atendente da secretaria (um ``usuarios`` com papel tenant_admin). ON DELETE SET NULL:
    # desligar a funcionária não pode apagar o histórico de quem respondeu ao responsável.
    atendente_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    atendente_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # Base da janela de 24h da Meta para texto livre (ver AtendimentoHumano).
    ultima_mensagem_responsavel_em: Mapped[datetime] = mapped_column()
    assumido_em: Mapped[datetime | None] = mapped_column(nullable=True)
    resolvido_em: Mapped[datetime | None] = mapped_column(nullable=True)
    criado_em: Mapped[datetime] = mapped_column()
    atualizado_em: Mapped[datetime] = mapped_column()

    __table_args__ = (
        # A fila de uma escola, mais antiga primeiro — a consulta quente do painel.
        Index("ix_atendimentos_tenant_status_criado", "tenant_id", "status", "criado_em"),
        # "esta conversa tem atendimento na fila?" roda a cada mensagem do inbound.
        Index("ix_atendimentos_conversa_status", "conversa_id", "status"),
    )


# --------------------------------------------------------------------------- #
# Documentos recebidos dos responsáveis pelo WhatsApp (§6k)
# --------------------------------------------------------------------------- #
class ArquivoArmazenadoORM(Base):
    """Bytes de um arquivo — implementação do ``ArquivoStorage`` em Postgres.

    Tabela **de infraestrutura**, não de negócio: existe porque hoje não há object
    storage, e some inteira no dia em que o adaptador virar R2. Por isso os metadados que
    a secretaria consulta ficam em ``documentos_recebidos``, e não aqui.
    """

    __tablename__ = "arquivos_armazenados"

    chave: Mapped[str] = mapped_column(String(120), primary_key=True)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary)
    mime: Mapped[str] = mapped_column(String(120), default="", server_default="")
    tamanho: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    criado_em: Mapped[datetime] = mapped_column()


class DocumentoRecebidoORM(Base):
    __tablename__ = "documentos_recebidos"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("tenants.id"))
    conversa_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("conversas.id")
    )
    contato: Mapped[str] = mapped_column(String(50), index=True)
    contato_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    # Ponteiro para o ArquivoStorage — nunca os bytes.
    chave_storage: Mapped[str] = mapped_column(String(120))
    mime: Mapped[str] = mapped_column(String(120))
    tamanho: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    nome_arquivo: Mapped[str] = mapped_column(String(300), default="", server_default="")
    observacao: Mapped[str] = mapped_column(Text, default="", server_default="")
    categoria: Mapped[str] = mapped_column(String(20), default="outro", server_default="outro")
    categoria_sugerida: Mapped[str] = mapped_column(
        String(20), default="", server_default=""
    )
    status: Mapped[str] = mapped_column(
        String(20), default="recebido", server_default="recebido"
    )
    # ON DELETE SET NULL: desligar o vínculo não pode apagar a prova de que o documento
    # chegou — é justamente o lastro que a escola precisa guardar.
    aluno_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("alunos.id", ondelete="SET NULL"), nullable=True
    )
    aluno_nome: Mapped[str] = mapped_column(String(200), default="", server_default="")
    atendimento_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("atendimentos_humanos.id", ondelete="SET NULL"),
        nullable=True,
    )
    media_id: Mapped[str] = mapped_column(String(120), default="", server_default="")
    # Prazo de retenção (LGPD): dado sensível de menor não fica indefinidamente.
    expira_em: Mapped[datetime | None] = mapped_column(nullable=True)
    processado_em: Mapped[datetime | None] = mapped_column(nullable=True)
    criado_em: Mapped[datetime] = mapped_column()

    __table_args__ = (
        # A listagem do painel: os documentos de uma escola, mais recentes primeiro.
        Index("ix_documentos_tenant_criado", "tenant_id", "criado_em"),
        # Dedupe da reentrega do webhook, por escola.
        Index("ix_documentos_tenant_media", "tenant_id", "media_id"),
        # Varredura do expurgo, que roda cross-tenant e só olha o prazo.
        Index("ix_documentos_expira_em", "expira_em"),
    )


class NumeroBloqueadoORM(Base):
    """Número cuja **mídia** é recusada no inbound (§6k, anti-spam).

    Bloqueia o arquivo, não a pessoa: o número segue sendo atendido em texto.
    """

    __tablename__ = "numeros_bloqueados"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("tenants.id"), index=True
    )
    telefone: Mapped[str] = mapped_column(String(50), index=True)
    motivo: Mapped[str] = mapped_column(Text, default="", server_default="")
    bloqueado_por: Mapped[str] = mapped_column(String(200), default="", server_default="")
    bloqueado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "telefone", name="uq_numero_bloqueado_tenant"),
    )
