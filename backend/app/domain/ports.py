"""Portas (interfaces) do domínio.

Definem os contratos que a camada de aplicação usa e que a infraestrutura implementa.
A regra de dependência aponta para dentro: aqui não há framework/SDK.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from app.domain.entities import (
    Broadcast,
    Contato,
    Conversa,
    Documento,
    FerramentaSpec,
    Grupo,
    MessageQuota,
    MessageTemplate,
    RespostaLLM,
    ResultadoBusca,
    TrechoConhecimento,
    TurnoConversa,
    Usuario,
)


# --------------------------------------------------------------------------- #
# LLM (geração / raciocínio)
# --------------------------------------------------------------------------- #
@runtime_checkable
class LLMProvider(Protocol):
    """Geração de texto. Adaptadores: fake, Anthropic, OpenAI..."""

    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        """Recebe um prompt de sistema e o histórico ({"role","content"}) e devolve texto."""
        ...

    async def gerar_com_ferramentas(
        self,
        *,
        sistema: str,
        turnos: list[TurnoConversa],
        ferramentas: list[FerramentaSpec],
    ) -> RespostaLLM:
        """Um round-trip com ferramentas: devolve texto e/ou chamadas de ferramenta.

        Não executa o loop agêntico — apenas reporta a intenção do modelo. Quem
        executa as ferramentas e itera é o caso de uso na camada de aplicação.
        """
        ...


@runtime_checkable
class Embedder(Protocol):
    """Geração de embeddings para o RAG."""

    @property
    def dimensao(self) -> int: ...

    async def embed(self, textos: list[str]) -> list[list[float]]: ...


# --------------------------------------------------------------------------- #
# Vector store / conhecimento (RAG)
# --------------------------------------------------------------------------- #
@runtime_checkable
class VectorStore(Protocol):
    async def indexar(self, trecho: TrechoConhecimento, embedding: list[float]) -> None: ...

    async def buscar(
        self, *, tenant_id: UUID, embedding: list[float], k: int = 4
    ) -> list[ResultadoBusca]: ...


# --------------------------------------------------------------------------- #
# Documentos (sistemas externos)
# --------------------------------------------------------------------------- #
@runtime_checkable
class DocumentSource(Protocol):
    """Recupera documentos em sistemas externos. Implementação atual: mock."""

    async def buscar_documentos(
        self, *, tenant_id: UUID, contato: str, consulta: str
    ) -> list[Documento]: ...


# --------------------------------------------------------------------------- #
# Canal de mensagens (inbound + outbound)
# --------------------------------------------------------------------------- #
@runtime_checkable
class MessageChannel(Protocol):
    async def enviar_texto(self, *, contato: str, texto: str) -> str:
        """Envia uma mensagem de texto livre. Retorna o id externo da mensagem."""
        ...

    async def enviar_template(
        self, *, contato: str, template: MessageTemplate, parametros: list[str]
    ) -> str:
        """Envia uma mensagem de template (HSM). Retorna o id externo."""
        ...

    async def enviar_documento(self, *, contato: str, documento: Documento) -> str: ...


# --------------------------------------------------------------------------- #
# Rate limiting / cota diária
# --------------------------------------------------------------------------- #
@runtime_checkable
class QuotaPolicy(Protocol):
    """Controla a cota diária de destinatários (tier Meta) por tenant."""

    async def cota_do_dia(self, tenant_id: UUID) -> MessageQuota: ...

    async def consumir(self, tenant_id: UUID, quantidade: int) -> MessageQuota: ...


@runtime_checkable
class RateLimiter(Protocol):
    """Throttling da taxa por segundo da API (independente da cota diária)."""

    async def aguardar_vaga(self) -> None: ...


# --------------------------------------------------------------------------- #
# Repositórios de persistência
# --------------------------------------------------------------------------- #
@runtime_checkable
class ConversaRepository(Protocol):
    async def obter_ou_criar(self, *, tenant_id: UUID, contato: str) -> Conversa: ...

    async def adicionar_mensagem(
        self, *, conversa_id: UUID, autor: str, texto: str, fontes: list[str] | None = None
    ) -> None: ...

    async def historico(self, *, conversa_id: UUID, limite: int = 20) -> list[dict[str, str]]: ...


@runtime_checkable
class TemplateRepository(Protocol):
    async def obter(self, *, tenant_id: UUID, template_id: UUID) -> MessageTemplate | None: ...


@runtime_checkable
class BroadcastRepository(Protocol):
    async def salvar(self, broadcast: Broadcast) -> None: ...

    async def obter(self, broadcast_id: UUID) -> Broadcast | None: ...


@runtime_checkable
class UsuarioRepository(Protocol):
    async def por_email(self, email: str) -> Usuario | None: ...

    async def criar(self, usuario: Usuario) -> Usuario: ...

    async def listar(self, *, tenant_id: UUID | None = None) -> list[Usuario]: ...


@runtime_checkable
class GrupoRepository(Protocol):
    async def criar(self, grupo: Grupo) -> Grupo: ...

    async def obter(self, *, tenant_id: UUID, grupo_id: UUID) -> Grupo | None: ...

    async def listar(self, *, tenant_id: UUID) -> list[Grupo]: ...

    async def adicionar_contato(
        self, *, tenant_id: UUID, grupo_id: UUID, nome: str, telefone: str
    ) -> Contato: ...

    async def membros(self, *, tenant_id: UUID, grupo_id: UUID) -> list[Contato]: ...
