"""Limite de taxa de entrada (item 5 do checklist de pré-deploy).

Cobre as três decisões que importam: contar por IP **e** por identificador no login,
recusar com 429 + ``Retry-After``, e cortar o inbound abusivo **antes** da LLM — que é o
recurso caro que um número em loop queimaria da escola.

Usa o adaptador em memória; o de Postgres (``SqlControleTaxa``) tem a mesma semântica de
janela fixa, validada aqui, e o SQL em si é exercitado pelo `alembic upgrade` do CI.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException, Request

from app.application.inbound_use_cases import ProcessarInboundMeta
from app.application.use_cases import (
    ReceberMensagemRecebida,
    RecuperarEEnviarDocumento,
    ResponderDuvida,
)
from app.config import Settings
from app.domain.entities import Tenant
from app.infrastructure.rate_limit import ControleTaxaMemoria
from app.interfaces.api.rate_limit import cliente_ip, exigir_limite, limitar_login
from tests.fakes import (
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeVectorStore,
    fake_embedder,
)
from tests.test_inbound_meta import (
    PID_ROSA,
    CanalEspiao,
    FakeTenantRepoInbound,
    _payload_mensagem,
)


def _request(ip: str = "203.0.113.7", *, encaminhado: str | None = None) -> Request:
    """Request mínima: só o que ``cliente_ip`` lê (client + cabeçalhos)."""
    headers = []
    if encaminhado is not None:
        headers.append((b"x-forwarded-for", encaminhado.encode()))
    return Request(
        {"type": "http", "method": "POST", "path": "/", "headers": headers, "client": (ip, 1234)}
    )


def _settings(**kwargs) -> Settings:
    base = {
        "rate_limit_habilitado": True,
        "rate_limit_login_tentativas": 3,
        "rate_limit_login_janela_segundos": 300,
        "trust_proxy_headers": False,
    }
    base.update(kwargs)
    return Settings(**base)


# --------------------------------------------------------------------------- #
# Contador de janela fixa
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_permite_ate_o_limite_e_recusa_o_excedente():
    controle = ControleTaxaMemoria()
    for esperado in (2, 1, 0):
        r = await controle.registrar(chave="k", limite=3, janela_segundos=60)
        assert r.permitido
        assert r.restantes == esperado

    r = await controle.registrar(chave="k", limite=3, janela_segundos=60)
    assert not r.permitido
    assert r.restantes == 0
    assert r.retry_after > 0


@pytest.mark.asyncio
async def test_chaves_diferentes_nao_se_contaminam():
    controle = ControleTaxaMemoria()
    for _ in range(3):
        await controle.registrar(chave="a", limite=3, janela_segundos=60)
    assert not (await controle.registrar(chave="a", limite=3, janela_segundos=60)).permitido
    assert (await controle.registrar(chave="b", limite=3, janela_segundos=60)).permitido


@pytest.mark.asyncio
async def test_janela_vencida_reinicia_a_contagem():
    """Sem isso o bloqueio seria permanente: quem errou a senha 3× nunca mais entraria."""
    controle = ControleTaxaMemoria()
    antiga = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=600)
    controle._janelas["k"] = (antiga, 99)

    r = await controle.registrar(chave="k", limite=3, janela_segundos=300)
    assert r.permitido
    assert r.contador == 1


# --------------------------------------------------------------------------- #
# Aplicação no login
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_excedente_recebe_429_com_retry_after():
    controle = ControleTaxaMemoria()
    for _ in range(3):
        await exigir_limite(
            controle, chaves=["x"], limite=3, janela_segundos=60, rotulo="teste"
        )

    with pytest.raises(HTTPException) as erro:
        await exigir_limite(
            controle, chaves=["x"], limite=3, janela_segundos=60, rotulo="teste"
        )
    assert erro.value.status_code == 429
    assert int(erro.value.headers["Retry-After"]) > 0
    # A mensagem não revela a régua do limite a quem está sondando.
    assert "tentativa" not in str(erro.value.detail).lower() or "instantes" in str(
        erro.value.detail
    )


@pytest.mark.asyncio
async def test_todas_as_chaves_sao_contadas_mesmo_apos_a_primeira_estourar():
    """Se parássemos na primeira chave recusada, um atacante que já estourou o contador
    do próprio IP ficaria invisível para o contador do e-mail que está tentando adivinhar."""
    controle = ControleTaxaMemoria()
    for _ in range(4):
        try:
            await exigir_limite(
                controle,
                chaves=["ip", "email"],
                limite=3,
                janela_segundos=60,
                rotulo="teste",
            )
        except HTTPException:
            pass

    r = await controle.registrar(chave="email", limite=100, janela_segundos=60)
    assert r.contador == 5  # 4 das tentativas + esta


@pytest.mark.asyncio
async def test_login_conta_por_ip_e_por_identificador():
    controle = ControleTaxaMemoria()
    settings = _settings(rate_limit_login_tentativas=3)

    # Mesmo e-mail, IPs diferentes: o contador do e-mail é que segura o ataque distribuído.
    for i in range(3):
        await limitar_login(
            _request(f"198.51.100.{i}"),
            identificador="diretor@escola.br",
            escopo="admin",
            controle=controle,
            settings=settings,
        )
    with pytest.raises(HTTPException) as erro:
        await limitar_login(
            _request("198.51.100.9"),
            identificador="diretor@escola.br",
            escopo="admin",
            controle=controle,
            settings=settings,
        )
    assert erro.value.status_code == 429


@pytest.mark.asyncio
async def test_identificador_e_normalizado_para_nao_burlar_o_contador():
    controle = ControleTaxaMemoria()
    settings = _settings(rate_limit_login_tentativas=2)
    for variante in (" Diretor@Escola.BR ", "diretor@escola.br"):
        await limitar_login(
            _request("198.51.100.1"),
            identificador=variante,
            escopo="admin",
            controle=controle,
            settings=settings,
        )
    with pytest.raises(HTTPException):
        await limitar_login(
            _request("198.51.100.2"),
            identificador="DIRETOR@ESCOLA.BR",
            escopo="admin",
            controle=controle,
            settings=settings,
        )


@pytest.mark.asyncio
async def test_escopos_de_login_sao_independentes():
    """Um professor tentando a senha não pode trancar o login do painel da secretaria."""
    controle = ControleTaxaMemoria()
    settings = _settings(rate_limit_login_tentativas=2)
    for _ in range(3):
        try:
            await limitar_login(
                _request("198.51.100.1"),
                identificador="+5515999990000",
                escopo="professor",
                controle=controle,
                settings=settings,
            )
        except HTTPException:
            pass

    await limitar_login(
        _request("198.51.100.1"),
        identificador="diretor@escola.br",
        escopo="admin",
        controle=controle,
        settings=settings,
    )


@pytest.mark.asyncio
async def test_limite_desligado_nao_bloqueia():
    controle = ControleTaxaMemoria()
    settings = _settings(rate_limit_habilitado=False)
    for _ in range(50):
        await limitar_login(
            _request(),
            identificador="a@b.c",
            escopo="admin",
            controle=controle,
            settings=settings,
        )


# --------------------------------------------------------------------------- #
# IP de origem atrás do proxy
# --------------------------------------------------------------------------- #


def test_ip_ignora_x_forwarded_for_quando_nao_ha_proxy_confiavel():
    """O cabeçalho é enviado pelo cliente: sem proxy reescrevendo, confiar nele daria ao
    atacante um IP novo por requisição."""
    req = _request("203.0.113.7", encaminhado="1.2.3.4")
    assert cliente_ip(req, _settings(trust_proxy_headers=False)) == "203.0.113.7"


def test_ip_usa_o_primeiro_do_x_forwarded_for_atras_de_proxy():
    req = _request("10.0.0.1", encaminhado="1.2.3.4, 10.0.0.2")
    assert cliente_ip(req, _settings(trust_proxy_headers=True)) == "1.2.3.4"


# --------------------------------------------------------------------------- #
# Inbound do webhook
# --------------------------------------------------------------------------- #


class LLMContada(FakeLLM):
    """FakeLLM que conta as chamadas — é o custo que o limite existe para conter."""

    def __init__(self) -> None:
        super().__init__()
        self.chamadas = 0

    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        self.chamadas += 1
        return await super().gerar(sistema=sistema, mensagens=mensagens)


def _inbound(controle, *, limite: int) -> tuple[ProcessarInboundMeta, CanalEspiao, LLMContada]:
    llm = LLMContada()
    canal = CanalEspiao()
    receber = ReceberMensagemRecebida(
        conversas=FakeConversaRepo(),
        responder=ResponderDuvida(
            embedder=fake_embedder(), store=FakeVectorStore(), llm=llm
        ),
        documentos=RecuperarEEnviarDocumento(
            source=FakeDocumentSource([]), canal=CanalEspiao()
        ),
    )
    escola = Tenant(
        id=uuid.uuid4(),
        nome="EM Rosa Cury",
        slug="rosa-cury",
        whatsapp_numero="+5515333330000",
        meta_phone_number_id=PID_ROSA,
    )
    uc = ProcessarInboundMeta(
        tenants=FakeTenantRepoInbound([escola]),
        receber=receber,
        canal=canal,
        controle_taxa=controle,
        limite_por_remetente=limite,
        janela_taxa_segundos=60,
    )
    return uc, canal, llm


@pytest.mark.asyncio
async def test_inbound_abusivo_e_cortado_antes_da_llm():
    """O ponto do limite: a mensagem excedente não pode chegar a custar uma chamada de LLM."""
    controle = ControleTaxaMemoria()
    uc, canal, llm = _inbound(controle, limite=2)

    for i in range(4):
        await uc.executar(
            payload=_payload_mensagem(phone_number_id=PID_ROSA, wamid=f"wamid.{i}")
        )

    assert len(canal.textos) == 2
    assert llm.chamadas == 2


@pytest.mark.asyncio
async def test_inbound_de_outro_remetente_nao_e_afetado():
    controle = ControleTaxaMemoria()
    uc, canal, _ = _inbound(controle, limite=1)

    await uc.executar(payload=_payload_mensagem(phone_number_id=PID_ROSA, wamid="w1"))
    r = await uc.executar(payload=_payload_mensagem(phone_number_id=PID_ROSA, wamid="w2"))
    assert r.limitadas == 1

    outro = await uc.executar(
        payload=_payload_mensagem(
            phone_number_id=PID_ROSA, de="5515777776666", wamid="w3"
        )
    )
    assert outro.respondidas == 1


@pytest.mark.asyncio
async def test_inbound_sem_limite_configurado_atende_tudo():
    uc, canal, _ = _inbound(ControleTaxaMemoria(), limite=0)
    for i in range(5):
        await uc.executar(
            payload=_payload_mensagem(phone_number_id=PID_ROSA, wamid=f"w{i}")
        )
    assert len(canal.textos) == 5
