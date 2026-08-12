"""A conversa como **sessão**, não como fio eterno (§13, Fase 3 do plano de 10/08).

Havia uma ``Conversa`` por ``(tenant, contato)``, para sempre. O sintoma visível era o
histórico ilegível; o caro era invisível: **o contexto enviado à LLM crescia sem limite**,
carregando meses de assunto encerrado a cada mensagem nova.

O que se testa aqui é o recorte — quando a sessão continua, quando ela vira outra, e o que
não pode vazar de uma para a outra.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.application.atendimento_humano_use_cases import ResolverAtendimento
from app.application.use_cases import AtenderConversa, RecuperarEEnviarDocumento
from app.domain.entities import (
    AtendimentoHumano,
    Conversa,
    Papel,
    StatusAtendimentoHumano,
    Usuario,
)
from tests.fakes import (
    FakeAtendimentoHumanoRepo,
    FakeChannel,
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()
CONTATO = "+5515999998888"
SEGUNDA_10H = datetime(2026, 8, 10, 13, 0, tzinfo=timezone.utc)


# --------------------------- o recorte da sessão --------------------------- #
def test_conversa_nasce_viva_e_com_a_janela_aberta():
    conversa = Conversa(tenant_id=TENANT, contato=CONTATO, ultima_mensagem_em=SEGUNDA_10H)
    assert conversa.encerrada is False
    assert conversa.vencida_em(SEGUNDA_10H + timedelta(hours=23), janela_horas=24) is False


def test_conversa_vence_depois_da_janela():
    conversa = Conversa(tenant_id=TENANT, contato=CONTATO, ultima_mensagem_em=SEGUNDA_10H)
    assert conversa.vencida_em(SEGUNDA_10H + timedelta(hours=25), janela_horas=24) is True


def test_janela_zero_devolve_a_conversa_eterna():
    """A válvula de escape: 0 desliga o recorte. Existe, mas não é o caminho."""
    conversa = Conversa(tenant_id=TENANT, contato=CONTATO, ultima_mensagem_em=SEGUNDA_10H)
    assert conversa.vencida_em(SEGUNDA_10H + timedelta(days=365), janela_horas=0) is False


async def test_mesma_sessao_dentro_da_janela():
    repo = FakeConversaRepo()
    repo.agora = SEGUNDA_10H
    primeira = await repo.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)

    repo.agora = SEGUNDA_10H + timedelta(hours=3)
    segunda = await repo.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)

    assert segunda.id == primeira.id


async def test_mensagem_depois_da_janela_abre_outra_sessao():
    repo = FakeConversaRepo()
    repo.agora = SEGUNDA_10H
    primeira = await repo.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)

    repo.agora = SEGUNDA_10H + timedelta(hours=30)
    segunda = await repo.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)

    assert segunda.id != primeira.id
    # A anterior é encerrada, não apagada: o histórico dela continua consultável.
    assert primeira.encerrada is True
    assert len(repo.sessoes) == 2


async def test_conversa_ativa_o_dia_todo_nao_vence_no_meio_do_assunto():
    """A janela conta da ÚLTIMA mensagem, não da primeira — senão uma conversa que dura
    a tarde inteira se partiria ao meio."""
    repo = FakeConversaRepo()
    repo.agora = SEGUNDA_10H
    conversa = await repo.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)

    for hora in (20, 40, 60):
        repo.agora = SEGUNDA_10H + timedelta(hours=hora)
        await repo.adicionar_mensagem(
            conversa_id=conversa.id, autor="usuario", texto="continuo aqui"
        )
        atual = await repo.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
        assert atual.id == conversa.id


async def test_sessoes_de_responsaveis_diferentes_nao_se_misturam():
    repo = FakeConversaRepo()
    a = await repo.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    b = await repo.obter_ou_criar(tenant_id=TENANT, contato="+5515999997777")
    assert a.id != b.id


async def test_mesmo_telefone_em_escolas_diferentes_sao_sessoes_diferentes():
    repo = FakeConversaRepo()
    a = await repo.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    b = await repo.obter_ou_criar(tenant_id=uuid.uuid4(), contato=CONTATO)
    assert a.id != b.id


async def test_encerrar_e_idempotente():
    repo = FakeConversaRepo()
    repo.agora = SEGUNDA_10H
    conversa = await repo.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)

    await repo.encerrar(conversa_id=conversa.id)
    primeira_data = conversa.encerrada_em
    repo.agora = SEGUNDA_10H + timedelta(hours=5)
    await repo.encerrar(conversa_id=conversa.id)

    assert conversa.encerrada_em == primeira_data


# --------------------- o que a LLM recebe (o ponto caro) ------------------- #
def _atender(conversas: FakeConversaRepo, llm: FakeLLM) -> AtenderConversa:
    return AtenderConversa(
        conversas=conversas,
        embedder=fake_embedder(),
        store=FakeVectorStore(),
        llm=llm,
        documentos=RecuperarEEnviarDocumento(
            source=FakeDocumentSource([]), canal=FakeChannel()
        ),
        mesa=None,
    )


async def test_o_assunto_da_sessao_antiga_nao_entra_no_contexto_da_nova():
    """É o custo invisível: sem o recorte, o modelo responde sobre a matrícula de março
    quando perguntam do uniforme de agosto — e ainda se paga por esse contexto."""
    conversas = FakeConversaRepo()
    llm = FakeLLM()
    uc = _atender(conversas, llm)

    conversas.agora = SEGUNDA_10H
    await uc.executar(tenant_id=TENANT, contato=CONTATO, texto="dúvida sobre a matrícula")

    conversas.agora = SEGUNDA_10H + timedelta(days=30)
    await uc.executar(tenant_id=TENANT, contato=CONTATO, texto="e o uniforme?")

    ultimo_contexto = " ".join(t.texto or "" for t in llm.turnos_recebidos[-1])
    assert "uniforme" in ultimo_contexto
    assert "matrícula" not in ultimo_contexto


async def test_o_contexto_da_mesma_sessao_e_preservado():
    """O recorte não pode custar a memória de curto prazo: dentro da sessão, o modelo
    precisa lembrar do que foi dito."""
    conversas = FakeConversaRepo()
    llm = FakeLLM()
    uc = _atender(conversas, llm)

    conversas.agora = SEGUNDA_10H
    await uc.executar(tenant_id=TENANT, contato=CONTATO, texto="quero falar do uniforme")
    conversas.agora = SEGUNDA_10H + timedelta(hours=2)
    await uc.executar(tenant_id=TENANT, contato=CONTATO, texto="qual a cor?")

    ultimo_contexto = " ".join(t.texto or "" for t in llm.turnos_recebidos[-1])
    assert "uniforme" in ultimo_contexto


# ------------------- resolver o atendimento encerra a sessão ---------------- #
async def test_resolver_atendimento_encerra_a_sessao():
    conversas = FakeConversaRepo()
    conversas.agora = SEGUNDA_10H
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    atendimentos = FakeAtendimentoHumanoRepo()
    atendimento = await atendimentos.criar(
        AtendimentoHumano(
            tenant_id=TENANT,
            conversa_id=conversa.id,
            contato=CONTATO,
            status=StatusAtendimentoHumano.ABERTO,
        )
    )
    atendente = Usuario(
        nome="Secretaria", email="s@escola.test", senha_hash="x",
        papel=Papel.TENANT_ADMIN, tenant_id=TENANT,
    )

    await ResolverAtendimento(atendimentos=atendimentos, conversas=conversas).executar(
        tenant_id=TENANT, atendimento_id=atendimento.id, usuario=atendente
    )

    assert conversa.encerrada is True
    # E a próxima mensagem do responsável abre uma sessão nova, no mesmo minuto.
    nova = await conversas.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    assert nova.id != conversa.id


async def test_resolver_sem_repositorio_de_conversa_nao_quebra():
    """Encerrar é efeito colateral; o caso de uso segue utilizável sem ele."""
    conversas = FakeConversaRepo()
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    atendimentos = FakeAtendimentoHumanoRepo()
    atendimento = await atendimentos.criar(
        AtendimentoHumano(
            tenant_id=TENANT,
            conversa_id=conversa.id,
            contato=CONTATO,
            status=StatusAtendimentoHumano.ABERTO,
        )
    )
    atendente = Usuario(
        nome="Secretaria", email="s@escola.test", senha_hash="x",
        papel=Papel.TENANT_ADMIN, tenant_id=TENANT,
    )

    resolvido = await ResolverAtendimento(atendimentos=atendimentos).executar(
        tenant_id=TENANT, atendimento_id=atendimento.id, usuario=atendente
    )

    assert resolvido.status is StatusAtendimentoHumano.RESOLVIDO
    assert conversa.encerrada is False
