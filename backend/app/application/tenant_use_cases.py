"""Casos de uso de escolas (tenants): CRUD do super admin e visualização de
conversas e mensagens em massa de uma escola.

A escrita de escolas é privilégio do super admin (cross-tenant). A visualização
de conversas/broadcasts é escopada por ``tenant_id`` e a permissão de acesso ao
tenant é verificada na camada de interface.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from uuid import UUID

from app.domain.entities import (
    Broadcast,
    Conversa,
    Mensagem,
    ResumoConversa,
    ResumoEscola,
    Tenant,
    Usuario,
)
from app.domain.ports import (
    BroadcastRepository,
    ConversaRepository,
    TenantRepository,
)


def _exige_super_admin(usuario: Usuario) -> None:
    if not usuario.eh_super_admin:
        raise PermissionError("Apenas o super admin pode gerenciar escolas.")


def slugify(texto: str) -> str:
    """Gera um slug ASCII a partir do nome (ex.: "Colégio São José" -> "colegio-sao-jose")."""
    normalizado = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", normalizado.lower()).strip("-")
    return slug or "escola"


# --------------------------------------------------------------------------- #
# CRUD de escolas (super admin)
# --------------------------------------------------------------------------- #
class CriarEscola:
    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(self, *, criador: Usuario, nome: str, slug: str = "") -> Tenant:
        _exige_super_admin(criador)
        nome = nome.strip()
        if not nome:
            raise ValueError("O nome da escola é obrigatório.")
        slug = slugify(slug or nome)
        if await self._tenants.por_slug(slug):
            raise ValueError("Já existe uma escola com este slug.")
        return await self._tenants.criar(Tenant(nome=nome, slug=slug))


class ListarEscolas:
    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(self, *, solicitante: Usuario) -> list[ResumoEscola]:
        _exige_super_admin(solicitante)
        return await self._tenants.listar_resumos()


class ObterEscola:
    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(self, *, solicitante: Usuario, tenant_id: UUID) -> Tenant | None:
        _exige_super_admin(solicitante)
        return await self._tenants.obter(tenant_id)


class AtualizarEscola:
    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(
        self, *, criador: Usuario, tenant_id: UUID, nome: str, slug: str = ""
    ) -> Tenant:
        _exige_super_admin(criador)
        existente = await self._tenants.obter(tenant_id)
        if existente is None:
            raise ValueError("Escola não encontrada.")
        nome = nome.strip()
        if not nome:
            raise ValueError("O nome da escola é obrigatório.")
        slug = slugify(slug or nome)
        conflito = await self._tenants.por_slug(slug)
        if conflito and conflito.id != tenant_id:
            raise ValueError("Já existe uma escola com este slug.")
        return await self._tenants.atualizar(
            Tenant(id=tenant_id, nome=nome, slug=slug, criado_em=existente.criado_em)
        )


class RemoverEscola:
    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(self, *, criador: Usuario, tenant_id: UUID) -> bool:
        _exige_super_admin(criador)
        return await self._tenants.remover(tenant_id)


# --------------------------------------------------------------------------- #
# Visualização: conversas (inbound) e broadcasts (outbound) de uma escola
# --------------------------------------------------------------------------- #
class ListarConversasDaEscola:
    def __init__(self, *, conversas: ConversaRepository) -> None:
        self._conversas = conversas

    async def executar(self, *, tenant_id: UUID) -> list[ResumoConversa]:
        return await self._conversas.listar_resumos(tenant_id=tenant_id)


@dataclass
class ConversaComMensagens:
    conversa: Conversa
    mensagens: list[Mensagem]


class ObterConversaDaEscola:
    def __init__(self, *, conversas: ConversaRepository) -> None:
        self._conversas = conversas

    async def executar(
        self, *, tenant_id: UUID, conversa_id: UUID
    ) -> ConversaComMensagens | None:
        conversa = await self._conversas.obter_conversa(
            tenant_id=tenant_id, conversa_id=conversa_id
        )
        if conversa is None:
            return None
        mensagens = await self._conversas.mensagens(conversa_id=conversa_id)
        return ConversaComMensagens(conversa=conversa, mensagens=mensagens)


class ListarBroadcastsDaEscola:
    def __init__(self, *, broadcasts: BroadcastRepository) -> None:
        self._broadcasts = broadcasts

    async def executar(self, *, tenant_id: UUID) -> list[Broadcast]:
        return await self._broadcasts.listar(tenant_id=tenant_id)
