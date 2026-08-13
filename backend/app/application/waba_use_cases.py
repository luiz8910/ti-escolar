"""Reconhecimento automático da conta do WhatsApp (WABA) pelo webhook.

O id da conta **não vem de variável de ambiente** (§9a-ter): ele é cadastro. Mas digitá-lo
é um passo manual que só existe porque a informação está do outro lado — e ela chega até
nós sozinha, em todo evento do webhook, no ``entry[].id``.

**Só que a documentação da Meta não afirma, em texto, que esse campo é o id da WABA.** Os
exemplos mostram o número; a descrição do campo não existe nas páginas de referência. Agir
sobre uma leitura não confirmada seria gravar no banco um id que, se estivesse errado,
faria toda submissão de template falhar com um erro que ninguém ligaria a esta decisão.

Por isso a adoção **pergunta à Meta antes de gravar**: ``CatalogoTemplates.descrever`` faz
um ``GET /{id}`` e só devolve nome quando aquele id é mesmo uma conta que enxergamos. A
resposta da própria Meta é que decide — não a nossa leitura do payload.
"""

from __future__ import annotations

import logging

from app.domain.entities import Waba
from app.domain.ports import CatalogoTemplates, WabaRepository

logger = logging.getLogger("wabas")


class AdotarContaDoWebhook:
    """Preenche o id da conta a partir de um evento, quando não há ambiguidade.

    Três condições, todas necessárias:

    1. o evento traz um id que **ainda não** conhecemos;
    2. existe **exatamente uma** conta sem id cadastrada — com duas, qualquer escolha seria
       chute, e o chute erra justamente no ambiente com várias contas;
    3. a Meta **confirma** que aquele id é uma conta nossa.

    Falhando qualquer uma, não faz nada: o id segue sendo preenchido no painel, que é o
    caminho que sempre existe. O custo de não adotar é um campo digitado; o de adotar
    errado seria um id inválido gravado sem ninguém ter pedido.
    """

    def __init__(
        self, *, wabas: WabaRepository, catalogo: CatalogoTemplates
    ) -> None:
        self._wabas = wabas
        self._catalogo = catalogo

    async def executar(self, *, payload: dict) -> Waba | None:
        candidatos = {
            id_bruto
            for entrada in payload.get("entry", []) or []
            if (id_bruto := str(entrada.get("id") or "").strip()).isdigit()
        }
        if not candidatos:
            return None

        desconhecidos = [
            c for c in sorted(candidatos) if await self._wabas.por_meta_id(c) is None
        ]
        if len(desconhecidos) != 1:
            # Nenhum novo (caso comum, todo evento depois do primeiro) ou mais de um, que é
            # ambíguo por natureza.
            return None
        candidato = desconhecidos[0]

        sem_id = [w for w in await self._wabas.listar() if not w.meta_waba_id]
        if len(sem_id) != 1:
            if sem_id:
                logger.info(
                    "Conta %r veio no webhook, mas há %d contas sem id: preencha no painel.",
                    candidato,
                    len(sem_id),
                )
            return None
        conta = sem_id[0]

        nome_na_meta = await self._catalogo.descrever(meta_waba_id=candidato)
        if nome_na_meta is None:
            logger.info(
                "Id %r do webhook não foi confirmado como conta nossa; nada foi gravado.",
                candidato,
            )
            return None

        conta.meta_waba_id = candidato
        if nome_na_meta:
            # O nome que a Meta usa vale mais que o nosso rótulo provisório: é assim que a
            # conta aparece no WhatsApp Manager, e é lá que alguém vai conferir.
            conta.nome = nome_na_meta
        salva = await self._wabas.salvar(conta)
        # `warning` porque é uma escrita que ninguém pediu: quem for auditar o que mudou no
        # cadastro precisa achar isto sem procurar.
        logger.warning(
            "Conta do WhatsApp %r (%s) reconhecida pelo webhook e confirmada na Meta.",
            salva.nome,
            salva.meta_waba_id,
        )
        return salva
