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
    # Número de WhatsApp (E.164) da escola: por onde ela atende/dispara. Roteia o inbound
    # (o ``To`` recebido) para o tenant certo e é o remetente (``From``) do outbound. Vazio
    # = usa o número padrão do canal (ex.: número único do Sandbox Twilio). É um número
    # **dedicado** à plataforma (a escola adquire um novo, deixando o número antigo livre).
    whatsapp_numero: str = ""
    # Telefone de contato (E.164) público da escola — o número que a secretaria já usa no
    # dia a dia. É apenas **informativo** (referência de contato): não roteia inbound, não é
    # remetente do outbound e não exige unicidade entre escolas. Ver ``whatsapp_numero`` para
    # o número operado pela plataforma.
    telefone_contato: str = ""
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
    """Pai/responsável com número de WhatsApp, dentro de um tenant.

    ``ativo=False`` marca um responsável **inativo** — normalmente porque todos os seus
    alunos já são ex-alunos (ver a progressão de série, §F1). Um responsável inativo
    permanece no cadastro (histórico), mas não deve receber novos avisos.
    """

    tenant_id: UUID
    nome: str
    telefone: str  # E.164, ex.: +5511999990000
    ativo: bool = True
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
    # Senha (hash PBKDF2) para o login do professor no mural (§A1). Vazio = sem acesso.
    senha_hash: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)

    @property
    def tem_acesso(self) -> bool:
        """Verdadeiro quando o professor tem senha definida (pode entrar no mural)."""
        return bool(self.senha_hash)


class StatusImpressao(str, enum.Enum):
    """Estado de uma solicitação de impressão na fila da secretaria."""

    PENDENTE = "pendente"  # na fila, aguardando a secretaria
    EM_PROCESSO = "em_processo"  # a secretaria está imprimindo
    CONCLUIDA = "concluida"  # impressa e disponível
    CANCELADA = "cancelada"  # cancelada (pelo professor ou pela secretaria)


@dataclass
class SolicitacaoImpressao:
    """Pedido de impressão feito por um professor à secretaria (fila de impressão).

    Dor de campo (Rosa Cury): "elas mandam atividade/prova/lista de chamada pra imprimir
    o dia inteiro". O professor envia o arquivo com os parâmetros (nº de cópias,
    colorido/PB, frente-e-verso) e o pedido cai numa fila para a secretaria processar,
    sem ficar perguntando cada detalhe. ``professor_nome`` é denormalizado só para exibição.
    """

    tenant_id: UUID
    arquivo_nome: str
    professor_id: UUID | None = None
    professor_nome: str = ""
    arquivo_url: str = ""  # referência/link do arquivo enviado
    copias: int = 1
    colorido: bool = False
    frente_verso: bool = False
    observacao: str = ""
    status: StatusImpressao = StatusImpressao.PENDENTE
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)


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
# Mural do professor: recados da secretaria + confirmação de leitura (§A1)
# --------------------------------------------------------------------------- #
@dataclass
class Recado:
    """Recado da secretaria/gestão publicado no mural dos professores.

    Substitui o WhatsApp pessoal das professoras (que "não leem" e reclamam do volume)
    por um canal profissional com **confirmação de leitura**: fica marcado quem viu, e
    quem não viu pode ser re-notificado. ``autor_nome`` é denormalizado para exibição.
    """

    tenant_id: UUID
    titulo: str
    corpo: str
    autor_id: str = ""  # id do usuário que publicou
    autor_nome: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)


@dataclass
class LeituraRecado:
    """Confirmação de leitura de um recado por um professor ("ticado")."""

    recado_id: UUID
    professor_id: UUID
    lido_em: datetime = field(default_factory=_now)


@dataclass
class RecadoResumo:
    """Recado com os contadores de leitura, para a visão da secretaria."""

    recado: Recado
    total_professores: int = 0
    total_lidos: int = 0

    @property
    def total_nao_lidos(self) -> int:
        return max(0, self.total_professores - self.total_lidos)


@dataclass
class RecadoDoProfessor:
    """Recado na visão do professor, com o seu próprio status de leitura."""

    recado: Recado
    lido: bool = False
    lido_em: datetime | None = None


@dataclass
class StatusLeituraRecado:
    """Detalhe de leitura de um recado: quem leu (com data) e quem ainda não leu."""

    recado: Recado
    lidos: list[tuple[Professor, datetime | None]] = field(default_factory=list)
    nao_lidos: list[Professor] = field(default_factory=list)


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
class RespostaRapida:
    """Resposta rápida ("atalho") da escola: uma chave curta + o conteúdo padrão.

    São os atalhos de "Respostas rápidas" que a secretaria já usa no WhatsApp
    (ex.: "SEDU", "Horário do portão", "Transporte escolar gratuito"). Cada uma é
    **ingerida na base de RAG** do tenant (``fonte_id`` aponta para a
    ``FonteConhecimento`` gerada) para que o bot responda automaticamente. ``ativo``
    controla se está indexada/disponível para o bot. Única por ``(tenant_id, chave)``.
    """

    tenant_id: UUID
    chave: str  # ex.: "Horário do portão"
    conteudo: str
    ativo: bool = True
    fonte_id: UUID | None = None
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)


@dataclass
class AvisoTemporizado:
    """Aviso geral **temporizado** que o bot responde automaticamente a quem inicia conversa.

    Dor de campo: hoje a secretaria só consegue configurar um recado do dia mexendo no
    aparelho ("fica arrumando bom dia/boa tarde"). Aqui o recado é cadastrado no painel,
    tem uma **janela de vigência** opcional (``inicia_em``/``expira_em``) e, enquanto
    vigente, é anexado à resposta do bot — sem mexer no celular. Ex.: "Por motivo de
    saúde, a secretaria não abre à tarde hoje."
    """

    tenant_id: UUID
    mensagem: str
    ativo: bool = True
    inicia_em: datetime | None = None
    expira_em: datetime | None = None
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)

    def vigente_em(self, agora: datetime | None = None) -> bool:
        """Verdadeiro se o aviso está ativo e dentro da janela de vigência."""
        if not self.ativo:
            return False
        agora = agora or _now()
        inicio = self.inicia_em
        fim = self.expira_em
        if inicio is not None and inicio.tzinfo is None:
            inicio = inicio.replace(tzinfo=timezone.utc)
        if fim is not None and fim.tzinfo is None:
            fim = fim.replace(tzinfo=timezone.utc)
        if inicio is not None and agora < inicio:
            return False
        if fim is not None and agora > fim:
            return False
        return True


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
    # Id do template aprovado no provedor (Twilio Content API: ``HX...``). Quando presente,
    # o canal envia via template aprovado (obrigatório fora da janela de 24h); vazio =
    # texto livre (Sandbox / dentro da janela de 24h).
    content_sid: str = ""


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


# --------------------------------------------------------------------------- #
# Onda 2 · A2/A4 — Canal interno professor → secretaria (com roteamento por assunto)
# --------------------------------------------------------------------------- #
class CategoriaSolicitacao(str, enum.Enum):
    """Para onde a solicitação do professor deve ser encaminhada (roteamento, §A4).

    A secretaria trata do operacional; comportamento/pedagógico vão para a **gestão**.
    """

    SECRETARIA = "secretaria"
    GESTAO = "gestao"
    PEDAGOGICO = "pedagogico"


class StatusSolicitacaoInterna(str, enum.Enum):
    ABERTA = "aberta"
    EM_ANDAMENTO = "em_andamento"
    RESOLVIDA = "resolvida"
    CANCELADA = "cancelada"


@dataclass
class SolicitacaoInterna:
    """Solicitação/recado que um **professor** envia à escola pelo sistema (§A2).

    Substitui o WhatsApp pessoal das professoras: o pedido (impressão à parte, na fila
    §B1; aqui é o canal geral — aviso, falta, dúvida) fica **registrado** e **roteado**
    por ``categoria`` (§A4) para a secretaria, a gestão ou o pedagógico. A resposta da
    escola fica no próprio registro (``resposta``), evitando o "elas mandam pra cá e a
    gente não tem controle". ``professor_nome`` é denormalizado só para exibição.
    """

    tenant_id: UUID
    assunto: str
    corpo: str
    professor_id: UUID | None = None
    professor_nome: str = ""
    categoria: CategoriaSolicitacao = CategoriaSolicitacao.SECRETARIA
    status: StatusSolicitacaoInterna = StatusSolicitacaoInterna.ABERTA
    resposta: str = ""
    respondido_em: datetime | None = None
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Onda 2 · A3 — Canal pai ↔ professor mediado (sem expor o número do professor)
# --------------------------------------------------------------------------- #
class DirecaoMensagem(str, enum.Enum):
    RESPONSAVEL_PARA_PROFESSOR = "responsavel_para_professor"
    PROFESSOR_PARA_RESPONSAVEL = "professor_para_responsavel"


@dataclass
class MensagemMediada:
    """Mensagem trocada entre um responsável e um professor **roteada pelo sistema** (§A3).

    O professor não expõe o contato pessoal: quando ele responde, a mensagem sai pelo
    **número da própria escola** (``MessageChannel`` com ``remetente`` = número do
    tenant) e é registrada aqui. As mensagens do responsável entram pelo mesmo canal e
    aparecem no painel do professor. Uma "conversa" é o par (``professor_id``,
    ``contato_telefone``). ``*_nome`` são denormalizados só para exibição.
    """

    tenant_id: UUID
    professor_id: UUID
    contato_telefone: str  # E.164 do responsável
    direcao: DirecaoMensagem
    corpo: str
    professor_nome: str = ""
    contato_nome: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)


@dataclass
class InterlocutorMediado:
    """Resumo de uma conversa mediada na visão do professor (um responsável)."""

    contato_telefone: str
    contato_nome: str
    total_mensagens: int
    ultima_em: datetime | None
    ultima_previa: str = ""


# --------------------------------------------------------------------------- #
# Onda 2 · B2 — Cota e relatório de impressões (por professor / competência)
# --------------------------------------------------------------------------- #
@dataclass
class CotaImpressao:
    """Franquia mensal de cópias de um professor (ex.: 3.000 cópias/mês), por tenant.

    ``limite_mensal <= 0`` significa **sem limite**. A cota é recorrente (vale para todo
    mês); o consumo é apurado por competência a partir das ``SolicitacaoImpressao``.
    """

    tenant_id: UUID
    professor_id: UUID
    limite_mensal: int = 0
    professor_nome: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)

    @property
    def ilimitado(self) -> bool:
        return self.limite_mensal <= 0


@dataclass
class LinhaRelatorioImpressao:
    """Consumo de impressão de um professor numa competência (mês)."""

    professor_id: UUID | None
    professor_nome: str
    total_solicitacoes: int
    total_copias: int
    limite_mensal: int = 0

    @property
    def ilimitado(self) -> bool:
        return self.limite_mensal <= 0

    @property
    def excedeu(self) -> bool:
        """Verdadeiro quando há limite e o consumo passou da franquia (bateu a meta)."""
        return not self.ilimitado and self.total_copias > self.limite_mensal

    @property
    def restante(self) -> int:
        if self.ilimitado:
            return 2**31
        return max(0, self.limite_mensal - self.total_copias)


@dataclass
class RelatorioImpressao:
    """Relatório mensal de impressões do tenant (agregado por professor)."""

    tenant_id: UUID
    competencia: str  # "YYYY-MM"
    linhas: list[LinhaRelatorioImpressao] = field(default_factory=list)

    @property
    def total_copias(self) -> int:
        return sum(linha.total_copias for linha in self.linhas)

    @property
    def total_solicitacoes(self) -> int:
        return sum(linha.total_solicitacoes for linha in self.linhas)


# --------------------------------------------------------------------------- #
# Onda 2 · F1 — Progressão de série e ciclo de vida do responsável
# --------------------------------------------------------------------------- #
@dataclass
class ResultadoPromocao:
    """Resultado da promoção de uma série na virada de ano (§F1)."""

    origem_sala_id: UUID
    origem_sala_nome: str
    destino_sala_id: UUID | None
    destino_sala_nome: str
    alunos_promovidos: int
    alunos_formados: int  # marcados como ex-aluno (última série)


@dataclass
class ResponsavelInativado:
    """Responsável cujo cadastro foi inativado por não ter mais alunos ativos (§F1)."""

    contato_id: UUID
    nome: str
    telefone: str


# --------------------------------------------------------------------------- #
# Onda 3 · I1 — Aviso de falta de professor e chamada de eventual
# --------------------------------------------------------------------------- #
class StatusFalta(str, enum.Enum):
    """Situação de um aviso de falta de professor."""

    ABERTA = "aberta"  # falta registrada, ainda sem substituto (eventual)
    COBERTA = "coberta"  # eventual confirmado para cobrir a falta
    CANCELADA = "cancelada"  # falta cancelada (o professor compareceu, etc.)


@dataclass
class AvisoFalta:
    """Aviso de falta de um professor + organização da chamada de eventual (§I1).

    Dor de campo (Rosa Cury): o professor avisa a falta pelo WhatsApp pessoal e a
    secretaria organiza o substituto ("eventual") em planilha + print manual de grupo.
    Aqui a falta fica **registrada** e a chamada de eventuais é disparada e rastreada
    pelo sistema. ``eventuais_chamados`` guarda os telefones notificados;
    ``eventual_*`` registra quem confirmou. ``professor_nome`` é denormalizado só para
    exibição. ``data`` é o dia da falta ("YYYY-MM-DD").
    """

    tenant_id: UUID
    data: str  # "YYYY-MM-DD" — dia da ausência
    motivo: str = ""
    professor_id: UUID | None = None
    professor_nome: str = ""
    status: StatusFalta = StatusFalta.ABERTA
    eventual_nome: str = ""
    eventual_telefone: str = ""
    eventuais_chamados: list[str] = field(default_factory=list)
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Onda 3 · H1 — Exportação de conversa para fins legais
# --------------------------------------------------------------------------- #
@dataclass
class ConversaExportada:
    """Conversa formatada para arquivamento legal (processo/prontuário) (§H1).

    Complementa o histórico existente: reúne as mensagens de uma conversa (opcionalmente
    recortadas por período) num **documento textual** com cabeçalho institucional e marca
    de exportação, válido para anexar a casos (ocorrências, racismo, etc.). ``documento``
    é o texto pronto para imprimir; os demais campos são os metadados da exportação.
    """

    tenant_id: UUID
    conversa_id: UUID
    escola_nome: str
    contato: str
    documento: str
    total_mensagens: int
    inicio: datetime | None = None
    fim: datetime | None = None
    gerado_em: datetime = field(default_factory=_now)


# --------------------------------------------------------------------------- #
# Onda 3 · D1/D2/D3 — Ficha de matrícula digital (campos ricos + sensíveis)
# --------------------------------------------------------------------------- #
@dataclass
class FichaMatricula:
    """Ficha de matrícula digital de um aluno (§D1/D2), 1:1 com ``Aluno``.

    Digitaliza a ficha física (frente + verso) da escola. Além dos dados cadastrais,
    carrega os **campos obrigatórios/sensíveis** (§D2): ``cor_raca`` (obrigatório nos
    dois sistemas), Bolsa Família/NIS, deficiência/necessidade especial, laudo/CID,
    restrição alimentar e alergia. ``dados_extra`` acomoda campos configuráveis por
    escola (§D1) sem migração. ``aluno_nome`` é denormalizado só para exibição.
    """

    tenant_id: UUID
    aluno_id: UUID
    # D2 — obrigatório
    cor_raca: str = ""
    # Frente da ficha
    ra_rm: str = ""
    data_nascimento: str = ""
    cpf: str = ""
    cartao_sus: str = ""
    sexo: str = ""
    cidade_natal: str = ""
    endereco: str = ""
    email: str = ""
    ano_etapa: str = ""
    periodo: str = ""
    filiacao1_nome: str = ""
    filiacao1_cpf: str = ""
    filiacao1_telefone: str = ""
    filiacao2_nome: str = ""
    filiacao2_cpf: str = ""
    filiacao2_telefone: str = ""
    responsavel_legal: str = ""
    termo_guarda: bool = False
    # Verso da ficha
    com_quem_mora: str = ""
    irmaos_na_escola: str = ""
    ubs: str = ""
    convenio: str = ""
    tratamento_medicacao: str = ""
    autorizacao_van: bool = False
    autorizacao_retirada: bool = False
    autorizacao_imagem: bool = False
    # D2 — dados sensíveis / de saúde
    bolsa_familia: bool = False
    nis: str = ""
    deficiencia: str = ""
    necessidade_especial: str = ""
    laudo_cid: str = ""
    restricao_alimentar: str = ""
    alergia: str = ""
    observacoes_saude: str = ""
    # D1 — campos configuráveis por escola (livres)
    dados_extra: dict = field(default_factory=dict)
    aluno_nome: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)


# Campos da ficha que são persistidos no JSON ``conteudo`` (todos, menos identidade/timestamps).
CAMPOS_FICHA_MATRICULA: tuple[str, ...] = (
    "cor_raca",
    "ra_rm",
    "data_nascimento",
    "cpf",
    "cartao_sus",
    "sexo",
    "cidade_natal",
    "endereco",
    "email",
    "ano_etapa",
    "periodo",
    "filiacao1_nome",
    "filiacao1_cpf",
    "filiacao1_telefone",
    "filiacao2_nome",
    "filiacao2_cpf",
    "filiacao2_telefone",
    "responsavel_legal",
    "termo_guarda",
    "com_quem_mora",
    "irmaos_na_escola",
    "ubs",
    "convenio",
    "tratamento_medicacao",
    "autorizacao_van",
    "autorizacao_retirada",
    "autorizacao_imagem",
    "bolsa_familia",
    "nis",
    "deficiencia",
    "necessidade_especial",
    "laudo_cid",
    "restricao_alimentar",
    "alergia",
    "observacoes_saude",
    "dados_extra",
)


@dataclass
class PreviaFichaMatricula:
    """Resultado da leitura de uma ficha por IA (§D3), pronto para revisão.

    A LLM extrai os campos de uma foto/PDF (texto bruto/OCR); o resultado é **validado
    em código** (a LLM não é fonte de verdade) e devolvido para o operador revisar antes
    de gravar. ``campos`` mapeia nome do campo → valor normalizado.
    """

    campos: dict = field(default_factory=dict)
    avisos: list[str] = field(default_factory=list)
    erros: list[str] = field(default_factory=list)

    @property
    def valido(self) -> bool:
        return not self.erros


# --------------------------------------------------------------------------- #
# Onda 3 · E1 — Matrícula/atendimento self-service pelo WhatsApp
# --------------------------------------------------------------------------- #
class StatusMatricula(str, enum.Enum):
    """Estágio de uma solicitação de matrícula iniciada pelo responsável."""

    INICIADA = "iniciada"  # bot enviou a lista de documentos
    DOCUMENTOS_ENVIADOS = "documentos_enviados"  # o responsável anexou documentos
    EM_ANALISE = "em_analise"  # a secretaria está conferindo
    CONCLUIDA = "concluida"  # aguardando/feita a assinatura presencial
    CANCELADA = "cancelada"


@dataclass
class DocumentoMatricula:
    """Um documento enviado pelo responsável no fluxo de matrícula self-service (§E1)."""

    nome: str
    url: str = ""
    recebido_em: datetime = field(default_factory=_now)


@dataclass
class SolicitacaoMatricula:
    """Matrícula iniciada pelo responsável via WhatsApp (§E1).

    Reduz o "pai vem só pra assinar": o bot envia a **lista de documentos**, o responsável
    manda fotos/scan e a secretaria imprime apenas para a **assinatura presencial**. Uma
    solicitação é aberta por telefone do responsável (WhatsApp).
    """

    tenant_id: UUID
    contato_telefone: str  # E.164 do responsável
    nome_responsavel: str = ""
    nome_aluno: str = ""
    status: StatusMatricula = StatusMatricula.INICIADA
    observacao: str = ""
    documentos: list[DocumentoMatricula] = field(default_factory=list)
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)


# Documentos exigidos na matrícula (reusa os "atalhos" de inscrição da secretaria, §E1).
DOCUMENTOS_MATRICULA_EXIGIDOS: tuple[str, ...] = (
    "RG do aluno (ou certidão de nascimento)",
    "CPF do aluno",
    "Comprovante de residência atualizado",
    "Cartão SUS do aluno",
    "Cartão de vacinação atualizado",
    "Foto 3x4 recente",
    "Histórico escolar ou declaração de escolaridade",
    "RG e CPF do responsável legal",
)
