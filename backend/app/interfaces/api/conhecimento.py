"""Rotas da base de conhecimento por tenant.

Dois recursos, ambos escopados por tenant e reaproveitando a autenticação do módulo
``admin`` (cabeçalhos ``X-User-Email`` / ``X-User-Senha``):

1. **Documentos (RAG):** a escola sobe textos/arquivos de procedimentos que são
   fragmentados e indexados no vector store, enriquecendo o contexto da LLM.
2. **System prompt do tenant:** um "CLAUDE.md" personalizado por escola, anexado às
   diretrizes do assistente.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.conhecimento_use_cases import (
    DefinirPromptTenant,
    IngerirDocumento,
    ListarFontesConhecimento,
    ObterPromptTenant,
    RemoverFonteConhecimento,
)
from app.domain.entities import FonteConhecimento, TipoConhecimento, Usuario
from app.infrastructure.db.pgvector_store import PgVectorStore
from app.infrastructure.db.repositories_conhecimento import (
    SqlFonteConhecimentoRepository,
    SqlPromptTenantRepository,
)
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import (
    get_fonte_conhecimento_repo,
    get_ingerir_documento,
    get_prompt_tenant_repo,
    get_session,
)
from app.interfaces.dto import (
    DocumentoConhecimentoEntrada,
    FonteConhecimentoSaida,
    PromptTenantEntrada,
    PromptTenantSaida,
)

router = APIRouter(prefix="/api/admin", tags=["conhecimento"])


def _fonte_saida(f: FonteConhecimento) -> FonteConhecimentoSaida:
    return FonteConhecimentoSaida(
        id=f.id,
        nome=f.nome,
        tipo=f.tipo.value,
        total_trechos=f.total_trechos,
        criado_em=f.criado_em,
    )


def _parse_tipo(tipo: str) -> TipoConhecimento:
    try:
        return TipoConhecimento(tipo)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo inválido: {tipo}. Use procedimento, aviso ou faq.",
        ) from e


# --------------------------------------------------------------------------- #
# Documentos (RAG)
# --------------------------------------------------------------------------- #
@router.post(
    "/conhecimento",
    response_model=FonteConhecimentoSaida,
    status_code=status.HTTP_201_CREATED,
)
async def adicionar_conhecimento(
    payload: DocumentoConhecimentoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    uc: IngerirDocumento = Depends(get_ingerir_documento),
) -> FonteConhecimentoSaida:
    """Ingestão de um documento colado como texto."""
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        fonte = await uc.executar(
            tenant_id=payload.tenant_id,
            nome=payload.nome,
            conteudo=payload.conteudo,
            tipo=_parse_tipo(payload.tipo),
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _fonte_saida(fonte)


@router.get("/conhecimento/tenant/{tenant_id}", response_model=list[FonteConhecimentoSaida])
async def listar_conhecimento(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    fontes: SqlFonteConhecimentoRepository = Depends(get_fonte_conhecimento_repo),
) -> list[FonteConhecimentoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    return [
        _fonte_saida(f)
        for f in await ListarFontesConhecimento(fontes=fontes).executar(tenant_id=tenant_id)
    ]


@router.delete("/conhecimento/{fonte_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_conhecimento(
    fonte_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    fontes: SqlFonteConhecimentoRepository = Depends(get_fonte_conhecimento_repo),
    session=Depends(get_session),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    remover = RemoverFonteConhecimento(fontes=fontes, store=PgVectorStore(session))
    if not await remover.executar(tenant_id=tenant_id, fonte_id=fonte_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado")


# --------------------------------------------------------------------------- #
# System prompt do tenant
# --------------------------------------------------------------------------- #
@router.get("/prompt/tenant/{tenant_id}", response_model=PromptTenantSaida)
async def obter_prompt(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    prompts: SqlPromptTenantRepository = Depends(get_prompt_tenant_repo),
) -> PromptTenantSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    prompt = await ObterPromptTenant(prompts=prompts).executar(tenant_id=tenant_id)
    return PromptTenantSaida(
        tenant_id=tenant_id, conteudo=prompt.conteudo, atualizado_em=prompt.atualizado_em
    )


@router.put("/prompt", response_model=PromptTenantSaida)
async def definir_prompt(
    payload: PromptTenantEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    prompts: SqlPromptTenantRepository = Depends(get_prompt_tenant_repo),
) -> PromptTenantSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    prompt = await DefinirPromptTenant(prompts=prompts).executar(
        tenant_id=payload.tenant_id, conteudo=payload.conteudo
    )
    return PromptTenantSaida(
        tenant_id=prompt.tenant_id, conteudo=prompt.conteudo, atualizado_em=prompt.atualizado_em
    )
