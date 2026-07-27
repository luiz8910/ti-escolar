"""Hash de senha, tokens JWT e assinatura de webhook (somente stdlib — sem dependência extra).

- Senha: PBKDF2-SHA256, formato ``pbkdf2_sha256$<iteracoes>$<salt_b64>$<hash_b64>``.
- Token: JWT compacto assinado com HS256 (HMAC-SHA256), usado na autenticação
  por ``Authorization: Bearer <token>`` do painel administrativo.
- Webhook: validação do ``X-Hub-Signature-256`` da Meta (HMAC-SHA256 do corpo bruto).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Any

_ALGO = "pbkdf2_sha256"
_ITERACOES = 200_000


def hash_senha(senha: str, *, iteracoes: int = _ITERACOES) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, iteracoes)
    return f"{_ALGO}${iteracoes}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verificar_senha(senha: str, armazenado: str) -> bool:
    try:
        algo, iters, salt_b64, dk_b64 = armazenado.split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        esperado = base64.b64decode(dk_b64)
        dk = hashlib.pbkdf2_hmac("sha256", senha.encode(), salt, int(iters))
        return hmac.compare_digest(dk, esperado)
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# JWT (HS256) — autenticação por token do painel administrativo
# --------------------------------------------------------------------------- #
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(segmento: str) -> bytes:
    padding = "=" * (-len(segmento) % 4)
    return base64.urlsafe_b64decode(segmento + padding)


def criar_token(claims: dict[str, Any], *, segredo: str, expira_em_segundos: int) -> str:
    """Gera um JWT HS256 com ``iat``/``exp`` a partir dos ``claims`` informados."""
    agora = int(time.time())
    payload = {**claims, "iat": agora, "exp": agora + expira_em_segundos}
    cabecalho = {"alg": "HS256", "typ": "JWT"}
    base = (
        f"{_b64url_encode(json.dumps(cabecalho, separators=(',', ':')).encode())}."
        f"{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    assinatura = hmac.new(segredo.encode(), base.encode(), hashlib.sha256).digest()
    return f"{base}.{_b64url_encode(assinatura)}"


def decodificar_token(token: str, *, segredo: str) -> dict[str, Any] | None:
    """Valida assinatura e expiração; devolve o payload ou ``None`` se inválido/expirado."""
    try:
        cabecalho_b64, payload_b64, assinatura_b64 = token.split(".")
    except ValueError:
        return None

    base = f"{cabecalho_b64}.{payload_b64}"
    esperado = hmac.new(segredo.encode(), base.encode(), hashlib.sha256).digest()
    try:
        recebido = _b64url_decode(assinatura_b64)
    except (ValueError, TypeError):
        return None
    if not hmac.compare_digest(esperado, recebido):
        return None

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None

    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time():
        return None
    return payload


def validar_assinatura_meta(*, corpo: bytes, cabecalho: str | None, app_secret: str) -> bool:
    """Valida o ``X-Hub-Signature-256`` de um webhook da Meta.

    A Meta assina o **corpo bruto** da requisição com HMAC-SHA256, usando o *app secret*
    como chave, e envia o resultado no formato ``sha256=<hex>``. O ``corpo`` precisa ser
    exatamente os bytes recebidos (``await request.body()``): reserializar o JSON muda os
    bytes (espaços, ordem das chaves) e invalida a assinatura.

    A comparação é feita em tempo constante para não vazar, pelo tempo de resposta, quantos
    bytes do prefixo da assinatura estavam corretos.
    """
    if not app_secret or not cabecalho:
        return False
    prefixo, _, recebido = cabecalho.partition("=")
    if prefixo != "sha256" or not recebido:
        return False
    esperado = hmac.new(app_secret.encode(), corpo, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, recebido)
