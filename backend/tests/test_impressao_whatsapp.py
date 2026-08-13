"""Impressão pelo WhatsApp: o professor manda o arquivo e ele cai na fila (§B1).

O que se prova aqui é a **decisão de roteamento** — quem escreveu é da escola ou é uma
família? — e as consequências dela: o arquivo do professor não vira documento recebido,
não passa pelo assistente (nem gasta LLM) e já sai debitado da franquia do mês.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.impressao_use_cases import (
    ConsultarSaldoImpressao,
    ReceberImpressaoDoProfessor,
    interpretar_legenda,
)
from app.application.inbound_use_cases import ProcessarInboundMeta
from app.application.use_cases import AtenderConversa, RecuperarEEnviarDocumento
from app.domain.entities import (
    ArquivoBaixado,
    CotaImpressao,
    OrigemImpressao,
    Professor,
    Tenant,
)
from app.infrastructure.storage import ArquivoStorageMemoria
from tests.fakes import (
    FakeConversaRepo,
    FakeCotaImpressaoRepo,
    FakeDocumentSource,
    FakeFonteMidia,
    FakeLLM,
    FakeProfessorRepo,
    FakeSolicitacaoImpressaoRepo,
    FakeVectorStore,
    fake_embedder,
)

PID = "111111111111111"
TEL_PROFESSORA = "+5515999990001"
TEL_MAE = "+5515999990002"


class CanalEspiao:
    def __init__(self) -> None:
        self.textos: list[dict] = []

    async def enviar_texto(self, *, contato, texto, remetente=None) -> str:
        self.textos.append({"contato": contato, "texto": texto, "remetente": remetente})
        return f"wamid.r{len(self.textos)}"

    async def enviar_template(self, *, contato, template, parametros, remetente=None) -> str:
        return "x"

    async def enviar_documento(self, *, contato, documento, remetente=None) -> str:
        return "x"


class FakeTenantRepoInbound:
    def __init__(self, tenants) -> None:
        self.tenants = list(tenants)

    async def por_meta_phone_number_id(self, phone_number_id):
        return next(
            (t for t in self.tenants if t.meta_phone_number_id == phone_number_id), None
        )


class LLMContado(FakeLLM):
    """FakeLLM que conta chamadas — é assim que se prova que o professor não custou nada."""

    def __init__(self) -> None:
        super().__init__()
        self.chamadas = 0

    async def gerar_com_ferramentas(self, **kwargs):
        self.chamadas += 1
        return await super().gerar_com_ferramentas(**kwargs)


class Cenario:
    """Monta o inbound inteiro com fakes e guarda as pontas que os testes inspecionam."""

    def __init__(self, *, ativo: bool = True, limite_mensal: int = 0, arquivos=None) -> None:
        self.escola = Tenant(
            id=uuid.uuid4(),
            nome="EM Rosa Cury",
            slug="rosa-cury",
            whatsapp_numero="+5515333330000",
            meta_phone_number_id=PID,
        )
        self.professora = Professor(
            tenant_id=self.escola.id,
            nome="Carla Mendes",
            telefone=TEL_PROFESSORA,
            ativo=ativo,
        )
        self.professores = FakeProfessorRepo()
        self.professores.professores[self.professora.id] = self.professora

        self.solicitacoes = FakeSolicitacaoImpressaoRepo()
        self.cotas = FakeCotaImpressaoRepo()
        if limite_mensal:
            self.cotas.cotas[(self.escola.id, self.professora.id)] = CotaImpressao(
                tenant_id=self.escola.id,
                professor_id=self.professora.id,
                limite_mensal=limite_mensal,
            )

        self.storage = ArquivoStorageMemoria()
        self.fonte = FakeFonteMidia(arquivos or {})
        self.conversas = FakeConversaRepo()
        self.canal = CanalEspiao()
        self.llm = LLMContado()

        self.impressao = ReceberImpressaoDoProfessor(
            fonte=self.fonte,
            storage=self.storage,
            solicitacoes=self.solicitacoes,
            saldo=ConsultarSaldoImpressao(
                solicitacoes=self.solicitacoes, cotas=self.cotas
            ),
            conversas=self.conversas,
        )
        self.inbound = ProcessarInboundMeta(
            tenants=FakeTenantRepoInbound([self.escola]),
            atender=AtenderConversa(
                conversas=self.conversas,
                embedder=fake_embedder(),
                store=FakeVectorStore(),
                llm=self.llm,
                documentos=RecuperarEEnviarDocumento(
                    source=FakeDocumentSource([]), canal=self.canal
                ),
            ),
            canal=self.canal,
            professores=self.professores,
            impressao=self.impressao,
        )

    @property
    def fila(self):
        return list(self.solicitacoes.solicitacoes.values())


def _payload(*, de: str, tipo: str = "document", corpo=None, texto="", wamid="wamid.A") -> dict:
    mensagem = {"from": de.lstrip("+"), "id": wamid, "timestamp": "1", "type": tipo}
    mensagem[tipo] = corpo if corpo is not None else {"body": texto}
    return {
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": PID},
                            "messages": [mensagem],
                        },
                    }
                ]
            }
        ]
    }


def _pdf(nome="prova_5A.pdf", tamanho=2048) -> ArquivoBaixado:
    return ArquivoBaixado(conteudo=b"x" * tamanho, mime="application/pdf", nome=nome)


# --------------------------------------------------------------------------- #
# Leitura da legenda (heurística, sem LLM)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "legenda,copias,informadas",
    [
        ("30 cópias", 30, True),
        ("30 copias frente e verso", 30, True),
        ("x25", 25, True),
        ("25x", 25, True),
        ("40 folhas", 40, True),
        ("32", 32, True),
        ("Prova do 2º bimestre", 1, False),
        ("", 1, False),
        # Ano não é tiragem: acima do teto o palpite é descartado, e não truncado.
        ("Planejamento 2026", 1, False),
    ],
)
def test_legenda_informa_a_quantidade(legenda, copias, informadas):
    parametros = interpretar_legenda(legenda)
    assert parametros.copias == copias
    assert parametros.copias_informadas is informadas


def test_legenda_informa_cor_e_frente_verso():
    parametros = interpretar_legenda("10 cópias coloridas, frente e verso")
    assert (parametros.copias, parametros.colorido, parametros.frente_verso) == (
        10,
        True,
        True,
    )


# --------------------------------------------------------------------------- #
# Roteamento: professor ativo × responsável
# --------------------------------------------------------------------------- #
async def test_arquivo_de_professor_vai_para_a_fila_de_impressao():
    c = Cenario(arquivos={"media-1": _pdf()})

    resultado = await c.inbound.executar(
        payload=_payload(
            de=TEL_PROFESSORA,
            corpo={"id": "media-1", "filename": "prova_5A.pdf", "caption": "30 cópias"},
        )
    )

    assert resultado.impressoes == 1
    assert resultado.documentos == 0
    pedido = c.fila[0]
    assert pedido.professor_id == c.professora.id
    assert pedido.copias == 30
    assert pedido.origem is OrigemImpressao.WHATSAPP
    # Os bytes ficaram com a escola: a fila sem arquivo não serve para imprimir.
    assert pedido.tem_arquivo
    assert await c.storage.ler(chave=pedido.chave_storage) == b"x" * 2048


async def test_professor_nao_consome_llm():
    """A razão de existir do desvio: o assistente é dos pais, não de quem dá aula."""
    c = Cenario(arquivos={"media-1": _pdf()})

    await c.inbound.executar(
        payload=_payload(de=TEL_PROFESSORA, tipo="text", texto="bom dia")
    )

    assert c.llm.chamadas == 0
    # E ele foi respondido — com a orientação de como mandar o arquivo.
    assert "impressão" in c.canal.textos[0]["texto"]


async def test_professor_desligado_volta_a_ser_atendido_como_qualquer_um():
    c = Cenario(ativo=False, arquivos={"media-1": _pdf()})

    resultado = await c.inbound.executar(
        payload=_payload(de=TEL_PROFESSORA, tipo="text", texto="qual o horário?")
    )

    assert resultado.impressoes == 0
    assert resultado.respondidas == 1
    assert c.llm.chamadas == 1
    assert c.fila == []


async def test_arquivo_de_responsavel_nao_entra_na_fila_de_impressao():
    """Sem `midias` configurado, a mídia da mãe é ignorada — mas jamais vira impressão."""
    c = Cenario(arquivos={"media-1": _pdf()})

    resultado = await c.inbound.executar(
        payload=_payload(de=TEL_MAE, corpo={"id": "media-1", "filename": "atestado.pdf"})
    )

    assert resultado.impressoes == 0
    assert c.fila == []


# --------------------------------------------------------------------------- #
# Franquia
# --------------------------------------------------------------------------- #
async def test_confirmacao_traz_o_saldo_ja_debitado():
    c = Cenario(limite_mensal=100, arquivos={"media-1": _pdf()})

    await c.inbound.executar(
        payload=_payload(
            de=TEL_PROFESSORA, corpo={"id": "media-1", "caption": "30 cópias"}
        )
    )

    resposta = c.canal.textos[0]["texto"]
    # O saldo é apurado depois de gravar: mostrar "100 restantes" logo após consumir 30
    # seria pior do que não mostrar nada.
    assert "30 de 100 cópias" in resposta
    assert "70 restantes" in resposta


async def test_estouro_da_franquia_avisa_mas_nao_recusa():
    """Recusar impressão por bot travaria a aula; quem decide é a secretaria."""
    c = Cenario(limite_mensal=10, arquivos={"media-1": _pdf()})

    await c.inbound.executar(
        payload=_payload(
            de=TEL_PROFESSORA, corpo={"id": "media-1", "caption": "50 cópias"}
        )
    )

    assert len(c.fila) == 1
    assert "passou da franquia" in c.canal.textos[0]["texto"]


async def test_sem_cota_definida_a_franquia_e_ilimitada():
    c = Cenario(arquivos={"media-1": _pdf()})

    await c.inbound.executar(
        payload=_payload(de=TEL_PROFESSORA, corpo={"id": "media-1", "caption": "5 cópias"})
    )

    assert "não tem limite" in c.canal.textos[0]["texto"]


async def test_quantidade_ausente_registra_uma_copia_e_avisa():
    c = Cenario(arquivos={"media-1": _pdf()})

    await c.inbound.executar(
        payload=_payload(de=TEL_PROFESSORA, corpo={"id": "media-1", "caption": "segue"})
    )

    assert c.fila[0].copias == 1
    assert "1 cópia" in c.canal.textos[0]["texto"]


# --------------------------------------------------------------------------- #
# Bordas
# --------------------------------------------------------------------------- #
async def test_reentrega_do_webhook_nao_duplica_o_pedido():
    """A Meta reenvia quando o 200 demora; imprimir duas vezes custa papel e franquia."""
    c = Cenario(arquivos={"media-1": _pdf()})
    payload = _payload(de=TEL_PROFESSORA, corpo={"id": "media-1", "caption": "10 cópias"})

    await c.inbound.executar(payload=payload)
    await c.inbound.executar(payload=payload)

    assert len(c.fila) == 1
    # E o professor não é confirmado de novo: pensaria ter enviado duas vezes.
    assert len(c.canal.textos) == 1


async def test_formato_recusado_nao_entra_na_fila():
    c = Cenario(
        arquivos={"media-1": ArquivoBaixado(conteudo=b"ovo", mime="audio/ogg", nome="a.ogg")}
    )

    await c.inbound.executar(payload=_payload(de=TEL_PROFESSORA, corpo={"id": "media-1"}))

    assert c.fila == []
    assert "PDF" in c.canal.textos[0]["texto"]


async def test_arquivo_que_a_graph_api_nao_entrega_pede_reenvio():
    c = Cenario(arquivos={})

    await c.inbound.executar(payload=_payload(de=TEL_PROFESSORA, corpo={"id": "sumiu"}))

    assert c.fila == []
    assert "Reenvie" in c.canal.textos[0]["texto"]


async def test_professor_de_outra_escola_nao_e_reconhecido():
    """O `por_telefone` é escopado por tenant — o isolamento não pode depender do acaso."""
    c = Cenario(arquivos={"media-1": _pdf()})
    c.professora.tenant_id = uuid.uuid4()

    resultado = await c.inbound.executar(
        payload=_payload(de=TEL_PROFESSORA, corpo={"id": "media-1"})
    )

    assert resultado.impressoes == 0
    assert c.fila == []
