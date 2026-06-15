"""Hash de senha (PBKDF2-SHA256, somente stdlib — sem dependência extra).

Formato armazenado: ``pbkdf2_sha256$<iteracoes>$<salt_b64>$<hash_b64>``.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

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
