"""Adaptador Meta WhatsApp Cloud API (outbound).

Implementa a porta ``MessageChannel`` para disparo real. As mensagens de texto livre só são
permitidas dentro da janela de atendimento de 24h; fora dela é obrigatório usar templates
(HSM) aprovados — por isso ``enviar_template`` é o caminho dos broadcasts.

A cota diária por tier e o throttling são aplicados nos casos de uso via ``QuotaPolicy`` e
``RateLimiter``, não aqui.
"""

from __future__ import annotations

import logging

import httpx

from app.domain.entities import Documento, MessageTemplate

logger = logging.getLogger("channel.meta")

_BASE = "https://graph.facebook.com/v21.0"


class MetaMessageChannel:
    """Multi-tenant: a origem do envio é resolvida **por mensagem**, não no construtor.

    Na Graph API o número remetente não vai no corpo — ele é o próprio caminho da URL
    (``/{phone_number_id}/messages``). Por isso o ``remetente`` da porta ``MessageChannel``
    (que ``Tenant.remetente_canal`` preenche com o ``meta_phone_number_id`` da escola) é
    aplicado aqui, e o ``META_PHONE_NUMBER_ID`` da env fica só como fallback.
    """

    def __init__(self, *, phone_number_id: str, access_token: str) -> None:
        # Fallback: usado quando a escola ainda não tem ``meta_phone_number_id`` cadastrado
        # (instalação single-tenant / desenvolvimento).
        self._phone_number_id_padrao = phone_number_id
        self._headers = {"Authorization": f"Bearer {access_token}"}

    def _origem(self, remetente: str | None) -> str:
        """Resolve o ``phone_number_id`` de origem do envio."""
        origem = (remetente or "").strip()
        if not origem:
            return self._phone_number_id_padrao
        if not origem.isdigit():
            # Chegou um E.164 (escola sem ``meta_phone_number_id``): a Graph API não aceita
            # telefone no caminho da URL. Cai no número padrão e AVISA — sem o id da escola
            # cadastrado o disparo sai do número errado, que é justamente o que §9e.1 evita.
            logger.warning(
                "Remetente %r não é um phone_number_id da Meta — usando o número padrão da "
                "env. Cadastre o meta_phone_number_id da escola.",
                origem,
            )
            return self._phone_number_id_padrao
        return origem

    async def _post(self, payload: dict, *, remetente: str | None) -> str:
        url = f"{_BASE}/{self._origem(remetente)}/messages"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
        return data["messages"][0]["id"]

    async def enviar_texto(
        self, *, contato: str, texto: str, remetente: str | None = None
    ) -> str:
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": contato,
                "type": "text",
                "text": {"body": texto},
            },
            remetente=remetente,
        )

    async def enviar_template(
        self,
        *,
        contato: str,
        template: MessageTemplate,
        parametros: list[str],
        remetente: str | None = None,
    ) -> str:
        componentes = []
        if parametros:
            componentes.append(
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in parametros],
                }
            )
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": contato,
                "type": "template",
                "template": {
                    "name": template.nome,
                    "language": {"code": template.idioma},
                    "components": componentes,
                },
            },
            remetente=remetente,
        )

    async def enviar_documento(
        self, *, contato: str, documento: Documento, remetente: str | None = None
    ) -> str:
        return await self._post(
            {
                "messaging_product": "whatsapp",
                "to": contato,
                "type": "document",
                "document": {"link": documento.url, "filename": documento.nome},
            },
            remetente=remetente,
        )
