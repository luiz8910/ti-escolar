"""Adaptadores de envio de e-mail (porta ``EmailSender``).

Dois adaptadores, escolhidos por ``EMAIL_PROVIDER``:

- ``LogEmailSender`` (``log``): registra a mensagem no logger. É o default em
  desenvolvimento — e era o único que existia, o que significava que o aviso de licença a
  vencer (§6e) rodava, o painel dizia "avisos enviados" e o e-mail **não saía de lugar
  nenhum**.
- ``ResendEmailSender`` (``resend``): envia de verdade pela API do resend.com.

Trocar de provedor é implementar a mesma porta; domínio e aplicação não mudam.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("tiescolar.email")

RESEND_ENDPOINT = "https://api.resend.com/emails"


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


class ResendEmailSender:
    """Envio real via API do Resend (https://resend.com).

    Escolhido por ser HTTP puro: não exige porta SMTP liberada — que provedores de PaaS
    costumam bloquear — nem credencial de servidor de e-mail.

    **Falhar não pode derrubar a operação que disparou o e-mail.** O aviso de licença a
    vencer percorre várias escolas; se o provedor recusar o envio de uma, as demais
    precisam continuar. Por isso o erro é registrado (e aparece no painel de Logs) em vez
    de propagado.
    """

    def __init__(
        self,
        *,
        remetente: str,
        api_key: str,
        timeout_segundos: float = 15.0,
        endpoint: str = RESEND_ENDPOINT,
    ) -> None:
        self._remetente = remetente
        self._api_key = api_key
        self._timeout = timeout_segundos
        self._endpoint = endpoint

    async def enviar(self, *, destinatario: str, assunto: str, corpo: str) -> None:
        if not self._api_key:
            # Configuração incompleta: avisa alto, mas não quebra quem chamou. O painel de
            # segurança sinaliza o provedor selecionado sem chave.
            logger.error(
                "Resend sem RESEND_API_KEY: e-mail para %s NÃO foi enviado (assunto=%r)",
                destinatario,
                assunto,
            )
            return

        payload = {
            "from": self._remetente,
            "to": [destinatario],
            "subject": assunto,
            # Corpo em texto puro: os avisos administrativos são curtos e sem layout, e
            # `text` evita cair em filtro de spam por HTML malformado.
            "text": corpo,
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resposta = await client.post(
                    self._endpoint,
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
            if resposta.status_code >= 400:
                logger.error(
                    "Resend recusou o e-mail para %s: HTTP %s — %s",
                    destinatario,
                    resposta.status_code,
                    resposta.text[:300],
                )
                return
            identificador = ""
            try:
                identificador = (resposta.json() or {}).get("id", "")
            except ValueError:
                pass
            logger.info("E-mail enviado para %s (resend id=%s)", destinatario, identificador)
        except httpx.HTTPError as erro:
            logger.error("Falha de rede ao enviar e-mail para %s: %s", destinatario, erro)
