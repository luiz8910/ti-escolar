"""Observabilidade: coleta de logs, id de correlação e tratamento de erro (§16).

O que se verifica aqui é o que torna o painel confiável: que o log **não** bloqueia a
requisição, que ele carrega o id que amarra as linhas de um mesmo erro, e que uma exceção
não tratada vira um 500 com esse id — em vez do 500 mudo de antes, impossível de rastrear.
"""

from __future__ import annotations

import asyncio
import logging

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.application.logs_use_cases import (
    POR_PAGINA_MAXIMO,
    POR_PAGINA_PADRAO,
    PaginaDeLogs,
    normalizar_paginacao,
)
from app.domain.entities import ContagemRotulada, NivelLog, ResumoLogs
from app.infrastructure.logs import ColetorDeLogs, correlacao_atual, novo_id_correlacao
from app.interfaces.middleware import (
    CABECALHO_CORRELACAO,
    ContextoRequisicaoMiddleware,
    registrar_handlers,
)


# --------------------------------------------------------------------------- #
# Coletor
# --------------------------------------------------------------------------- #
def _registro_de(coletor: ColetorDeLogs):
    return coletor.fila.get_nowait()


@pytest.mark.asyncio
async def test_coletor_enfileira_sem_tocar_no_banco():
    """`emit` roda no meio da requisição: tudo que ele pode fazer é operação de memória."""
    coletor = ColetorDeLogs()
    logger = logging.getLogger("teste.coletor")
    logger.addHandler(coletor)
    logger.setLevel(logging.INFO)
    try:
        logger.warning("algo estranho aconteceu")
    finally:
        logger.removeHandler(coletor)

    registro = _registro_de(coletor)
    assert registro.nivel is NivelLog.WARNING
    assert registro.mensagem == "algo estranho aconteceu"
    assert registro.logger == "teste.coletor"


@pytest.mark.asyncio
async def test_coletor_ignora_debug_e_loggers_ruidosos():
    """DEBUG é ruído de desenvolvimento; `sqlalchemy.engine` sozinho encheria a tabela."""
    coletor = ColetorDeLogs(nivel_minimo=logging.DEBUG)

    ruidoso = logging.getLogger("sqlalchemy.engine.Engine")
    ruidoso.addHandler(coletor)
    ruidoso.setLevel(logging.DEBUG)
    quieto = logging.getLogger("teste.debug")
    quieto.addHandler(coletor)
    quieto.setLevel(logging.DEBUG)
    try:
        ruidoso.info("SELECT 1")
        quieto.debug("detalhe interno")
    finally:
        ruidoso.removeHandler(coletor)
        quieto.removeHandler(coletor)

    assert coletor.fila.empty()


@pytest.mark.asyncio
async def test_coletor_captura_o_id_de_correlacao_do_contexto():
    """É isso que amarra a linha do caso de uso à requisição que a originou."""
    coletor = ColetorDeLogs()
    logger = logging.getLogger("teste.correlacao")
    logger.addHandler(coletor)
    logger.setLevel(logging.INFO)
    token = correlacao_atual.set("abc123def456")
    try:
        logger.error("falhou")
    finally:
        correlacao_atual.reset(token)
        logger.removeHandler(coletor)

    assert _registro_de(coletor).correlacao_id == "abc123def456"


@pytest.mark.asyncio
async def test_fila_cheia_descarta_o_mais_antigo_e_nunca_bloqueia():
    """Perder log é ruim; travar o atendimento de um responsável para gravar log é pior."""
    coletor = ColetorDeLogs(capacidade=2)
    logger = logging.getLogger("teste.fila")
    logger.addHandler(coletor)
    logger.setLevel(logging.INFO)
    try:
        for i in range(5):
            logger.info("mensagem %d", i)
    finally:
        logger.removeHandler(coletor)

    assert coletor.fila.qsize() == 2
    assert coletor.descartados == 3
    # Sobraram as MAIS RECENTES — que são as que interessam durante um incidente.
    restantes = [_registro_de(coletor).mensagem for _ in range(2)]
    assert restantes == ["mensagem 3", "mensagem 4"]


@pytest.mark.asyncio
async def test_registro_defeituoso_nao_propaga_excecao():
    """Logging jamais pode ser a causa de um erro na requisição: um formato inválido
    (`%d` com texto) tem que morrer dentro do handler, não subir para quem chamou."""
    coletor = ColetorDeLogs()
    record = logging.LogRecord(
        name="teste.robusto",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="valor %d",
        args=("não é número",),
        exc_info=None,
    )
    coletor.handleError = lambda _record: None  # silencia o aviso no stderr do teste

    coletor.emit(record)  # não levanta

    assert coletor.fila.empty()


@pytest.mark.asyncio
async def test_excecao_vira_traceback_no_registro():
    coletor = ColetorDeLogs()
    logger = logging.getLogger("teste.excecao")
    logger.addHandler(coletor)
    logger.setLevel(logging.INFO)
    try:
        try:
            raise ValueError("banco fora do ar")
        except ValueError:
            logger.exception("falha ao gravar")
    finally:
        logger.removeHandler(coletor)

    registro = _registro_de(coletor)
    assert "ValueError: banco fora do ar" in registro.excecao
    assert registro.falha


def test_id_de_correlacao_e_curto_e_unico():
    """Curto o bastante para ser lido ao telefone por quem relata o erro."""
    ids = {novo_id_correlacao() for _ in range(500)}
    assert len(ids) == 500
    assert all(len(i) == 12 for i in ids)


# --------------------------------------------------------------------------- #
# Paginação
# --------------------------------------------------------------------------- #
def test_paginacao_tem_teto_e_piso():
    # Ausente ou zero = não informado, cai no padrão.
    assert normalizar_paginacao(None, None) == (1, POR_PAGINA_PADRAO)
    assert normalizar_paginacao(0, 0) == (1, POR_PAGINA_PADRAO)
    # Valores hostis: página negativa vira 1, e o teto impede que um ?por_pagina=10000
    # transforme a tela de diagnóstico no próximo incidente.
    assert normalizar_paginacao(-5, 10_000) == (1, POR_PAGINA_MAXIMO)
    assert normalizar_paginacao(3, -1) == (3, 1)


def test_total_de_paginas_arredonda_para_cima():
    pagina = PaginaDeLogs(itens=[], total=21, pagina=1, por_pagina=10, loggers=[])
    assert pagina.total_paginas == 3
    vazia = PaginaDeLogs(itens=[], total=0, pagina=1, por_pagina=10, loggers=[])
    assert vazia.total_paginas == 1


# --------------------------------------------------------------------------- #
# Resumo
# --------------------------------------------------------------------------- #
def _resumo(**over) -> ResumoLogs:
    base = dict(
        janela_horas=24,
        total=100,
        erros=0,
        alertas=2,
        requisicoes=80,
        duracao_media_ms=45,
        duracao_p95_ms=210,
        atendimentos_concluidos=12,
        atendimentos_em_andamento=1,
        atendimentos_falhos=0,
        rotas_mais_lentas=[ContagemRotulada(rotulo="/api/admin/logs", quantidade=210)],
        erros_mais_comuns=[],
    )
    base.update(over)
    return ResumoLogs(**base)


def test_resumo_saudavel_exige_zero_erro_e_zero_atendimento_falho():
    assert _resumo().saudavel
    assert not _resumo(erros=1).saudavel
    # Atendimento falho não aparece como erro HTTP, mas é falha de produto: o responsável
    # mandou mensagem e não foi respondido.
    assert not _resumo(atendimentos_falhos=1).saudavel


def test_taxa_de_erro_nao_divide_por_zero():
    assert _resumo(requisicoes=0, erros=3).taxa_erro_percentual == 0.0
    assert _resumo(requisicoes=200, erros=3).taxa_erro_percentual == 1.5


# --------------------------------------------------------------------------- #
# Middleware / handlers de erro
# --------------------------------------------------------------------------- #
def _app_de_teste() -> FastAPI:
    app = FastAPI()
    app.add_middleware(ContextoRequisicaoMiddleware)
    registrar_handlers(app)

    router = APIRouter()

    @router.get("/ok")
    async def ok():
        return {"ok": True}

    @router.get("/explode")
    async def explode():
        raise RuntimeError("coluna inexistente")

    app.include_router(router)
    return app


def test_toda_resposta_carrega_o_id_de_correlacao():
    with TestClient(_app_de_teste()) as client:
        resp = client.get("/ok")
    assert resp.status_code == 200
    assert len(resp.headers[CABECALHO_CORRELACAO]) == 12


def test_id_enviado_pelo_proxy_e_preservado():
    """O Render/CDN já emite um X-Request-Id; gerar outro quebraria o rastro ponta a ponta."""
    with TestClient(_app_de_teste()) as client:
        resp = client.get("/ok", headers={CABECALHO_CORRELACAO: "id-do-proxy"})
    assert resp.headers[CABECALHO_CORRELACAO] == "id-do-proxy"


def test_erro_nao_tratado_vira_500_com_id_e_sem_stack_trace():
    """Antes: 500 mudo do FastAPI, nada para rastrear. Agora: id para o suporte cruzar
    com o log — e o traceback fica no log, nunca na resposta."""
    with TestClient(_app_de_teste(), raise_server_exceptions=False) as client:
        resp = client.get("/explode")

    assert resp.status_code == 500
    corpo = resp.json()
    assert corpo["id_correlacao"]
    assert corpo["id_correlacao"] == resp.headers[CABECALHO_CORRELACAO]
    assert "RuntimeError" not in resp.text
    assert "coluna inexistente" not in resp.text


def test_404_tambem_traz_o_id():
    with TestClient(_app_de_teste()) as client:
        resp = client.get("/rota-que-nao-existe")
    assert resp.status_code == 404
    assert resp.json()["id_correlacao"]


@pytest.mark.asyncio
async def test_contexto_nao_vaza_entre_requisicoes():
    """ContextVar sujo faria o log de uma requisição herdar o id de outra."""
    app = _app_de_teste()
    with TestClient(app) as client:
        primeiro = client.get("/ok").headers[CABECALHO_CORRELACAO]
        segundo = client.get("/ok").headers[CABECALHO_CORRELACAO]
    assert primeiro != segundo
    await asyncio.sleep(0)
    assert correlacao_atual.get("") == ""
