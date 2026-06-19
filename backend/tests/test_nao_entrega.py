"""Confirmação de recebimento de avisos (não-entrega reativa).

Cobre: o id externo guardado no envio, a aplicação dos status do webhook da Meta e a
detecção reativa de destinatários que não confirmaram o recebimento.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.application.use_cases import (
    EnviarBroadcast,
    RegistrarStatusEntrega,
    VerificarRecebimentoBroadcast,
)
from app.domain.entities import (
    Broadcast,
    CategoriaTemplate,
    Contato,
    DestinatarioBroadcast,
    MessageTemplate,
    StatusEntrega,
    StatusTemplate,
)
from tests.fakes import (
    FakeBroadcastRepo,
    FakeChannel,
    FakeContatoRepo,
    FakeQuota,
    FakeRateLimiter,
    FakeTemplateRepo,
)

TENANT = uuid.uuid4()


def _template() -> MessageTemplate:
    return MessageTemplate(
        tenant_id=TENANT,
        nome="aviso",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}!",
        status=StatusTemplate.APROVADO,
    )


async def test_enviar_broadcast_guarda_id_externo_e_timestamp():
    template = _template()
    broadcast = Broadcast(
        tenant_id=TENANT,
        template_id=template.id,
        titulo="t",
        destinatarios=[DestinatarioBroadcast(contato="+5511900000001", parametros=["Ana"])],
    )
    uc = EnviarBroadcast(
        broadcasts=FakeBroadcastRepo(),
        templates=FakeTemplateRepo(template),
        canal=FakeChannel(),
        quota=FakeQuota(limite_diario=-1),
        rate_limiter=FakeRateLimiter(),
    )
    await uc.executar(broadcast=broadcast)

    dest = broadcast.destinatarios[0]
    assert dest.status == StatusEntrega.ENVIADO
    assert dest.mensagem_id_externo == "wamid:+5511900000001"
    assert dest.atualizado_em is not None


async def test_registrar_status_aplica_eventos_do_webhook():
    template = _template()
    broadcast = Broadcast(
        tenant_id=TENANT,
        template_id=template.id,
        titulo="t",
        destinatarios=[DestinatarioBroadcast(contato="+5511900000002", parametros=["Bia"])],
    )
    repo = FakeBroadcastRepo()
    enviar = EnviarBroadcast(
        broadcasts=repo,
        templates=FakeTemplateRepo(template),
        canal=FakeChannel(),
        quota=FakeQuota(limite_diario=-1),
        rate_limiter=FakeRateLimiter(),
    )
    await enviar.executar(broadcast=broadcast)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "statuses": [
                                {"id": "wamid:+5511900000002", "status": "delivered"},
                                {"id": "wamid:desconhecido", "status": "read"},
                            ]
                        }
                    }
                ]
            }
        ],
    }
    atualizados = await RegistrarStatusEntrega(broadcasts=repo).executar(payload=payload)

    assert atualizados == 1  # só o id conhecido
    assert broadcast.destinatarios[0].status == StatusEntrega.ENTREGUE


async def test_registrar_status_ignora_status_desconhecido():
    repo = FakeBroadcastRepo()
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "x", "status": "??"}]}}]}]}
    assert await RegistrarStatusEntrega(broadcasts=repo).executar(payload=payload) == 0


def _broadcast_com(*dests: DestinatarioBroadcast) -> Broadcast:
    return Broadcast(
        tenant_id=TENANT, template_id=uuid.uuid4(), titulo="aviso", destinatarios=list(dests)
    )


async def test_verificar_sinaliza_falha_e_sem_confirmacao():
    antigo = datetime.now(timezone.utc) - timedelta(minutes=120)
    falhou = DestinatarioBroadcast(contato="+5511900000010", status=StatusEntrega.FALHOU)
    sem_conf = DestinatarioBroadcast(
        contato="+5511900000011", status=StatusEntrega.ENVIADO, atualizado_em=antigo
    )
    entregue = DestinatarioBroadcast(
        contato="+5511900000012", status=StatusEntrega.ENTREGUE, atualizado_em=antigo
    )
    lido = DestinatarioBroadcast(contato="+5511900000013", status=StatusEntrega.LIDO)
    pendente = DestinatarioBroadcast(contato="+5511900000014", status=StatusEntrega.PENDENTE)
    broadcast = _broadcast_com(falhou, sem_conf, entregue, lido, pendente)

    repo = FakeBroadcastRepo()
    await repo.salvar(broadcast)

    contatos = FakeContatoRepo()
    await contatos.criar(
        Contato(tenant_id=TENANT, nome="Carlos", telefone="+5511900000011")
    )

    uc = VerificarRecebimentoBroadcast(broadcasts=repo, contatos=contatos)
    avisos = await uc.executar(
        tenant_id=TENANT, broadcast_id=broadcast.id, apos_minutos=60
    )

    contatos_alertados = {a.contato: a for a in avisos}
    assert set(contatos_alertados) == {"+5511900000010", "+5511900000011"}
    assert contatos_alertados["+5511900000010"].motivo == "falha_envio"
    assert contatos_alertados["+5511900000011"].motivo == "sem_confirmacao"
    assert contatos_alertados["+5511900000011"].nome == "Carlos"
    assert contatos_alertados["+5511900000010"].nome == ""  # sem contato cadastrado


async def test_verificar_respeita_janela_de_espera():
    recente = DestinatarioBroadcast(
        contato="+5511900000020",
        status=StatusEntrega.ENVIADO,
        atualizado_em=datetime.now(timezone.utc),
    )
    broadcast = _broadcast_com(recente)
    repo = FakeBroadcastRepo()
    await repo.salvar(broadcast)

    uc = VerificarRecebimentoBroadcast(broadcasts=repo, contatos=FakeContatoRepo())
    avisos = await uc.executar(
        tenant_id=TENANT, broadcast_id=broadcast.id, apos_minutos=60
    )
    assert avisos == []  # enviado há pouco, ainda dentro da janela


async def test_verificar_isola_por_tenant():
    broadcast = _broadcast_com(
        DestinatarioBroadcast(contato="+5511900000030", status=StatusEntrega.FALHOU)
    )
    repo = FakeBroadcastRepo()
    await repo.salvar(broadcast)

    uc = VerificarRecebimentoBroadcast(broadcasts=repo, contatos=FakeContatoRepo())
    avisos = await uc.executar(
        tenant_id=uuid.uuid4(), broadcast_id=broadcast.id, apos_minutos=60
    )
    assert avisos == []  # tenant diferente não enxerga o broadcast
