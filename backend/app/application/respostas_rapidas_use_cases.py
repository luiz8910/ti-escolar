"""Casos de uso das respostas rápidas ("atalhos") da escola.

As respostas rápidas são a base de conhecimento pronta da secretaria (ex.: os atalhos
do WhatsApp). Cada uma é **ingerida na base de RAG** do tenant para que o bot responda
automaticamente; ``fonte_id`` liga a resposta rápida à ``FonteConhecimento`` gerada,
permitindo reindexar (ao editar) e remover os trechos (ao apagar/desativar).

A camada de aplicação só orquestra as portas (``RespostaRapidaRepository``,
``Embedder``, ``VectorStore`` e ``FonteConhecimentoRepository``); sem framework/ORM/SDK.
"""

from __future__ import annotations

from uuid import UUID

from app.application.conhecimento_use_cases import (
    IngerirDocumento,
    RemoverFonteConhecimento,
)
from app.domain.entities import RespostaRapida, TipoConhecimento, _now
from app.domain.ports import (
    Embedder,
    FonteConhecimentoRepository,
    RespostaRapidaRepository,
    VectorStore,
)


class _IndexadorRespostaRapida:
    """Ponte com o RAG: indexa/remove o conteúdo de uma resposta rápida por ``fonte_id``."""

    def __init__(
        self,
        *,
        embedder: Embedder,
        store: VectorStore,
        fontes: FonteConhecimentoRepository,
    ) -> None:
        self._ingerir = IngerirDocumento(embedder=embedder, store=store, fontes=fontes)
        self._remover = RemoverFonteConhecimento(fontes=fontes, store=store)

    async def indexar(self, resposta: RespostaRapida) -> UUID:
        """Ingere o conteúdo no RAG e devolve o ``fonte_id`` gerado."""
        fonte = await self._ingerir.executar(
            tenant_id=resposta.tenant_id,
            nome=resposta.chave,
            conteudo=resposta.conteudo,
            tipo=TipoConhecimento.FAQ,
        )
        return fonte.id

    async def remover(self, resposta: RespostaRapida) -> None:
        if resposta.fonte_id is not None:
            await self._remover.executar(
                tenant_id=resposta.tenant_id, fonte_id=resposta.fonte_id
            )


class CriarRespostaRapida:
    """Cadastra uma resposta rápida e, se ativa, a indexa no RAG do tenant."""

    def __init__(
        self,
        *,
        respostas: RespostaRapidaRepository,
        embedder: Embedder,
        store: VectorStore,
        fontes: FonteConhecimentoRepository,
    ) -> None:
        self._respostas = respostas
        self._rag = _IndexadorRespostaRapida(embedder=embedder, store=store, fontes=fontes)

    async def executar(
        self, *, tenant_id: UUID, chave: str, conteudo: str, ativo: bool = True
    ) -> RespostaRapida:
        chave = chave.strip()
        conteudo = conteudo.strip()
        if not chave:
            raise ValueError("A resposta rápida precisa de uma chave.")
        if not conteudo:
            raise ValueError("A resposta rápida precisa de um conteúdo.")
        if await self._respostas.por_chave(tenant_id=tenant_id, chave=chave):
            raise ValueError("Já existe uma resposta rápida com esta chave neste tenant.")

        resposta = RespostaRapida(
            tenant_id=tenant_id, chave=chave, conteudo=conteudo, ativo=ativo
        )
        if ativo:
            resposta.fonte_id = await self._rag.indexar(resposta)
        return await self._respostas.criar(resposta)


class ListarRespostasRapidas:
    def __init__(self, *, respostas: RespostaRapidaRepository) -> None:
        self._respostas = respostas

    async def executar(self, *, tenant_id: UUID) -> list[RespostaRapida]:
        return await self._respostas.listar(tenant_id=tenant_id)


class ObterRespostaRapida:
    def __init__(self, *, respostas: RespostaRapidaRepository) -> None:
        self._respostas = respostas

    async def executar(self, *, tenant_id: UUID, resposta_id: UUID) -> RespostaRapida:
        resposta = await self._respostas.obter(tenant_id=tenant_id, resposta_id=resposta_id)
        if resposta is None:
            raise ValueError("Resposta rápida não encontrada para o tenant.")
        return resposta


class AtualizarRespostaRapida:
    """Edita uma resposta rápida e **reindexa** o RAG conforme o novo conteúdo/estado.

    Como o texto muda, sempre removemos os trechos antigos e, se ficar ativa, indexamos
    de novo (gerando um novo ``fonte_id``).
    """

    def __init__(
        self,
        *,
        respostas: RespostaRapidaRepository,
        embedder: Embedder,
        store: VectorStore,
        fontes: FonteConhecimentoRepository,
    ) -> None:
        self._respostas = respostas
        self._rag = _IndexadorRespostaRapida(embedder=embedder, store=store, fontes=fontes)

    async def executar(
        self,
        *,
        tenant_id: UUID,
        resposta_id: UUID,
        chave: str,
        conteudo: str,
        ativo: bool = True,
    ) -> RespostaRapida:
        atual = await self._respostas.obter(tenant_id=tenant_id, resposta_id=resposta_id)
        if atual is None:
            raise ValueError("Resposta rápida não encontrada para o tenant.")
        chave = chave.strip()
        conteudo = conteudo.strip()
        if not chave:
            raise ValueError("A resposta rápida precisa de uma chave.")
        if not conteudo:
            raise ValueError("A resposta rápida precisa de um conteúdo.")
        if chave != atual.chave:
            existente = await self._respostas.por_chave(tenant_id=tenant_id, chave=chave)
            if existente is not None and existente.id != resposta_id:
                raise ValueError("Já existe uma resposta rápida com esta chave neste tenant.")

        # Reindexação: remove o conteúdo antigo do RAG e indexa o novo (se ativa).
        await self._rag.remover(atual)
        atual.chave = chave
        atual.conteudo = conteudo
        atual.ativo = ativo
        atual.atualizado_em = _now()
        atual.fonte_id = await self._rag.indexar(atual) if ativo else None
        return await self._respostas.atualizar(atual)


class RemoverRespostaRapida:
    """Remove a resposta rápida e os trechos que ela indexou no RAG."""

    def __init__(
        self,
        *,
        respostas: RespostaRapidaRepository,
        embedder: Embedder,
        store: VectorStore,
        fontes: FonteConhecimentoRepository,
    ) -> None:
        self._respostas = respostas
        self._rag = _IndexadorRespostaRapida(embedder=embedder, store=store, fontes=fontes)

    async def executar(self, *, tenant_id: UUID, resposta_id: UUID) -> bool:
        atual = await self._respostas.obter(tenant_id=tenant_id, resposta_id=resposta_id)
        if atual is None:
            return False
        await self._rag.remover(atual)
        return await self._respostas.remover(tenant_id=tenant_id, resposta_id=resposta_id)
