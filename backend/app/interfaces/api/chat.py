"""Rotas de chat (inbound): REST e WebSocket usadas pelo demo Next.js."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.application.use_cases import (
    AtenderConversa,
    RecuperarEEnviarDocumento,
)
from app.config import get_settings
from app.infrastructure.db.pgvector_store import PgVectorStore
from app.infrastructure.db.repositories import SqlConversaRepository
from app.infrastructure.db.repositories_admin import SqlAuditLogRepository
from app.infrastructure.db.repositories_conhecimento import SqlPromptTenantRepository
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.documents.mock_source import MockDocumentSource
from app.infrastructure.factories import criar_canal, criar_embedder, criar_llm
from app.interfaces.deps import get_atender_conversa
from app.interfaces.dto import DocumentoSaida, MensagemEntrada, MensagemSaida

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/mensagens", response_model=MensagemSaida)
async def enviar_mensagem(
    payload: MensagemEntrada,
    uc: AtenderConversa = Depends(get_atender_conversa),
) -> MensagemSaida:
    resultado = await uc.executar(
        tenant_id=payload.tenant_id, contato=payload.contato, texto=payload.texto
    )
    return MensagemSaida(
        texto=resultado.texto,
        fontes=resultado.fontes,
        documentos=[
            DocumentoSaida(nome=d.nome, categoria=d.categoria, url=d.url)
            for d in resultado.documentos
        ],
    )


def _montar_uc(session) -> AtenderConversa:
    settings = get_settings()
    documentos = RecuperarEEnviarDocumento(
        source=MockDocumentSource(), canal=criar_canal(settings)
    )
    return AtenderConversa(
        conversas=SqlConversaRepository(session),
        embedder=criar_embedder(settings),
        store=PgVectorStore(session),
        llm=criar_llm(settings),
        documentos=documentos,
        prompts=SqlPromptTenantRepository(session),
        auditoria=SqlAuditLogRepository(session),
    )


@router.websocket("/ws/{tenant_id}/{contato}")
async def chat_ws(websocket: WebSocket, tenant_id: UUID, contato: str) -> None:
    await websocket.accept()
    try:
        while True:
            texto = await websocket.receive_text()
            async with SessionLocal() as session:
                uc = _montar_uc(session)
                resultado = await uc.executar(
                    tenant_id=tenant_id, contato=contato, texto=texto
                )
                await session.commit()
            await websocket.send_json(
                {
                    "texto": resultado.texto,
                    "fontes": resultado.fontes,
                    "documentos": [
                        {"nome": d.nome, "categoria": d.categoria, "url": d.url}
                        for d in resultado.documentos
                    ],
                }
            )
    except WebSocketDisconnect:
        return
