"""Adaptadores de envio de e-mail (porta ``EmailSender``).

Por enquanto há apenas o adaptador de **log** (mock): registra a mensagem no
logger em vez de falar com um servidor SMTP/provedor real. Trocar por um adaptador
real (SMTP, SES, etc.) é só implementar a mesma porta — domínio/aplicação não mudam.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("tiescolar.email")


class LogEmailSender:
    """Implementação de ``EmailSender`` que apenas registra o e-mail no log."""

    def __init__(self, *, remetente: str) -> None:
        self._remetente = remetente

    async def enviar(self, *, destinatario: str, assunto: str, corpo: str) -> None:
        logger.info(
            "E-mail (mock) de %s para %s | assunto=%r | corpo=%r",
            self._remetente,
            destinatario,
            assunto,
            corpo,
        )
