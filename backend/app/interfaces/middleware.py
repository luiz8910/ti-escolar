"""Middleware de observabilidade e tratamento de erro (§16, item 6 do checklist).

Três coisas, na ordem em que importam:

1. **Id de correlação por requisição.** Gerado (ou herdado do ``X-Request-Id`` do proxy),
   guardado num ``ContextVar`` para que qualquer log emitido durante o atendimento o
   carregue, e devolvido no cabeçalho da resposta. É o número que se pede a quem relata
   um erro — sem ele, "deu erro ontem no painel" é impossível de achar no log.
2. **Uma linha por requisição**, com rota, status e duração. É o que alimenta o painel de
   logs e a medição de latência.
3. **Handler de exceção não tratada.** Antes, a exceção virava o 500 padrão do FastAPI:
   sem stack trace vazando ao cliente (bom), mas também sem nada para rastrear. Agora o
   traceback vai para o log com o id de correlação, e o cliente recebe **só o id**.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

from app.infrastructure.logs import (
    correlacao_atual,
    metodo_atual,
    novo_id_correlacao,
    rota_atual,
    tenant_atual,
)

logger = logging.getLogger("http")

CABECALHO_CORRELACAO = "X-Request-Id"

# Rotas cuja linha de log não acrescenta nada: o health check do Render bate a cada poucos
# segundos e sozinho encheria o painel.
ROTAS_SILENCIOSAS = ("/health", "/docs", "/openapi.json", "/redoc")


class ContextoRequisicaoMiddleware(BaseHTTPMiddleware):
    """Injeta o id de correlação, mede a duração e registra o desfecho da requisição."""

    async def dispatch(self, request: Request, call_next):
        correlacao = (request.headers.get(CABECALHO_CORRELACAO) or "").strip()[:40]
        correlacao = correlacao or novo_id_correlacao()

        caminho = request.url.path
        # Também no ``scope`` da requisição, não só no ContextVar: o handler de exceção
        # não tratada roda no ``ServerErrorMiddleware``, que é mais externo que este
        # middleware — quando ele executa, o ContextVar já foi restaurado. O ``state`` é
        # carregado no scope e atravessa essa fronteira.
        request.state.correlacao = correlacao

        # Guarda os tokens para restaurar o contexto anterior: o ContextVar é por task, e
        # deixá-lo sujo faria o próximo log dessa task herdar o id de outra requisição.
        tokens = (
            correlacao_atual.set(correlacao),
            rota_atual.set(caminho),
            metodo_atual.set(request.method),
            tenant_atual.set(None),
        )
        inicio = time.perf_counter()
        try:
            resposta = await call_next(request)
            duracao = int((time.perf_counter() - inicio) * 1000)
            resposta.headers[CABECALHO_CORRELACAO] = correlacao
            self._registrar(request, caminho, resposta.status_code, duracao)
            return resposta
        except Exception:
            # O handler de exceção do app ainda vai rodar e produzir a resposta; aqui só
            # garantimos que a duração e o desfecho apareçam no log mesmo assim.
            duracao = int((time.perf_counter() - inicio) * 1000)
            logger.error(
                "%s %s falhou após %dms",
                request.method,
                caminho,
                duracao,
                extra={"status_code": 500, "duracao_ms": duracao},
            )
            raise
        finally:
            correlacao_atual.reset(tokens[0])
            rota_atual.reset(tokens[1])
            metodo_atual.reset(tokens[2])
            tenant_atual.reset(tokens[3])

    @staticmethod
    def _registrar(request: Request, caminho: str, status_code: int, duracao: int) -> None:
        if caminho.startswith(ROTAS_SILENCIOSAS):
            return
        nivel = logging.INFO
        if status_code >= 500:
            nivel = logging.ERROR
        elif status_code >= 400:
            nivel = logging.WARNING
        logger.log(
            nivel,
            "%s %s → %d (%dms)",
            request.method,
            caminho,
            status_code,
            duracao,
            extra={"status_code": status_code, "duracao_ms": duracao},
        )


def correlacao_de(request: Request) -> str:
    """Id da requisição, preferindo o ``scope`` (sobrevive à troca de middleware)."""
    return getattr(request.state, "correlacao", "") or correlacao_atual.get("")


def registrar_handlers(app: FastAPI) -> None:
    """Instala os handlers de erro que devolvem o id de correlação ao cliente."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Erros esperados (401, 403, 404, 429...) já são logados pelo middleware; aqui só
        # acrescentamos o id à resposta, para o suporte conseguir cruzar com o log.
        correlacao = correlacao_de(request)
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, "id_correlacao": correlacao},
            headers={**(exc.headers or {}), CABECALHO_CORRELACAO: correlacao},
        )

    @app.exception_handler(RequestValidationError)
    async def _validacao(request: Request, exc: RequestValidationError) -> JSONResponse:
        correlacao = correlacao_de(request)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors(), "id_correlacao": correlacao},
            headers={CABECALHO_CORRELACAO: correlacao},
        )

    @app.exception_handler(Exception)
    async def _erro_interno(request: Request, exc: Exception) -> JSONResponse:
        correlacao = correlacao_de(request)
        # exc_info=True: o traceback vai para o log (e para o painel), nunca para a resposta.
        logger.exception(
            "Erro não tratado em %s %s", request.method, request.url.path,
            extra={"status_code": 500},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "detail": (
                    "Erro interno. Informe o código abaixo ao suporte para localizarmos "
                    "o ocorrido."
                ),
                "id_correlacao": correlacao,
            },
            headers={CABECALHO_CORRELACAO: correlacao},
        )
