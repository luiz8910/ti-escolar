"""Aplicação FastAPI: composição das rotas e middlewares."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.interfaces.api import admin, broadcast, chat, webhook

settings = get_settings()

app = FastAPI(
    title="TI-Escolar API",
    description="Chatbot escolar via WhatsApp — inbound (RAG + documentos) e outbound (broadcasts).",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router)
app.include_router(broadcast.router)
app.include_router(admin.router)
app.include_router(webhook.router)


@app.get("/health", tags=["infra"])
async def health() -> dict:
    return {"status": "ok", "llm": settings.llm_provider, "canal": settings.message_channel}
