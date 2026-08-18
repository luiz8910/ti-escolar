"""Testa o outbound: cota diária (tier Meta), template aprovado e falhas parciais."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.application.use_cases import EnviarBroadcast
from app.domain.entities import (
    Broadcast,
    CategoriaTemplate,
    DestinatarioBroadcast,
    MessageTemplate,
    StatusBroadcast,
    StatusEntrega,
    StatusTemplate,
    TemplateNaWaba,
    Tenant,
)
from tests.fakes import (
    FakeBroadcastRepo,
    FakeChannel,
    FakeQuota,
    FakeRateLimiter,
    FakeTemplateRepo,
    WABA_PADRAO_ID,
)

TENANT = uuid.uuid4()


def _template(status=StatusTemplate.APROVADO) -> MessageTemplate:
    return MessageTemplate(
        tenant_id=TENANT,
        nome="aviso",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}!",
        wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=status)],
    )


def _broadcast(n: int) -> Broadcast:
    template = _template()
    dests = [
        DestinatarioBroadcast(contato=f"+5511{i:09d}", parametros=["Maria"]) for i in range(n)
    ]
    return Broadcast(tenant_id=TENANT, template_id=template.id, titulo="t", destinatarios=dests)


def _uc(template, *, limite, falhar_em=None):
    return (
        EnviarBroadcast(
            broadcasts=FakeBroadcastRepo(),
            templates=FakeTemplateRepo(template),
            canal=FakeChannel(falhar_em=falhar_em),
            quota=FakeQuota(limite_diario=limite),
            rate_limiter=FakeRateLimiter(),
        ),
    )[0]


async def test_template_nao_aprovado_falha():
    template = _template(StatusTemplate.PENDENTE)
    broadcast = _broadcast(1)
    broadcast.template_id = template.id
    uc = _uc(template, limite=1000)
    with pytest.raises(ValueError, match="APROVADO"):
        await uc.executar(broadcast=broadcast)


async def test_respeita_limite_diario_e_marca_parcial():
    template = _template()
    broadcast = _broadcast(5)
    broadcast.template_id = template.id
    uc = _uc(template, limite=3)  # só 3 cabem hoje

    resultado = await uc.executar(broadcast=broadcast)

    assert resultado.enviados == 3
    assert resultado.bloqueados_por_limite == 2
    assert resultado.status == StatusBroadcast.PARCIAL_LIMITE
    assert resultado.restante_cota == 0
    pendentes = [d for d in broadcast.destinatarios if d.status == StatusEntrega.PENDENTE]
    assert len(pendentes) == 2  # ficam para a próxima janela


async def test_envio_completo_dentro_da_cota():
    template = _template()
    broadcast = _broadcast(2)
    broadcast.template_id = template.id
    uc = _uc(template, limite=-1)  # ilimitado

    resultado = await uc.executar(broadcast=broadcast)

    assert resultado.enviados == 2
    assert resultado.bloqueados_por_limite == 0
    assert resultado.status == StatusBroadcast.CONCLUIDO


async def test_falha_de_envio_nao_derruba_lote():
    template = _template()
    broadcast = _broadcast(3)
    broadcast.template_id = template.id
    alvo = broadcast.destinatarios[1].contato
    uc = _uc(template, limite=1000, falhar_em={alvo})

    resultado = await uc.executar(broadcast=broadcast)

    assert resultado.enviados == 2
    assert resultado.falhas == 1
    assert resultado.status == StatusBroadcast.CONCLUIDO


class _TenantRepoDeUmaConta:
    def __init__(self, tenant: Tenant) -> None:
        self._tenant = tenant

    async def obter(self, tenant_id):
        return self._tenant if tenant_id == self._tenant.id else None


@pytest.mark.asyncio
async def test_template_aprovado_em_outra_conta_nao_dispara():
    """A falha que o status numa coluna só escondia (§9e.3).

    O template está aprovado — mas na conta onde estão *as outras* escolas. Para o número
    desta, ele não existe: a Graph API recusaria depois de a trava já ter dado o aval.
    """
    outra_conta = uuid.uuid4()
    template = _template()  # aprovado na WABA_PADRAO_ID
    escola = Tenant(
        id=TENANT, nome="EM Rosa Cury", slug="rosacury", waba_id=outra_conta
    )
    broadcast = Broadcast(
        tenant_id=TENANT,
        template_id=template.id,
        titulo="Aviso",
        destinatarios=[DestinatarioBroadcast(contato="+5511900000001")],
    )
    canal = FakeChannel()
    with pytest.raises(ValueError, match="conta do WhatsApp"):
        await EnviarBroadcast(
            broadcasts=FakeBroadcastRepo(),
            templates=FakeTemplateRepo(template),
            canal=canal,
            quota=FakeQuota(limite_diario=100),
            rate_limiter=FakeRateLimiter(),
            tenants=_TenantRepoDeUmaConta(escola),
        ).executar(broadcast=broadcast)
    assert canal.enviados == []


@pytest.mark.asyncio
async def test_template_aprovado_na_conta_da_escola_dispara():
    template = _template()
    escola = Tenant(
        id=TENANT, nome="EM Rosa Cury", slug="rosacury", waba_id=WABA_PADRAO_ID
    )
    broadcast = Broadcast(
        tenant_id=TENANT,
        template_id=template.id,
        titulo="Aviso",
        destinatarios=[DestinatarioBroadcast(contato="+5511900000001")],
    )
    resultado = await EnviarBroadcast(
        broadcasts=FakeBroadcastRepo(),
        templates=FakeTemplateRepo(template),
        canal=FakeChannel(),
        quota=FakeQuota(limite_diario=100),
        rate_limiter=FakeRateLimiter(),
        tenants=_TenantRepoDeUmaConta(escola),
    ).executar(broadcast=broadcast)
    assert resultado.enviados == 1


@pytest.mark.asyncio
async def test_falha_de_envio_guarda_o_motivo():
    """Sem o motivo, o painel diz "Falhou" e a causa não existe em lugar nenhum.

    Foi o que aconteceu no primeiro disparo real: dois destinatários falharam porque o
    template não existia na conta, e descobrir isso exigiu consultar a Graph API à mão.
    """
    template = _template()
    broadcast = Broadcast(
        tenant_id=TENANT,
        template_id=template.id,
        titulo="Aviso",
        destinatarios=[DestinatarioBroadcast(contato="+5511900000001", parametros=["Ana"])],
    )
    canal = FakeChannel(falhar_em={"+5511900000001"})
    resultado = await EnviarBroadcast(
        broadcasts=FakeBroadcastRepo(),
        templates=FakeTemplateRepo(template),
        canal=canal,
        quota=FakeQuota(limite_diario=100),
        rate_limiter=FakeRateLimiter(),
    ).executar(broadcast=broadcast)

    assert resultado.falhas == 1
    assert broadcast.destinatarios[0].status is StatusEntrega.FALHOU
    assert "template inexistente na conta" in broadcast.destinatarios[0].erro


# --------------------------------------------------------------------------- #
# Janela de 24h corridas, no portfólio (§9e.3)
# --------------------------------------------------------------------------- #
async def test_mesmo_responsavel_duas_vezes_consome_uma_vaga():
    """A Meta cobra **cliente único** na janela, não mensagem enviada.

    Um responsável com dois filhos aparece duas vezes na lista da turma. Contando por
    mensagem, uma escola com muitos irmãos batia no teto antes da hora e o aviso ficava
    pela metade sem que nenhuma capacidade real tivesse sido gasta.
    """
    template = _template()
    repetido = "+5511900000001"
    broadcast = Broadcast(
        tenant_id=TENANT,
        template_id=template.id,
        titulo="Reunião",
        destinatarios=[
            DestinatarioBroadcast(contato=repetido, parametros=["Ana"]),
            DestinatarioBroadcast(contato=repetido, parametros=["Bruno"]),
            DestinatarioBroadcast(contato="+5511900000002", parametros=["Carla"]),
        ],
    )
    uc = _uc(template, limite=2)

    resultado = await uc.executar(broadcast=broadcast)

    # Três mensagens saem, mas só duas vagas são consumidas — cabe no teto de 2.
    assert resultado.enviados == 3
    assert resultado.bloqueados_por_limite == 0
    assert resultado.status is StatusBroadcast.CONCLUIDO


async def test_envio_fora_da_janela_de_24h_nao_conta():
    """Passadas 24 horas, a vaga volta sozinha — é o que "próxima janela" quer dizer."""
    quota = FakeQuota(limite_diario=1)
    # Um envio de 25 horas atrás já saiu da janela; um de 23 ainda ocupa vaga.
    agora = datetime.now(timezone.utc)
    quota.envios.append(("", "+5511911111111", agora - timedelta(hours=25)))

    cota = await quota.cota(TENANT)
    assert cota.enviados == 0
    assert cota.restante == 1
    assert cota.proxima_liberacao is None  # nada na janela para liberar

    quota.envios.append(("", "+5511922222222", agora - timedelta(hours=23)))
    cota = await quota.cota(TENANT)
    assert cota.enviados == 1
    assert cota.restante == 0
    # A vaga volta uma hora à frente, não à meia-noite.
    assert cota.proxima_liberacao is not None
    assert timedelta(minutes=50) < (cota.proxima_liberacao - agora) < timedelta(minutes=70)


async def test_duas_escolas_do_mesmo_portfolio_somam_no_mesmo_teto():
    """O teto é do Business Account, compartilhado por todos os números abaixo dele.

    Enquanto a conta era por escola, cadastrar cinco escolas de teste dava a impressão de
    1250 de capacidade — e a recusa vinha da Graph API, depois de o painel dizer que o
    disparo tinha saído.
    """
    outra_escola = uuid.uuid4()
    template = _template()
    quota = FakeQuota(limite_diario=3)  # portfólio único: ambas caem no balde ""

    await quota.registrar_envio(outra_escola, "+5511933333331")
    await quota.registrar_envio(outra_escola, "+5511933333332")

    broadcast = _broadcast(3)
    broadcast.template_id = template.id
    resultado = await EnviarBroadcast(
        broadcasts=FakeBroadcastRepo(),
        templates=FakeTemplateRepo(template),
        canal=FakeChannel(),
        quota=quota,
        rate_limiter=FakeRateLimiter(),
    ).executar(broadcast=broadcast)

    # Sobrava uma vaga das três; as outras duas foram da escola vizinha.
    assert resultado.enviados == 1
    assert resultado.bloqueados_por_limite == 2
    assert resultado.status is StatusBroadcast.PARCIAL_LIMITE


# --------------------------------------------------------------------------- #
# Fila: reenvio de falha transitória (§9a-septies)
# --------------------------------------------------------------------------- #
async def test_falha_transitoria_volta_para_a_fila_em_vez_de_virar_falha():
    """Timeout e 5xx passam — desistir na primeira perde o aviso por nada.

    A escola acredita ter mandado; o responsável não recebeu; e não há nada a fazer,
    porque o destinatário está marcado como FALHOU e ninguém volta nele.
    """
    template = _template()
    broadcast = _broadcast(3)
    broadcast.template_id = template.id
    instavel = broadcast.destinatarios[1].contato
    uc = EnviarBroadcast(
        broadcasts=FakeBroadcastRepo(),
        templates=FakeTemplateRepo(template),
        canal=FakeChannel(transitorio_em={instavel}),
        quota=FakeQuota(limite_diario=100),
        rate_limiter=FakeRateLimiter(),
    )

    resultado = await uc.executar(broadcast=broadcast)

    assert resultado.enviados == 2
    assert resultado.falhas == 0  # não é falha: é "ainda não"
    assert resultado.reenfileirados == 1
    # PARCIAL_LIMITE é o estado "volta para a fila" — é o que a retomada procura.
    assert resultado.status is StatusBroadcast.PARCIAL_LIMITE
    pendente = broadcast.destinatarios[1]
    assert pendente.status is StatusEntrega.PENDENTE
    assert pendente.tentativas == 1


async def test_falha_definitiva_nao_e_retentada():
    """Template inexistente dá o mesmo erro na segunda tentativa — e cada repetição
    gasta cota e derruba a qualidade do número, que é o que trava a subida do tier."""
    template = _template()
    broadcast = _broadcast(2)
    broadcast.template_id = template.id
    alvo = broadcast.destinatarios[0].contato
    uc = _uc(template, limite=100, falhar_em={alvo})

    resultado = await uc.executar(broadcast=broadcast)

    assert resultado.falhas == 1
    assert resultado.reenfileirados == 0
    assert broadcast.destinatarios[0].status is StatusEntrega.FALHOU
    assert broadcast.destinatarios[0].tentativas == 0  # nem contou: não vai tentar


async def test_reenvio_desiste_no_teto_de_tentativas():
    """Sem teto, um número que dá timeout para sempre voltaria à fila em toda passada,
    pelos 7 dias da janela, tomando a vaga de quem ainda podia receber."""
    template = _template()
    broadcast = _broadcast(1)
    broadcast.template_id = template.id
    canal = FakeChannel(transitorio_em={broadcast.destinatarios[0].contato})
    uc = EnviarBroadcast(
        broadcasts=FakeBroadcastRepo(),
        templates=FakeTemplateRepo(template),
        canal=canal,
        quota=FakeQuota(limite_diario=100),
        rate_limiter=FakeRateLimiter(),
        max_tentativas=3,
    )

    for _ in range(3):
        await uc.executar(broadcast=broadcast)

    dest = broadcast.destinatarios[0]
    assert dest.tentativas == 3
    assert dest.status is StatusEntrega.FALHOU  # desistiu no teto
    assert canal.tentativas_por_contato[dest.contato] == 3


async def test_indisponibilidade_que_passa_acaba_entregando():
    """O caso que justifica tudo isso: a segunda tentativa dá certo."""
    template = _template()
    broadcast = _broadcast(1)
    broadcast.template_id = template.id
    alvo = broadcast.destinatarios[0].contato
    uc = EnviarBroadcast(
        broadcasts=FakeBroadcastRepo(),
        templates=FakeTemplateRepo(template),
        # Falha uma vez e depois volta ao normal.
        canal=FakeChannel(transitorio_em={alvo}, curar_apos=1),
        quota=FakeQuota(limite_diario=100),
        rate_limiter=FakeRateLimiter(),
    )

    primeira = await uc.executar(broadcast=broadcast)
    assert primeira.reenfileirados == 1
    assert broadcast.destinatarios[0].status is StatusEntrega.PENDENTE

    segunda = await uc.executar(broadcast=broadcast)
    assert segunda.enviados == 1
    assert broadcast.destinatarios[0].status is StatusEntrega.ENVIADO
    assert segunda.status is StatusBroadcast.CONCLUIDO
