"""Casos de uso da base de conhecimento que a escola alimenta.

- Ingestão de documentos (texto) que enriquecem o contexto da LLM via RAG, por tenant.
- Gestão do system prompt personalizado por tenant (o "CLAUDE.md" da escola).

A camada de aplicação só orquestra as portas (``Embedder``, ``VectorStore``,
``FonteConhecimentoRepository`` e ``PromptTenantRepository``); sem framework/ORM/SDK.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import (
    FonteConhecimento,
    PromptTenant,
    TipoConhecimento,
    TrechoConhecimento,
)
from app.domain.ports import (
    Embedder,
    FonteConhecimentoRepository,
    PromptTenantRepository,
    VectorStore,
)


# --------------------------------------------------------------------------- #
# Fragmentação de texto
# --------------------------------------------------------------------------- #
def fragmentar(texto: str, *, max_chars: int = 800) -> list[str]:
    """Quebra um texto em trechos coesos para indexação.

    Agrupa parágrafos (separados por linha em branco) até ``max_chars``; parágrafos
    isolados maiores que o limite viram trechos próprios. Mantém o sentido sem cortar
    no meio de uma frase, o que melhora a recuperação no RAG.
    """
    paragrafos = [p.strip() for p in texto.split("\n\n") if p.strip()]
    trechos: list[str] = []
    atual = ""
    for p in paragrafos:
        if atual and len(atual) + len(p) + 2 > max_chars:
            trechos.append(atual)
            atual = p
        else:
            atual = f"{atual}\n\n{p}" if atual else p
    if atual:
        trechos.append(atual)
    return trechos


# --------------------------------------------------------------------------- #
# Ingestão de documentos (RAG por tenant)
# --------------------------------------------------------------------------- #
class IngerirDocumento:
    """Recebe um documento da escola, fragmenta, indexa e registra a fonte.

    Cada trecho referencia a ``FonteConhecimento`` para permitir gestão (listar/remover)
    sem perder a rastreabilidade. Tudo escopado por ``tenant_id``.
    """

    def __init__(
        self,
        *,
        embedder: Embedder,
        store: VectorStore,
        fontes: FonteConhecimentoRepository,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self._fontes = fontes

    async def executar(
        self,
        *,
        tenant_id: UUID,
        nome: str,
        conteudo: str,
        tipo: TipoConhecimento = TipoConhecimento.PROCEDIMENTO,
    ) -> FonteConhecimento:
        nome = nome.strip()
        if not nome:
            raise ValueError("O documento precisa de um nome.")
        trechos_texto = fragmentar(conteudo)
        if not trechos_texto:
            raise ValueError("O documento está vazio.")

        fonte = FonteConhecimento(
            tenant_id=tenant_id, nome=nome, tipo=tipo, total_trechos=len(trechos_texto)
        )
        await self._fontes.criar(fonte)

        embeddings = await self._embedder.embed([f"{nome}\n{t}" for t in trechos_texto])
        for texto, embedding in zip(trechos_texto, embeddings):
            trecho = TrechoConhecimento(
                tenant_id=tenant_id,
                tipo=tipo,
                titulo=nome,
                conteudo=texto,
                fonte_id=fonte.id,
            )
            await self._store.indexar(trecho, embedding)
        return fonte


class ListarFontesConhecimento:
    def __init__(self, *, fontes: FonteConhecimentoRepository) -> None:
        self._fontes = fontes

    async def executar(self, *, tenant_id: UUID) -> list[FonteConhecimento]:
        return await self._fontes.listar(tenant_id=tenant_id)


class RemoverFonteConhecimento:
    """Remove um documento e todos os seus trechos indexados (RAG) do tenant."""

    def __init__(
        self, *, fontes: FonteConhecimentoRepository, store: VectorStore
    ) -> None:
        self._fontes = fontes
        self._store = store

    async def executar(self, *, tenant_id: UUID, fonte_id: UUID) -> bool:
        await self._store.remover_por_fonte(tenant_id=tenant_id, fonte_id=fonte_id)
        return await self._fontes.remover(tenant_id=tenant_id, fonte_id=fonte_id)


# --------------------------------------------------------------------------- #
# System prompt personalizado por tenant
# --------------------------------------------------------------------------- #
class ObterPromptTenant:
    def __init__(self, *, prompts: PromptTenantRepository) -> None:
        self._prompts = prompts

    async def executar(self, *, tenant_id: UUID) -> PromptTenant:
        prompt = await self._prompts.obter(tenant_id=tenant_id)
        return prompt or PromptTenant(tenant_id=tenant_id, conteudo="")


class DefinirPromptTenant:
    def __init__(self, *, prompts: PromptTenantRepository) -> None:
        self._prompts = prompts

    async def executar(self, *, tenant_id: UUID, conteudo: str) -> PromptTenant:
        return await self._prompts.salvar(tenant_id=tenant_id, conteudo=conteudo)
