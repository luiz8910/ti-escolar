"""Aplicação FastAPI: composição das rotas e middlewares."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import get_settings
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.factories import canal_efetivo
from app.infrastructure.logs import ColetorDeLogs, GravadorDeLogs, configurar_logging
from app.interfaces.api import (
    admin,
    atendimento_humano,
    avisos,
    broadcast,
    cadastro,
    comunicacao_interna,
    conhecimento,
    documentos,
    exportacao,
    faltas,
    fichas,
    impressao,
    logs,
    matricula,
    mediacao,
    mural,
    professor,
    progressao,
    respostas_rapidas,
    seguranca,
    templates,
    webhook,
)
from app.interfaces.middleware import ContextoRequisicaoMiddleware, registrar_handlers

settings = get_settings()

# Único texto do aviso, para o log do boot e o /health dizerem a mesma coisa.
_MOTIVO_CANAL_DEGRADADO = (
    "MESSAGE_CHANNEL=meta sem META_ACCESS_TOKEN: a aplicação subiu no canal demo. "
    "Nenhuma mensagem chega ao WhatsApp — o inbound é atendido, cobra LLM e a resposta "
    "se perde. Configure o token do usuário do sistema (docs/producao-whatsapp.md §4)."
)

_coletor = ColetorDeLogs(
    capacidade=settings.log_fila_capacidade,
    nivel_minimo=logging.getLevelName(settings.log_nivel_persistido.upper()),
)
_gravador = GravadorDeLogs(
    _coletor, SessionLocal, retencao_dias=settings.log_retencao_dias
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Sobe e desce o gravador de logs junto com a aplicação.

    O gravador precisa do event loop rodando (a fila é ``asyncio``), então não pode ser
    iniciado no import. E o encerramento drena o que sobrou: o log do erro que derrubou o
    processo é justamente o que não pode se perder no shutdown.
    """
    configurar_logging(nivel=settings.log_nivel, formato_json=settings.log_json)
    if settings.log_persistir:
        logging.getLogger().addHandler(_coletor)
        _gravador.iniciar()
    if canal_efetivo(settings) != settings.message_channel:
        # Um deploy que pede "meta" e recebe "demo" não falha em lugar nenhum: as mensagens
        # são aceitas e descartadas em memória. Gritar no boot é a única chance de alguém ver.
        logging.getLogger("canal").error(_MOTIVO_CANAL_DEGRADADO)
    try:
        yield
    finally:
        if settings.log_persistir:
            await _gravador.parar()
            logging.getLogger().removeHandler(_coletor)


app = FastAPI(
    title="TI-Escolar API",
    description="Chatbot escolar via WhatsApp — inbound (RAG + documentos) e outbound (broadcasts).",
    version="0.1.0",
    lifespan=lifespan,
)

# Contexto/observabilidade por dentro do CORS: adicionado primeiro, executa por último —
# assim o id de correlação e a duração cobrem o handler de verdade, não o preflight.
app.add_middleware(ContextoRequisicaoMiddleware)
registrar_handlers(app)

# "*" libera qualquer origem (útil em testes, antes de conhecer a URL final do front).
# Com curinga, credenciais por cookie ficam desabilitadas (o painel usa Bearer no header).
_origens = settings.cors_origins
if "*" in _origens:
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origens,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(broadcast.router)
app.include_router(admin.router)
app.include_router(cadastro.router)
app.include_router(conhecimento.router)
app.include_router(respostas_rapidas.router)
app.include_router(avisos.router)
app.include_router(impressao.router)
app.include_router(mural.router)
app.include_router(comunicacao_interna.router)
app.include_router(atendimento_humano.router)
app.include_router(documentos.router)
app.include_router(mediacao.router)
app.include_router(progressao.router)
app.include_router(professor.router)
app.include_router(faltas.router)
app.include_router(exportacao.router)
app.include_router(fichas.router)
app.include_router(matricula.router)
app.include_router(seguranca.router)
app.include_router(templates.router)
app.include_router(logs.router)
app.include_router(webhook.router)


@app.get("/health", tags=["infra"])
async def health() -> dict:
    """Liveness: o processo está de pé. Não toca no banco de propósito — se o Postgres
    cair, derrubar também o processo (que o Render reiniciaria em laço) só piora.

    ``canal`` é o adaptador **efetivo**, não o valor de ``MESSAGE_CHANNEL``: com a env em
    ``meta`` e sem token a aplicação sobe falando pelo canal demo, e ecoar a env aqui
    afirmaria que o WhatsApp está no ar enquanto nenhuma mensagem sai. Quando os dois
    divergem o corpo diz qual foi pedido e por quê caiu.
    """
    efetivo = canal_efetivo(settings)
    corpo = {"status": "ok", "llm": settings.llm_provider, "canal": efetivo}
    if efetivo != settings.message_channel:
        corpo["canal_configurado"] = settings.message_channel
        corpo["canal_alerta"] = _MOTIVO_CANAL_DEGRADADO
    return corpo


@app.get("/health/pronto", tags=["infra"])
async def prontidao() -> dict:
    """Readiness: a aplicação consegue **atender**, o que exige o banco.

    O ``/health`` sozinho dizia "ok" com o Neon inteiramente fora do ar — um verde que
    escondia a única dependência que derruba todas as funcionalidades.
    """
    try:
        async with SessionLocal() as session:
            await session.execute(text("SELECT 1"))
        banco = "ok"
    except Exception as erro:  # noqa: BLE001
        logging.getLogger("health").error("Banco indisponível: %s", erro)
        return {"status": "degradado", "banco": "indisponivel"}
    return {"status": "ok", "banco": banco}
