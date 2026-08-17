"""Entidades e value objects do domínio.

Camada mais interna da arquitetura hexagonal: não importa framework, ORM ou SDK.
São dataclasses puras que modelam o negócio escolar multi-tenant.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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


# Dias da semana no padrão ISO (o mesmo de ``datetime.isoweekday``).
_DIAS_SEMANA = {
    1: "segunda-feira",
    2: "terça-feira",
    3: "quarta-feira",
    4: "quinta-feira",
    5: "sexta-feira",
    6: "sábado",
    7: "domingo",
}

# Como a escola escreve o expediente: "segunda a sexta", não "segunda-feira a sexta-feira".
_DIAS_SEMANA_CURTO = {
    1: "segunda",
    2: "terça",
    3: "quarta",
    4: "quinta",
    5: "sexta",
    6: "sábado",
    7: "domingo",
}

TIMEZONE_PADRAO = "America/Sao_Paulo"


def formatar_hora(h: time) -> str:
    """``07:30`` → ``7h30``; ``17:00`` → ``17h`` (como a escola escreve)."""
    return f"{h.hour}h{h.minute:02d}" if h.minute else f"{h.hour}h"


@dataclass(frozen=True)
class JanelaDeExecucao:
    """Quando uma tarefa de fundo pode acordar: N passadas por dia, numa faixa, em certos dias.

    Existe por duas razões que se somam, e nenhuma delas sozinha justificaria o desenho.

    **A primeira é o responsável.** Uma tarefa que acorda de hora em hora acaba disparando
    aviso escolar às 3h da manhã no dia em que a cota liberar de madrugada. A escola fala
    com pais, e a hora da mensagem é parte da mensagem.

    **A segunda é a conta do banco.** O Postgres é serverless (Neon) e dorme quando ninguém
    o procura. Uma passada de 30 em 30 minutos abre sessão 48 vezes por dia — inclusive de
    madrugada, sábado e domingo — e o mantém acordado 24/7 só para descobrir que não havia
    nada a fazer. Três passadas em dias úteis derrubam esse piso em mais de 90%.

    Espelha de propósito o vocabulário do expediente do `Tenant` (``dias``/``inicio``/
    ``fim``/``timezone``): é a mesma ideia — uma faixa de horas em certos dias da semana,
    no relógio de quem lê — e ter dois vocabulários para ela só criaria dúvida sobre qual
    vale.
    """

    dias: tuple[int, ...] = (1, 2, 3, 4, 5)  # ISO: 1 = segunda … 7 = domingo
    inicio: time = time(7, 0)
    fim: time = time(18, 0)
    passadas: int = 3
    timezone: str = TIMEZONE_PADRAO

    @property
    def _zona(self) -> ZoneInfo:
        """Mesma queda para o padrão do expediente: fuso inválido não pode parar a tarefa."""
        try:
            return ZoneInfo(self.timezone or TIMEZONE_PADRAO)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo(TIMEZONE_PADRAO)

    @property
    def ativa(self) -> bool:
        """Há alguma passada configurada. ``passadas <= 0`` desliga sem precisar de flag."""
        return bool(self.dias) and self.passadas > 0 and self.inicio <= self.fim

    def horarios(self) -> tuple[time, ...]:
        """As passadas distribuídas uniformemente na faixa, extremos incluídos.

        Três entre 7h e 18h dão **7h, 12h30 e 18h**. Uma única passada roda no ``inicio``:
        o começo do expediente é a hora mais útil para um disparo travado desde ontem.
        """
        if not self.ativa:
            return ()
        if self.passadas == 1:
            return (self.inicio,)
        base = datetime(2000, 1, 1)
        span = (
            datetime.combine(base.date(), self.fim) - datetime.combine(base.date(), self.inicio)
        ).total_seconds()
        passo = span / (self.passadas - 1)
        return tuple(
            (datetime.combine(base.date(), self.inicio) + timedelta(seconds=passo * i)).time()
            for i in range(self.passadas)
        )

    def proxima_execucao(self, depois_de: datetime) -> datetime | None:
        """Primeiro horário da grade estritamente após ``depois_de``, em UTC.

        ``None`` só quando a janela está desligada. Oito dias de busca bastam: a grade se
        repete toda semana, e o oitavo cobre o caso de ``depois_de`` cair no fim do último
        dia útil configurado.
        """
        if not self.ativa:
            return None
        local = depois_de.astimezone(self._zona)
        for offset in range(0, 8):
            dia = (local + timedelta(days=offset)).date()
            if dia.isoweekday() not in self.dias:
                continue
            for hora in self.horarios():
                quando = datetime.combine(dia, hora, tzinfo=self._zona)
                if quando > local:
                    return quando.astimezone(timezone.utc)
        return None

    @property
    def descricao(self) -> str:
        """Como aparece no log de boot — o valor da env não é o horário efetivo.

        Sem isto, conferir a grade em produção exige reproduzir a divisão de cabeça, e
        ninguém confere o que dá trabalho conferir.
        """
        if not self.ativa:
            return "desligada"
        horas = ", ".join(formatar_hora(h) for h in self.horarios())
        dias = "/".join(_DIAS_SEMANA_CURTO.get(d, str(d)) for d in sorted(self.dias))
        # O fuso **efetivo**, não o configurado: com um nome inválido a tarefa roda em
        # Brasília, e um log que repetisse o que foi digitado esconderia justamente o erro
        # que ele existe para revelar.
        return f"{horas} ({dias}, {self._zona.key})"


@dataclass
class Waba:
    """Uma conta do WhatsApp Business (WABA) sob a qual escolas operam.

    **Por que é entidade e não uma variável de ambiente.** A WABA é o endereço de tudo
    que é template (``/{waba_id}/message_templates``) e uma só não comporta o produto
    inteiro: o cadastro de números tem teto (§9e.3), e ao esgotá-lo a escola seguinte
    entra em outra conta. Com o id numa env, a vigésima primeira escola criaria template
    na conta errada — onde o número dela não está — e o disparo falharia na Graph API
    depois de o painel já ter dito "aprovado".

    ``meta_business_id`` é o **portfólio** dono da conta, e não é decoração: o teto de
    números e o limite diário de envio são medidos ali, não por WABA. Guardá-lo é o que
    permite responder "quantos números ainda cabem?" sem abrir o console.
    """

    meta_waba_id: str
    nome: str
    id: UUID = field(default_factory=_new_id)
    # Portfólio empresarial (Meta Business Account) dono desta WABA. Vazio = não
    # informado; só atrapalha a contagem de ocupação, não o envio.
    meta_business_id: str = ""
    # Desligada, deixa de receber replicação de template novo e de ser oferecida a escola
    # nova. Não é o mesmo que remover: as escolas que já estão nela seguem operando.
    ativo: bool = True
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime | None = None


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
    # para o tenant certo e é o remetente do outbound. Vazio = usa o número padrão do canal.
    # É um número **dedicado** à plataforma (a escola adquire um novo, deixando o número
    # antigo da secretaria livre para o atendimento manual).
    whatsapp_numero: str = ""
    # Identificador do número da escola **na Meta** (``phone_number_id``): é o que a Graph
    # API exige na URL de envio (``/{phone_number_id}/messages``) e o que o webhook devolve
    # em ``value.metadata.phone_number_id`` para rotear o inbound. Não confundir com
    # ``whatsapp_numero``, que é o mesmo número em E.164 legível — os dois coexistem, o
    # E.164 para exibição e o id para falar com a API. Único entre escolas (dois tenants com
    # o mesmo id tornariam o roteamento do inbound ambíguo). Vazio = usa o número padrão da
    # env (``META_PHONE_NUMBER_ID``).
    meta_phone_number_id: str = ""
    # WABA (``Waba``) onde o número desta escola está cadastrado. É o que diz **onde**
    # criar e conferir template para ela — o número roteia a mensagem, a WABA responde
    # pelo catálogo. Nulo = escola ainda sem conta atribuída: dispara pelo número, mas o
    # painel não sabe em qual catálogo procurar e recusa o envio por template.
    waba_id: UUID | None = None
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
    # --- Expediente da secretaria (§6j) --------------------------------------------- #
    # Quando há gente da escola para assumir um atendimento encaminhado pelo assistente.
    # É **campo estruturado, e não texto na base de conhecimento**, de propósito: a base
    # responde a quem *pergunta* o horário (RAG), mas aqui o horário **governa
    # comportamento** — se o recall falhasse, o assistente prometeria atendimento imediato
    # às 23h. Dias no padrão ISO (1 = segunda … 7 = domingo); horas na hora local da escola.
    expediente_dias: tuple[int, ...] = (1, 2, 3, 4, 5)
    expediente_inicio: time = time(7, 30)
    expediente_fim: time = time(17, 0)
    expediente_timezone: str = TIMEZONE_PADRAO

    @property
    def remetente_canal(self) -> str:
        """Identificador do número da escola **para o canal de mensagens** (o ``remetente``).

        Na Meta Cloud API a origem de um envio é o ``phone_number_id`` — a URL
        ``/{phone_number_id}/messages`` não aceita o E.164. Por isso o id da Meta tem
        precedência; o ``whatsapp_numero`` fica como fallback para canais que roteiam pelo
        número (demo) e para escolas ainda sem id cadastrado. Vazio = número padrão do canal.
        """
        return self.meta_phone_number_id.strip() or self.whatsapp_numero.strip()

    # --- Expediente ------------------------------------------------------------------ #
    @property
    def _zona(self) -> ZoneInfo:
        """Fuso da escola, com queda para o padrão se o nome for inválido.

        Um fuso digitado errado no painel não pode derrubar o atendimento: o pior caso
        aceitável é responder no horário de Brasília.
        """
        try:
            return ZoneInfo(self.expediente_timezone or TIMEZONE_PADRAO)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo(TIMEZONE_PADRAO)

    def hora_local(self, quando: datetime | None = None) -> datetime:
        """Um instante convertido para a hora local da escola.

        É o que permite falar com o responsável no relógio dele ("amanhã às 7h30") sem
        espalhar ``ZoneInfo`` pela camada de aplicação.
        """
        return (quando or _now()).astimezone(self._zona)

    @property
    def tem_expediente(self) -> bool:
        """Há uma janela de atendimento válida configurada."""
        return bool(self.expediente_dias) and self.expediente_inicio < self.expediente_fim

    def dentro_do_expediente(self, agora: datetime | None = None) -> bool:
        """A secretaria está aberta neste instante (hora local da escola)?"""
        if not self.tem_expediente:
            return False
        local = (agora or _now()).astimezone(self._zona)
        if local.isoweekday() not in self.expediente_dias:
            return False
        return self.expediente_inicio <= local.time() < self.expediente_fim

    def proxima_abertura(self, agora: datetime | None = None) -> datetime | None:
        """Quando a secretaria abre de novo (em UTC), ou ``None`` sem expediente.

        Devolve o próprio instante quando já está aberta — quem pergunta "quando abre"
        estando aberto quer ouvir "agora".
        """
        if not self.tem_expediente:
            return None
        agora = agora or _now()
        if self.dentro_do_expediente(agora):
            return agora

        local = agora.astimezone(self._zona)
        # Hoje ainda conta se o expediente não começou; a partir de amanhã, sempre na
        # abertura. Sete dias bastam: os dias configurados se repetem toda semana.
        for offset in range(0, 8):
            dia = (local + timedelta(days=offset)).date()
            if dia.isoweekday() not in self.expediente_dias:
                continue
            abertura = datetime.combine(dia, self.expediente_inicio, tzinfo=self._zona)
            if abertura > local:
                return abertura.astimezone(timezone.utc)
        return None

    @property
    def descricao_expediente(self) -> str:
        """Expediente em texto ("segunda a sexta, das 7h30 às 17h").

        É o que o assistente diz ao responsável — por isso nasce do campo, e não da base
        de conhecimento: a promessa feita a quem espera tem uma fonte só.
        """
        if not self.tem_expediente:
            return ""
        dias = sorted(self.expediente_dias)
        nomes = [_DIAS_SEMANA_CURTO[d] for d in dias]
        if len(dias) > 1 and dias == list(range(dias[0], dias[-1] + 1)):
            rotulo = f"{nomes[0]} a {nomes[-1]}"
        elif len(nomes) > 1:
            rotulo = f"{', '.join(nomes[:-1])} e {nomes[-1]}"
        else:
            rotulo = nomes[0]
        inicio = formatar_hora(self.expediente_inicio)
        fim = formatar_hora(self.expediente_fim)
        return f"{rotulo}, das {inicio} às {fim}"

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
    """A **fronteira de autorização**: o que a conta pode fazer no sistema.

    Distinto de ``Cargo``, que é o posto da pessoa na escola. Existem separados porque
    respondem a perguntas diferentes — ``Papel`` é checado por rota, ``Cargo`` ordena a
    hierarquia de quem gere quem. Colapsar os dois faria "coordenadora" virar uma regra
    espalhada por dezenas de guardas.
    """

    # Controle da plataforma (cross-tenant) — o "seu" controle.
    SUPER_ADMIN = "super_admin"
    # Administra uma única escola (tenant): gere usuários, cadastros e disparos.
    TENANT_ADMIN = "tenant_admin"
    # Opera uma escola **sem gerir usuários**: a secretaria. Papel próprio, e não um
    # ``tenant_admin`` com um campo a mais, para falhar **fechado**: uma rota que só
    # pergunte "é tenant_admin?" recusa a secretaria por construção, em vez de liberar
    # tudo porque alguém esqueceu de conferir o cargo.
    SECRETARIA = "secretaria"


class Cargo(str, enum.Enum):
    """Posto na escola. A ordem importa: define **quem pode gerir quem**.

    Um usuário só cria, edita ou desliga alguém **estritamente abaixo** de si. Coordenador
    não mexe em vice-diretor, e ninguém se promove — senão a tela de equipe seria o
    caminho mais curto para uma escalada de privilégio dentro da própria escola.
    """

    DIRETOR = "diretor"
    VICE_DIRETOR = "vice_diretor"
    COORDENADOR = "coordenador"
    SECRETARIA = "secretaria"

    @property
    def nivel(self) -> int:
        """Maior manda em menor. Só a ordem relativa importa."""
        return _NIVEL_CARGO[self]

    @property
    def rotulo(self) -> str:
        return _ROTULO_CARGO[self]

    @property
    def papel_correspondente(self) -> Papel:
        """Todo cargo é admin da escola, **menos** a secretaria (§2.4 do plano)."""
        return Papel.SECRETARIA if self is Cargo.SECRETARIA else Papel.TENANT_ADMIN


_NIVEL_CARGO: dict[Cargo, int] = {
    Cargo.DIRETOR: 4,
    Cargo.VICE_DIRETOR: 3,
    Cargo.COORDENADOR: 2,
    Cargo.SECRETARIA: 1,
}

_ROTULO_CARGO: dict[Cargo, str] = {
    Cargo.DIRETOR: "Diretor(a)",
    Cargo.VICE_DIRETOR: "Vice-diretor(a)",
    Cargo.COORDENADOR: "Coordenador(a)",
    Cargo.SECRETARIA: "Secretaria",
}


class Turno(str, enum.Enum):
    """Turno de trabalho (usuário) ou período da turma."""

    MANHA = "manha"
    TARDE = "tarde"
    INTEGRAL = "integral"
    NOITE = "noite"

    @property
    def rotulo(self) -> str:
        return {
            Turno.MANHA: "Manhã",
            Turno.TARDE: "Tarde",
            Turno.INTEGRAL: "Integral",
            Turno.NOITE: "Noite",
        }[self]


@dataclass
class Usuario:
    """Usuário administrativo. ``tenant_id`` é None para o super admin.

    ``cargo`` é ``None`` só para o super admin, que não ocupa posto em escola nenhuma.
    ``telefone`` existe para o dia em que a fila de atendimento (§6j) notificar por
    WhatsApp — hoje a notificação é in-app, e a falta deste campo era o que a travava.
    """

    nome: str
    email: str
    senha_hash: str
    papel: Papel
    id: UUID = field(default_factory=_new_id)
    tenant_id: UUID | None = None
    cargo: Cargo | None = None
    telefone: str = ""  # E.164
    endereco: str = ""
    turno: Turno | None = None
    ativo: bool = True
    criado_em: datetime = field(default_factory=_now)

    @property
    def eh_super_admin(self) -> bool:
        return self.papel == Papel.SUPER_ADMIN

    @property
    def gere_usuarios(self) -> bool:
        """Pode abrir a tela de equipe e mexer em contas.

        A secretaria **não** pode: é a única exceção do apontamento ("com exceção da
        secretaria os usuários são admins da escola").
        """
        return self.papel in (Papel.SUPER_ADMIN, Papel.TENANT_ADMIN)

    @property
    def nivel_hierarquico(self) -> int:
        """Posição na hierarquia. O super admin fica acima de qualquer cargo."""
        if self.eh_super_admin:
            return max(_NIVEL_CARGO.values()) + 1
        return self.cargo.nivel if self.cargo else 0

    def manda_em(self, outro: "Usuario") -> bool:
        """Pode gerir ``outro``? Exige estar **estritamente acima** na hierarquia.

        Estritamente, e não "no mesmo nível ou acima", porque diretor editando diretor é o
        caminho por onde uma conta é tomada — inclusive a própria, com senha trocada.
        """
        if self.eh_super_admin:
            return True
        if outro.eh_super_admin or outro.tenant_id != self.tenant_id:
            return False
        return self.nivel_hierarquico > outro.nivel_hierarquico


# --------------------------------------------------------------------------- #
# Contatos (pais/responsáveis) e grupos de distribuição
# --------------------------------------------------------------------------- #
class TipoFiliacao(str, enum.Enum):
    """Vínculo do responsável com o aluno.

    ``RESPONSAVEL_LEGAL`` é o caso do **termo de guarda**: quem responde pelo aluno sem
    ser mãe ou pai. Ele é um ``Contato`` como qualquer outro — recebe disparo, é
    reconhecido no WhatsApp e aparece na ficha —, e não um booleano na ficha, que era
    como estava modelado antes (``FichaMatricula.termo_guarda``) e deixava a pessoa
    invisível para o canal.
    """

    MAE = "mae"
    PAI = "pai"
    RESPONSAVEL_LEGAL = "responsavel_legal"
    OUTRO = "outro"

    @property
    def rotulo(self) -> str:
        return {
            TipoFiliacao.MAE: "Mãe",
            TipoFiliacao.PAI: "Pai",
            TipoFiliacao.RESPONSAVEL_LEGAL: "Responsável legal (termo de guarda)",
            TipoFiliacao.OUTRO: "Outro",
        }[self]


@dataclass
class Contato:
    """Pai/responsável com número de WhatsApp, dentro de um tenant.

    ``ativo=False`` marca um responsável **inativo** — normalmente porque todos os seus
    alunos já são ex-alunos (ver a progressão de série, §F1). Um responsável inativo
    permanece no cadastro (histórico), mas não deve receber novos avisos.

    **``telefone`` é o número da conversa.** É por ele que o inbound roteia (o webhook
    entrega o remetente, não o id do contato) e por ele que o disparo sai — daí ser único
    por tenant. ``telefone_2`` e ``telefone_trabalho`` são contato de emergência e **não
    entram em disparo nenhum**: dois números na mesma conversa quebrariam o roteamento,
    que casa por telefone (decisão E do plano de 10/08).

    ``tipo_filiacao`` é o vínculo declarado da pessoa. Fica no ``Contato``, e não na
    associação com o aluno, porque é assim que a secretaria cadastra e enxerga — "a mãe",
    "o responsável legal". O caso de alguém ser mãe de um aluno e guardiã de outro na
    mesma escola existe, mas é raro o bastante para não justificar hoje um campo por
    vínculo; quando aparecer, ele entra em ``aluno_responsaveis``.
    """

    tenant_id: UUID
    nome: str
    telefone: str  # E.164 — o número da conversa; ver o docstring
    ativo: bool = True
    # Cadastro do responsável. CPF em 11 dígitos sem pontuação; datas em ISO.
    cpf: str = ""
    tipo_filiacao: TipoFiliacao | None = None
    data_nascimento: str = ""
    telefone_2: str = ""  # emergência — NÃO recebe disparo
    local_trabalho: str = ""
    telefone_trabalho: str = ""  # emergência — NÃO recebe disparo
    email: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)

    @property
    def eh_responsavel_legal(self) -> bool:
        """Entrou por termo de guarda (não é mãe nem pai)."""
        return self.tipo_filiacao is TipoFiliacao.RESPONSAVEL_LEGAL


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

    Um professor pode estar à frente de **várias séries/turmas** (``Sala``), mas cada
    série tem **no máximo um** professor responsável (o vínculo mora em
    ``Sala.professor_id``).

    Nasceu enxuto — só nome e telefone — e ganhou o cadastro funcional em 11/ago/2026.
    Dois campos merecem explicação:

    - **``titular``** distingue o professor da turma do **eventual** (substituto). Não é
      rótulo: é a lista de quem a secretaria chama quando alguém falta (§I1), que hoje é
      digitada à mão a cada aviso de falta.
    - **``telefone``** é o número que recebe recado da escola e o mural; **``telefone_2``
      é contato de emergência** e não entra em disparo nenhum. Um professor com dois
      números ativos no canal receberia a mesma mensagem duas vezes.
    """

    tenant_id: UUID
    nome: str
    telefone: str  # E.164, ex.: +5511999990000 — o número que a escola usa
    # Cadastro funcional. CPF em 11 dígitos sem pontuação; datas em ISO (AAAA-MM-DD).
    cpf: str = ""
    data_nascimento: str = ""
    matricula: str = ""  # matrícula funcional na rede
    endereco: str = ""
    telefone_2: str = ""  # emergência — NÃO recebe disparo (ver docstring)
    email: str = ""
    # Habilitação e vínculo. `titular=False` significa **eventual**.
    educacao_fisica: bool = False
    titular: bool = True
    # Senha (hash PBKDF2) para o login do professor no mural (§A1). Vazio = sem acesso.
    senha_hash: str = ""
    # Vínculo vivo com a escola. Desligado, o professor deixa de entrar no mural **e** o
    # número dele deixa de ser reconhecido no WhatsApp — que é o ponto: sem esta flag,
    # quem saiu da escola continuaria mandando arquivo direto para a fila de impressão,
    # porque o cadastro permanece (o histórico da fila depende dele).
    ativo: bool = True
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)

    @property
    def tem_acesso(self) -> bool:
        """Verdadeiro quando o professor tem senha definida (pode entrar no mural)."""
        return bool(self.senha_hash)

    @property
    def eh_eventual(self) -> bool:
        """Candidato a cobrir falta de outro professor (§I1)."""
        return not self.titular


class StatusImpressao(str, enum.Enum):
    """Estado de uma solicitação de impressão na fila da secretaria."""

    PENDENTE = "pendente"  # na fila, aguardando a secretaria
    EM_PROCESSO = "em_processo"  # a secretaria está imprimindo
    CONCLUIDA = "concluida"  # impressa e disponível
    CANCELADA = "cancelada"  # cancelada (pelo professor ou pela secretaria)


class OrigemImpressao(str, enum.Enum):
    """Por onde o pedido entrou na fila.

    Não é enfeite de relatório: o pedido que chega pelo WhatsApp não passou por
    formulário nenhum — o número de cópias saiu de um palpite sobre a legenda —, e a
    secretaria precisa saber disso antes de mandar 200 folhas para a impressora.
    """

    PORTAL = "portal"  # formulário do portal do professor (§A1/§B1)
    WHATSAPP = "whatsapp"  # arquivo enviado ao número da escola


@dataclass
class SolicitacaoImpressao:
    """Pedido de impressão feito por um professor à secretaria (fila de impressão).

    Dor de campo (Rosa Cury): "elas mandam atividade/prova/lista de chamada pra imprimir
    o dia inteiro". O professor envia o arquivo com os parâmetros (nº de cópias,
    colorido/PB, frente-e-verso) e o pedido cai numa fila para a secretaria processar,
    sem ficar perguntando cada detalhe. ``professor_nome`` é denormalizado só para exibição.

    O arquivo pode chegar por dois caminhos. Pelo portal, ele é apenas **referenciado**
    (``arquivo_url``). Pelo WhatsApp, os **bytes ficam com a escola** (``chave_storage``
    aponta para o ``ArquivoStorage``, como nos documentos recebidos — §6k): sem isso, o
    pedido cairia na fila sem o que imprimir.
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
    origem: OrigemImpressao = OrigemImpressao.PORTAL
    # Arquivo guardado (só no caminho do WhatsApp). Vazio = nada para baixar.
    chave_storage: str = ""
    mime: str = ""
    tamanho: int = 0
    # `media_id` da Meta — deduplica a reentrega do webhook, como em `DocumentoRecebido`.
    media_id: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)

    @property
    def tem_arquivo(self) -> bool:
        """Verdadeiro quando os bytes estão com a escola e há o que baixar."""
        return bool(self.chave_storage)


@dataclass
class Sala:
    """Turma da escola, dentro de um tenant.

    Chamada ``Sala`` no domínio por herança — no painel a seção é **Turmas**, que é o
    vocabulário da escola ("sala" lá é o espaço físico, e virou ``numero_sala``).

    Nasceu com ``nome`` em texto livre ("4ª série B"). A partir de 12/ago/2026 a turma é
    **estruturada**: ``ano_letivo``, ``etapa``, ``turma``, ``numero_sala`` e ``periodo``.
    Texto livre impedia ordenar, promover série automaticamente e cruzar com a ficha; e
    "4ª B", "4ª série B" e "4a serie B" conviviam como turmas diferentes.

    ``nome`` continua existindo, agora **derivado** (``etapa`` + ``turma``), para não
    quebrar relatórios, seed e telas que já o exibem.

    ``pais`` é **derivado dos alunos** desde a mesma data: um responsável pertence à turma
    porque tem um aluno ativo nela. Antes era um vínculo manual (``sala_contatos``), que
    permitia pai vinculado a turma sem nenhum filho lá — e fazia a cobertura de contatos
    contar errado.

    ``professor_id`` é o **professor responsável** pela turma (1:1 — uma turma tem no
    máximo um professor; um professor pode ter várias); ``professor_nome`` é denormalizado
    só para exibição.
    """

    tenant_id: UUID
    nome: str  # derivado de etapa + turma; ex.: "4ª série B"
    descricao: str = ""
    # Identificação estruturada da turma (ficha física: ANO · ETAPA · TURMA · PERÍODO).
    ano_letivo: int = 0
    etapa: str = ""  # "1º", "4ª série"…
    turma: str = ""  # "A", "B", "C", "D"
    numero_sala: str = ""  # a sala física
    periodo: Turno | None = None
    # Grade de horário — JSON, com os dois formatos da decisão B. Ver `GRADE_*`.
    grade_horario: dict = field(default_factory=dict)
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    pais: list[Contato] = field(default_factory=list)
    professor_id: UUID | None = None
    professor_nome: str = ""

    @property
    def nome_derivado(self) -> str:
        """``etapa`` + ``turma``, com o ``nome`` atual como retaguarda.

        A retaguarda importa para as turmas anteriores à migration, cujo texto livre pode
        não ter sido separável em etapa/turma.
        """
        composto = " ".join(p for p in (self.etapa.strip(), self.turma.strip()) if p)
        return composto or self.nome

    @property
    def chave_unica(self) -> tuple[int, str, str]:
        """O que identifica a turma dentro da escola: ano + etapa + turma."""
        return (self.ano_letivo, self.etapa.strip().casefold(), self.turma.strip().casefold())


# Formatos da grade de horário (decisão B do plano de 10/08: **os dois**, sobre a mesma
# coluna JSON, para comparar na prática antes de escolher). Como o formato gravado é o
# mesmo, descartar um deles depois é apagar componente de tela, não migrar dado.
#
# - ``turno``: o suficiente para a secretaria hoje — entrada, saída e o intervalo.
# - ``aulas``: a grade aula a aula, com um bloco por dia/horário.
GRADE_TURNO = "turno"
GRADE_AULAS = "aulas"
GRADE_FORMATOS = (GRADE_TURNO, GRADE_AULAS)

# Tipos de bloco na grade aula a aula. O intervalo é bloco como qualquer outro: era o que
# o apontamento pedia ("grade de horário com intervalo incluso") e tratá-lo à parte faria
# a soma da carga horária ignorá-lo.
BLOCO_AULA = "aula"
BLOCO_INTERVALO = "intervalo"
BLOCO_TIPOS = (BLOCO_AULA, BLOCO_INTERVALO)


@dataclass
class Aluno:
    """Aluno da escola, dentro de um tenant.

    Pertence **obrigatoriamente** a uma série/turma (``sala_id`` — relação 1:1 com
    ``Sala``) e tem **N** responsáveis (``Contato``s, N:N via ``aluno_responsaveis``).
    ``ativo=False`` marca um ex-aluno. **O aluno nunca é apagado**: o registro de que ele
    estudou aqui é o lastro que a escola precisa preservar (histórico escolar, declarações,
    prestação de contas). Desativar é a única forma de "remover" um aluno pelo painel —
    ``desativado_em`` e ``motivo_desativacao`` guardam quando e por quê.
    ``sala_nome`` é denormalizado só para exibição.
    """

    tenant_id: UUID
    nome: str
    sala_id: UUID
    matricula: str = ""
    ativo: bool = True
    # Foto do aluno — **opcional** (decisão D do plano de 10/08). Aponta para o
    # `ArquivoStorage`, o mesmo dos documentos recebidos (§6k): os bytes não moram no
    # cadastro. Vazio = sem foto, e a tela não cobra.
    foto_chave: str = ""
    desativado_em: datetime | None = None
    motivo_desativacao: str = ""
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    responsaveis: list[Contato] = field(default_factory=list)
    sala_nome: str = ""

    def desativar(self, *, motivo: str = "", quando: datetime | None = None) -> None:
        """Marca como ex-aluno, preservando o registro. Idempotente: repetir não reescreve
        a data original — o que interessa é quando ele **saiu**, não o último clique."""
        if not self.ativo:
            return
        self.ativo = False
        self.desativado_em = quando or _now()
        self.motivo_desativacao = motivo.strip()

    def reativar(self) -> None:
        """Desfaz a desativação (rematrícula, ou correção de um clique errado)."""
        self.ativo = True
        self.desativado_em = None
        self.motivo_desativacao = ""

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
    # Uma pessoa da secretaria respondendo pelo mesmo fio, depois de o assistente
    # encaminhar o atendimento (§6j). Do lado do responsável não há transferência
    # visível — é a mesma conversa, com alguém melhor respondendo.
    ATENDENTE = "atendente"


@dataclass
class Mensagem:
    conversa_id: UUID
    autor: Autor
    texto: str
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    # Fontes (RAG) que embasaram uma resposta do bot.
    fontes: list[str] = field(default_factory=list)
    # Quem da secretaria respondeu (só quando ``autor`` é ``ATENDENTE``).
    autor_nome: str = ""


@dataclass
class Conversa:
    """Uma **sessão** de conversa com um responsável, não a conversa eterna dele.

    Até 12/ago/2026 havia uma ``Conversa`` por ``(tenant, contato)``, para sempre. Duas
    consequências, e a segunda custa dinheiro:

    1. o histórico do painel virava um fio infinito, impossível de ler;
    2. **o contexto enviado à LLM crescia sem limite** — cada mensagem nova carregava meses
       de assunto encerrado, encarecendo a chamada e piorando a resposta (o modelo responde
       sobre a matrícula de março quando perguntam do uniforme de agosto).

    Agora a sessão **viva** é a que não foi encerrada e cuja última mensagem está dentro de
    ``CONVERSA_JANELA_HORAS`` (24 por padrão — o mesmo relógio da janela da Meta, que é o
    que o responsável percebe). Fora disso, a próxima mensagem abre uma sessão nova.

    Resolver um ``AtendimentoHumano`` também encerra a sessão: assunto resolvido não deve
    continuar carregando contexto para o próximo, que costuma ser outro completamente.
    """

    tenant_id: UUID
    # Telefone (E.164) ou identificador do usuário no canal.
    contato: str
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    # Quando a última mensagem entrou — a base da janela de 24h da sessão.
    ultima_mensagem_em: datetime = field(default_factory=_now)
    # Sessão fechada (por inatividade ou por atendimento resolvido). None = viva.
    encerrada_em: datetime | None = None

    @property
    def encerrada(self) -> bool:
        return self.encerrada_em is not None

    def vencida_em(self, agora: datetime, *, janela_horas: int) -> bool:
        """A sessão passou da janela de inatividade?

        ``janela_horas <= 0`` desliga o recorte e devolve a conversa eterna de antes —
        existe como válvula, não como caminho recomendado.
        """
        if janela_horas <= 0:
            return False
        return (agora - self.ultima_mensagem_em) > timedelta(hours=janela_horas)


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
    # Retrato do nome no momento da ação. Fica como **fallback histórico**: quem lê o log
    # é resolvido na leitura contra o cadastro atual (ver `ListarAuditoria`), senão um
    # nome corrigido depois deixaria a mesma pessoa aparecendo com dois nomes no log — e
    # registro antigo, gravado antes de o campo existir, ficaria anônimo para sempre.
    ator_nome: str = ""
    # **Não persistido.** Preenchido na leitura com o id do `Usuario` que ainda existe,
    # e é o que autoriza o painel a linkar para o perfil. Vazio = ator sem conta (LLM,
    # sistema) ou conta que não está mais lá: um link para o nada é pior que texto puro.
    ator_perfil_id: str = ""
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
    metadados **e o texto original** do documento, para gestão no painel admin.

    ``conteudo`` guarda o texto **como foi enviado**. Sem ele o documento só existia
    fragmentado no vector store: dava para apagar, nunca para reler ou corrigir — e um
    procedimento que muda de ano em ano tinha de ser reenviado do zero.

    ``ativo`` separa **existir** de **estar indexado**. Um procedimento que saiu de vigência
    precisa parar de alimentar o bot sem que o texto seja destruído (quem apaga é o super
    admin). Desativada, a fonte não tem nenhum trecho no vector store; ``total_trechos``
    continua contando os fragmentos que o texto *tem*, para o número não oscilar a cada
    clique no interruptor.
    """

    tenant_id: UUID
    nome: str  # ex.: "Manual de procedimentos 2026"
    tipo: TipoConhecimento = TipoConhecimento.PROCEDIMENTO
    total_trechos: int = 0
    conteudo: str = ""
    ativo: bool = True
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)


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
class TemplateNaWaba:
    """O mesmo texto de template, do lado de **uma** WABA.

    Existe porque template é aprovado **por WABA**: o ``aviso_reuniao`` aprovado na WABA
    onde estão as vinte primeiras escolas simplesmente **não existe** na segunda. Enquanto
    o status morava numa coluna só do template, o produto respondia "aprovado" para uma
    escola cujo número está na outra conta — e a Graph API recusava o envio depois de a
    trava já ter dado o aval. É o único lugar onde `meta_template_id` faz sentido: a Meta
    emite um id por WABA para o mesmo texto.
    """

    waba_id: UUID
    status: StatusTemplate = StatusTemplate.PENDENTE
    meta_template_id: str = ""
    motivo_rejeicao: str = ""
    atualizado_em: datetime | None = None


# Do pior para o melhor. `REJEITADO` primeiro porque é o único que exige ação humana;
# `RASCUNHO` aqui significa "ainda não submetido nesta WABA", que também impede o envio.
_ORDEM_STATUS_TEMPLATE = [
    StatusTemplate.REJEITADO,
    StatusTemplate.RASCUNHO,
    StatusTemplate.PENDENTE,
    StatusTemplate.APROVADO,
]


@dataclass
class MessageTemplate:
    """Template (HSM) exigido pela Meta fora da janela de 24h.

    **``tenant_id`` nulo = template global**, do catálogo compartilhado — o caso comum: um
    ``aviso_geral`` com o nome da escola em ``{{1}}`` é revisado uma vez e serve todas, em
    vez de N revisões do mesmo texto e N chances de rejeição. O escopo por escola fica
    para o que é mesmo específico dela, com o nome prefixado pelo slug
    (``rosacury_festa_junina``).

    **O texto é um; as submissões são N.** Templates moram na WABA, e uma WABA não comporta
    todas as escolas (§9e.3), então o mesmo global precisa ser replicado em cada uma.
    Duplicar a linha inteira por WABA faria de editar um texto um trabalho de manter N
    cópias em sincronia — e o painel mostraria o mesmo template várias vezes. Por isso o
    corpo, a categoria e os exemplos vivem aqui, uma vez só, e o que varia por WABA (id na
    Meta, status, motivo) fica em ``wabas``.
    """

    nome: str
    categoria: CategoriaTemplate
    idioma: str
    corpo: str  # com placeholders {{1}}, {{2}}...
    tenant_id: UUID | None = None
    id: UUID = field(default_factory=_new_id)
    # Uma entrada por WABA onde este texto foi submetido. Vazio = ainda não foi a lugar
    # nenhum (rascunho).
    wabas: list[TemplateNaWaba] = field(default_factory=list)
    # Valores de exemplo para os placeholders. **Obrigatórios pela Meta** quando o corpo
    # tem variáveis: a revisão é humana e sem amostra o template é recusado de saída.
    exemplos: list[str] = field(default_factory=list)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime | None = None

    @property
    def global_(self) -> bool:
        return self.tenant_id is None

    @property
    def escopo(self) -> str:
        return "global" if self.global_ else "escola"

    def na_waba(self, waba_id: UUID | None) -> TemplateNaWaba | None:
        if waba_id is None:
            return None
        return next((w for w in self.wabas if w.waba_id == waba_id), None)

    def status_em(self, waba_id: UUID | None) -> StatusTemplate:
        """Status **naquela** WABA. Não submetido lá é ``RASCUNHO``, nunca ``APROVADO``.

        Falhar fechado é o ponto: a pergunta que o envio faz é "dá para enviar por este
        número?", e a resposta para uma WABA onde o texto nunca foi submetido é não.
        """
        entrada = self.na_waba(waba_id)
        return entrada.status if entrada else StatusTemplate.RASCUNHO

    def aprovado_em(self, waba_id: UUID | None) -> bool:
        return self.status_em(waba_id) is StatusTemplate.APROVADO

    def motivo_em(self, waba_id: UUID | None) -> str:
        entrada = self.na_waba(waba_id)
        return entrada.motivo_rejeicao if entrada else ""

    @property
    def status(self) -> StatusTemplate:
        """Status consolidado para exibição: o **pior** entre as WABAs.

        A tela precisa de um selo só, e o selo otimista seria o perigoso — "aprovado" com
        uma WABA ainda pendente convida a secretaria daquela escola a um disparo que
        falha. Sem nenhuma WABA, é rascunho.
        """
        if not self.wabas:
            return StatusTemplate.RASCUNHO
        return min(
            (w.status for w in self.wabas),
            key=lambda s: _ORDEM_STATUS_TEMPLATE.index(s),
        )

    @property
    def utilizavel(self) -> bool:
        """Enviável em **todas** as WABAs em que existe. Para uma escola específica, a
        pergunta certa é ``aprovado_em(waba_id)`` — esta é a visão do catálogo."""
        return bool(self.wabas) and self.status is StatusTemplate.APROVADO

    def visivel_para(self, tenant_id: UUID) -> bool:
        return self.global_ or self.tenant_id == tenant_id


@dataclass(frozen=True)
class TemplateRemoto:
    """Como a Meta descreve um template — o retrato do lado de lá, para sincronizar."""

    nome: str
    idioma: str
    status: StatusTemplate
    categoria: CategoriaTemplate
    meta_template_id: str = ""
    motivo_rejeicao: str = ""
    # Corpo, quando a listagem trouxe os componentes. É o que permite **importar** para o
    # catálogo um template que já existe na Meta, em vez de só contá-lo como desconhecido.
    corpo: str = ""


class StatusEntrega(str, enum.Enum):
    PENDENTE = "pendente"
    ENFILEIRADO = "enfileirado"
    ENVIADO = "sent"
    ENTREGUE = "delivered"
    LIDO = "read"
    FALHOU = "failed"


class OrigemParametro(str, enum.Enum):
    """De onde sai o valor de um ``{{n}}`` no disparo.

    São as três — e únicas — coisas disponíveis na hora do envio a um grupo: quem recebe,
    a escola que assina, e o que a secretaria escreveu. Um campo livre para tudo obrigaria
    a repetir o nome de cada responsável à mão; um valor fixo para tudo entregaria "Olá,
    {{1}}" com o mesmo nome para a turma inteira.
    """

    RESPONSAVEL = "responsavel"  # nome de quem recebe — varia por destinatário
    ESCOLA = "escola"  # nome da escola que assina
    TEXTO = "texto"  # o que a secretaria digitou, igual para todos


@dataclass(frozen=True)
class ParametroTemplate:
    """Um ``{{n}}`` do template e a regra para preenchê-lo em cada destinatário."""

    origem: OrigemParametro
    texto: str = ""

    def resolver(self, *, responsavel: str, escola: str) -> str:
        if self.origem is OrigemParametro.RESPONSAVEL:
            return responsavel
        if self.origem is OrigemParametro.ESCOLA:
            return escola
        return self.texto


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
    # Por que falhou, **na palavra da Meta**. Sem isto o painel diz "Falhou" e não há mais
    # nada em lugar nenhum: a exceção era engolida para não derrubar o lote, e com ela ia
    # embora a única explicação — foi o que aconteceu no primeiro disparo real, em que dois
    # envios falharam porque o template não existia na conta e ninguém tinha como saber.
    erro: str = ""
    # Quantas vezes o envio já foi tentado e falhou por motivo **transitório**. Falha
    # definitiva não conta aqui: ela vai direto para `FALHOU`, porque repetir daria o mesmo
    # erro e cada repetição queima a qualidade do número.
    tentativas: int = 0
    id: UUID = field(default_factory=_new_id)

    def desistir_de_reenviar(self, maximo: int) -> bool:
        """Já se tentou o bastante?

        Um teto é obrigatório: sem ele, um número que dá timeout para sempre voltaria à
        fila em toda passada, pelos 7 dias da janela de validade, consumindo vaga de quem
        ainda podia receber.
        """
        return self.tentativas >= maximo


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
    """Cota de conversas iniciadas pelo negócio na janela de **24h corridas** do portfólio.

    "Diário" aqui quer dizer *por 24 horas*, não *por data*. A distinção não é preciosismo —
    a versão anterior contava dia de calendário em UTC, por escola, e errava nos três eixos
    ao mesmo tempo:

    - **A janela é corrida.** A Meta conta as conversas iniciadas nas últimas 24 horas e
      devolve capacidade continuamente, à medida que cada envio completa 24h. **Não existe
      reset à meia-noite** — quem esperasse por ele esperaria por nada.
    - **O relógio era UTC**, então o "dia" virava às 21h de Brasília, no meio do expediente
      da escola: um disparo às 20h e outro às 22h caíam em cotas diferentes sem que nada na
      realidade tivesse mudado.
    - **O teto é do portfólio**, compartilhado por todos os números desde out/2025 (§9e.3).
      Contando por escola, cinco escolas de teste acreditam ter 1250 de capacidade e a Meta
      recusa na 251ª.

    ``enviados`` são **destinatários distintos**: a Meta cobra conversa iniciada com cliente
    único, então dois avisos ao mesmo responsável dentro da janela consomem **um**.
    """

    tenant_id: UUID
    # -1 = ilimitado
    limite_diario: int
    enviados: int = 0
    # Quando o envio mais antigo da janela completa 24h e devolve uma vaga. ``None`` quando
    # não há nada na janela — não há o que liberar, a cota já está inteira.
    proxima_liberacao: datetime | None = None
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
# Observabilidade — logs da aplicação (§16)
# --------------------------------------------------------------------------- #
class NivelLog(str, enum.Enum):
    """Níveis persistidos. Espelham os do ``logging`` da stdlib, sem DEBUG — que é ruído
    de desenvolvimento e não deve ocupar linha no banco de produção."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @property
    def severidade(self) -> int:
        return {"INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}[self.value]


@dataclass
class RegistroLog:
    """Uma linha de log da aplicação, consultável no painel.

    Distinto de ``RegistroAuditoria`` (§13), que registra **decisões de negócio** ("quem
    disparou o quê") e é evidência de compliance. Este aqui é **operacional**: o que o
    processo fez, quanto demorou e onde quebrou. Misturar os dois transformaria a
    auditoria em depósito de ruído técnico.
    """

    nivel: NivelLog
    mensagem: str
    logger: str = ""
    # Id que amarra todas as linhas de uma mesma requisição — é o que se pede ao usuário
    # que relatou o erro ("qual o código que apareceu na tela?").
    correlacao_id: str = ""
    rota: str = ""
    metodo: str = ""
    status_code: int | None = None
    duracao_ms: int | None = None
    tenant_id: UUID | None = None
    # Traceback, quando houver.
    excecao: str = ""
    metadados: dict = field(default_factory=dict)
    criado_em: datetime = field(default_factory=_now)
    id: UUID = field(default_factory=_new_id)

    @property
    def falha(self) -> bool:
        return self.nivel in (NivelLog.ERROR, NivelLog.CRITICAL)


@dataclass(frozen=True)
class ContagemRotulada:
    """Par rótulo/quantidade — usado nos rankings do painel (rotas, loggers, erros)."""

    rotulo: str
    quantidade: int


@dataclass(frozen=True)
class ResumoLogs:
    """Visão agregada da janela recente: é a tela de abertura do painel de logs."""

    janela_horas: int
    total: int
    erros: int
    alertas: int
    requisicoes: int
    # Latência das requisições na janela (ms).
    duracao_media_ms: int
    duracao_p95_ms: int
    # Atendimentos do WhatsApp na janela (o análogo das "filas" do Horizon).
    atendimentos_concluidos: int
    atendimentos_em_andamento: int
    atendimentos_falhos: int
    rotas_mais_lentas: list[ContagemRotulada] = field(default_factory=list)
    erros_mais_comuns: list[ContagemRotulada] = field(default_factory=list)

    @property
    def taxa_erro_percentual(self) -> float:
        if not self.requisicoes:
            return 0.0
        return round(100 * self.erros / self.requisicoes, 2)

    @property
    def saudavel(self) -> bool:
        """Sem erro e sem atendimento travado na janela."""
        return self.erros == 0 and self.atendimentos_falhos == 0


@dataclass(frozen=True)
class AtendimentoInbound:
    """Estado de um atendimento de WhatsApp, para a visão tipo Horizon."""

    chave: str
    status: str
    origem: str
    resumo: str
    criado_em: datetime
    atualizado_em: datetime
    tenant_id: UUID | None = None
    tenant_nome: str = ""


class EstadoAtendimento(str, enum.Enum):
    """Em que pé está o atendimento de uma mensagem recebida (§9e.1).

    Substitui o antigo "já vi este wamid, sim/não". A diferença que importa é entre
    ``EM_ATENDIMENTO`` e ``CONCLUIDA``: a reentrega da Meta chega tipicamente **enquanto**
    a primeira ainda está esperando a LLM, e um cache booleano de processo não distingue
    isso de uma dúvida já respondida — nem enxerga o que a outra réplica está fazendo.
    """

    # A mensagem é inédita e acabou de ser reservada por este processo.
    NOVO = "novo"
    # Havia uma reserva anterior abandonada (processo caiu / falhou) e foi retomada.
    RETOMADO = "retomado"
    # Outro processo (ou este, antes) está atendendo agora — não atender de novo.
    EM_ATENDIMENTO = "em_atendimento"
    # A dúvida já foi sanada; a resposta já saiu para o responsável.
    CONCLUIDA = "concluida"


@dataclass(frozen=True)
class ResultadoTaxa:
    """Veredito de um limite de taxa sobre uma chave (IP, e-mail, telefone).

    Diferente da ``MessageQuota`` (cota diária de envio, regra da Meta), este é o limite
    **de entrada**: quantas vezes a mesma origem pode bater numa rota numa janela curta.
    """

    permitido: bool
    # Quantas chamadas ainda cabem na janela atual.
    restantes: int
    # Segundos até a janela virar — vira o cabeçalho Retry-After no 429.
    retry_after: int
    # Quantas chamadas já foram contabilizadas nesta janela (inclui a atual).
    contador: int = 0


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


@dataclass(frozen=True)
class SaldoImpressao:
    """Franquia de um professor numa competência, já cruzada com o consumo.

    É o que o professor ouve de volta quando manda um arquivo pelo WhatsApp. O saldo é
    **derivado** das solicitações do mês, nunca um contador guardado: um contador
    divergiria da fila no primeiro cancelamento, e aí a escola teria dois números
    diferentes para a mesma pergunta.
    """

    competencia: str  # "YYYY-MM"
    limite_mensal: int = 0
    consumido: int = 0

    @property
    def ilimitado(self) -> bool:
        return self.limite_mensal <= 0

    @property
    def restante(self) -> int:
        return max(0, self.limite_mensal - self.consumido)

    @property
    def excedeu(self) -> bool:
        return not self.ilimitado and self.consumido > self.limite_mensal


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
    """Responsável cuja situação (``ativo``) mudou pela sincronização com os alunos (§F1)."""

    contato_id: UUID
    nome: str
    telefone: str


@dataclass
class ResultadoSincronizacao:
    """O que a sincronização de responsáveis mexeu.

    Os dois lados importam para a tela: inativar sozinho pareceria perda de cadastro, e
    reativar sem dizer deixaria a secretaria sem entender por que a família voltou a
    receber aviso.
    """

    inativados: list[ResponsavelInativado] = field(default_factory=list)
    reativados: list[ResponsavelInativado] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.inativados) + len(self.reativados)


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
    # A ficha física tem três caixas: NÃO · SIM (com CID) · EM INVESTIGAÇÃO. Só um texto
    # livre não distingue "não tem laudo" de "está sendo investigado", e a diferença
    # importa: uma fecha o assunto, a outra é pendência que a escola precisa acompanhar.
    laudo_status: str = ""  # "" | "nao" | "sim" | "em_investigacao"
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
    "laudo_status",
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


# ---------------------------------------------------------------------------
# Postura de segurança — auditoria interna do super admin
# ---------------------------------------------------------------------------


class StatusMedida(str, enum.Enum):
    """Situação de uma medida protetiva.

    ``ATENCAO`` é deliberadamente distinto de ``ATIVA``: a medida existe no código, mas a
    configuração em uso a enfraquece (segredo default, CORS liberado). Uma auditoria que
    só respondesse "implementado sim/não" esconderia exatamente esse caso.
    """

    ATIVA = "ativa"
    ATENCAO = "atencao"
    PENDENTE = "pendente"
    # Item que não se aplica ao produto como ele é hoje (ex.: expirar link de redefinição
    # de senha, quando não existe fluxo de redefinição). Distinto de PENDENTE para não
    # gerar alarme falso — mas com a nota registrando quando ele passa a valer.
    NAO_APLICAVEL = "nao_aplicavel"


@dataclass(frozen=True)
class MedidaSeguranca:
    """Uma medida protetiva e o risco concreto que ela cobre."""

    chave: str
    titulo: str
    categoria: str
    # O que a medida faz.
    descricao: str
    # O que aconteceria sem ela — é o que dá sentido à auditoria.
    risco: str
    status: StatusMedida
    # Observação sobre a configuração vigente (por que está ATENCAO/PENDENTE).
    detalhe: str = ""
    # Onde a medida vive no código ou na documentação.
    referencia: str = ""


@dataclass(frozen=True)
class ItemChecklist:
    """Um item do checklist de pré-deploy, auditado contra o código.

    Diferente de ``MedidaSeguranca`` (que descreve o que a plataforma faz), o item de
    checklist descreve o que uma **fonte externa exige** — por isso carrega o ``numero``
    original, para conferência 1:1 contra a lista de origem.
    """

    numero: int
    titulo: str
    # O que a fonte exige.
    exigencia: str
    status: StatusMedida
    # O que o código faz hoje sobre isso, incluindo o que falta.
    situacao: str
    # Chaves de ``MedidaSeguranca`` que sustentam este item (quando há).
    medidas_relacionadas: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PosturaSeguranca:
    """Retrato das medidas protetivas da plataforma num dado momento."""

    medidas: list[MedidaSeguranca] = field(default_factory=list)
    # Checklist de pré-deploy auditado contra o código (fonte externa).
    checklist: list[ItemChecklist] = field(default_factory=list)
    # De onde veio o checklist — mostrado no painel para permitir a conferência.
    checklist_fonte: str = ""

    @property
    def total_ativas(self) -> int:
        return sum(1 for m in self.medidas if m.status is StatusMedida.ATIVA)

    @property
    def total_atencao(self) -> int:
        return sum(1 for m in self.medidas if m.status is StatusMedida.ATENCAO)

    @property
    def total_pendentes(self) -> int:
        return sum(1 for m in self.medidas if m.status is StatusMedida.PENDENTE)

    @property
    def checklist_ok(self) -> int:
        return sum(1 for i in self.checklist if i.status is StatusMedida.ATIVA)

    @property
    def checklist_pendentes(self) -> int:
        """Itens que exigem ação — ``NAO_APLICAVEL`` não conta como dívida."""
        return sum(
            1
            for i in self.checklist
            if i.status in (StatusMedida.ATENCAO, StatusMedida.PENDENTE)
        )

    @property
    def pronto_para_producao(self) -> bool:
        """Só quando nenhuma medida e nenhum item de checklist exige ação."""
        return not self.total_atencao and not self.total_pendentes and not self.checklist_pendentes


# --------------------------------------------------------------------------- #
# Atendimento humano: o assistente passa a conversa para a secretaria (§6j)
# --------------------------------------------------------------------------- #
# Janela da Meta para texto livre: 24h desde a última mensagem do responsável. Passado
# esse prazo, só template aprovado reabre a conversa (§9a).
JANELA_ATENDIMENTO_HORAS = 24


class StatusAtendimentoHumano(str, enum.Enum):
    """Ciclo de um encaminhamento do assistente para a secretaria.

    ``OFERECIDO`` é o estado que separa esta feature de um encaminhamento cego: o
    assistente **pergunta** antes ("quer que eu chame alguém da secretaria?") e só o
    "sim" do responsável leva a ``ABERTO``. Uma oferta ignorada vira ``DESCARTADO`` — e a
    razão entre oferecido e descartado é o termômetro de o assistente estar desistindo
    cedo demais.
    """

    OFERECIDO = "oferecido"
    ABERTO = "aberto"
    EM_ATENDIMENTO = "em_atendimento"
    RESOLVIDO = "resolvido"
    DESCARTADO = "descartado"


# Estados que ocupam a fila da secretaria e silenciam o assistente na conversa.
STATUS_ATENDIMENTO_NA_FILA = (
    StatusAtendimentoHumano.ABERTO,
    StatusAtendimentoHumano.EM_ATENDIMENTO,
)


@dataclass
class AtendimentoHumano:
    """Uma conversa que o assistente entregou a uma pessoa da secretaria (§6j).

    O responsável continua no **mesmo fio de WhatsApp**: a resposta do atendente entra na
    mesma ``Conversa`` (como ``Mensagem`` de autor ``atendente``) e sai pelo número da
    própria escola. Do lado do responsável, não há transferência visível — há alguém
    respondendo melhor.

    ``ultima_mensagem_responsavel_em`` existe para uma razão específica: é dela que sai a
    **janela de 24h** da Meta. Sem esse carimbo, o atendente escreve, a Graph API recusa o
    texto livre e a resposta some sem ninguém notar.
    """

    tenant_id: UUID
    conversa_id: UUID
    contato: str  # E.164 do responsável
    contato_nome: str = ""
    # Resumo escrito pelo próprio assistente — é o que a secretaria lê antes de abrir.
    motivo: str = ""
    status: StatusAtendimentoHumano = StatusAtendimentoHumano.OFERECIDO
    # As duas etapas do gatilho (§6j): a oferta e o "sim" do responsável.
    ofereceu_em: datetime | None = None
    confirmado_em: datetime | None = None
    # Encaminhado com a secretaria fechada: entra na fila do próximo dia útil.
    fora_expediente: bool = False
    atendente_id: UUID | None = None
    atendente_nome: str = ""
    ultima_mensagem_responsavel_em: datetime = field(default_factory=_now)
    assumido_em: datetime | None = None
    resolvido_em: datetime | None = None
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)
    atualizado_em: datetime = field(default_factory=_now)

    @property
    def na_fila(self) -> bool:
        """Ocupa a fila da secretaria — e, portanto, silencia o assistente."""
        return self.status in STATUS_ATENDIMENTO_NA_FILA

    @property
    def janela_expira_em(self) -> datetime:
        """Limite para responder em texto livre (24h da última mensagem do responsável)."""
        return self.ultima_mensagem_responsavel_em + timedelta(
            hours=JANELA_ATENDIMENTO_HORAS
        )

    def janela_aberta(self, agora: datetime | None = None) -> bool:
        return (agora or _now()) < self.janela_expira_em

    def minutos_de_espera(self, agora: datetime | None = None) -> int:
        """Há quanto tempo o responsável aguarda (do encaminhamento até assumir)."""
        fim = self.assumido_em or agora or _now()
        base = self.confirmado_em or self.criado_em
        return max(0, int((fim - base).total_seconds() // 60))


# --------------------------------------------------------------------------- #
# Documentos recebidos dos responsáveis pelo WhatsApp (§6k)
# --------------------------------------------------------------------------- #
class CategoriaDocumento(str, enum.Enum):
    """Para que serve o arquivo que o responsável mandou.

    A sugestão vem da conversa (legenda + contexto), mas **quem confirma é a secretaria**:
    classificar um atestado como "outro" é problema de prontuário, não de UX.
    """

    MATRICULA = "matricula"
    ATESTADO = "atestado"
    COMPROVANTE = "comprovante"
    OUTRO = "outro"


class StatusDocumento(str, enum.Enum):
    RECEBIDO = "recebido"
    PROCESSADO = "processado"
    # Ilegível, duplicado ou fora de propósito. Mantém o registro de que chegou.
    DESCARTADO = "descartado"
    # Veio de um número **sem cadastro** na escola. Fica fora da fila de trabalho, mas o
    # arquivo é guardado: pode ser um pai que trocou de número, e descartá-lo de saída
    # perderia o documento de quem mais precisa dele. A secretaria decide o que é.
    QUARENTENA = "quarentena"


@dataclass
class DocumentoLido:
    """O que a leitura por IA extraiu de um documento (§4.3). Tudo **sugestão**.

    ``campos_ficha`` só vem preenchido quando o documento é uma ficha de matrícula — aí
    ele alimenta o mesmo fluxo de revisão do §D3, em vez de a secretaria redigitar a ficha
    inteira a partir da foto.
    """

    categoria: CategoriaDocumento | None = None
    aluno_nome: str = ""
    resumo: str = ""
    campos_ficha: dict = field(default_factory=dict)
    # Erro amigável quando o modelo não conseguiu ler. Não é exceção: documento ilegível é
    # resultado normal, e a tela precisa dizer isso sem parecer falha do sistema.
    erro: str = ""

    @property
    def vazio(self) -> bool:
        return not (self.categoria or self.aluno_nome or self.resumo or self.campos_ficha)


@dataclass
class NumeroBloqueado:
    """Número cuja **mídia** é recusada no inbound (§6k, anti-spam).

    Bloqueia o arquivo, **não a pessoa**: o número segue sendo atendido em texto, e o
    remetente é avisado. O inbound é público — quem descobre o número da escola manda o
    que quiser —, mas silenciar alguém por completo com base num contador é o erro que o
    produto existe para evitar.
    """

    tenant_id: UUID
    telefone: str  # E.164
    motivo: str = ""
    bloqueado_por: str = ""  # nome de quem bloqueou (auditoria já guarda o resto)
    id: UUID = field(default_factory=_new_id)
    bloqueado_em: datetime = field(default_factory=_now)


@dataclass
class SugestaoBloqueio:
    """Número que cruzou o limiar de descartes e **merece uma olhada** (decisão C).

    A sugestão é o produto final: o bloqueio automático é perigoso aqui — um pai que manda
    três fotos tremidas do mesmo atestado é indistinguível de spam para um contador, e
    bloqueá-lo em silêncio é exatamente a falha que o produto existe para evitar.
    """

    telefone: str
    descartados: int
    contato_nome: str = ""
    ultimo_em: datetime | None = None


# Limiar da sugestão de bloqueio (decisão C do plano de 10/08): três documentos
# descartados do mesmo número em sete dias. Números redondos e explicáveis à secretaria —
# não há dado para calibrar melhor, e fingir precisão seria pior.
DESCARTES_PARA_SUGERIR_BLOQUEIO = 3
JANELA_DESCARTES_DIAS = 7


# Só o que a secretaria consegue de fato usar. Áudio fica de fora: sem transcrição, é um
# arquivo que alguém precisa parar para ouvir — o oposto do que a feature promete.
MIMES_ACEITOS = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
)

# Foto do aluno: só imagem, e um teto bem menor que o dos documentos. Uma foto 3x4 não
# passa de alguns megabytes, e aceitar PDF aqui só criaria "foto" que a tela não exibe.
MIMES_FOTO = frozenset({"image/jpeg", "image/png", "image/webp"})
TAMANHO_MAXIMO_FOTO = 5 * 1024 * 1024

# Teto por arquivo. A Meta já limita a mídia, mas o teto aqui é nosso: protege o banco e
# deixa o limite explícito em vez de herdado.
TAMANHO_MAXIMO_DOCUMENTO = 16 * 1024 * 1024


@dataclass(frozen=True)
class ArquivoBaixado:
    """Bytes de uma mídia recuperada do canal, com o que se sabe sobre ela."""

    conteudo: bytes
    mime: str
    nome: str = ""

    @property
    def tamanho(self) -> int:
        return len(self.conteudo)


@dataclass
class DocumentoRecebido:
    """Arquivo que um responsável enviou pelo WhatsApp (§6k).

    Nasce da dor de época de matrícula: hoje o documento chega no celular de alguém da
    secretaria e vira responsabilidade pessoal daquela pessoa — se ela falta, o documento
    some. Aqui ele fica no tenant, ligado à conversa que o originou.

    **Dado sensível de menor.** Um atestado médico é dado de saúde de criança (LGPD arts.
    11 e 14), e é por isso que este registro guarda `expira_em` desde o nascimento: sem
    prazo, um bucket de atestados vira passivo permanente. O conteúdo nunca mora aqui —
    `chave_storage` aponta para o `ArquivoStorage`, que é trocável.
    """

    tenant_id: UUID
    conversa_id: UUID
    contato: str  # E.164 de quem enviou
    chave_storage: str
    mime: str
    tamanho: int
    nome_arquivo: str = ""
    contato_nome: str = ""
    # Legenda que o responsável escreveu junto do arquivo — costuma ser o único contexto
    # ("atestado do João, faltou terça").
    observacao: str = ""
    categoria: CategoriaDocumento = CategoriaDocumento.OUTRO
    # Palpite do assistente a partir da legenda/conversa, guardado à parte da categoria
    # confirmada: serve para pré-selecionar no painel sem se passar por decisão humana.
    categoria_sugerida: CategoriaDocumento | None = None
    status: StatusDocumento = StatusDocumento.RECEBIDO
    aluno_id: UUID | None = None
    aluno_nome: str = ""
    atendimento_id: UUID | None = None
    # Id da mídia na Meta: identifica a origem e deduplica reentrega do webhook.
    media_id: str = ""
    expira_em: datetime | None = None
    processado_em: datetime | None = None
    id: UUID = field(default_factory=_new_id)
    criado_em: datetime = field(default_factory=_now)

    @property
    def eh_imagem(self) -> bool:
        return self.mime.startswith("image/")

    def expirado(self, agora: datetime | None = None) -> bool:
        return self.expira_em is not None and (agora or _now()) >= self.expira_em

    @property
    def tamanho_legivel(self) -> str:
        if self.tamanho < 1024:
            return f"{self.tamanho} B"
        if self.tamanho < 1024 * 1024:
            return f"{self.tamanho / 1024:.0f} KB"
        return f"{self.tamanho / (1024 * 1024):.1f} MB"
