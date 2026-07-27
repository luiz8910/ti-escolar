"""Rotas de chat (inbound): REST e WebSocket usadas pelo demo Next.js.

**São públicas por desenho** — o demo é a vitrine do produto e não tem login. O preço disso é
que elas gravam conversa real e consomem LLM do ``tenant_id`` recebido; apontá-las para uma
escola de verdade poluiria o histórico dela e queimaria a cota de graça. Por isso o acesso é
limitado ao **tenant de vitrine** (`CHAT_DEMO_TENANT_ID`) e o demo inteiro pode ser desligado
em produção com `CHAT_DEMO_HABILITADO=false`.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from app.application.use_cases import (
    AtenderConversa,
    RecuperarEEnviarDocumento,
)
from app.config import get_settings
from app.infrastructure.db.pgvector_store import PgVectorStore
from app.infrastructure.db.repositories import SqlConversaRepository
from app.infrastructure.db.repositories_admin import SqlAuditLogRepository
from app.infrastructure.db.repositories_comunicacao import SqlAvisoTemporizadoRepository
from app.infrastructure.db.repositories_conhecimento import SqlPromptTenantRepository
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.documents.mock_source import MockDocumentSource
from app.infrastructure.factories import criar_canal, criar_embedder, criar_llm
from app.interfaces.deps import get_atender_conversa
from app.interfaces.dto import DocumentoSaida, MensagemEntrada, MensagemSaida

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _demo_liberado(tenant_id: UUID) -> bool:
    """O demo só atende o tenant de vitrine, e só enquanto estiver habilitado."""
    settings = get_settings()
    if not settings.chat_demo_habilitado:
        return False
    try:
        return tenant_id == UUID(settings.chat_demo_tenant_id)
    except ValueError:  # id de vitrine mal configurado: fecha em vez de abrir
        return False


@router.post("/mensagens", response_model=MensagemSaida)
async def enviar_mensagem(
    payload: MensagemEntrada,
    uc: AtenderConversa = Depends(get_atender_conversa),
) -> MensagemSaida:
    if not _demo_liberado(payload.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="O chat de demonstração atende apenas o tenant de vitrine.",
        )
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
        avisos=SqlAvisoTemporizadoRepository(session),
    )


@router.websocket("/ws/{tenant_id}/{contato}")
async def chat_ws(websocket: WebSocket, tenant_id: UUID, contato: str) -> None:
    if not _demo_liberado(tenant_id):
        # Fecha antes do accept: o handshake é recusado e nenhuma sessão é aberta.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
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
