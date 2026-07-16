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
    FichaFinanceiraEscola,
    Mensagem,
    PlanoTenant,
    ResumoConversa,
    ResumoEscola,
    StatusEntrega,
    StatusTenant,
    Tenant,
    Usuario,
)
from app.domain.ports import (
    BroadcastRepository,
    ContatoRepository,
    ConversaRepository,
    EmailSender,
    TemplateRepository,
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


def normalizar_whatsapp(bruto: str) -> str:
    """Normaliza o número de WhatsApp para E.164 (``+<dígitos>``); "" quando vazio.

    Aceita internacional (ex.: número do Sandbox Twilio ``+14155238886``), então não força
    DDI do Brasil. Remove o prefixo ``whatsapp:`` e qualquer separador (espaços, traços,
    parênteses). Valida um formato E.164 plausível (8 a 15 dígitos após o ``+``).
    """
    bruto = (bruto or "").strip()
    if not bruto:
        return ""
    if bruto.startswith("whatsapp:"):
        bruto = bruto.split(":", 1)[1]
    digitos = re.sub(r"\D", "", bruto)
    if not (8 <= len(digitos) <= 15):
        raise ValueError("Número de WhatsApp inválido: informe no formato E.164 (ex.: +14155238886).")
    return f"+{digitos}"


def normalizar_telefone_contato(bruto: str) -> str:
    """Normaliza o telefone de contato para E.164. **Obrigatório:** vazio levanta erro.

    Diferente de ``whatsapp_numero``, o contato é só informativo (número público da
    secretaria) — não é validado por unicidade nem roteia mensagens.
    """
    if not (bruto or "").strip():
        raise ValueError("O telefone de contato da escola é obrigatório.")
    try:
        return normalizar_whatsapp(bruto)
    except ValueError as e:
        raise ValueError(
            "Telefone de contato inválido: informe no formato E.164 (ex.: +5511999998888)."
        ) from e


async def _validar_whatsapp_unico(
    tenants: TenantRepository, *, numero: str, tenant_id: UUID | None = None
) -> None:
    """Impede dois tenants com o mesmo número (roteamento do inbound seria ambíguo)."""
    if not numero:
        return
    conflito = await tenants.por_whatsapp(numero)
    if conflito and conflito.id != tenant_id:
        raise ValueError(f"O número {numero} já está vinculado a outra escola.")


# --------------------------------------------------------------------------- #
# CRUD de escolas (super admin)
# --------------------------------------------------------------------------- #
class CriarEscola:
    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(
        self,
        *,
        criador: Usuario,
        nome: str,
        slug: str = "",
        whatsapp_numero: str = "",
        telefone_contato: str = "",
    ) -> Tenant:
        _exige_super_admin(criador)
        nome = nome.strip()
        if not nome:
            raise ValueError("O nome da escola é obrigatório.")
        slug = slugify(slug or nome)
        if await self._tenants.por_slug(slug):
            raise ValueError("Já existe uma escola com este slug.")
        numero = normalizar_whatsapp(whatsapp_numero)
        contato = normalizar_telefone_contato(telefone_contato)
        await _validar_whatsapp_unico(self._tenants, numero=numero)
        return await self._tenants.criar(
            Tenant(nome=nome, slug=slug, whatsapp_numero=numero, telefone_contato=contato)
        )


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
        self,
        *,
        criador: Usuario,
        tenant_id: UUID,
        nome: str,
        slug: str = "",
        whatsapp_numero: str = "",
        telefone_contato: str = "",
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
        numero = normalizar_whatsapp(whatsapp_numero)
        contato = normalizar_telefone_contato(telefone_contato)
        await _validar_whatsapp_unico(self._tenants, numero=numero, tenant_id=tenant_id)
        # Renomear não mexe no licenciamento: preserva status/plano/expiração.
        existente.nome = nome
        existente.slug = slug
        existente.whatsapp_numero = numero
        existente.telefone_contato = contato
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


class CancelarEscola:
    """Cancela (churn) a escola: ela deixa a plataforma e perde acesso. Só super admin.

    Diferente do bloqueio (suspensão reversível), o cancelamento marca o fim do ciclo de
    vida e registra ``cancelado_em``/``motivo_cancelamento`` para a ficha/histórico.
    """

    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(self, *, criador: Usuario, tenant_id: UUID, motivo: str) -> Tenant:
        _exige_super_admin(criador)
        motivo = motivo.strip()
        if not motivo:
            raise ValueError("O motivo do cancelamento é obrigatório.")
        escola = await _obter_existente(self._tenants, tenant_id)
        escola.status = StatusTenant.CANCELADO
        escola.motivo_cancelamento = motivo
        escola.cancelado_em = _now()
        return await self._tenants.atualizar(escola)


class ReativarEscola:
    """Reverte um cancelamento, reativando a escola. Só super admin."""

    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(self, *, criador: Usuario, tenant_id: UUID) -> Tenant:
        _exige_super_admin(criador)
        escola = await _obter_existente(self._tenants, tenant_id)
        escola.status = StatusTenant.ATIVO
        escola.motivo_cancelamento = ""
        escola.cancelado_em = None
        return await self._tenants.atualizar(escola)


class DefinirLicenca:
    """Define plano, expiração e (opcionalmente) os preços de cobrança. Só super admin.

    Os preços (``valor_*_centavos``) só são alterados quando informados, de modo que ajustar
    apenas o plano/expiração preserva a tabela de preços já cadastrada.
    """

    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(
        self,
        *,
        criador: Usuario,
        tenant_id: UUID,
        plano: PlanoTenant,
        licenca_expira_em: datetime | None,
        valor_mensal_centavos: int | None = None,
        valor_anual_centavos: int | None = None,
    ) -> Tenant:
        _exige_super_admin(criador)
        escola = await _obter_existente(self._tenants, tenant_id)
        escola.plano = plano
        escola.licenca_expira_em = licenca_expira_em
        if valor_mensal_centavos is not None:
            if valor_mensal_centavos < 0:
                raise ValueError("O valor mensal não pode ser negativo.")
            escola.valor_mensal_centavos = valor_mensal_centavos
        if valor_anual_centavos is not None:
            if valor_anual_centavos < 0:
                raise ValueError("O valor anual não pode ser negativo.")
            escola.valor_anual_centavos = valor_anual_centavos
        return await self._tenants.atualizar(escola)


class ObterFichaFinanceira:
    """Monta a ficha financeira/histórico de uma escola (cobrança + uso). Só super admin."""

    def __init__(self, *, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def executar(
        self, *, solicitante: Usuario, tenant_id: UUID, limite_diario_meta: int
    ) -> FichaFinanceiraEscola | None:
        _exige_super_admin(solicitante)
        escola = await self._tenants.obter(tenant_id)
        if escola is None:
            return None
        uso = await self._tenants.metricas_uso(tenant_id)
        return FichaFinanceiraEscola(
            tenant=escola, uso=uso, limite_diario_meta=limite_diario_meta
        )


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


@dataclass
class BroadcastComTemplate:
    """Broadcast acompanhado do nome do template usado (para o histórico de disparos)."""

    broadcast: Broadcast
    template_nome: str


class ListarBroadcastsDaEscola:
    """Histórico de disparos (mensagens em massa) da escola, com o nome do template.

    Resolve os nomes dos templates em lote (um lookup por template distinto), evitando
    N+1 ao montar a listagem.
    """

    def __init__(
        self,
        *,
        broadcasts: BroadcastRepository,
        templates: TemplateRepository | None = None,
    ) -> None:
        self._broadcasts = broadcasts
        self._templates = templates

    async def executar(self, *, tenant_id: UUID) -> list[BroadcastComTemplate]:
        bs = await self._broadcasts.listar(tenant_id=tenant_id)
        nomes: dict[UUID, str] = {}
        if self._templates is not None:
            for template_id in {b.template_id for b in bs}:
                template = await self._templates.obter(
                    tenant_id=tenant_id, template_id=template_id
                )
                nomes[template_id] = template.nome if template else ""
        return [
            BroadcastComTemplate(broadcast=b, template_nome=nomes.get(b.template_id, ""))
            for b in bs
        ]


@dataclass
class DestinatarioComNome:
    contato: str  # telefone E.164
    nome: str  # nome do responsável, se cadastrado
    status: StatusEntrega
    atualizado_em: datetime | None


@dataclass
class BroadcastDetalhado:
    broadcast: Broadcast
    template_nome: str
    destinatarios: list[DestinatarioComNome]


class ObterBroadcastDaEscola:
    """Detalhe de um disparo: template, destinatários (com o nome do responsável) e status.

    Escopado por ``tenant_id``: um broadcast de outra escola devolve ``None``.
    """

    def __init__(
        self,
        *,
        broadcasts: BroadcastRepository,
        contatos: ContatoRepository,
        templates: TemplateRepository | None = None,
    ) -> None:
        self._broadcasts = broadcasts
        self._contatos = contatos
        self._templates = templates

    async def executar(
        self, *, tenant_id: UUID, broadcast_id: UUID
    ) -> BroadcastDetalhado | None:
        broadcast = await self._broadcasts.obter(broadcast_id)
        if broadcast is None or broadcast.tenant_id != tenant_id:
            return None

        template_nome = ""
        if self._templates is not None:
            template = await self._templates.obter(
                tenant_id=tenant_id, template_id=broadcast.template_id
            )
            template_nome = template.nome if template else ""

        destinatarios: list[DestinatarioComNome] = []
        for dest in broadcast.destinatarios:
            contato = await self._contatos.por_telefone(
                tenant_id=tenant_id, telefone=dest.contato
            )
            destinatarios.append(
                DestinatarioComNome(
                    contato=dest.contato,
                    nome=contato.nome if contato else "",
                    status=dest.status,
                    atualizado_em=dest.atualizado_em,
                )
            )
        return BroadcastDetalhado(
            broadcast=broadcast, template_nome=template_nome, destinatarios=destinatarios
        )
