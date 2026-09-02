"""Provisionamento de números na Meta — WhatsApp Business Management API (§9e.3).

Implementa a porta ``GestorDeNumeros`` sobre ``/{waba_id}/phone_numbers`` e
``/{phone_number_id}/{request_code,verify_code,register}``. Exige o escopo
``whatsapp_business_management`` no token de usuário do sistema — o mesmo do catálogo de
templates, e **não** o de envio.

**Por que existe.** Até aqui, pôr uma escola no ar exigia percorrer o console da Meta à
mão: criar o número, disparar o código, verificar, registrar com PIN, inscrever a WABA no
app e conferir o estado. Seis passos em três telas diferentes, dois deles silenciosos —
o app não publicado (§1.1) e a WABA não inscrita (§5.1) não dão erro em lugar nenhum,
apenas fazem o webhook emudecer. Automatizar isso não é conveniência: é transformar
falhas silenciosas em resposta de API com motivo escrito.

**O que continua manual, e vai continuar.** Comprar o chip, pôr num aparelho e ler o
código de 6 dígitos. Não há endpoint para isso, e o roteiro reflete a realidade: o painel
conduz tudo, para no campo do código, e segue quando alguém digita o que recebeu.
"""

from __future__ import annotations

import logging

import httpx

from app.domain.entities import EtapaOnboarding, NumeroNaMeta

logger = logging.getLogger("channel.meta.numeros")

_BASE = "https://graph.facebook.com/v21.0"

# Campos que descrevem o estado de um número. `name_status` é o que diz se o nome de
# exibição passou pela revisão — o caminho crítico do prazo de onboarding (§9e.3).
_CAMPOS = (
    "id,display_phone_number,verified_name,status,code_verification_status,"
    "name_status,quality_rating"
)


class ProvisionamentoIndisponivel(RuntimeError):
    """Erro de configuração ou recusa da Meta, levantado no uso — não no boot.

    Mesma escolha de ``CatalogoTemplatesIndisponivel``: o resto do produto não depende de
    cadastrar número, e derrubar a aplicação inteira por causa de uma env faltando
    repetiria justamente o erro que ``canal_efetivo`` (§9c) existe para acusar.
    """


def etapa_da_meta(*, status: str, verificacao: str) -> EtapaOnboarding:
    """Traduz os dois campos que a Meta usa para dizer onde o número parou.

    São **dois** porque descrevem coisas diferentes, e confundi-los é o erro clássico
    deste fluxo: ``code_verification_status`` responde "o código foi conferido?" e
    ``status`` responde "o número fala pela Cloud API?". **Verificar não é registrar** —
    depois do código o número passa de *Não verificado* para *Não registrado*, e continua
    mudo até o ``POST /register`` (docs/producao-whatsapp.md §2, passo 5).

    Desconhecido vira ``DESCONHECIDA``, nunca ``REGISTRADO``: falhar fechado aqui custa um
    passo repetido; falhar aberto libera um disparo que morre na Graph API depois de o
    painel já ter dito "pronto".
    """
    status = (status or "").upper()
    verificacao = (verificacao or "").upper()
    if status == "CONNECTED":
        return EtapaOnboarding.REGISTRADO
    if status in {"PENDING", "DISCONNECTED", "FLAGGED", "RESTRICTED", "UNKNOWN", ""}:
        # `EXPIRED` aparece em número que já está registrado há tempo — o código de
        # verificação de então caducou e não faz falta. Por isso o `status` manda: só
        # quando ele NÃO é CONNECTED é que a verificação decide a etapa.
        if verificacao in {"VERIFIED", "EXPIRED"}:
            return EtapaOnboarding.NAO_REGISTRADO
        if verificacao in {"NOT_VERIFIED", ""}:
            return EtapaOnboarding.NAO_VERIFICADO
    return EtapaOnboarding.DESCONHECIDA


def numero_da_meta(dados: dict) -> NumeroNaMeta:
    status = str(dados.get("status") or "")
    verificacao = str(dados.get("code_verification_status") or "")
    return NumeroNaMeta(
        phone_number_id=str(dados.get("id") or ""),
        numero_exibicao=str(dados.get("display_phone_number") or ""),
        nome_exibicao=str(dados.get("verified_name") or ""),
        etapa=etapa_da_meta(status=status, verificacao=verificacao),
        status_nome=str(dados.get("name_status") or ""),
        qualidade=str(dados.get("quality_rating") or ""),
        bruto=f"status={status or '-'} verificacao={verificacao or '-'}",
    )


def separar_e164(numero: str) -> tuple[str, str]:
    """Quebra ``+55 15 99753-6978`` em ``("55", "1599753678…")``.

    A Meta pede o código do país **separado** do resto (``cc`` e ``phone_number``), e o
    número sem ``+`` nem pontuação. Quem digita no painel digita E.164, que é o formato
    que o resto do produto usa — converter aqui é mais barato que pedir dois campos e
    depois descobrir que alguém repetiu o 55 nos dois.

    Só trata **+55**: aceitar um país qualquer exigiria a tabela de prefixos (que tem
    códigos de 1, 2 e 3 dígitos e não é derivável do texto), e o produto atende escolas
    brasileiras. Outro país é recusado com a causa por extenso, não adivinhado.
    """
    digitos = "".join(c for c in (numero or "") if c.isdigit())
    if not digitos:
        raise ProvisionamentoIndisponivel(
            "Informe o número do chip em formato internacional, por exemplo "
            "+55 15 99753-6978."
        )
    if not digitos.startswith("55") or not 12 <= len(digitos) <= 13:
        raise ProvisionamentoIndisponivel(
            "Por enquanto só números do Brasil (+55) são cadastrados automaticamente. "
            f"Recebido: {numero!r}. Cadastre pelo console da Meta e informe o "
            "phone_number_id à mão."
        )
    return "55", digitos[2:]


class MetaGestorDeNumeros:
    """Fala com a Graph API pelo token de usuário do sistema.

    Sem estado além do cabeçalho: a conta e o número são **parâmetro de cada chamada**,
    pelo mesmo motivo de ``MetaCatalogoTemplates`` — o token administra todo o portfólio,
    e fixar uma WABA no construtor faria a segunda escola ser cadastrada na conta errada.
    """

    def __init__(self, *, access_token: str) -> None:
        self._headers = {"Authorization": f"Bearer {access_token}"}

    # ---------------------------------------------------------------- infraestrutura --
    @staticmethod
    def _erro_legivel(exc: httpx.HTTPStatusError) -> str:
        """A causa real está no corpo, não no status.

        O ``HTTPStatusError`` cru diria "Client error '400'" para coisas tão diferentes
        quanto número já em uso, chip ativo no WhatsApp comum e token sem escopo — e é
        justamente essa distinção que decide o próximo passo de quem opera.
        """
        try:
            erro = exc.response.json().get("error", {})
        except Exception:  # noqa: BLE001 — corpo não-JSON: cai no texto bruto
            return (exc.response.text or "")[:300] or f"HTTP {exc.response.status_code}"
        partes = [
            erro.get("error_user_msg"),
            erro.get("error_user_title"),
            erro.get("message"),
            (erro.get("error_data") or {}).get("details"),
        ]
        return next(
            (str(p) for p in partes if p), f"HTTP {exc.response.status_code}"
        )

    async def _post(self, caminho: str, *, dados: dict, acao: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_BASE}/{caminho}", headers=self._headers, data=dados
            )
            try:
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                motivo = self._erro_legivel(exc)
                logger.warning("Meta recusou %s: %s", acao, motivo)
                raise ProvisionamentoIndisponivel(f"{acao}: {motivo}") from exc
            try:
                return resp.json()
            except Exception:  # noqa: BLE001 — 200 sem corpo JSON é sucesso mudo
                return {}

    @staticmethod
    def _exigir(valor: str, *, campo: str, onde: str) -> str:
        valor = (valor or "").strip()
        if not valor:
            # Recusar aqui dá a causa; deixar seguir montaria uma URL com um nó vazio e a
            # Meta responderia um 400 sobre outra coisa.
            raise ProvisionamentoIndisponivel(
                f"{campo} não informado — {onde}"
            )
        return valor

    def _waba(self, meta_waba_id: str) -> str:
        return self._exigir(
            meta_waba_id,
            campo="O id da conta do WhatsApp Business (WABA)",
            onde="preencha-o em Administração → Contas WhatsApp.",
        )

    def _numero(self, phone_number_id: str) -> str:
        return self._exigir(
            phone_number_id,
            campo="O id do número na Meta (phone_number_id)",
            onde="cadastre o número da escola antes deste passo.",
        )

    # --------------------------------------------------------------------- consultas --
    async def descrever(self, *, phone_number_id: str) -> NumeroNaMeta | None:
        """``None`` para qualquer falha — id desconhecido, token sem acesso ou rede.

        Quem chama trata isso como "não sei o estado" e mostra isso ao operador, em vez de
        inventar uma etapa. Errar para o lado de não saber custa um refresh; errar para o
        outro afirmaria que um número está no ar.
        """
        phone_number_id = (phone_number_id or "").strip()
        if not phone_number_id:
            return None
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{_BASE}/{phone_number_id}",
                    headers=self._headers,
                    params={"fields": _CAMPOS},
                )
                resp.raise_for_status()
                dados = resp.json()
        except Exception as exc:  # noqa: BLE001
            logger.info("Número %r não descrito na Meta: %s", phone_number_id, exc)
            return None
        if str(dados.get("id") or "") != phone_number_id:
            return None
        return numero_da_meta(dados)

    async def listar(self, *, meta_waba_id: str) -> list[NumeroNaMeta]:
        url: str | None = f"{_BASE}/{self._waba(meta_waba_id)}/phone_numbers"
        params: dict = {"fields": _CAMPOS, "limit": "100"}
        numeros: list[NumeroNaMeta] = []
        async with httpx.AsyncClient(timeout=30) as client:
            while url:
                resp = await client.get(url, headers=self._headers, params=params)
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    raise ProvisionamentoIndisponivel(
                        "Não foi possível listar os números da conta: "
                        f"{self._erro_legivel(exc)}"
                    ) from exc
                corpo = resp.json()
                numeros.extend(numero_da_meta(item) for item in corpo.get("data", []))
                # O ``next`` já carrega os filtros; repetir ``params`` duplicaria o cursor
                # e devolveria a mesma página para sempre.
                url = corpo.get("paging", {}).get("next")
                params = {}
        return numeros

    # ------------------------------------------------------------------ provisionamento --
    async def adicionar(
        self, *, meta_waba_id: str, codigo_pais: str, numero: str, nome_exibicao: str
    ) -> NumeroNaMeta:
        waba = self._waba(meta_waba_id)
        nome = (nome_exibicao or "").strip()
        if not nome:
            raise ProvisionamentoIndisponivel(
                "O nome de exibição é obrigatório: é o que os pais veem no WhatsApp, e a "
                "revisão dele pela Meta é o passo mais demorado do onboarding."
            )
        dados = await self._post(
            f"{waba}/phone_numbers",
            dados={
                "cc": codigo_pais,
                "phone_number": numero,
                "verified_name": nome,
            },
            acao="cadastrar o número na conta",
        )
        novo_id = str(dados.get("id") or "")
        if not novo_id:
            raise ProvisionamentoIndisponivel(
                "A Meta aceitou o cadastro mas não devolveu o id do número. "
                "Confira em Gerenciador do WhatsApp → Números de telefone."
            )
        logger.warning(
            "Número %s cadastrado na conta %s (id %s, nome %r).",
            numero,
            waba,
            novo_id,
            nome,
        )
        # Reler em vez de montar o retrato pela resposta: o POST devolve só o id, e o que
        # interessa ao painel (etapa, status do nome) só existe no GET.
        return await self.descrever(phone_number_id=novo_id) or NumeroNaMeta(
            phone_number_id=novo_id,
            nome_exibicao=nome,
            etapa=EtapaOnboarding.NAO_VERIFICADO,
        )

    async def solicitar_codigo(
        self, *, phone_number_id: str, metodo: str = "SMS", idioma: str = "pt_BR"
    ) -> None:
        metodo = (metodo or "SMS").upper()
        if metodo not in {"SMS", "VOICE"}:
            raise ProvisionamentoIndisponivel(
                f"Método de verificação inválido: {metodo!r}. Use SMS ou VOICE."
            )
        await self._post(
            f"{self._numero(phone_number_id)}/request_code",
            dados={"code_method": metodo, "language": idioma},
            acao="pedir o código de verificação",
        )
        logger.warning(
            "Código de verificação pedido por %s para o número %s.",
            metodo,
            phone_number_id,
        )

    async def confirmar_codigo(
        self, *, phone_number_id: str, codigo: str
    ) -> NumeroNaMeta:
        numero_id = self._numero(phone_number_id)
        digitos = "".join(c for c in (codigo or "") if c.isdigit())
        if len(digitos) != 6:
            raise ProvisionamentoIndisponivel(
                "O código de verificação tem 6 dígitos."
            )
        await self._post(
            f"{numero_id}/verify_code",
            dados={"code": digitos},
            acao="confirmar o código de verificação",
        )
        logger.warning("Número %s verificado.", numero_id)
        return await self.descrever(phone_number_id=numero_id) or NumeroNaMeta(
            phone_number_id=numero_id, etapa=EtapaOnboarding.NAO_REGISTRADO
        )

    async def registrar(self, *, phone_number_id: str, pin: str) -> NumeroNaMeta:
        numero_id = self._numero(phone_number_id)
        digitos = "".join(c for c in (pin or "") if c.isdigit())
        if len(digitos) != 6:
            raise ProvisionamentoIndisponivel(
                "O PIN de verificação em duas etapas tem 6 dígitos. Guarde-o no "
                "gerenciador de senhas: a Meta o exige de novo para reinscrever o número "
                "e não o exibe outra vez."
            )
        await self._post(
            f"{numero_id}/register",
            dados={"messaging_product": "whatsapp", "pin": digitos},
            acao="inscrever o número na Cloud API",
        )
        logger.warning("Número %s inscrito na Cloud API.", numero_id)
        return await self.descrever(phone_number_id=numero_id) or NumeroNaMeta(
            phone_number_id=numero_id, etapa=EtapaOnboarding.REGISTRADO
        )

    async def inscrever_no_app(self, *, meta_waba_id: str) -> bool:
        waba = self._waba(meta_waba_id)
        dados = await self._post(
            f"{waba}/subscribed_apps",
            dados={},
            acao="inscrever a conta no app (subscribed_apps)",
        )
        sucesso = bool(dados.get("success", True))
        logger.warning("Conta %s inscrita no app: %s", waba, sucesso)
        return sucesso

    async def definir_perfil(
        self,
        *,
        phone_number_id: str,
        descricao: str = "",
        endereco: str = "",
        email: str = "",
        site: str = "",
        setor: str = "EDU",
    ) -> bool:
        campos: dict[str, str] = {"messaging_product": "whatsapp", "vertical": setor}
        if descricao:
            # `about` é a linha curta sob o nome; `description`, o texto do perfil.
            campos["about"] = descricao[:139]
            campos["description"] = descricao[:512]
        if endereco:
            campos["address"] = endereco[:256]
        if email:
            campos["email"] = email[:128]
        if site:
            campos["websites"] = site
        await self._post(
            f"{self._numero(phone_number_id)}/whatsapp_business_profile",
            dados=campos,
            acao="atualizar o perfil comercial do número",
        )
        return True


class GestorDeNumerosAusente:
    """Stub para quando o canal efetivo é ``demo`` (sem token de acesso).

    Falha **no uso**, com a causa por extenso — nunca no boot. As consultas devolvem
    "não sei" em vez de levantar: um painel que não consegue perguntar o estado à Meta
    deve dizer isso, não explodir ao abrir a tela da escola.
    """

    def __init__(self, motivo: str) -> None:
        self._motivo = motivo

    def _falhar(self) -> None:
        raise ProvisionamentoIndisponivel(self._motivo)

    async def descrever(self, *, phone_number_id: str) -> NumeroNaMeta | None:
        return None

    async def listar(self, *, meta_waba_id: str) -> list[NumeroNaMeta]:
        return []

    async def adicionar(
        self, *, meta_waba_id: str, codigo_pais: str, numero: str, nome_exibicao: str
    ) -> NumeroNaMeta:
        self._falhar()
        raise AssertionError("inalcançável")  # pragma: no cover

    async def solicitar_codigo(
        self, *, phone_number_id: str, metodo: str = "SMS", idioma: str = "pt_BR"
    ) -> None:
        self._falhar()

    async def confirmar_codigo(self, *, phone_number_id: str, codigo: str) -> NumeroNaMeta:
        self._falhar()
        raise AssertionError("inalcançável")  # pragma: no cover

    async def registrar(self, *, phone_number_id: str, pin: str) -> NumeroNaMeta:
        self._falhar()
        raise AssertionError("inalcançável")  # pragma: no cover

    async def inscrever_no_app(self, *, meta_waba_id: str) -> bool:
        self._falhar()
        raise AssertionError("inalcançável")  # pragma: no cover

    async def definir_perfil(
        self,
        *,
        phone_number_id: str,
        descricao: str = "",
        endereco: str = "",
        email: str = "",
        site: str = "",
        setor: str = "EDU",
    ) -> bool:
        self._falhar()
        raise AssertionError("inalcançável")  # pragma: no cover
