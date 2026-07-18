"""Caso de uso de exportação de conversa para fins legais (§H1).

Reúne as mensagens de uma conversa (opcionalmente recortadas por período) num documento
textual com cabeçalho institucional e marca de exportação, válido para anexar a
processos/prontuários (ocorrências, casos de racismo, etc.). Complementa o histórico
existente, que não garante um formato de retenção. Sem framework/ORM/SDK.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.domain.entities import Autor, ConversaExportada, _now
from app.domain.ports import ConversaRepository, TenantRepository


def _rotulo_autor(autor: Autor) -> str:
    return "Responsável" if autor == Autor.USUARIO else "Escola (assistente)"


def _fmt(dt: datetime | None) -> str:
    return dt.strftime("%d/%m/%Y %H:%M") if dt else "--/--/---- --:--"


class ExportarConversaLegal:
    """Monta o documento textual de uma conversa para arquivamento legal."""

    def __init__(
        self,
        *,
        conversas: ConversaRepository,
        tenants: TenantRepository | None = None,
    ) -> None:
        self._conversas = conversas
        self._tenants = tenants

    async def executar(
        self,
        *,
        tenant_id: UUID,
        conversa_id: UUID,
        inicio: datetime | None = None,
        fim: datetime | None = None,
    ) -> ConversaExportada:
        conversa = await self._conversas.obter_conversa(
            tenant_id=tenant_id, conversa_id=conversa_id
        )
        if conversa is None:
            raise ValueError("Conversa não encontrada para o tenant.")

        mensagens = await self._conversas.mensagens(conversa_id=conversa_id)
        # Recorte por período (inclusivo), quando informado.
        if inicio is not None:
            mensagens = [m for m in mensagens if m.criado_em and m.criado_em >= inicio]
        if fim is not None:
            mensagens = [m for m in mensagens if m.criado_em and m.criado_em <= fim]
        mensagens = sorted(mensagens, key=lambda m: m.criado_em or _now())

        escola_nome = ""
        if self._tenants is not None:
            tenant = await self._tenants.obter(tenant_id)
            if tenant is not None:
                escola_nome = tenant.nome

        gerado_em = _now()
        documento = self._render(
            escola_nome=escola_nome,
            contato=conversa.contato,
            inicio=inicio,
            fim=fim,
            gerado_em=gerado_em,
            mensagens=mensagens,
        )
        return ConversaExportada(
            tenant_id=tenant_id,
            conversa_id=conversa_id,
            escola_nome=escola_nome,
            contato=conversa.contato,
            documento=documento,
            total_mensagens=len(mensagens),
            inicio=inicio,
            fim=fim,
            gerado_em=gerado_em,
        )

    @staticmethod
    def _render(
        *,
        escola_nome: str,
        contato: str,
        inicio: datetime | None,
        fim: datetime | None,
        gerado_em: datetime,
        mensagens: list,
    ) -> str:
        periodo = "todo o histórico"
        if inicio or fim:
            periodo = f"{_fmt(inicio)} a {_fmt(fim)}"
        linhas = [
            "REGISTRO DE CONVERSA — DOCUMENTO PARA FINS LEGAIS",
            "=" * 56,
            f"Escola: {escola_nome or '(não informada)'}",
            f"Responsável (contato): {contato}",
            f"Período: {periodo}",
            f"Total de mensagens: {len(mensagens)}",
            f"Documento gerado em: {_fmt(gerado_em)}",
            "=" * 56,
            "",
        ]
        for m in mensagens:
            linhas.append(f"[{_fmt(m.criado_em)}] {_rotulo_autor(m.autor)}:")
            linhas.append(m.texto)
            if m.fontes:
                linhas.append("  Fontes citadas: " + "; ".join(m.fontes))
            linhas.append("")
        linhas.append("=" * 56)
        linhas.append(
            "Documento extraído automaticamente do sistema TI-Escolar. As mensagens "
            "reproduzem o conteúdo registrado na plataforma na data da exportação."
        )
        return "\n".join(linhas)
