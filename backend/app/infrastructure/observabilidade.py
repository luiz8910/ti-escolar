"""Alerta ativo de falha (§15, item 8) via Sentry.

**Por que existia um buraco.** O log já é persistido e consultável em `/admin/logs` (§16),
mas ninguém é *avisado*: era preciso alguém abrir o painel para descobrir que algo quebrou.
Numa plataforma que a secretaria usa em horário escolar, isso significa a escola descobrir o
erro antes de nós.

**Por que Sentry, e por que isso não prende ninguém.** No plano free são 5 mil erros/mês, de
sobra para uma escola-piloto. E o GlitchTip fala o mesmo protocolo: se o volume crescer ou o
preço incomodar, migrar é trocar o DSN — nenhuma linha deste arquivo muda.

**O ponto delicado é a LGPD, não a integração.** O Sentry é operador nos Estados Unidos, e
um payload de erro carrega, sem pedir licença, o corpo da requisição, os cabeçalhos e as
variáveis locais do traceback. Numa base que guarda laudo, CPF e telefone de responsável,
mandar isso para fora é transferência internacional de dado sensível de menor. Por isso:

- ``send_default_pii=False`` — não anexa corpo de requisição, cookies nem IP;
- ``before_send`` **remove o que sobrar**, e falha fechado: qualquer erro na limpeza
  descarta o evento inteiro, porque um evento perdido custa menos que um laudo vazado;
- ``max_request_body_size="never"`` — reforça o primeiro, para o caso de uma versão futura
  do SDK mudar o default.

O que continua indo, e é o que interessa: tipo da exceção, traceback, rota, método, status,
e o **id de correlação** que o `middleware.py` já produz — que é o que liga o alerta à linha
correspondente em `/admin/logs`.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger("observabilidade")

# Chaves cujo valor nunca deve sair daqui, casadas por substring no nome (minúsculo).
_CHAVES_SENSIVEIS = (
    "senha", "password", "token", "secret", "authorization", "cookie", "api_key",
    "cpf", "rg", "nis", "telefone", "phone", "contato", "email", "e-mail",
    "laudo", "cid", "cor_raca", "alergia", "saude", "nome", "responsavel", "aluno",
)

_REDIGIDO = "[redigido]"

# Telefone brasileiro em E.164 e CPF, para o caso de virem embutidos numa MENSAGEM de erro
# (ex.: "número +5515997536978 inválido"), onde a limpeza por chave não alcança.
_TELEFONE = re.compile(r"\+?55\d{10,11}\b")
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")


def _mascarar_texto(valor: str) -> str:
    return _CPF.sub(_REDIGIDO, _TELEFONE.sub(_REDIGIDO, valor))


def _limpar(obj, profundidade: int = 0):
    """Percorre o evento removendo dado pessoal.

    O limite de profundidade não é paranoia: eventos do Sentry aninham stack frames com
    variáveis locais que podem referenciar estruturas grandes, e uma recursão sem freio
    transformaria o `before_send` — que roda no caminho do erro — num segundo problema.
    """
    if profundidade > 12:
        return _REDIGIDO
    if isinstance(obj, dict):
        limpo = {}
        for chave, valor in obj.items():
            nome = str(chave).lower()
            if any(s in nome for s in _CHAVES_SENSIVEIS):
                limpo[chave] = _REDIGIDO
            else:
                limpo[chave] = _limpar(valor, profundidade + 1)
        return limpo
    if isinstance(obj, (list, tuple)):
        return type(obj)(_limpar(v, profundidade + 1) for v in obj)
    if isinstance(obj, str):
        return _mascarar_texto(obj)
    return obj


def before_send(evento: dict, _hint) -> dict | None:
    """Última barreira antes de o evento sair do processo.

    **Falha fechado de propósito.** Se a limpeza levantar exceção, o evento é descartado em
    vez de enviado cru: perder um alerta é um incômodo, vazar um laudo de criança é um
    incidente de dados. Deixar passar "só desta vez" seria escolher o pior dos dois.
    """
    try:
        return _limpar(evento)
    except Exception:  # noqa: BLE001
        logger.warning("Evento do Sentry descartado: falha ao remover dado pessoal.")
        return None


def iniciar_sentry(settings) -> bool:
    """Liga o Sentry se houver DSN. Devolve se ficou ativo.

    Sem DSN não é erro: é o estado de desenvolvimento e o de quem não quer o subprocessador.
    O produto funciona igual — só não avisa ninguém.
    """
    if not settings.sentry_dsn:
        return False
    try:
        import sentry_sdk
    except ImportError:
        # Extra não instalado. Avisa e segue: um alerta ausente não pode derrubar a API.
        logger.warning(
            "SENTRY_DSN definido, mas o pacote sentry-sdk não está instalado "
            '(instale o extra "obs"). Seguindo sem alerta ativo.'
        )
        return False

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment or settings.app_env,
        # Amostragem de performance desligada por padrão: o valor aqui é o alerta de erro,
        # e trace de transação é o que consome a franquia do plano free depressa.
        traces_sample_rate=settings.sentry_traces_sample_rate,
        send_default_pii=False,
        max_request_body_size="never",
        before_send=before_send,
    )
    logger.info(
        "Sentry ativo (ambiente %r).", settings.sentry_environment or settings.app_env
    )
    return True
