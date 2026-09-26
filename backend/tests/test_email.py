"""Envio de e-mail: adaptador do Resend e escolha do provedor (item 5 do plano).

O que estava errado antes: o único adaptador era o de log. O aviso de licença a vencer
rodava, o painel reportava "avisos enviados" e nenhum e-mail saía. O teste central aqui é
justamente o do contrato com o provedor — e o de que uma falha dele não derruba o lote.
"""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.infrastructure.factories import criar_email_sender
from app.infrastructure.messaging.email import (
    LogEmailSender,
    ResendEmailSender,
    SmtpEmailSender,
)


class TransporteFake(httpx.AsyncBaseTransport):
    """Intercepta a chamada HTTP sem rede: guarda a requisição e devolve o que se pedir."""

    def __init__(self, status: int = 200, corpo: dict | None = None) -> None:
        self.status = status
        self.corpo = corpo if corpo is not None else {"id": "re_123"}
        self.requisicoes: list[httpx.Request] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes.append(request)
        return httpx.Response(self.status, json=self.corpo, request=request)


@pytest.fixture
def transporte(monkeypatch) -> TransporteFake:
    fake = TransporteFake()
    original = httpx.AsyncClient

    def cliente_com_transporte(*args, **kwargs):
        kwargs["transport"] = fake
        return original(*args, **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", cliente_com_transporte)
    return fake


# --------------------------------------------------------------------------- #
# Contrato com o Resend
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_envia_com_o_payload_e_a_autenticacao_esperados(transporte):
    import json

    sender = ResendEmailSender(remetente="no-reply@tiescolar.com.br", api_key="re_chave")
    await sender.enviar(
        destinatario="diretor@escola.br",
        assunto="Licença a vencer",
        corpo="Sua licença vence em 30 dias.",
    )

    assert len(transporte.requisicoes) == 1
    req = transporte.requisicoes[0]
    assert req.headers["Authorization"] == "Bearer re_chave"
    corpo = json.loads(req.content)
    assert corpo["from"] == "no-reply@tiescolar.com.br"
    assert corpo["to"] == ["diretor@escola.br"]
    assert corpo["subject"] == "Licença a vencer"
    assert corpo["text"] == "Sua licença vence em 30 dias."


@pytest.mark.asyncio
async def test_erro_do_provedor_nao_propaga(transporte):
    """O aviso de licença percorre várias escolas: se o provedor recusar uma, as demais
    precisam continuar. Por isso a falha é registrada, não levantada."""
    transporte.status = 422
    sender = ResendEmailSender(remetente="no-reply@tiescolar.com.br", api_key="re_chave")

    await sender.enviar(destinatario="x@y.z", assunto="a", corpo="b")  # não levanta


@pytest.mark.asyncio
async def test_falha_de_rede_nao_propaga(monkeypatch):
    class TransporteQueFalha(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):
            raise httpx.ConnectError("sem rota para o host", request=request)

    original = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *a, **kw: original(*a, **{**kw, "transport": TransporteQueFalha()}),
    )
    sender = ResendEmailSender(remetente="a@b.c", api_key="re_chave")

    await sender.enviar(destinatario="x@y.z", assunto="a", corpo="b")  # não levanta


@pytest.mark.asyncio
async def test_sem_chave_nao_chama_a_api(transporte):
    """Config incompleta não pode virar uma requisição sem credencial — que só voltaria
    401 e ainda gastaria o timeout."""
    sender = ResendEmailSender(remetente="a@b.c", api_key="")

    await sender.enviar(destinatario="x@y.z", assunto="a", corpo="b")

    assert transporte.requisicoes == []


# --------------------------------------------------------------------------- #
# Escolha do provedor
# --------------------------------------------------------------------------- #


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_provedor_resend_com_chave_usa_o_adaptador_real():
    sender = criar_email_sender(
        _settings(email_provider="resend", resend_api_key="re_chave")
    )
    assert isinstance(sender, ResendEmailSender)


def test_provedor_resend_sem_chave_cai_no_log():
    """Um deploy sem RESEND_API_KEY não derruba a aplicação — mas o painel de segurança
    é quem denuncia a situação, para ela não passar despercebida."""
    sender = criar_email_sender(_settings(email_provider="resend", resend_api_key=None))
    assert isinstance(sender, LogEmailSender)


def test_default_e_o_adaptador_de_log():
    assert isinstance(criar_email_sender(_settings()), LogEmailSender)


def test_provedor_smtp_com_host_usa_o_adaptador_smtp():
    sender = criar_email_sender(_settings(email_provider="smtp", smtp_host="mailpit"))
    assert isinstance(sender, SmtpEmailSender)


def test_provedor_smtp_sem_host_cai_no_log():
    sender = criar_email_sender(_settings(email_provider="smtp", smtp_host=""))
    assert isinstance(sender, LogEmailSender)


# --------------------------------------------------------------------------- #
# SMTP (Mailpit local)
# --------------------------------------------------------------------------- #


class SmtpFake:
    """Substitui ``smtplib.SMTP``: guarda a conexão e as mensagens, sem rede."""

    instancias: list["SmtpFake"] = []

    def __init__(self, host: str, porta: int, timeout: float) -> None:
        self.host, self.porta = host, porta
        self.mensagens: list = []
        SmtpFake.instancias.append(self)

    def __enter__(self) -> "SmtpFake":
        return self

    def __exit__(self, *exc) -> None:
        return None

    def send_message(self, mensagem) -> None:
        self.mensagens.append(mensagem)


@pytest.mark.asyncio
async def test_smtp_entrega_remetente_destinatario_assunto_e_corpo(monkeypatch):
    import smtplib

    SmtpFake.instancias = []
    monkeypatch.setattr(smtplib, "SMTP", SmtpFake)
    sender = SmtpEmailSender(remetente="no-reply@tiescolar.test", host="mailpit", porta=1025)

    await sender.enviar(destinatario="diretor@escola.br", assunto="Licença", corpo="Vence.")

    [conexao] = SmtpFake.instancias
    assert (conexao.host, conexao.porta) == ("mailpit", 1025)
    [mensagem] = conexao.mensagens
    assert mensagem["From"] == "no-reply@tiescolar.test"
    assert mensagem["To"] == "diretor@escola.br"
    assert mensagem["Subject"] == "Licença"
    assert mensagem.get_content().strip() == "Vence."


@pytest.mark.asyncio
async def test_smtp_fora_do_ar_nao_derruba_quem_chamou():
    """Porta fechada: o erro vai para o log e o lote de avisos segue."""
    sender = SmtpEmailSender(remetente="a@b.c", host="127.0.0.1", porta=1, timeout_segundos=1)

    await sender.enviar(destinatario="x@y.z", assunto="a", corpo="b")
