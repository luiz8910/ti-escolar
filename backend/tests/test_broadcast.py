"""Testa o outbound: cota diária (tier Meta), template aprovado e falhas parciais."""

from __future__ import annotations

import uuid

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
)
from tests.fakes import (
    FakeBroadcastRepo,
    FakeChannel,
    FakeQuota,
    FakeRateLimiter,
    FakeTemplateRepo,
)

TENANT = uuid.uuid4()


def _template(status=StatusTemplate.APROVADO) -> MessageTemplate:
    return MessageTemplate(
        tenant_id=TENANT,
        nome="aviso",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}!",
        status=status,
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
