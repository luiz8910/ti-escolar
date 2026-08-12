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
class _IndexadorFonte:
    """Sincroniza o vector store com o estado atual de uma ``FonteConhecimento``.

    Sempre apaga os trechos da fonte antes de reindexar. Reindexação incremental
    (comparar trecho a trecho) economizaria embeddings, mas deixaria lixo no store
    quando o texto encurtasse — e trecho órfão no RAG é resposta errada ao responsável,
    que custa mais caro que reembeddar um documento de procedimentos.

    Fonte **inativa** fica com zero trechos indexados: é o que "desativar" significa.
    """

    def __init__(self, *, embedder: Embedder, store: VectorStore) -> None:
        self._embedder = embedder
        self._store = store

    async def sincronizar(self, fonte: FonteConhecimento) -> None:
        await self._store.remover_por_fonte(
            tenant_id=fonte.tenant_id, fonte_id=fonte.id
        )
        if not fonte.ativo:
            return
        trechos_texto = fragmentar(fonte.conteudo)
        if not trechos_texto:
            return
        embeddings = await self._embedder.embed(
            [f"{fonte.nome}\n{t}" for t in trechos_texto]
        )
        for texto, embedding in zip(trechos_texto, embeddings):
            await self._store.indexar(
                TrechoConhecimento(
                    tenant_id=fonte.tenant_id,
                    tipo=fonte.tipo,
                    titulo=fonte.nome,
                    conteudo=texto,
                    fonte_id=fonte.id,
                ),
                embedding,
            )


class IngerirDocumento:
    """Recebe um documento da escola, fragmenta, indexa e registra a fonte.

    Cada trecho referencia a ``FonteConhecimento`` para permitir gestão (listar/editar/
    remover) sem perder a rastreabilidade. Tudo escopado por ``tenant_id``.
    """

    def __init__(
        self,
        *,
        embedder: Embedder,
        store: VectorStore,
        fontes: FonteConhecimentoRepository,
    ) -> None:
        self._fontes = fontes
        self._indexador = _IndexadorFonte(embedder=embedder, store=store)

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
            tenant_id=tenant_id,
            nome=nome,
            tipo=tipo,
            total_trechos=len(trechos_texto),
            conteudo=conteudo,
        )
        await self._fontes.criar(fonte)
        await self._indexador.sincronizar(fonte)
        return fonte


class ListarFontesConhecimento:
    def __init__(self, *, fontes: FonteConhecimentoRepository) -> None:
        self._fontes = fontes

    async def executar(self, *, tenant_id: UUID) -> list[FonteConhecimento]:
        return await self._fontes.listar(tenant_id=tenant_id)


class ObterFonteConhecimento:
    """Um documento com o **texto original** — é o que a tela de leitura/edição mostra."""

    def __init__(self, *, fontes: FonteConhecimentoRepository) -> None:
        self._fontes = fontes

    async def executar(
        self, *, tenant_id: UUID, fonte_id: UUID
    ) -> FonteConhecimento | None:
        return await self._fontes.obter(tenant_id=tenant_id, fonte_id=fonte_id)


class AtualizarFonteConhecimento:
    """Edita um documento e **reindexa** o RAG com o texto novo.

    Mantém o mesmo ``fonte_id``: quem edita está corrigindo *aquele* procedimento, e
    trocar o id quebraria a rastreabilidade de qual documento originou uma resposta.
    """

    def __init__(
        self,
        *,
        fontes: FonteConhecimentoRepository,
        embedder: Embedder,
        store: VectorStore,
    ) -> None:
        self._fontes = fontes
        self._indexador = _IndexadorFonte(embedder=embedder, store=store)

    async def executar(
        self,
        *,
        tenant_id: UUID,
        fonte_id: UUID,
        nome: str,
        conteudo: str,
        tipo: TipoConhecimento,
        ativo: bool = True,
    ) -> FonteConhecimento:
        atual = await self._fontes.obter(tenant_id=tenant_id, fonte_id=fonte_id)
        if atual is None:
            raise ValueError("Documento não encontrado para o tenant.")
        nome = nome.strip()
        if not nome:
            raise ValueError("O documento precisa de um nome.")
        trechos_texto = fragmentar(conteudo)
        if not trechos_texto:
            raise ValueError("O documento está vazio.")

        atual.nome = nome
        atual.conteudo = conteudo
        atual.tipo = tipo
        atual.ativo = ativo
        # Conta os fragmentos que o texto **tem**, mesmo desativado: o número descreve o
        # documento, não o estado do interruptor, e não pode zerar a cada clique.
        atual.total_trechos = len(trechos_texto)

        salvo = await self._fontes.atualizar(atual)
        await self._indexador.sincronizar(salvo)
        return salvo


class DefinirAtivoFonteConhecimento:
    """Liga/desliga a indexação de um documento sem tocar no texto (decisão A).

    É a alternativa da escola ao ``DELETE``, que passou a ser do super admin: um
    procedimento que saiu de vigência precisa parar de alimentar o bot **hoje**, e esperar
    por nós para isso deixaria o assistente respondendo regra revogada.
    """

    def __init__(
        self,
        *,
        fontes: FonteConhecimentoRepository,
        embedder: Embedder,
        store: VectorStore,
    ) -> None:
        self._fontes = fontes
        self._indexador = _IndexadorFonte(embedder=embedder, store=store)

    async def executar(
        self, *, tenant_id: UUID, fonte_id: UUID, ativo: bool
    ) -> FonteConhecimento:
        atual = await self._fontes.obter(tenant_id=tenant_id, fonte_id=fonte_id)
        if atual is None:
            raise ValueError("Documento não encontrado para o tenant.")
        if atual.ativo == ativo:
            return atual
        atual.ativo = ativo
        salvo = await self._fontes.atualizar(atual)
        await self._indexador.sincronizar(salvo)
        return salvo


class RemoverFonteConhecimento:
    """Remove um documento e todos os seus trechos indexados (RAG) do tenant.

    **Só super admin** (decisão A): apagar destrói o texto original, e a escola tem
    ``DefinirAtivoFonteConhecimento`` para o que ela realmente precisa no dia a dia —
    tirar do ar sem perder o conteúdo. O guarda mora na rota; aqui fica o efeito.
    """

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
