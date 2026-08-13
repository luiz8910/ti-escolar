"""Gestão de templates na Meta — WhatsApp Business Management API.

Implementa a porta ``CatalogoTemplates`` sobre ``/{waba_id}/message_templates``. Exige o
escopo ``whatsapp_business_management`` no token de usuário do sistema (o de envio,
``whatsapp_business_messaging``, **não** serve aqui — e o sintoma de faltar é um 400 cujo
texto não menciona escopo nenhum, por isso ``_erro_legivel`` extrai a mensagem da Meta).

**A conta é parâmetro de cada chamada.** O mesmo token administra todas as WABAs do
portfólio; o que muda entre elas é só o nó da URL. Fixar uma no construtor — como este
adaptador nasceu, lendo ``META_WABA_ID`` — faz todo template ser criado numa conta só, e
a escola cujo número está em outra fica com um catálogo que não existe para ela.
"""

from __future__ import annotations

import logging

import httpx

from app.domain.entities import (
    CategoriaTemplate,
    MessageTemplate,
    StatusTemplate,
    TemplateRemoto,
)

logger = logging.getLogger("channel.meta.templates")

_BASE = "https://graph.facebook.com/v21.0"

# A Meta tem mais estados do que o nosso enum, e o que importa para nós é uma pergunta só:
# **dá para enviar?**. PAUSED e DISABLED são templates que foram aprovados e depois caíram
# por qualidade — enviar com eles falha. Mapeá-los para APROVADO deixaria o painel
# convidando a secretaria a um disparo que morre na Graph API, então caem em REJEITADO,
# que é o estado que a tela já sabe explicar. O motivo real vai em ``motivo_rejeicao``.
_STATUS = {
    "APPROVED": StatusTemplate.APROVADO,
    "PENDING": StatusTemplate.PENDENTE,
    "IN_APPEAL": StatusTemplate.PENDENTE,
    "PENDING_DELETION": StatusTemplate.PENDENTE,
    "REJECTED": StatusTemplate.REJEITADO,
    "PAUSED": StatusTemplate.REJEITADO,
    "DISABLED": StatusTemplate.REJEITADO,
}

_MOTIVO_IMPLICITO = {
    "PAUSED": "Pausado pela Meta por qualidade — não pode ser enviado até ser reativado.",
    "DISABLED": "Desativado pela Meta por qualidade — precisa ser recriado.",
}


def status_da_meta(bruto: str) -> StatusTemplate:
    """Traduz o status da Meta. Desconhecido vira PENDENTE, nunca APROVADO.

    Falhar fechado importa: um status novo que a gente não conheça sendo lido como
    aprovado liberaria disparo com template que a Meta não aceita.
    """
    return _STATUS.get((bruto or "").upper(), StatusTemplate.PENDENTE)


def motivo_da_meta(*, status_bruto: str, motivo: str | None) -> str:
    motivo = (motivo or "").strip()
    if motivo and motivo.upper() != "NONE":
        return motivo
    return _MOTIVO_IMPLICITO.get((status_bruto or "").upper(), "")


def categoria_da_meta(bruto: str) -> CategoriaTemplate:
    try:
        return CategoriaTemplate((bruto or "").lower())
    except ValueError:
        return CategoriaTemplate.UTILITY


class CatalogoTemplatesIndisponivel(RuntimeError):
    """Erro de configuração, levantado no uso — não no boot."""


class MetaCatalogoTemplates:
    def __init__(self, *, access_token: str) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}

    @staticmethod
    def _url(meta_waba_id: str) -> str:
        meta_waba_id = (meta_waba_id or "").strip()
        if not meta_waba_id:
            # Sem id não há nó a chamar. Recusar aqui dá a causa; deixar seguir montaria
            # ``/​/message_templates`` e a Meta devolveria um 400 sobre outra coisa.
            raise CatalogoTemplatesIndisponivel(
                "A conta do WhatsApp Business (WABA) desta escola está sem o id da Meta. "
                "Preencha-o em Administração → Contas WhatsApp."
            )
        return f"{_BASE}/{meta_waba_id}/message_templates"

    @staticmethod
    def _erro_legivel(exc: httpx.HTTPStatusError) -> str:
        """A Graph API responde 400 com o motivo real dentro do corpo.

        Deixar subir o ``HTTPStatusError`` cru daria à secretaria um "Client error '400'",
        que não diz se o nome já existe, se faltou exemplo ou se o token não tem escopo.
        """
        try:
            erro = exc.response.json().get("error", {})
        except Exception:  # noqa: BLE001 - corpo não-JSON: cai no texto bruto
            return exc.response.text[:300]
        partes = [
            erro.get("error_user_msg"),
            erro.get("error_user_title"),
            erro.get("message"),
        ]
        return next((p for p in partes if p), exc.response.text[:300])

    def _componentes(self, template: MessageTemplate) -> list[dict]:
        corpo: dict = {"type": "BODY", "text": template.corpo}
        if template.exemplos:
            # ``body_text`` é uma lista de listas: um conjunto de exemplos por variação.
            corpo["example"] = {"body_text": [list(template.exemplos)]}
        return [corpo]

    async def submeter(
        self, template: MessageTemplate, *, meta_waba_id: str
    ) -> TemplateRemoto:
        url = self._url(meta_waba_id)
        payload = {
            "name": template.nome,
            "language": template.idioma,
            "category": template.categoria.value.upper(),
            "components": self._componentes(template),
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, headers=self._headers, json=payload)
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                motivo = self._erro_legivel(exc)
                logger.warning("Meta recusou o template %r: %s", template.nome, motivo)
                raise CatalogoTemplatesIndisponivel(
                    f"A Meta recusou o template: {motivo}"
                ) from exc
            data = resp.json()

        status_bruto = data.get("status", "PENDING")
        return TemplateRemoto(
            nome=template.nome,
            idioma=template.idioma,
            status=status_da_meta(status_bruto),
            categoria=categoria_da_meta(data.get("category", template.categoria.value)),
            meta_template_id=str(data.get("id", "")),
            motivo_rejeicao=motivo_da_meta(status_bruto=status_bruto, motivo=None),
        )

    async def listar(self, *, meta_waba_id: str) -> list[TemplateRemoto]:
        params = {
            "fields": "id,name,language,status,category,rejected_reason",
            "limit": "200",
        }
        remotos: list[TemplateRemoto] = []
        url: str | None = self._url(meta_waba_id)
        async with httpx.AsyncClient(timeout=30) as client:
            while url:
                resp = await client.get(url, headers=self._headers, params=params)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise CatalogoTemplatesIndisponivel(
                        f"Não foi possível listar os templates na Meta: {self._erro_legivel(exc)}"
                    ) from exc
                corpo = resp.json()
                for item in corpo.get("data", []):
                    bruto = item.get("status", "")
                    remotos.append(
                        TemplateRemoto(
                            nome=item.get("name", ""),
                            idioma=item.get("language", ""),
                            status=status_da_meta(bruto),
                            categoria=categoria_da_meta(item.get("category", "")),
                            meta_template_id=str(item.get("id", "")),
                            motivo_rejeicao=motivo_da_meta(
                                status_bruto=bruto, motivo=item.get("rejected_reason")
                            ),
                        )
                    )
                # A paginação já carrega os filtros no ``next``; repetir ``params`` aqui
                # duplicaria o cursor e traria a mesma página para sempre.
                url = corpo.get("paging", {}).get("next")
                params = {}
        return remotos

    async def descrever(self, *, meta_waba_id: str) -> str | None:
        """``GET /{waba_id}?fields=id,name`` — existe e enxergamos? Então é conta nossa.

        Qualquer falha devolve ``None``: quem chama trata isso como "não confirmado" e não
        grava nada. Errar para o lado de não adotar custa um preenchimento manual; errar
        para o outro grava um id que faz toda submissão falhar.
        """
        meta_waba_id = (meta_waba_id or "").strip()
        if not meta_waba_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{_BASE}/{meta_waba_id}",
                    headers=self._headers,
                    params={"fields": "id,name"},
                )
                resp.raise_for_status()
                dados = resp.json()
        except Exception as exc:  # noqa: BLE001 — id desconhecido, token sem acesso, rede
            logger.info("Conta %r não confirmada na Meta: %s", meta_waba_id, exc)
            return None
        if str(dados.get("id") or "") != meta_waba_id:
            return None
        return str(dados.get("name") or "")

    async def remover(self, *, nome: str, meta_waba_id: str) -> bool:
        url = self._url(meta_waba_id)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(
                url, headers=self._headers, params={"name": nome}
            )
            if resp.status_code == 404:
                # Já não existe lá: para quem chamou, o efeito desejado está satisfeito.
                return False
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise CatalogoTemplatesIndisponivel(
                    f"Não foi possível remover o template na Meta: {self._erro_legivel(exc)}"
                ) from exc
        return True


class CatalogoTemplatesAusente:
    """Stub para quando o canal efetivo é ``demo`` (sem token de acesso).

    Falha **no uso**, com a causa dita por extenso, em vez de no boot: o resto do produto
    não depende de gerir template, e derrubar a aplicação inteira por causa de uma env
    faltando repetiria o erro que ``canal_efetivo`` (§9c) existe para acusar.
    """

    def __init__(self, motivo: str) -> None:
        self._motivo = motivo

    def _falhar(self) -> None:
        raise CatalogoTemplatesIndisponivel(self._motivo)

    async def submeter(
        self, template: MessageTemplate, *, meta_waba_id: str
    ) -> TemplateRemoto:
        self._falhar()
        raise AssertionError("inalcançável")  # pragma: no cover

    async def listar(self, *, meta_waba_id: str) -> list[TemplateRemoto]:
        self._falhar()
        raise AssertionError("inalcançável")  # pragma: no cover

    async def remover(self, *, nome: str, meta_waba_id: str) -> bool:
        self._falhar()
        raise AssertionError("inalcançável")  # pragma: no cover

    async def descrever(self, *, meta_waba_id: str) -> str | None:
        # Sem canal não há como confirmar — e "não confirmado" já é o estado seguro, então
        # esta é a única operação do stub que **não** levanta: adoção simplesmente não
        # acontece, e o id segue sendo preenchido à mão.
        return None
