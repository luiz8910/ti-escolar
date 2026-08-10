"""Testa a recuperação e o envio de documentos ao responsável.

O roteamento "isto é pedido de documento?" deixou de ser por palavra-chave: quem decide
hoje é o modelo, chamando a ferramenta ``recuperar_documento`` (ver
``tests/test_atender_conversa.py``). O que sobra aqui — e continua valendo em qualquer
roteamento — é o comportamento do caso de uso que busca e entrega os arquivos.
"""

from __future__ import annotations

import uuid

from app.application.use_cases import RecuperarEEnviarDocumento
from app.domain.entities import Documento
from tests.fakes import FakeChannel, FakeDocumentSource

TENANT = uuid.uuid4()


async def test_sem_documento_correspondente_nao_envia_nada():
    uc = RecuperarEEnviarDocumento(source=FakeDocumentSource([]), canal=(canal := FakeChannel()))
    entregues = await uc.executar(tenant_id=TENANT, contato="+551199", consulta="boletim")
    assert entregues == []
    assert canal.enviados == []


async def test_documento_encontrado_e_enviado_ao_responsavel():
    doc = Documento(tenant_id=TENANT, nome="Boletim.pdf", categoria="boletim", url="http://x")
    canal = FakeChannel()
    uc = RecuperarEEnviarDocumento(source=FakeDocumentSource([doc]), canal=canal)

    entregues = await uc.executar(
        tenant_id=TENANT, contato="+551199", consulta="segunda via do boletim"
    )

    assert [d.nome for d in entregues] == ["Boletim.pdf"]
    assert canal.enviados == [("+551199", "documento")]


class _CanalQueFalhaNoDoc(FakeChannel):
    async def enviar_documento(self, *, contato, documento, remetente=None) -> str:
        raise RuntimeError("canal rejeitou a mídia (ex.: URL inacessível)")


async def test_falha_ao_enviar_documento_nao_derruba_o_atendimento():
    # Uma falha de entrega (canal real recusando a mídia) não pode abortar o atendimento
    # inteiro: só o documento não entregue sai da lista, e o assistente segue respondendo.
    doc = Documento(tenant_id=TENANT, nome="Boletim.pdf", categoria="boletim", url="http://x")
    uc = RecuperarEEnviarDocumento(
        source=FakeDocumentSource([doc]), canal=_CanalQueFalhaNoDoc()
    )

    entregues = await uc.executar(tenant_id=TENANT, contato="+551199", consulta="boletim")

    assert entregues == []  # nada entregue → nada é anunciado ao responsável
