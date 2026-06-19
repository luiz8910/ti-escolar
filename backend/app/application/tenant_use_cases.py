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
from datetime import datetime, timezone
from uuid import UUID

from app.domain.entities import (
    Broadcast,
    Conversa,
    Mensagem,
    PlanoTenant,
    ResumoConversa,
    ResumoEscola,
    StatusTenant,
    Tenant,
    Usuario,
)
from app.domain.ports import (
    BroadcastRepository,
    ConversaRepository,
    EmailSender,
    TenantRepository,
    UsuarioRepository,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


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
        # Renomear não mexe no licenciamento: preserva status/plano/expiração.
        existente.nome = nome
        existente.slug = slug
        return await self._tenants.atualizar(existente)


class RemoverEscola:
    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(self, *, criador: Usuario, tenant_id: UUID) -> bool:
        _exige_super_admin(criador)
        return await self._tenants.remover(tenant_id)


# --------------------------------------------------------------------------- #
# Licenciamento / cobrança / bloqueio (super admin)
# --------------------------------------------------------------------------- #
async def _obter_existente(tenants: TenantRepository, tenant_id: UUID) -> Tenant:
    escola = await tenants.obter(tenant_id)
    if escola is None:
        raise ValueError("Escola não encontrada.")
    return escola


class BloquearEscola:
    """Suspende a escola (falta de pagamento ou outro motivo). Só super admin.

    Uma escola bloqueada perde acesso ao painel e aos disparos; o motivo fica
    registrado para rastreabilidade.
    """

    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(self, *, criador: Usuario, tenant_id: UUID, motivo: str) -> Tenant:
        _exige_super_admin(criador)
        motivo = motivo.strip()
        if not motivo:
            raise ValueError("O motivo do bloqueio é obrigatório.")
        escola = await _obter_existente(self._tenants, tenant_id)
        escola.status = StatusTenant.BLOQUEADO
        escola.motivo_bloqueio = motivo
        escola.bloqueado_em = _now()
        return await self._tenants.atualizar(escola)


class DesbloquearEscola:
    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(self, *, criador: Usuario, tenant_id: UUID) -> Tenant:
        _exige_super_admin(criador)
        escola = await _obter_existente(self._tenants, tenant_id)
        escola.status = StatusTenant.ATIVO
        escola.motivo_bloqueio = ""
        escola.bloqueado_em = None
        return await self._tenants.atualizar(escola)


class DefinirLicenca:
    """Define o plano de cobrança e a data de expiração da licença. Só super admin."""

    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(
        self,
        *,
        criador: Usuario,
        tenant_id: UUID,
        plano: PlanoTenant,
        licenca_expira_em: datetime | None,
    ) -> Tenant:
        _exige_super_admin(criador)
        escola = await _obter_existente(self._tenants, tenant_id)
        escola.plano = plano
        escola.licenca_expira_em = licenca_expira_em
        return await self._tenants.atualizar(escola)


@dataclass
class AvisoLicenca:
    """Resultado de um aviso de vencimento enviado para uma escola."""

    tenant: Tenant
    dias_para_expirar: int
    destinatarios: list[str]


class NotificarLicencasAVencer:
    """Avisa por e-mail os admins de escolas com licença anual próxima do vencimento.

    Considera apenas o **plano anual** com licença ainda válida, porém dentro da
    janela de ``dias_aviso`` dias do vencimento. Envia a cada ``tenant_admin`` da
    escola. Pode ser disparado por um job agendado ou manualmente pelo super admin.
    """

    def __init__(
        self,
        *,
        tenants: TenantRepository,
        usuarios: UsuarioRepository,
        emails: EmailSender,
    ) -> None:
        self._tenants = tenants
        self._usuarios = usuarios
        self._emails = emails

    async def executar(self, *, dias_aviso: int = 30) -> list[AvisoLicenca]:
        avisos: list[AvisoLicenca] = []
        for escola in await self._tenants.listar():
            if escola.plano != PlanoTenant.ANUAL or not escola.licenca_a_vencer(dias_aviso):
                continue
            admins = await self._usuarios.listar(tenant_id=escola.id)
            destinatarios = [u.email for u in admins if u.ativo]
            dias = escola.dias_para_expirar or 0
            for email in destinatarios:
                await self._emails.enviar(
                    destinatario=email,
                    assunto=f"Sua licença do TI-Escolar vence em {dias} dia(s)",
                    corpo=(
                        f"Olá! A licença anual da escola {escola.nome} vence em {dias} "
                        f"dia(s) ({escola.licenca_expira_em:%d/%m/%Y}). "
                        "Para evitar a suspensão do acesso, regularize a renovação."
                    ),
                )
            avisos.append(
                AvisoLicenca(tenant=escola, dias_para_expirar=dias, destinatarios=destinatarios)
            )
        return avisos


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
