"""Testa o atendimento inbound orquestrado por agente (tool use).

O agente decide, via ferramentas, entre responder dúvida e recuperar documento — sem
roteamento por palavra-chave. O ``FakeLLM`` é roteirizado (uma ``RespostaLLM`` por iteração)
para tornar a decisão determinística.
"""

from __future__ import annotations

import uuid

from app.application.use_cases import AtenderConversa, RecuperarEEnviarDocumento
from app.domain.entities import (
    ChamadaFerramenta,
    Documento,
    RespostaLLM,
    TipoConhecimento,
    TrechoConhecimento,
)
from tests.fakes import (
    FakeChannel,
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()


async def _store_com_trecho(titulo: str, conteudo: str) -> FakeVectorStore:
    store = FakeVectorStore()
    embedder = fake_embedder()
    trecho = TrechoConhecimento(
        tenant_id=TENANT, tipo=TipoConhecimento.FAQ, titulo=titulo, conteudo=conteudo
    )
    [emb] = await embedder.embed([f"{titulo}\n{conteudo}"])
    await store.indexar(trecho, emb)
    return store


def _montar(*, store, documentos, respostas):
    canal = FakeChannel()
    docs_uc = RecuperarEEnviarDocumento(source=FakeDocumentSource(documentos), canal=canal)
    uc = AtenderConversa(
        conversas=FakeConversaRepo(),
        embedder=fake_embedder(),
        store=store,
        llm=FakeLLM(respostas),
        documentos=docs_uc,
    )
    return uc, canal


async def test_duvida_usa_conhecimento_e_cita_fonte():
    store = await _store_com_trecho("Horário de funcionamento", "Das 7h às 12h.")
    # Iteração 1: agente busca conhecimento. Iteração 2: responde com base no trecho.
    respostas = [
        RespostaLLM(
            chamadas=[
                ChamadaFerramenta(
                    id="c1", nome="buscar_conhecimento", argumentos={"consulta": "horário"}
                )
            ]
        ),
        RespostaLLM(texto="A escola funciona das 7h às 12h. [Horário de funcionamento]"),
    ]
    uc, canal = _montar(store=store, documentos=[], respostas=respostas)

    resp = await uc.executar(tenant_id=TENANT, contato="+551199", texto="Qual o horário?")

    assert resp.documentos == []
    assert canal.enviados == []  # nenhuma busca de documento
    assert "Horário de funcionamento" in resp.fontes  # fonte citada veio da ferramenta


async def test_pedido_explicito_recupera_documento():
    doc = Documento(tenant_id=TENANT, nome="Boletim.pdf", categoria="boletim", url="http://x")
    respostas = [
        RespostaLLM(
            chamadas=[
                ChamadaFerramenta(
                    id="c1", nome="recuperar_documento", argumentos={"consulta": "boletim"}
                )
            ]
        ),
        RespostaLLM(texto="Enviei o boletim para você."),
    ]
    uc, canal = _montar(store=FakeVectorStore(), documentos=[doc], respostas=respostas)

    resp = await uc.executar(
        tenant_id=TENANT, contato="+551199", texto="Quero a segunda via do meu boletim"
    )

    assert len(resp.documentos) == 1
    assert canal.enviados == [("+551199", "documento")]


async def test_frase_ambigua_sem_palavra_chave_recupera_documento():
    """Caso que o roteador por palavra-chave (``_GATILHOS_DOC``) erra: 'ver as notas' não
    contém nenhum gatilho, mas o agente decide recuperar o documento."""
    doc = Documento(tenant_id=TENANT, nome="Boletim.pdf", categoria="boletim", url="http://x")
    respostas = [
        RespostaLLM(
            chamadas=[
                ChamadaFerramenta(
                    id="c1", nome="recuperar_documento", argumentos={"consulta": "notas"}
                )
            ]
        ),
        RespostaLLM(texto="Segue o boletim com as notas."),
    ]
    uc, canal = _montar(store=FakeVectorStore(), documentos=[doc], respostas=respostas)

    resp = await uc.executar(
        tenant_id=TENANT, contato="+551199", texto="quero ver as notas da minha filha"
    )

    assert len(resp.documentos) == 1
    assert canal.enviados == [("+551199", "documento")]


async def test_limite_de_iteracoes_encerra_com_cortesia():
    # Agente sempre pede ferramenta, nunca conclui: o loop deve cortar e responder com cortesia.
    respostas = [
        RespostaLLM(
            chamadas=[
                ChamadaFerramenta(
                    id=f"c{i}", nome="buscar_conhecimento", argumentos={"consulta": "x"}
                )
            ]
        )
        for i in range(8)
    ]
    uc, _ = _montar(store=FakeVectorStore(), documentos=[], respostas=respostas)

    resp = await uc.executar(tenant_id=TENANT, contato="+551199", texto="oi")

    assert "secretaria" in resp.texto.lower()
