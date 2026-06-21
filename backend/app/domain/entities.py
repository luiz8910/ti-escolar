"""Entidades e value objects do domínio.

Camada mais interna da arquitetura hexagonal: não importa framework, ORM ou SDK.
São dataclasses puras que modelam o negócio escolar multi-tenant.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID, uuid4


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> UUID:
    return uuid4()


# --------------------------------------------------------------------------- #
# Tenant
# --------------------------------------------------------------------------- #
class StatusTenant(str, enum.Enum):
    """Situação operacional da escola na plataforma."""

    ATIVO = "ativo"
    # Suspenso (falta de pagamento ou outro motivo): sem acesso ao painel e a disparos.
    # É reversível (``DesbloquearEscola``).
    BLOQUEADO = "bloqueado"
    # Cancelado (churn): a escola deixou a plataforma. Também sem acesso, mas marca o fim
    # do ciclo de vida — registra ``cancelado_em`` e ``motivo_cancelamento`` para a ficha.
    CANCELADO = "cancelado"


class PlanoTenant(str, enum.Enum):
    """Ciclo de cobrança da licença da escola."""

    MENSAL = "mensal"
    ANUAL = "anual"


@dataclass
class Tenant:
    """Uma escola. Raiz de isolamento multi-tenant.

    Além da identidade (``nome``/``slug``), carrega o **licenciamento**: situação
    (``status``/``motivo_bloqueio``), a licença (``plano``/``licenca_expira_em``) e a
    **cobrança** (preços ``valor_*_centavos`` por ciclo). ``criado_em`` é a data de início
    (quando a escola entrou); ``cancelado_em``/``motivo_cancelamento`` registram a saída
    (churn). Uma escola ``BLOQUEADO`` ou ``CANCELADO`` perde acesso ao painel e aos disparos.
    """

    nome: str
    slug: str
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    status: StatusTenant = StatusTenant.ATIVO
    motivo_bloqueio: str = ""
    bloqueado_em: datetime | None = None
    plano: PlanoTenant = PlanoTenant.MENSAL
    # Data de expiração da licença (relevante sobretudo no plano anual).
    licenca_expira_em: datetime | None = None
    # Cobrança: preços por ciclo, em centavos (evita imprecisão de ponto flutuante).
    valor_mensal_centavos: int = 0
    valor_anual_centavos: int = 0
    # Cancelamento (churn): quando a escola deixou a plataforma e por quê.
    cancelado_em: datetime | None = None
    motivo_cancelamento: str = ""

    @property
    def bloqueado(self) -> bool:
        return self.status == StatusTenant.BLOQUEADO

    @property
    def cancelado(self) -> bool:
        return self.status == StatusTenant.CANCELADO

    @property
    def acesso_suspenso(self) -> bool:
        """Sem acesso ao painel/disparos: bloqueada (reversível) ou cancelada (churn)."""
        return self.bloqueado or self.cancelado

    @property
    def motivo_suspensao(self) -> str:
        """Mensagem do impedimento de acesso (bloqueio ou cancelamento)."""
        if self.cancelado:
            return self.motivo_cancelamento
        return self.motivo_bloqueio

    @property
    def dias_para_expirar(self) -> int | None:
        """Dias corridos até a licença expirar (negativo se já expirou)."""
        if self.licenca_expira_em is None:
            return None
        return (self.licenca_expira_em.date() - _now().date()).days

    @property
    def licenca_expirada(self) -> bool:
        d = self.dias_para_expirar
        return d is not None and d < 0

    def licenca_a_vencer(self, dias_aviso: int) -> bool:
        """Licença ainda válida, porém dentro da janela de aviso de vencimento."""
        d = self.dias_para_expirar
        return d is not None and 0 <= d <= dias_aviso

    @property
    def mrr_centavos(self) -> int:
        """Receita recorrente mensal (MRR) normalizada pelo ciclo do plano."""
        if self.plano == PlanoTenant.ANUAL:
            return self.valor_anual_centavos // 12
        return self.valor_mensal_centavos

    @property
    def arr_centavos(self) -> int:
        """Receita recorrente anual (ARR) = MRR × 12."""
        return self.mrr_centavos * 12


@dataclass
class ResumoEscola:
    """Escola acompanhada de contadores, para a listagem do super admin."""

    tenant: Tenant
    total_conversas: int = 0
    total_contatos: int = 0
    total_broadcasts: int = 0


@dataclass
class MetricasUsoEscola:
    """Contadores de uso de uma escola, para a ficha do super admin."""

    total_usuarios_ativos: int = 0
    total_contatos: int = 0
    total_alunos: int = 0
    total_conversas: int = 0
    total_broadcasts: int = 0


class StatusPagamento(str, enum.Enum):
    """Situação de cobrança derivada do licenciamento (não há ledger de faturas)."""

    EM_DIA = "em_dia"
    A_VENCER = "a_vencer"
    VENCIDO = "vencido"
    INADIMPLENTE = "inadimplente"  # bloqueada por pagamento
    CANCELADO = "cancelado"


@dataclass
class FichaFinanceiraEscola:
    """Ficha financeira/histórico de uma escola para o super admin.

    Consolida ciclo de vida (início/cancelamento), cobrança (preços, MRR/ARR, receita
    acumulada estimada/LTV), uso agregado e um *health score* heurístico. É **derivada**:
    não há tabela de faturas — a receita acumulada é uma estimativa por meses ativos × MRR.
    """

    tenant: Tenant
    uso: MetricasUsoEscola = field(default_factory=MetricasUsoEscola)
    # Cota diária de destinatários (tier Meta) — insumo do health score.
    limite_diario_meta: int = 0

    @property
    def meses_ativos(self) -> int:
        """Meses (aprox., 30 dias) entre o início e o cancelamento (ou hoje)."""
        fim = self.tenant.cancelado_em or _now()
        dias = (fim.date() - self.tenant.criado_em.date()).days
        return max(0, dias // 30)

    @property
    def receita_acumulada_centavos(self) -> int:
        """Receita acumulada estimada (LTV) = meses ativos × MRR."""
        return self.meses_ativos * self.tenant.mrr_centavos

    @property
    def dias_de_casa(self) -> int:
        """Dias corridos desde o início (referência para a 'data de entrada')."""
        return max(0, (_now().date() - self.tenant.criado_em.date()).days)

    @property
    def status_pagamento(self) -> StatusPagamento:
        t = self.tenant
        if t.cancelado:
            return StatusPagamento.CANCELADO
        if t.bloqueado:
            return StatusPagamento.INADIMPLENTE
        if t.licenca_expirada:
            return StatusPagamento.VENCIDO
        if t.licenca_a_vencer(15):
            return StatusPagamento.A_VENCER
        return StatusPagamento.EM_DIA

    @property
    def health_score(self) -> int:
        """Saúde da conta (0–100): heurística sobre licença, bloqueio e tier de envio.

        Sem dados de qualidade do número Meta, aproxima a saúde pelo tier de envio
        (cota diária) e pela situação de licenciamento/cobrança.
        """
        t = self.tenant
        if t.cancelado:
            return 0
        score = 100
        if t.bloqueado:
            score -= 50
        if t.licenca_expirada:
            score -= 30
        elif t.licenca_a_vencer(15):
            score -= 10
        # Tier de envio: número mais "saudável" alcança tiers maiores (-1 = ilimitado).
        if 0 <= self.limite_diario_meta < 1000:
            score -= 10
        return max(0, min(100, score))


# --------------------------------------------------------------------------- #
# Administração: usuários (super admin e admin de tenant)
# --------------------------------------------------------------------------- #
class Papel(str, enum.Enum):
    # Controle da plataforma (cross-tenant) — o "seu" controle.
    SUPER_ADMIN = "super_admin"
    # Administra uma única escola (tenant).
    TENANT_ADMIN = "tenant_admin"


@dataclass
class Usuario:
    """Usuário administrativo. ``tenant_id`` é None para o super admin."""

    nome: str
    email: str
    senha_hash: str
    papel: Papel
    id: UUID = field(default_factory=_new_id)
    tenant_id: UUID | None = None
    ativo: bool = True
    criado_em: datetime = field(default_factory=_now)

    @property
    def eh_super_admin(self) -> bool:
        return self.papel == Papel.SUPER_ADMIN


# --------------------------------------------------------------------------- #
# Contatos (pais/responsáveis) e grupos de distribuição
# --------------------------------------------------------------------------- #
@dataclass
class Contato:
    """Pai/responsável com número de WhatsApp, dentro de um tenant."""

    tenant_id: UUID
    nome: str
    telefone: str  # E.164, ex.: +5511999990000
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)


@dataclass
class Grupo:
    """Grupo de distribuição: destinatários de mensagens dirigidas a um subconjunto.

    Ex.: "Turma 5º A", "Pais do Fundamental I". Mensagens enviadas a um grupo só
    alcançam os contatos cadastrados nele.
    """

    tenant_id: UUID
    nome: str
    descricao: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    membros: list[Contato] = field(default_factory=list)


@dataclass
class Professor:
    """Professor da escola, dentro de um tenant.

    Modelo enxuto: **apenas nome e telefone** (WhatsApp). Um professor pode estar à
    frente de **várias séries/turmas** (``Sala``), mas cada série tem **no máximo um**
    professor responsável (o vínculo mora em ``Sala.professor_id``).
    """

    tenant_id: UUID
    nome: str
    telefone: str  # E.164, ex.: +5511999990000
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)


@dataclass
class Sala:
    """Sala/turma da escola (ex.: "4ª série B"), dentro de um tenant.

    Agrega os ``Contato``s (pais/responsáveis) vinculados àquela turma (N:N — um
    responsável pode ter filhos em salas diferentes). É a base do relatório de pais
    por sala. ``professor_id`` é o **professor responsável** pela série (1:1 — uma
    série tem no máximo um professor; um professor pode ter várias séries);
    ``professor_nome`` é denormalizado só para exibição.
    """

    tenant_id: UUID
    nome: str  # ex.: "4ª série B"
    descricao: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    pais: list[Contato] = field(default_factory=list)
    professor_id: UUID | None = None
    professor_nome: str = ""


@dataclass
class Aluno:
    """Aluno da escola, dentro de um tenant.

    Pertence **obrigatoriamente** a uma série/turma (``sala_id`` — relação 1:1 com
    ``Sala``) e tem **N** responsáveis (``Contato``s, N:N via ``aluno_responsaveis``).
    ``ativo=False`` marca um ex-aluno (base para a futura transferência/promoção de
    série). ``sala_nome`` é denormalizado só para exibição.
    """

    tenant_id: UUID
    nome: str
    sala_id: UUID
    matricula: str = ""
    ativo: bool = True
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    responsaveis: list[Contato] = field(default_factory=list)
    sala_nome: str = ""

    @property
    def tem_contato(self) -> bool:
        """Verdadeiro se ao menos um responsável tem telefone (WhatsApp) cadastrado."""
        return any(c.telefone.strip() for c in self.responsaveis)


@dataclass
class CoberturaContatosSala:
    """Cobertura de contatos de uma turma: alunos **ativos** sem nenhum responsável
    com telefone (WhatsApp) cadastrado.

    Base do alerta "X alunos na sala, Y sem contato de responsável" e do disparo de
    notificação ao professor para coletar os contatos faltantes (dor de campo: hoje
    pedem ao professor e ele esquece).
    """

    sala_id: UUID
    sala_nome: str
    total_alunos: int = 0
    alunos_sem_contato: list[Aluno] = field(default_factory=list)

    @property
    def total_sem_contato(self) -> int:
        return len(self.alunos_sem_contato)


# --------------------------------------------------------------------------- #
# Importação de alunos em massa (planilha/PDF normalizados pela LLM)
# --------------------------------------------------------------------------- #
@dataclass
class ResponsavelImportado:
    """Responsável extraído de uma linha da planilha/PDF, já normalizado.

    ``telefone`` é o WhatsApp em E.164 (vazio se não veio ou não pôde ser
    normalizado). ``aviso`` registra observações que não impedem a importação
    (ex.: telefone ausente/suspeito).
    """

    nome: str
    telefone: str = ""
    aviso: str = ""


@dataclass
class LinhaImportacaoAluno:
    """Uma linha de aluno normalizada pela LLM, pronta para revisão antes de persistir.

    ``serie`` é o nome da turma/série como interpretado (resolvido depois contra as
    ``Sala``s do tenant). ``erros`` impedem a persistência da linha; ``avisos`` apenas
    sinalizam. ``serie_nova`` marca que a série citada ainda não existe no tenant.
    """

    nome: str
    serie: str
    matricula: str = ""
    responsaveis: list[ResponsavelImportado] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    serie_nova: bool = False

    @property
    def valido(self) -> bool:
        return not self.erros


@dataclass
class PreviaImportacaoAlunos:
    """Resultado da etapa de **prévia**: linhas normalizadas + contexto de séries.

    Nada é persistido aqui — o admin revisa as linhas e confirma depois. ``series_novas``
    são os nomes de séries citados que ainda não existem no tenant (precisam ser criados
    na confirmação para que os alunos correspondentes sejam importados).
    """

    linhas: list[LinhaImportacaoAluno] = field(default_factory=list)
    series_existentes: list[str] = field(default_factory=list)
    series_novas: list[str] = field(default_factory=list)

    @property
    def total_validos(self) -> int:
        return sum(1 for linha in self.linhas if linha.valido)


@dataclass
class ResultadoImportacaoAlunos:
    """Resultado da etapa de **confirmação**: o que foi efetivamente persistido."""

    criados: int = 0
    ignorados: int = 0
    series_criadas: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Conversa / mensagens (inbound)
# --------------------------------------------------------------------------- #
class Autor(str, enum.Enum):
    USUARIO = "usuario"
    BOT = "bot"


@dataclass
class Mensagem:
    conversa_id: UUID
    autor: Autor
    texto: str
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    # Fontes (RAG) que embasaram uma resposta do bot.
    fontes: list[str] = field(default_factory=list)


@dataclass
class Conversa:
    tenant_id: UUID
    # Telefone (E.164) ou identificador do usuário no canal.
    contato: str
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)


@dataclass
class ResumoConversa:
    """Conversa com metadados para a listagem (sem carregar todas as mensagens)."""

    conversa: Conversa
    total_mensagens: int = 0
    ultima_mensagem: str = ""
    ultima_em: datetime | None = None


# --------------------------------------------------------------------------- #
# Auditoria de ações (usuários logados + LLM)
# --------------------------------------------------------------------------- #
class AtorAuditoria(str, enum.Enum):
    """Quem executou a ação registrada na auditoria."""

    USUARIO = "usuario"  # admin logado (super admin ou tenant admin)
    LLM = "llm"  # o assistente, ao atender uma conversa
    SISTEMA = "sistema"  # rotinas automáticas (jobs, webhooks)


@dataclass
class RegistroAuditoria:
    """Uma ação registrada para rastreabilidade/compliance.

    Escopado por ``tenant_id`` (a escola onde a ação teve efeito) para que o admin da
    escola consulte apenas as suas; ações cross-tenant do super admin podem ter
    ``tenant_id`` nulo. ``acao`` é um código curto (ex.: ``broadcast.grupo.enviar``);
    ``descricao`` é legível e ``metadados`` guarda o payload relevante (JSON).
    """

    ator: AtorAuditoria
    acao: str
    tenant_id: UUID | None = None
    ator_id: str = ""  # id do usuário ou telefone do contato (LLM)
    ator_nome: str = ""
    descricao: str = ""
    metadados: dict = field(default_factory=dict)
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Base de conhecimento (RAG)
# --------------------------------------------------------------------------- #
class TipoConhecimento(str, enum.Enum):
    FAQ = "faq"
    AVISO = "aviso"
    PROCEDIMENTO = "procedimento"


@dataclass
class TrechoConhecimento:
    """Unidade indexável no vector store (com seu embedding calculado fora).

    Quando proveniente de um documento enviado pela escola, ``fonte_id`` aponta para
    a ``FonteConhecimento`` que o originou (vários trechos por documento).
    """

    tenant_id: UUID
    tipo: TipoConhecimento
    titulo: str
    conteudo: str
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    fonte_id: UUID | None = None


@dataclass
class FonteConhecimento:
    """Documento enviado pela escola para enriquecer a base de RAG do tenant.

    A escola sobe um texto/arquivo de procedimentos; ele é fragmentado em vários
    ``TrechoConhecimento`` indexados no vector store. Esta entidade guarda os
    metadados do documento original para gestão (listar/remover) no painel admin.
    """

    tenant_id: UUID
    nome: str  # ex.: "Manual de procedimentos 2026"
    tipo: TipoConhecimento = TipoConhecimento.PROCEDIMENTO
    total_trechos: int = 0
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)


@dataclass
class PromptTenant:
    """Instruções de sistema personalizadas por escola — um "CLAUDE.md" do tenant.

    Texto livre acrescentado às diretrizes institucionais do assistente, ajustando
    tom, regras e contexto específicos daquela escola. É escopado por ``tenant_id``.
    """

    tenant_id: UUID
    conteudo: str = ""
    id: UUID = field(default_factory=_new_id)
    atualizado_em: datetime = field(default_factory=_now)


@dataclass
class ResultadoBusca:
    trecho: TrechoConhecimento
    score: float


# --------------------------------------------------------------------------- #
# Documentos (integração externa)
# --------------------------------------------------------------------------- #
@dataclass
class Documento:
    tenant_id: UUID
    nome: str
    # Categoria livre: "boletim", "declaracao", "calendario"...
    categoria: str
    url: str
    id: UUID = field(default_factory=_new_id)


# --------------------------------------------------------------------------- #
# Agente / tool use (orquestração inbound)
# --------------------------------------------------------------------------- #
@dataclass
class FerramentaSpec:
    """Definição declarativa de uma ferramenta exposta ao LLM.

    Neutra em relação ao provedor: ``parametros`` é um JSON Schema (objeto) que o
    adaptador concreto traduz para o formato esperado pelo SDK.
    """

    nome: str
    descricao: str
    parametros: dict  # JSON Schema do tipo "object"


@dataclass
class ChamadaFerramenta:
    """Intenção do LLM de executar uma ferramenta (um bloco ``tool_use``)."""

    id: str
    nome: str
    argumentos: dict


@dataclass
class ResultadoFerramenta:
    """Resultado de uma ferramenta a ser devolvido ao LLM (um ``tool_result``)."""

    id: str  # casa com ``ChamadaFerramenta.id``
    conteudo: str


@dataclass
class TurnoConversa:
    """Um turno na conversa com o LLM, em vocabulário neutro de domínio.

    Texto simples ou turnos com chamadas/resultados de ferramentas. O adaptador
    concreto converte para o formato de mensagens do provedor.
    """

    papel: str  # "user" | "assistant"
    texto: str = ""
    chamadas: list[ChamadaFerramenta] = field(default_factory=list)  # assistant: tool_use
    resultados: list[ResultadoFerramenta] = field(default_factory=list)  # user: tool_result


@dataclass
class RespostaLLM:
    """Saída de um round-trip do LLM: texto e/ou pedidos de ferramenta."""

    texto: str = ""
    chamadas: list[ChamadaFerramenta] = field(default_factory=list)

    @property
    def quer_ferramenta(self) -> bool:
        return bool(self.chamadas)


# --------------------------------------------------------------------------- #
# Outbound: templates, broadcasts e cota Meta
# --------------------------------------------------------------------------- #
class CategoriaTemplate(str, enum.Enum):
    UTILITY = "utility"
    MARKETING = "marketing"
    AUTHENTICATION = "authentication"


class StatusTemplate(str, enum.Enum):
    RASCUNHO = "rascunho"
    PENDENTE = "pendente"
    APROVADO = "aprovado"
    REJEITADO = "rejeitado"


@dataclass
class MessageTemplate:
    """Template (HSM) exigido pela Meta fora da janela de 24h."""

    tenant_id: UUID
    nome: str
    categoria: CategoriaTemplate
    idioma: str
    corpo: str  # com placeholders {{1}}, {{2}}...
    id: UUID = field(default_factory=_new_id)
    status: StatusTemplate = StatusTemplate.RASCUNHO


class StatusEntrega(str, enum.Enum):
    PENDENTE = "pendente"
    ENFILEIRADO = "enfileirado"
    ENVIADO = "sent"
    ENTREGUE = "delivered"
    LIDO = "read"
    FALHOU = "failed"


@dataclass
class DestinatarioBroadcast:
    contato: str  # telefone E.164
    parametros: list[str] = field(default_factory=list)
    status: StatusEntrega = StatusEntrega.PENDENTE
    # Id externo da mensagem na Meta (``wamid...``), usado para casar os eventos de
    # status do webhook com este destinatário.
    mensagem_id_externo: str = ""
    # Última atualização de status (envio ou webhook). Base para a verificação reativa
    # de não-entrega (quanto tempo se passou desde o envio sem confirmação).
    atualizado_em: datetime | None = None
    id: UUID = field(default_factory=_new_id)


class StatusBroadcast(str, enum.Enum):
    RASCUNHO = "rascunho"
    AGENDADO = "agendado"
    EM_ENVIO = "em_envio"
    CONCLUIDO = "concluido"
    PARCIAL_LIMITE = "parcial_limite"  # interrompido por limite diário


@dataclass
class Broadcast:
    """Campanha de disparo ativo a pais/responsáveis."""

    tenant_id: UUID
    template_id: UUID
    titulo: str
    destinatarios: list[DestinatarioBroadcast] = field(default_factory=list)
    id: UUID = field(default_factory=_new_id)
    status: StatusBroadcast = StatusBroadcast.RASCUNHO
    agendado_para: datetime | None = None
    criado_em: datetime = field(default_factory=_now)


@dataclass
class MessageQuota:
    """Cota diária de destinatários únicos por número (tier Meta)."""

    tenant_id: UUID
    # -1 = ilimitado
    limite_diario: int
    dia: str  # ISO date "YYYY-MM-DD" (UTC)
    enviados: int = 0
    id: UUID = field(default_factory=_new_id)

    @property
    def ilimitado(self) -> bool:
        return self.limite_diario < 0

    @property
    def restante(self) -> int:
        if self.ilimitado:
            return 2**31
        return max(0, self.limite_diario - self.enviados)

    def pode_enviar(self, quantidade: int = 1) -> bool:
        return self.ilimitado or self.enviados + quantidade <= self.limite_diario
