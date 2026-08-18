"""Retomada de disparos travados pela cota diária (§9a-quinquies).

O teto real da Meta são 250 destinatários únicos por 24h no portfólio. Uma escola de 600
responsáveis não cabe num dia, e até 15/ago/2026 "espera a próxima janela" significava
alguém lembrar de re-disparar à mão — na prática, metade da escola sem o aviso.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.application.retomada_use_cases import RetomarBroadcastsPendentes
from app.infrastructure.retomada import RetomadorDeDisparos
from app.application.use_cases import EnviarBroadcast
from app.domain.entities import (
    Broadcast,
    CategoriaTemplate,
    DestinatarioBroadcast,
    MessageTemplate,
    StatusBroadcast,
    StatusEntrega,
    JanelaDeExecucao,
    StatusTemplate,
    TemplateNaWaba,
)
from tests.fakes import (
    WABA_PADRAO_ID,
    FakeBroadcastRepo,
    FakeChannel,
    FakeQuota,
    FakeRateLimiter,
    FakeTemplateRepo,
)

pytestmark = pytest.mark.asyncio

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


def _template(tenant_id=TENANT) -> MessageTemplate:
    return MessageTemplate(
        tenant_id=tenant_id,
        nome="aviso_geral",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}! {{2}}",
        wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
    )


def _broadcast(template, *, n: int, tenant_id=TENANT, dias_atras: int = 0) -> Broadcast:
    return Broadcast(
        tenant_id=tenant_id,
        template_id=template.id,
        titulo="Reunião de pais",
        status=StatusBroadcast.PARCIAL_LIMITE,
        criado_em=datetime.now(timezone.utc) - timedelta(days=dias_atras),
        destinatarios=[
            DestinatarioBroadcast(contato=f"+551190000{i:04d}", parametros=["Ana", "oi"])
            for i in range(n)
        ],
    )


class _RepoRetomavel(FakeBroadcastRepo):
    """Guarda os broadcasts e responde `listar_retomaveis` como o SQL responderia."""

    def __init__(self, *broadcasts: Broadcast) -> None:
        super().__init__()
        self.guardados = list(broadcasts)

    async def listar_retomaveis(self, *, desde):
        return sorted(
            (
                b
                for b in self.guardados
                if b.status is StatusBroadcast.PARCIAL_LIMITE and b.criado_em >= desde
            ),
            key=lambda b: b.criado_em,
        )


def _retomada(repo, template, *, limite: int, janela_dias: int = 7):
    canal = FakeChannel()
    enviar = EnviarBroadcast(
        broadcasts=repo,
        templates=FakeTemplateRepo(template),
        canal=canal,
        quota=FakeQuota(limite_diario=limite),
        rate_limiter=FakeRateLimiter(),
    )
    uc = RetomarBroadcastsPendentes(
        broadcasts=repo, enviar=enviar, janela_dias=janela_dias
    )
    return uc, canal


async def test_retoma_de_onde_parou_sem_reenviar_para_quem_ja_recebeu():
    """A idempotência já existia em `EnviarBroadcast`; faltava alguém chamá-lo de novo."""
    template = _template()
    broadcast = _broadcast(template, n=5)
    # Três já saíram na janela de ontem.
    for dest in broadcast.destinatarios[:3]:
        dest.status = StatusEntrega.ENVIADO

    uc, canal = _retomada(_RepoRetomavel(broadcast), template, limite=100)
    resultado = await uc.executar()

    assert resultado.broadcasts == 1
    assert resultado.enviados == 2  # só os que faltavam
    assert len(canal.enviados) == 2
    assert broadcast.status is StatusBroadcast.CONCLUIDO


async def test_cota_ainda_curta_deixa_o_resto_para_a_proxima_janela():
    template = _template()
    broadcast = _broadcast(template, n=5)
    uc, canal = _retomada(_RepoRetomavel(broadcast), template, limite=2)
    resultado = await uc.executar()

    assert resultado.enviados == 2
    assert resultado.ainda_bloqueados == 3
    assert broadcast.status is StatusBroadcast.PARCIAL_LIMITE  # volta para a fila


def _duas_escolas(quota):
    """Duas escolas com broadcast pendente, a maior mais antiga (retomada primeiro)."""
    template_a = _template()
    template_b = _template(tenant_id=OUTRO_TENANT)
    grande = _broadcast(template_a, n=5, dias_atras=2)
    pequeno = _broadcast(template_b, n=1, tenant_id=OUTRO_TENANT, dias_atras=1)
    repo = _RepoRetomavel(grande, pequeno)

    class _TemplatesPorTenant:
        async def obter(self, *, tenant_id, template_id):
            for t in (template_a, template_b):
                if t.id == template_id:
                    return t
            return None

    enviar = EnviarBroadcast(
        broadcasts=repo,
        templates=_TemplatesPorTenant(),
        canal=FakeChannel(),
        quota=quota,
        rate_limiter=FakeRateLimiter(),
    )
    return RetomarBroadcastsPendentes(broadcasts=repo, enviar=enviar), grande, pequeno


async def test_escolas_do_mesmo_portfolio_dividem_o_teto():
    """O teto é do portfólio, não da escola — e uma escola grande consome o das outras.

    Era o contrário até 17/ago/2026, e não por decisão nossa: a Meta passou a medir o
    limite no Business Account em out/2025. Enquanto contávamos por escola, cinco escolas
    de teste acreditavam ter 1250 de capacidade e a Graph API recusava na 251ª — o painel
    dizia "enviado" para uma mensagem que não saiu.
    """
    uc, grande, pequeno = _duas_escolas(FakeQuota(limite_diario=2))
    resultado = await uc.executar()

    assert resultado.broadcasts == 2
    assert grande.status is StatusBroadcast.PARCIAL_LIMITE
    # A pequena não passa: a grande chegou antes e levou as duas vagas do portfólio.
    assert pequeno.status is StatusBroadcast.PARCIAL_LIMITE
    assert resultado.enviados == 2


async def test_escolas_de_portfolios_diferentes_nao_se_atrapalham():
    """Portfólios distintos têm tetos distintos — a fila não pode confundi-los.

    É o que sobra do princípio antigo ("uma escola grande não cala as demais"): ele
    continua valendo, só que a fronteira é o portfólio, não a escola.
    """
    quota = FakeQuota(
        limite_diario=2, portfolios={TENANT: "portfolio-a", OUTRO_TENANT: "portfolio-b"}
    )
    uc, grande, pequeno = _duas_escolas(quota)
    resultado = await uc.executar()

    assert resultado.broadcasts == 2
    assert grande.status is StatusBroadcast.PARCIAL_LIMITE  # estourou o teto do A
    assert pequeno.status is StatusBroadcast.CONCLUIDO  # o teto do B estava inteiro


async def test_disparo_vencido_nao_e_retomado():
    """Aviso de três semanas atrás entregue hoje é pior que aviso não entregue."""
    template = _template()
    antigo = _broadcast(template, n=3, dias_atras=30)
    uc, canal = _retomada(_RepoRetomavel(antigo), template, limite=100)
    resultado = await uc.executar()

    assert resultado.broadcasts == 0
    assert canal.enviados == []


async def test_broadcast_com_erro_nao_trava_a_fila():
    """Template desmentido numa escola não pode impedir o aviso da escola seguinte."""
    template = _template()
    quebrado = _broadcast(template, n=1, dias_atras=2)
    quebrado.template_id = uuid.uuid4()  # template que não existe → ValueError
    bom = _broadcast(template, n=1, dias_atras=1)

    repo = _RepoRetomavel(quebrado, bom)
    uc, canal = _retomada(repo, template, limite=100)
    resultado = await uc.executar()

    assert resultado.broadcasts == 1
    assert resultado.enviados == 1
    assert bom.status is StatusBroadcast.CONCLUIDO


async def test_sem_pendencia_nao_faz_nada():
    template = _template()
    resultado, _ = _retomada(_RepoRetomavel(), template, limite=100)
    assert (await resultado.executar()).broadcasts == 0


SP = ZoneInfo("America/Sao_Paulo")


async def test_tarefa_nao_abre_sessao_fora_dos_horarios():
    """O comportamento pelo qual estamos pagando: fora da grade, zero acesso ao banco.

    Um intervalo fixo de 30 min abria sessão 48 vezes por dia, o que mantinha o Postgres
    serverless acordado 24/7 — e o custo aparecia na fatura, não no log.
    """
    aberturas = []

    def _sessionmaker():
        aberturas.append(1)
        raise AssertionError("não deveria abrir sessão fora dos horários")

    # Sábado de manhã: a próxima passada só na segunda às 7h.
    retomador = RetomadorDeDisparos(
        _sessionmaker,
        montar=lambda s: None,
        janela=JanelaDeExecucao(),
        agora=lambda: datetime(2026, 8, 15, 10, 0, tzinfo=SP),
    )
    retomador.iniciar()
    await asyncio.sleep(0.05)  # tempo de sobra para o laço rodar várias voltas
    await retomador.parar()

    assert aberturas == []


async def test_cutucao_drena_sem_esperar_o_horario():
    """O disparo manual não pode esperar a grade.

    A grade existe para o que a **máquina** decide reenviar; segurar até 12h30 um aviso
    que a secretaria acabou de mandar às 8h seria usar a proteção contra o usuário dela.
    """
    passadas = []

    class _SessaoFalsa:
        async def __aenter__(self):
            passadas.append(1)
            raise RuntimeError("basta contar a passada")

        async def __aexit__(self, *a):
            return False

    # Sábado: a grade só voltaria na segunda às 7h.
    retomador = RetomadorDeDisparos(
        lambda: _SessaoFalsa(),
        montar=lambda s: None,
        janela=JanelaDeExecucao(),
        agora=lambda: datetime(2026, 8, 15, 10, 0, tzinfo=SP),
    )
    retomador.iniciar()
    await asyncio.sleep(0.02)
    assert passadas == []  # dormindo, como esperado

    retomador.cutucar()
    await asyncio.sleep(0.02)
    await retomador.parar()

    assert passadas == [1]  # acordou na hora, e uma vez só


async def test_broadcast_agendado_vencido_entra_na_fila():
    """Era funcionalidade morta: o disparo com `agendado_para` ganhava o status AGENDADO
    e nenhum código voltava para executá-lo — a tela prometia o que nunca acontecia."""
    template = _template()
    vencido = _broadcast(template, n=2)
    vencido.status = StatusBroadcast.AGENDADO
    vencido.agendado_para = datetime.now(timezone.utc) - timedelta(hours=1)

    futuro = _broadcast(template, n=2)
    futuro.status = StatusBroadcast.AGENDADO
    futuro.agendado_para = datetime.now(timezone.utc) + timedelta(days=1)

    class _RepoComAgendados(_RepoRetomavel):
        async def listar_retomaveis(self, *, desde):
            agora = datetime.now(timezone.utc)
            return [
                b
                for b in self.guardados
                if b.criado_em >= desde
                and (
                    b.status is StatusBroadcast.PARCIAL_LIMITE
                    or (
                        b.status is StatusBroadcast.AGENDADO
                        and b.agendado_para is not None
                        and b.agendado_para <= agora
                    )
                )
            ]

    repo = _RepoComAgendados(vencido, futuro)
    uc, canal = _retomada(repo, template, limite=100)
    resultado = await uc.executar()

    assert resultado.broadcasts == 1  # só o vencido
    assert vencido.status is StatusBroadcast.CONCLUIDO
    assert futuro.status is StatusBroadcast.AGENDADO  # a hora dele não chegou
    assert len(canal.enviados) == 2
