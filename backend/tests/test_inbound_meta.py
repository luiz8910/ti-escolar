"""Inbound real do webhook da Meta: roteamento multi-tenant e resposta ativa (§9e.1).

Fakes das portas, sem BD nem framework — o que se testa aqui é a decisão de para qual
escola a mensagem vai e por qual número a resposta sai.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.inbound_use_cases import (
    ProcessarInboundMeta,
    normalizar_origem,
)
from app.application.use_cases import (
    ReceberMensagemRecebida,
    RecuperarEEnviarDocumento,
    ResponderDuvida,
)
from app.domain.entities import EstadoAtendimento, Tenant
from app.infrastructure.atendimento import RegistroAtendimentoMemoria
from tests.fakes import (
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeVectorStore,
    fake_embedder,
)

PID_ROSA = "111111111111111"
PID_SAO_JOSE = "222222222222222"


class FakeTenantRepoInbound:
    """Só o que o inbound usa da porta: buscar a escola pelo phone_number_id."""

    def __init__(self, tenants: list[Tenant]) -> None:
        self.tenants = tenants

    async def por_meta_phone_number_id(self, phone_number_id):
        if not phone_number_id:
            return None
        return next(
            (t for t in self.tenants if t.meta_phone_number_id == phone_number_id), None
        )


class CanalEspiao:
    """Registra cada envio com o remetente, que é o ponto do multi-tenant."""

    def __init__(self) -> None:
        self.textos: list[dict] = []

    async def enviar_texto(self, *, contato, texto, remetente=None) -> str:
        self.textos.append({"contato": contato, "texto": texto, "remetente": remetente})
        return f"wamid.resposta{len(self.textos)}"

    async def enviar_template(self, *, contato, template, parametros, remetente=None) -> str:
        return "x"

    async def enviar_documento(self, *, contato, documento, remetente=None) -> str:
        return "x"


def _escolas() -> tuple[Tenant, Tenant]:
    rosa = Tenant(
        id=uuid.uuid4(),
        nome="EM Rosa Cury",
        slug="rosa-cury",
        whatsapp_numero="+5515333330000",
        meta_phone_number_id=PID_ROSA,
    )
    sao_jose = Tenant(
        id=uuid.uuid4(),
        nome="Colégio São José",
        slug="sao-jose",
        whatsapp_numero="+5511222220000",
        meta_phone_number_id=PID_SAO_JOSE,
    )
    return rosa, sao_jose


def _montar(tenants: list[Tenant], *, atendimentos=None):
    conversas = FakeConversaRepo()
    receber = ReceberMensagemRecebida(
        conversas=conversas,
        responder=ResponderDuvida(
            embedder=fake_embedder(), store=FakeVectorStore(), llm=FakeLLM()
        ),
        documentos=RecuperarEEnviarDocumento(
            source=FakeDocumentSource([]), canal=CanalEspiao()
        ),
    )
    canal = CanalEspiao()
    uc = ProcessarInboundMeta(
        tenants=FakeTenantRepoInbound(tenants),
        receber=receber,
        canal=canal,
        atendimentos=atendimentos,
    )
    return uc, canal, conversas


def _payload_mensagem(
    *, phone_number_id: str, de: str = "5515999998888", texto: str = "Qual o horário?", wamid="wamid.A"
) -> dict:
    """Envelope de mensagem recebida, no formato aninhado da Meta."""
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA_ID",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "5515333330000",
                                "phone_number_id": phone_number_id,
                            },
                            "contacts": [{"profile": {"name": "Mãe da Ana"}, "wa_id": de}],
                            "messages": [
                                {
                                    "from": de,
                                    "id": wamid,
                                    "timestamp": "1753600000",
                                    "type": "text",
                                    "text": {"body": texto},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


# --------------------------------------------------------------------------- #
# Roteamento por phone_number_id
# --------------------------------------------------------------------------- #
async def test_mensagem_vai_para_a_escola_dona_do_phone_number_id():
    rosa, sao_jose = _escolas()
    uc, canal, conversas = _montar([rosa, sao_jose])

    resultado = await uc.executar(payload=_payload_mensagem(phone_number_id=PID_SAO_JOSE))

    assert resultado.recebidas == 1
    assert resultado.respondidas == 1
    # A conversa foi aberta no tenant do São José — e em nenhum outro.
    tenants_com_conversa = {c.tenant_id for c in conversas.conversas.values()}
    assert tenants_com_conversa == {sao_jose.id}
    assert rosa.id not in tenants_com_conversa


async def test_escolas_diferentes_nao_se_misturam():
    """Dois números, duas escolas: cada mensagem fica na sua e responde pelo seu número."""
    rosa, sao_jose = _escolas()
    uc, canal, conversas = _montar([rosa, sao_jose])

    await uc.executar(
        payload=_payload_mensagem(phone_number_id=PID_ROSA, de="5515900000001", wamid="wamid.1")
    )
    await uc.executar(
        payload=_payload_mensagem(
            phone_number_id=PID_SAO_JOSE, de="5511900000002", wamid="wamid.2"
        )
    )

    por_tenant = {c.contato: c.tenant_id for c in conversas.conversas.values()}
    assert por_tenant["+5515900000001"] == rosa.id
    assert por_tenant["+5511900000002"] == sao_jose.id
    assert [t["remetente"] for t in canal.textos] == [PID_ROSA, PID_SAO_JOSE]


async def test_numero_desconhecido_e_descartado_sem_cair_em_tenant_padrao():
    """O ponto inegociável: sem escola dona do número, a mensagem morre aqui."""
    rosa, sao_jose = _escolas()
    uc, canal, conversas = _montar([rosa, sao_jose])

    resultado = await uc.executar(payload=_payload_mensagem(phone_number_id="999999999999999"))

    assert resultado.descartadas == 1
    assert resultado.recebidas == 0
    # Nada foi persistido em nenhuma escola e ninguém foi respondido.
    assert conversas.conversas == {}
    assert canal.textos == []


async def test_metadata_sem_phone_number_id_e_descartado():
    rosa, _ = _escolas()
    uc, canal, conversas = _montar([rosa])
    payload = _payload_mensagem(phone_number_id=PID_ROSA)
    payload["entry"][0]["changes"][0]["value"]["metadata"] = {}

    resultado = await uc.executar(payload=payload)

    assert resultado.descartadas == 1
    assert conversas.conversas == {}
    assert canal.textos == []


# --------------------------------------------------------------------------- #
# Resposta ativa (a Meta não aceita resposta no corpo do webhook)
# --------------------------------------------------------------------------- #
async def test_resposta_sai_pelo_numero_da_escola_certa():
    rosa, sao_jose = _escolas()
    uc, canal, _ = _montar([rosa, sao_jose])

    await uc.executar(payload=_payload_mensagem(phone_number_id=PID_ROSA))

    assert len(canal.textos) == 1
    envio = canal.textos[0]
    assert envio["remetente"] == PID_ROSA
    assert envio["remetente"] != PID_SAO_JOSE
    # Responde a quem escreveu, em E.164 com "+".
    assert envio["contato"] == "+5515999998888"
    assert envio["texto"]


async def test_escola_sem_id_na_meta_cai_no_e164_como_remetente():
    """Fallback previsto em ``Tenant.remetente_canal`` enquanto o id não é cadastrado."""
    rosa, _ = _escolas()
    rosa.meta_phone_number_id = ""
    uc, canal, _ = _montar([rosa])
    # Sem id, o roteamento do inbound não acha a escola — é o preço de não ter fallback.
    resultado = await uc.executar(payload=_payload_mensagem(phone_number_id=PID_ROSA))
    assert resultado.descartadas == 1

    # Já o outbound (que resolve o tenant por id) ainda funciona pelo E.164.
    assert rosa.remetente_canal == "+5515333330000"


def test_normalizar_origem_poe_o_mais_no_telefone_da_meta():
    """A Meta manda o ``from`` sem "+"; as conversas/contatos são chaveados com ele."""
    assert normalizar_origem("5515999998888") == "+5515999998888"
    assert normalizar_origem("+5515999998888") == "+5515999998888"
    assert normalizar_origem("") == ""


async def test_mesma_origem_reaproveita_a_conversa():
    """Sem a normalização do "+", cada mensagem abriria uma conversa nova."""
    rosa, _ = _escolas()
    uc, _, conversas = _montar([rosa])
    await uc.executar(payload=_payload_mensagem(phone_number_id=PID_ROSA, wamid="wamid.1"))
    await uc.executar(payload=_payload_mensagem(phone_number_id=PID_ROSA, wamid="wamid.2"))
    assert len(conversas.conversas) == 1


# --------------------------------------------------------------------------- #
# Tipos não textuais
# --------------------------------------------------------------------------- #
async def test_mensagem_de_imagem_e_ignorada_sem_derrubar_o_lote():
    rosa, _ = _escolas()
    uc, canal, conversas = _montar([rosa])
    payload = _payload_mensagem(phone_number_id=PID_ROSA)
    payload["entry"][0]["changes"][0]["value"]["messages"] = [
        {"from": "5515999998888", "id": "wamid.img", "type": "image", "image": {"id": "m1"}},
        {
            "from": "5515999998888",
            "id": "wamid.txt",
            "type": "text",
            "text": {"body": "E o boletim?"},
        },
    ]

    resultado = await uc.executar(payload=payload)

    assert resultado.ignoradas == 1
    assert resultado.recebidas == 1
    assert len(canal.textos) == 1


# --------------------------------------------------------------------------- #
# Convivência de mensagem + status no mesmo envelope
# --------------------------------------------------------------------------- #
async def test_envelope_so_de_status_nao_gera_inbound():
    """O caminho de status é de ``RegistrarStatusEntrega``; aqui não pode sobrar nada."""
    rosa, _ = _escolas()
    uc, canal, conversas = _montar([rosa])
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": PID_ROSA},
                            "statuses": [
                                {"id": "wamid.env1", "status": "delivered", "timestamp": "1"}
                            ],
                        }
                    }
                ]
            }
        ],
    }

    resultado = await uc.executar(payload=payload)

    assert (resultado.recebidas, resultado.descartadas, resultado.ignoradas) == (0, 0, 0)
    assert conversas.conversas == {}
    assert canal.textos == []


async def test_mensagem_e_status_no_mesmo_post_convivem():
    """A Meta empacota os dois no mesmo envelope — cada caminho pega o seu."""
    from app.application.use_cases import RegistrarStatusEntrega
    from app.domain.entities import StatusEntrega

    rosa, _ = _escolas()
    uc, canal, conversas = _montar([rosa])

    payload = _payload_mensagem(phone_number_id=PID_ROSA)
    payload["entry"].append(
        {
            "changes": [
                {
                    "value": {
                        "metadata": {"phone_number_id": PID_ROSA},
                        "statuses": [
                            {"id": "wamid.broadcast", "status": "failed", "timestamp": "1"}
                        ],
                    }
                }
            ]
        }
    )

    class FakeBroadcastRepo:
        def __init__(self) -> None:
            self.registrados: list[tuple[str, StatusEntrega]] = []

        async def registrar_status(self, *, mensagem_id_externo, status) -> bool:
            self.registrados.append((mensagem_id_externo, status))
            return True

    broadcasts = FakeBroadcastRepo()
    atualizados = await RegistrarStatusEntrega(broadcasts=broadcasts).executar(payload=payload)
    resultado = await uc.executar(payload=payload)

    assert atualizados == 1
    assert broadcasts.registrados == [("wamid.broadcast", StatusEntrega.FALHOU)]
    assert resultado.recebidas == 1
    assert len(canal.textos) == 1


# --------------------------------------------------------------------------- #
# Idempotência (a Meta reenvia o webhook)
# --------------------------------------------------------------------------- #
async def test_reentrega_do_mesmo_wamid_nao_responde_duas_vezes():
    rosa, _ = _escolas()
    uc, canal, conversas = _montar([rosa], atendimentos=RegistroAtendimentoMemoria())
    payload = _payload_mensagem(phone_number_id=PID_ROSA, wamid="wamid.unico")

    primeira = await uc.executar(payload=payload)
    segunda = await uc.executar(payload=payload)  # reentrega da Meta

    assert primeira.recebidas == 1 and primeira.respondidas == 1
    assert segunda.recebidas == 0 and segunda.repetidas == 1
    assert len(canal.textos) == 1


async def test_wamids_distintos_nao_se_bloqueiam():
    rosa, _ = _escolas()
    uc, canal, _ = _montar([rosa], atendimentos=RegistroAtendimentoMemoria())
    await uc.executar(payload=_payload_mensagem(phone_number_id=PID_ROSA, wamid="wamid.1"))
    await uc.executar(payload=_payload_mensagem(phone_number_id=PID_ROSA, wamid="wamid.2"))
    assert len(canal.textos) == 2


async def test_reserva_marca_a_duvida_como_sanada_ao_terminar():
    """O estado final tem que ser 'concluída', não 'em atendimento' — é o que faz a
    reentrega tardia ser reconhecida como dúvida já respondida."""
    rosa, _ = _escolas()
    registro = RegistroAtendimentoMemoria()
    uc, _, _ = _montar([rosa], atendimentos=registro)

    await uc.executar(payload=_payload_mensagem(phone_number_id=PID_ROSA, wamid="w.ok"))

    assert registro._registros["w.ok"]["status"] == "concluida"
    assert await registro.iniciar(chave="w.ok") is EstadoAtendimento.CONCLUIDA


async def test_falha_no_atendimento_libera_a_reserva_para_a_retentativa():
    """Sem liberar, um erro na LLM deixaria a mensagem travada em 'em atendimento' e a
    reentrega da Meta — que é a chance de acertar — seria descartada."""
    rosa, _ = _escolas()
    registro = RegistroAtendimentoMemoria()
    uc, _, _ = _montar([rosa], atendimentos=registro)

    class CanalQueFalha:
        async def enviar_texto(self, **kwargs):
            raise RuntimeError("Graph API fora do ar")

        async def enviar_template(self, **kwargs):
            return "x"

        async def enviar_documento(self, **kwargs):
            return "x"

    uc._canal = CanalQueFalha()
    payload = _payload_mensagem(phone_number_id=PID_ROSA, wamid="w.falha")

    with pytest.raises(RuntimeError):
        await uc.executar(payload=payload)

    assert registro._registros["w.falha"]["status"] == "falhou"
    # A retentativa consegue retomar a reserva em vez de esbarrar nela.
    assert await registro.iniciar(chave="w.falha") is EstadoAtendimento.RETOMADO


async def test_reserva_viva_de_outro_processo_bloqueia_o_atendimento_duplo():
    """A reentrega chega enquanto a primeira ainda espera a LLM: nesse instante o estado
    é 'em atendimento', não 'concluída'. Um cache booleano não distinguiria os dois."""
    registro = RegistroAtendimentoMemoria()
    assert await registro.iniciar(chave="w.x") is EstadoAtendimento.NOVO
    assert await registro.iniciar(chave="w.x") is EstadoAtendimento.EM_ATENDIMENTO


async def test_reserva_abandonada_pode_ser_retomada():
    """Se o processo cai no meio, a mensagem não pode ficar travada para sempre."""
    registro = RegistroAtendimentoMemoria(reserva_abandonada_segundos=0)
    await registro.iniciar(chave="w.y")
    assert await registro.iniciar(chave="w.y") is EstadoAtendimento.RETOMADO


async def test_mensagem_sem_wamid_e_atendida():
    """Sem id não há como deduplicar; perder a resposta é pior que uma duplicata rara."""
    registro = RegistroAtendimentoMemoria()
    assert await registro.iniciar(chave="") is EstadoAtendimento.NOVO
