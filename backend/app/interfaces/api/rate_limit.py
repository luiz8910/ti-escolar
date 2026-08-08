"""Aplicação do limite de taxa na borda HTTP (item 5 do checklist de pré-deploy).

Protege dois pontos, pelos motivos que os tornam diferentes:

- **Login** (`/api/admin/login`, `/api/professor/login`): brute force. O PBKDF2 encarece
  cada tentativa, mas não limita quantas o atacante faz. Conta-se por **IP e por e-mail**:
  só por IP, uma botnet distribuída passa livre; só por e-mail, qualquer um consegue
  trancar a conta do diretor de propósito. Exigindo os dois, o ataque distribuído esbarra
  no contador do e-mail e o bloqueio de conta alheia exige controlar o IP da vítima.
- **Webhook inbound**: um número em loop consome a cota de LLM da escola. O limite é por
  **telefone remetente**, não por IP — o IP é sempre o da Meta.

Recusa devolve **429** com ``Retry-After``. Sem mensagem detalhada: dizer "senha errada,
faltam 3 tentativas" entrega ao atacante a régua do limite.
"""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status

from app.config import Settings, get_settings
from app.domain.ports import ControleTaxa
from app.infrastructure.db.session import SessionLocal
from app.infrastructure.rate_limit import SqlControleTaxa

logger = logging.getLogger("rate_limit")

# Compartilhado entre requisições; o estado real está no Postgres, não aqui.
_controle = SqlControleTaxa(SessionLocal)


def get_controle_taxa() -> ControleTaxa:
    return _controle


def cliente_ip(request: Request, settings: Settings | None = None) -> str:
    """IP de origem, considerando o proxy do provedor de deploy.

    No Render a aplicação está atrás de um proxy, então ``request.client.host`` é sempre o
    IP dele — inútil para limitar. O ``X-Forwarded-For`` resolve, mas é **enviado pelo
    cliente** e portanto forjável: só é considerado quando ``TRUST_PROXY_HEADERS`` está
    ligado, ou seja, quando sabemos que há um proxy reescrevendo o cabeçalho na frente.
    """
    settings = settings or get_settings()
    if settings.trust_proxy_headers:
        encaminhado = request.headers.get("x-forwarded-for", "")
        if encaminhado:
            # O primeiro da lista é o cliente original; os demais são proxies.
            return encaminhado.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


async def exigir_limite(
    controle: ControleTaxa,
    *,
    chaves: list[str],
    limite: int,
    janela_segundos: int,
    rotulo: str,
) -> None:
    """Contabiliza a chamada em cada chave e levanta 429 se qualquer uma estourar.

    Todas as chaves são registradas mesmo quando a primeira já recusa: se parássemos na
    primeira, um atacante que já estourou o contador do próprio IP ficaria invisível para
    o contador do e-mail que ele está tentando adivinhar.
    """
    if limite <= 0:
        return
    excedida: str | None = None
    retry_after = janela_segundos
    for chave in chaves:
        resultado = await controle.registrar(
            chave=chave, limite=limite, janela_segundos=janela_segundos
        )
        if not resultado.permitido and excedida is None:
            excedida, retry_after = chave, resultado.retry_after
    if excedida is None:
        return
    logger.warning(
        "Limite de taxa excedido em %s (chave=%s, limite=%d/%ds)",
        rotulo,
        excedida,
        limite,
        janela_segundos,
    )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Muitas tentativas. Tente novamente em instantes.",
        headers={"Retry-After": str(retry_after)},
    )


async def limitar_login(
    request: Request,
    *,
    identificador: str,
    escopo: str,
    controle: ControleTaxa | None = None,
    settings: Settings | None = None,
) -> None:
    """Limite do login, por IP **e** por identificador (e-mail do admin / do professor)."""
    settings = settings or get_settings()
    if not settings.rate_limit_habilitado:
        return
    controle = controle or get_controle_taxa()
    ip = cliente_ip(request, settings)
    identificador = (identificador or "").strip().lower()
    chaves = [f"login:{escopo}:ip:{ip}"]
    if identificador:
        chaves.append(f"login:{escopo}:id:{identificador}")
    await exigir_limite(
        controle,
        chaves=chaves,
        limite=settings.rate_limit_login_tentativas,
        janela_segundos=settings.rate_limit_login_janela_segundos,
        rotulo=f"login/{escopo}",
    )


# O limite do **inbound** não mora aqui: ele é injetado em ``ProcessarInboundMeta``
# (`app/interfaces/deps.py`), porque a decisão ali não é devolver 429 — o webhook precisa
# responder ``200 OK`` à Meta de qualquer jeito, sob pena de o evento ser reenviado e a
# saúde do endpoint cair. A mensagem excedente é apenas **não atendida**.
