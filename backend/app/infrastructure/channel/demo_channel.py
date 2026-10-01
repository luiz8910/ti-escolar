"""Canal "demo": registra envios em memória, sem tocar em rede.

É o canal de **desenvolvimento local e de teste** — roda o fluxo de documentos/outbound
inteiro registrando o que "seria enviado" ao WhatsApp, sem token nem chamada à Meta. Em
produção ele nunca deve estar em uso: ``canal_efetivo`` existe justamente para acusar a
instância que caiu aqui por falta de ``META_ACCESS_TOKEN`` (§9c).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.domain.entities import Documento, MessageTemplate


def _agora() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class EnvioRegistrado:
    contato: str
    tipo: str  # "texto" | "template" | "documento"
    conteudo: str
    # Quem "enviou" e quando — só o simulador local lê isto (``/api/dev/whatsapp``).
    remetente: str | None = None
    em: datetime = field(default_factory=_agora)


class DemoMessageChannel:
    def __init__(self) -> None:
        self.enviados: list[EnvioRegistrado] = field(default_factory=list)  # type: ignore[assignment]
        self.enviados = []

    # ``remetente`` só é guardado: no demo não há número real a partir do qual enviar.
    async def enviar_texto(self, *, contato: str, texto: str, remetente: str | None = None) -> str:
        self.enviados.append(
            EnvioRegistrado(contato=contato, tipo="texto", conteudo=texto, remetente=remetente)
        )
        return f"demo-{len(self.enviados)}"

    async def enviar_template(
        self,
        *,
        contato: str,
        template: MessageTemplate,
        parametros: list[str],
        remetente: str | None = None,
    ) -> str:
        corpo = template.corpo
        for i, p in enumerate(parametros, start=1):
            corpo = corpo.replace(f"{{{{{i}}}}}", p)
        self.enviados.append(
            EnvioRegistrado(contato=contato, tipo="template", conteudo=corpo, remetente=remetente)
        )
        return f"demo-{len(self.enviados)}"

    async def enviar_documento(
        self, *, contato: str, documento: Documento, remetente: str | None = None
    ) -> str:
        self.enviados.append(
            EnvioRegistrado(
                contato=contato,
                tipo="documento",
                conteudo=documento.url,
                remetente=remetente,
            )
        )
        return f"demo-{len(self.enviados)}"
