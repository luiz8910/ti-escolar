"""Testa o canal pai ↔ professor mediado (§A3): envio pelo número da escola (sem expor
o professor), registro de mensagem recebida, thread cronológica e resumo de
interlocutores.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.mediacao_use_cases import (
    EnviarMensagemAoResponsavel,
    ListarConversaMediada,
    ListarInterlocutoresDoProfessor,
    RegistrarMensagemDoResponsavel,
)
from app.domain.entities import Contato, DirecaoMensagem, Professor, Tenant
from tests.fakes import (
    FakeChannel,
    FakeContatoRepo,
    FakeMediacaoRepo,
    FakeProfessorRepo,
    FakeTenantRepo,
)

TENANT = uuid.uuid4()
CONTATO_TEL = "+5515999990000"


async def _cenario(*, whatsapp_numero="+5515333330000"):
    professores = FakeProfessorRepo()
    prof = await professores.criar(
        Professor(tenant_id=TENANT, nome="Prof. Ana", telefone="+5511999990000")
    )
    tenants = FakeTenantRepo(
        [Tenant(id=TENANT, nome="EM Rosa Cury", slug="rosa-cury", whatsapp_numero=whatsapp_numero)]
    )
    contatos = FakeContatoRepo()
    await contatos.criar(Contato(tenant_id=TENANT, nome="Mãe do João", telefone=CONTATO_TEL))
    return professores, prof, tenants, contatos


async def test_envio_sai_pelo_numero_da_escola():
    professores, prof, tenants, contatos = await _cenario()
    mediacao = FakeMediacaoRepo()
    canal = FakeChannel()

    msg = await EnviarMensagemAoResponsavel(
        mediacao=mediacao,
        professores=professores,
        canal=canal,
        tenants=tenants,
        contatos=contatos,
    ).executar(
        tenant_id=TENANT,
        professor_id=prof.id,
        contato_telefone=CONTATO_TEL,
        corpo="Bom dia! O João foi muito bem hoje.",
    )

    assert msg.direcao == DirecaoMensagem.PROFESSOR_PARA_RESPONSAVEL
    assert msg.contato_nome == "Mãe do João"
    assert msg.professor_nome == "Prof. Ana"
    # Saiu pelo número da escola (remetente), não pelo número do professor.
    assert canal.enviados == [(CONTATO_TEL, "texto")]
    assert canal.remetente == "+5515333330000"


async def test_envio_sem_numero_da_escola_usa_padrao():
    professores, prof, tenants, contatos = await _cenario(whatsapp_numero="")
    mediacao = FakeMediacaoRepo()
    canal = FakeChannel()

    await EnviarMensagemAoResponsavel(
        mediacao=mediacao,
        professores=professores,
        canal=canal,
        tenants=tenants,
        contatos=contatos,
    ).executar(
        tenant_id=TENANT, professor_id=prof.id, contato_telefone=CONTATO_TEL, corpo="Oi"
    )
    assert canal.remetente is None


async def test_corpo_e_telefone_obrigatorios():
    professores, prof, tenants, contatos = await _cenario()
    enviar = EnviarMensagemAoResponsavel(
        mediacao=FakeMediacaoRepo(),
        professores=professores,
        canal=FakeChannel(),
        tenants=tenants,
        contatos=contatos,
    )
    with pytest.raises(ValueError):
        await enviar.executar(
            tenant_id=TENANT, professor_id=prof.id, contato_telefone="  ", corpo="oi"
        )
    with pytest.raises(ValueError):
        await enviar.executar(
            tenant_id=TENANT, professor_id=prof.id, contato_telefone=CONTATO_TEL, corpo=" "
        )


async def test_thread_cronologica_e_interlocutores():
    professores, prof, tenants, contatos = await _cenario()
    mediacao = FakeMediacaoRepo()
    canal = FakeChannel()

    # Responsável escreve (inbound roteado), professor responde.
    await RegistrarMensagemDoResponsavel(
        mediacao=mediacao, professores=professores, contatos=contatos
    ).executar(
        tenant_id=TENANT,
        professor_id=prof.id,
        contato_telefone=CONTATO_TEL,
        corpo="Professora, o João pode sair mais cedo?",
    )
    await EnviarMensagemAoResponsavel(
        mediacao=mediacao,
        professores=professores,
        canal=canal,
        tenants=tenants,
        contatos=contatos,
    ).executar(
        tenant_id=TENANT, professor_id=prof.id, contato_telefone=CONTATO_TEL, corpo="Pode sim."
    )

    thread = await ListarConversaMediada(mediacao=mediacao).executar(
        tenant_id=TENANT, professor_id=prof.id, contato_telefone=CONTATO_TEL
    )
    assert [m.direcao for m in thread] == [
        DirecaoMensagem.RESPONSAVEL_PARA_PROFESSOR,
        DirecaoMensagem.PROFESSOR_PARA_RESPONSAVEL,
    ]

    interlocutores = await ListarInterlocutoresDoProfessor(mediacao=mediacao).executar(
        tenant_id=TENANT, professor_id=prof.id
    )
    assert len(interlocutores) == 1
    assert interlocutores[0].contato_telefone == CONTATO_TEL
    assert interlocutores[0].total_mensagens == 2
    assert interlocutores[0].contato_nome == "Mãe do João"


async def test_professor_de_outro_tenant_recusado():
    professores, prof, tenants, contatos = await _cenario()
    enviar = EnviarMensagemAoResponsavel(
        mediacao=FakeMediacaoRepo(),
        professores=professores,
        canal=FakeChannel(),
        tenants=tenants,
        contatos=contatos,
    )
    with pytest.raises(ValueError):
        await enviar.executar(
            tenant_id=uuid.uuid4(),  # tenant errado
            professor_id=prof.id,
            contato_telefone=CONTATO_TEL,
            corpo="oi",
        )
