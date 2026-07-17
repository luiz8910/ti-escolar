"""Aplicação FastAPI: composição das rotas e middlewares."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.interfaces.api import (
    admin,
    avisos,
    broadcast,
    cadastro,
    chat,
    comunicacao_interna,
    conhecimento,
    impressao,
    mediacao,
    mural,
    professor,
    progressao,
    respostas_rapidas,
    webhook,
    webhook_twilio,
)

settings = get_settings()

app = FastAPI(
    title="TI-Escolar API",
    description="Chatbot escolar via WhatsApp — inbound (RAG + documentos) e outbound (broadcasts).",
    version="0.1.0",
)

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

app.include_router(chat.router)
app.include_router(broadcast.router)
app.include_router(admin.router)
app.include_router(cadastro.router)
app.include_router(conhecimento.router)
app.include_router(respostas_rapidas.router)
app.include_router(avisos.router)
app.include_router(impressao.router)
app.include_router(mural.router)
app.include_router(comunicacao_interna.router)
app.include_router(mediacao.router)
app.include_router(progressao.router)
app.include_router(professor.router)
app.include_router(webhook.router)
app.include_router(webhook_twilio.router)


@app.get("/health", tags=["infra"])
async def health() -> dict:
    return {"status": "ok", "llm": settings.llm_provider, "canal": settings.message_channel}
