"""Download da mídia recebida — implementação da porta ``FonteMidia`` (§6k).

Na Meta o download tem **dois passos**, e nenhum deles é opcional:

1. ``GET /{media_id}`` devolve os metadados, incluindo uma ``url`` **temporária**;
2. essa URL só entrega o arquivo com o mesmo ``Authorization: Bearer`` — ela não é
   pública, apesar de parecer um link comum.

Por isso o arquivo é baixado **na hora** e guardado no ``ArquivoStorage``: salvar a URL em
vez dos bytes daria um registro que expira sozinho em poucos minutos, e a secretaria
descobriria isso no dia em que precisasse do atestado.

Duas defesas ficam aqui, antes de qualquer byte entrar no banco: **allowlist de MIME** e
**teto de tamanho**. O `content-length` é conferido antes do download e o tamanho real
depois — o cabeçalho é informado pela outra ponta e um arquivo maior do que ele anuncia
não pode ser gravado só porque mentiu.
"""

from __future__ import annotations

import logging

import httpx

from app.domain.entities import (
    MIMES_ACEITOS,
    TAMANHO_MAXIMO_DOCUMENTO,
    ArquivoBaixado,
)

logger = logging.getLogger("channel.meta.midia")

_BASE = "https://graph.facebook.com/v21.0"


def _mime_base(bruto: str) -> str:
    """``image/jpeg; codecs=...`` → ``image/jpeg``."""
    return (bruto or "").split(";")[0].strip().lower()


class MetaFonteMidia:
    """Baixa mídia do WhatsApp Cloud API pelo ``media_id`` do webhook."""

    def __init__(self, *, access_token: str, timeout: float = 30.0) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}
        self._timeout = timeout

    async def baixar(self, media_id: str) -> ArquivoBaixado | None:
        media_id = (media_id or "").strip()
        if not media_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                meta = await self._metadados(client, media_id)
                if meta is None:
                    return None
                url, mime, tamanho_anunciado, nome = meta

                if mime not in MIMES_ACEITOS:
                    logger.warning(
                        "Mídia %s recusada: tipo %r fora da allowlist", media_id, mime
                    )
                    return None
                if tamanho_anunciado and tamanho_anunciado > TAMANHO_MAXIMO_DOCUMENTO:
                    logger.warning(
                        "Mídia %s recusada: %d bytes acima do teto", media_id, tamanho_anunciado
                    )
                    return None

                conteudo = await self._conteudo(client, url)
        except httpx.HTTPError:
            # Falha de rede/HTTP não pode derrubar o atendimento inteiro: o responsável
            # ainda recebe resposta, e o log é o que permite descobrir o documento perdido.
            logger.warning("Falha ao baixar a mídia %s da Meta", media_id, exc_info=True)
            return None

        if conteudo is None:
            return None
        if len(conteudo) > TAMANHO_MAXIMO_DOCUMENTO:
            # O content-length é declarado pela outra ponta; o que vale é o que chegou.
            logger.warning(
                "Mídia %s recusada após o download: %d bytes acima do teto",
                media_id,
                len(conteudo),
            )
            return None
        return ArquivoBaixado(conteudo=conteudo, mime=mime, nome=nome)

    async def _metadados(
        self, client: httpx.AsyncClient, media_id: str
    ) -> tuple[str, str, int, str] | None:
        resp = await client.get(f"{_BASE}/{media_id}", headers=self._headers)
        resp.raise_for_status()
        dados = resp.json()
        url = str(dados.get("url") or "")
        if not url:
            logger.warning("Mídia %s sem URL nos metadados da Meta", media_id)
            return None
        return (
            url,
            _mime_base(str(dados.get("mime_type") or "")),
            int(dados.get("file_size") or 0),
            str(dados.get("filename") or ""),
        )

    async def _conteudo(self, client: httpx.AsyncClient, url: str) -> bytes | None:
        # A URL temporária exige o MESMO Bearer — ela não é pública, apesar da aparência.
        resp = await client.get(url, headers=self._headers, follow_redirects=True)
        resp.raise_for_status()
        return resp.content


class FonteMidiaIndisponivel:
    """Adaptador nulo: usado quando o canal é o demo (sem token da Meta).

    Devolver ``None`` faz o inbound registrar a mídia como não recuperada, em vez de
    fingir que baixou um arquivo vazio.
    """

    async def baixar(self, media_id: str) -> ArquivoBaixado | None:
        logger.info(
            "Download de mídia indisponível no canal demo (media_id %s ignorado)", media_id
        )
        return None
