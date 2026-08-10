"""Inbound real do WhatsApp: mensagens recebidas pelo webhook da Meta (§9e.1).

É o que faz o produto **atender**, e não apenas disparar. O webhook da Meta entrega um
envelope JSON aninhado (``entry[].changes[].value``) que carrega, no mesmo POST, mensagens
recebidas e status de entrega; este caso de uso cuida só do primeiro caminho (o segundo é
de ``RegistrarStatusEntrega``).

Três pontos definem o desenho:

- **Roteamento por ``phone_number_id``.** Cada escola tem o seu número registrado na nossa
  WABA, e o webhook diz em ``value.metadata.phone_number_id`` para qual deles a mensagem
  foi. Um ``phone_number_id`` sem escola correspondente é **descartado com log** — nunca
  cai num tenant padrão, o que jogaria a conversa de um responsável na caixa de outra
  escola.
- **A resposta não vai no corpo do HTTP.** Diferente de um webhook que responde em TwiML, a
  Meta exige ``200 OK`` imediato e a resposta ao responsável precisa ser **enviada
  ativamente** por uma segunda chamada à API — daqui, via ``MessageChannel.enviar_texto``,
  a partir do número da própria escola.
- **Reentrega.** A Meta reenvia o evento quando não recebe o ``200`` a tempo. O
  ``RegistroAtendimento`` **reserva** a mensagem pelo ``id`` (wamid) numa tabela do
  Postgres antes de chamar a LLM, e a reentrega encontra a dúvida ou *em atendimento* ou
  já *sanada* — em qualquer dos casos, não é atendida (nem cobrada) de novo. A reserva
  está no banco, e não em memória, porque a duplicata costuma cair em outra réplica.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.application.use_cases import Atendedor
from app.domain.entities import EstadoAtendimento
from app.domain.ports import (
    ControleTaxa,
    MessageChannel,
    RegistroAtendimento,
    TenantRepository,
)

logger = logging.getLogger("inbound.meta")


@dataclass
class ResultadoInboundMeta:
    """Contagem do que o envelope rendeu — o webhook loga isso e devolve no corpo."""

    recebidas: int = 0
    respondidas: int = 0
    # Sem escola dona do phone_number_id: descartadas (ver docstring do módulo).
    descartadas: int = 0
    # Reentregas da Meta que já haviam sido atendidas.
    repetidas: int = 0
    # Tipos ainda não tratados (imagem, áudio, documento, localização, ...).
    ignoradas: int = 0
    # Recusadas pelo limite de taxa por remetente (número em loop / abuso).
    limitadas: int = 0
    # Registradas sem resposta automática porque a secretaria assumiu a conversa (§6j).
    # Contada à parte de ``respondidas``: sem isso, um silêncio deliberado ficaria
    # indistinguível de uma falha de atendimento no painel de logs (§16).
    silenciadas: int = 0


def normalizar_origem(bruto: str) -> str:
    """Põe o telefone do webhook em E.164 com ``+``.

    A Meta entrega o ``from`` **sem** o ``+`` (ex.: ``5511988887777``), enquanto os
    ``Contato``s e as ``Conversa``s do produto são chaveados em E.164 com ``+``. Sem essa
    normalização o mesmo responsável abriria uma conversa nova a cada mensagem e não casaria
    com o cadastro da escola.
    """
    bruto = (bruto or "").strip()
    if not bruto:
        return ""
    return bruto if bruto.startswith("+") else f"+{bruto}"


class ProcessarInboundMeta:
    """Roteia as mensagens recebidas do webhook da Meta para o chatbot."""

    def __init__(
        self,
        *,
        tenants: TenantRepository,
        atender: Atendedor,
        canal: MessageChannel,
        atendimentos: RegistroAtendimento | None = None,
        controle_taxa: ControleTaxa | None = None,
        limite_por_remetente: int = 0,
        janela_taxa_segundos: int = 60,
    ) -> None:
        self._tenants = tenants
        self._atender = atender
        self._canal = canal
        self._atendimentos = atendimentos
        self._controle_taxa = controle_taxa
        self._limite_por_remetente = limite_por_remetente
        self._janela_taxa_segundos = janela_taxa_segundos

    async def executar(self, *, payload: dict) -> ResultadoInboundMeta:
        resultado = ResultadoInboundMeta()
        for entry in payload.get("entry", []) or []:
            for change in entry.get("changes", []) or []:
                valor = change.get("value", {}) or {}
                mensagens = valor.get("messages", []) or []
                if not mensagens:
                    continue  # envelope só de status de entrega — não é conosco
                await self._processar_lote(valor, mensagens, resultado)
        return resultado

    async def _processar_lote(
        self, valor: dict, mensagens: list, resultado: ResultadoInboundMeta
    ) -> None:
        metadata = valor.get("metadata", {}) or {}
        phone_number_id = str(metadata.get("phone_number_id") or "").strip()
        escola = (
            await self._tenants.por_meta_phone_number_id(phone_number_id)
            if phone_number_id
            else None
        )
        if escola is None:
            # SEM fallback de tenant: melhor perder a mensagem do que entregá-la à escola
            # errada. O log é o que permite descobrir um número registrado na Meta e ainda
            # não cadastrado no painel.
            resultado.descartadas += len(mensagens)
            logger.warning(
                "Inbound Meta descartado: nenhuma escola cadastrada com o phone_number_id %r "
                "(%d mensagem(ns)). Cadastre o id no painel do super admin.",
                phone_number_id,
                len(mensagens),
            )
            return

        for mensagem in mensagens:
            await self._processar_mensagem(mensagem, escola, resultado)

    async def _liberar(self, wamid: str, reservado: bool, motivo: str) -> None:
        """Devolve a reserva quando o atendimento não aconteceu."""
        if reservado and self._atendimentos is not None:
            await self._atendimentos.falhar(chave=wamid, erro=motivo)

    async def _dentro_do_limite(self, origem: str) -> bool:
        """Franquia de mensagens por remetente na janela configurada.

        Não é o mesmo que a cota diária da Meta (§9a), que protege o *envio*; aqui o que
        se protege é o custo de LLM da escola contra um número que dispara em loop.
        """
        if self._controle_taxa is None or self._limite_por_remetente <= 0:
            return True
        resultado = await self._controle_taxa.registrar(
            chave=f"inbound:{origem}",
            limite=self._limite_por_remetente,
            janela_segundos=self._janela_taxa_segundos,
        )
        return resultado.permitido

    async def _processar_mensagem(self, mensagem: dict, escola, resultado) -> None:
        wamid = str(mensagem.get("id") or "").strip()
        origem = normalizar_origem(str(mensagem.get("from") or ""))
        texto = ((mensagem.get("text") or {}).get("body") or "").strip()

        if mensagem.get("type") != "text" or not texto or not origem:
            # Mídia (imagem/áudio/documento/localização) ainda não é atendida — o download
            # exige baixar o media_id pela Graph API. [Roadmap]
            resultado.ignoradas += 1
            logger.info(
                "Inbound Meta ignorado (tipo %r sem texto tratável), escola %s",
                mensagem.get("type"),
                escola.slug,
            )
            return

        # Reserva a mensagem ANTES da LLM. A reentrega da Meta chega justamente durante a
        # espera pela resposta, e é aqui que ela é reconhecida — inclusive vinda de outra
        # réplica, porque a reserva está no banco.
        reservado = True
        if self._atendimentos is not None and wamid:
            estado = await self._atendimentos.iniciar(
                chave=wamid, tenant_id=escola.id, origem=origem
            )
            if estado is EstadoAtendimento.CONCLUIDA:
                resultado.repetidas += 1
                logger.info(
                    "Inbound Meta repetido (wamid %s): dúvida já sanada — descartado", wamid
                )
                return
            if estado is EstadoAtendimento.EM_ATENDIMENTO:
                resultado.repetidas += 1
                logger.info(
                    "Inbound Meta repetido (wamid %s): já em atendimento em outro "
                    "processo — descartado",
                    wamid,
                )
                return
            if estado is EstadoAtendimento.RETOMADO:
                logger.warning(
                    "Inbound Meta retomado (wamid %s): a tentativa anterior não concluiu",
                    wamid,
                )
        else:
            reservado = False

        # Limite de taxa por remetente, DEPOIS da reserva (uma reentrega da Meta não pode
        # consumir a franquia do responsável) e ANTES da LLM — que é justamente o recurso
        # caro que um número em loop queimaria da escola.
        if not await self._dentro_do_limite(origem):
            resultado.limitadas += 1
            logger.warning(
                "Inbound Meta recusado por limite de taxa: %s (escola %s)",
                origem,
                escola.slug,
            )
            # Libera a reserva: a mensagem não foi atendida, e deixá-la travada em
            # "em atendimento" impediria uma retentativa legítima quando a janela abrir.
            await self._liberar(wamid, reservado, "recusado por limite de taxa")
            return

        resultado.recebidas += 1
        try:
            resposta = await self._atender.executar(
                tenant_id=escola.id, contato=origem, texto=texto
            )

            # A Meta não aceita a resposta no corpo do webhook: é uma nova chamada à API,
            # saindo do número da própria escola. Texto vazio é silêncio deliberado — a
            # conversa está com uma pessoa da secretaria (§6j) e o assistente não fala por
            # cima dela.
            if resposta.texto.strip():
                await self._canal.enviar_texto(
                    contato=origem,
                    texto=resposta.texto,
                    remetente=escola.remetente_canal or None,
                )
                resultado.respondidas += 1
            else:
                resultado.silenciadas += 1
                logger.info(
                    "Inbound Meta registrado sem resposta automática (escola %s): a "
                    "conversa está em atendimento humano",
                    escola.slug,
                )
        except Exception as erro:
            # Falha na LLM ou no envio: libera a reserva para que a reentrega da Meta —
            # ou a próxima tentativa — possa atender de verdade, em vez de encontrar a
            # mensagem marcada como "em atendimento" e descartá-la.
            await self._liberar(wamid, reservado, f"{type(erro).__name__}: {erro}")
            raise

        if reservado:
            await self._atendimentos.concluir(chave=wamid, resumo=resposta.texto[:500])
