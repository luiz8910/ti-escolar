"""Coleta de logs: logging estruturado + gravação assíncrona no Postgres (§16).

Item 8 do checklist de pré-deploy. Antes disso existiam loggers por módulo, mas nenhuma
configuração (nem ``basicConfig``) e nenhum lugar onde olhar: o log ia para o stdout do
Render, que é volátil e só aparece se alguém abrir o painel do provedor na hora certa.

**A decisão de projeto que importa é não gravar no caminho da requisição.** Um `INSERT`
síncrono dentro do handler de logging acopla a latência de cada resposta ao banco e,
pior, um erro de banco durante o log de um erro de banco vira recursão. Por isso:

- o ``logging.Handler`` só **enfileira** um registro já formatado (operação em memória,
  sem I/O);
- uma tarefa de fundo drena a fila em **lotes** e grava;
- se a fila encher, o registro mais antigo é **descartado** com contagem — perder log é
  ruim, mas travar o atendimento de um responsável para gravar log é pior.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import traceback
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.domain.entities import NivelLog, RegistroLog
from app.infrastructure.db.models import LogAplicacaoORM

# Contexto da requisição atual: preenchido pelo middleware e lido por qualquer log emitido
# durante o atendimento dela, inclusive de dentro dos casos de uso — é o que permite
# reunir depois todas as linhas de um mesmo erro.
correlacao_atual: ContextVar[str] = ContextVar("correlacao_atual", default="")
rota_atual: ContextVar[str] = ContextVar("rota_atual", default="")
metodo_atual: ContextVar[str] = ContextVar("metodo_atual", default="")
tenant_atual: ContextVar[UUID | None] = ContextVar("tenant_atual", default=None)

# Loggers ruidosos de bibliotecas: úteis no console, inúteis como linha de banco.
LOGGERS_IGNORADOS = ("uvicorn.access", "sqlalchemy.engine", "httpx", "httpcore")


def novo_id_correlacao() -> str:
    """Curto o bastante para o usuário ler ao telefone, longo o bastante para não colidir."""
    return uuid4().hex[:12]


def _nivel(record: logging.LogRecord) -> NivelLog | None:
    if record.levelno >= logging.CRITICAL:
        return NivelLog.CRITICAL
    if record.levelno >= logging.ERROR:
        return NivelLog.ERROR
    if record.levelno >= logging.WARNING:
        return NivelLog.WARNING
    if record.levelno >= logging.INFO:
        return NivelLog.INFO
    return None  # DEBUG não é persistido


class ColetorDeLogs(logging.Handler):
    """Handler que enfileira registros para gravação assíncrona.

    Não toca no banco: ``emit`` roda no meio da requisição (e às vezes numa thread do
    executor), então tudo que ele faz é montar o ``RegistroLog`` e empurrar na fila.
    """

    def __init__(self, *, capacidade: int = 2_000, nivel_minimo: int = logging.INFO) -> None:
        super().__init__(level=nivel_minimo)
        self.fila: asyncio.Queue[RegistroLog] = asyncio.Queue(maxsize=capacidade)
        self.descartados = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            nivel = _nivel(record)
            if nivel is None or record.name.startswith(LOGGERS_IGNORADOS):
                return

            excecao = ""
            if record.exc_info:
                excecao = "".join(traceback.format_exception(*record.exc_info))[:8000]

            registro = RegistroLog(
                nivel=nivel,
                mensagem=record.getMessage()[:4000],
                logger=record.name[:120],
                correlacao_id=correlacao_atual.get(""),
                rota=rota_atual.get("")[:200],
                metodo=metodo_atual.get("")[:10],
                status_code=getattr(record, "status_code", None),
                duracao_ms=getattr(record, "duracao_ms", None),
                tenant_id=tenant_atual.get(None),
                excecao=excecao,
                metadados=getattr(record, "metadados", {}) or {},
            )
            try:
                self.fila.put_nowait(registro)
            except asyncio.QueueFull:
                # Fila cheia: descarta o mais antigo para preservar o mais recente, que é
                # o que interessa quando algo está acontecendo agora.
                self.descartados += 1
                try:
                    self.fila.get_nowait()
                    self.fila.put_nowait(registro)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass
        except Exception:  # noqa: BLE001 — logging jamais pode derrubar quem o chamou
            self.handleError(record)


class GravadorDeLogs:
    """Tarefa de fundo que drena a fila em lotes e grava no Postgres."""

    def __init__(
        self,
        coletor: ColetorDeLogs,
        sessionmaker: async_sessionmaker,
        *,
        lote_maximo: int = 100,
        intervalo_segundos: float = 1.0,
        retencao_dias: int = 14,
    ) -> None:
        self._coletor = coletor
        self._sessionmaker = sessionmaker
        self._lote_maximo = lote_maximo
        self._intervalo = intervalo_segundos
        self._retencao_dias = retencao_dias
        self._tarefa: asyncio.Task | None = None
        self._parar = asyncio.Event()

    def iniciar(self) -> None:
        if self._tarefa is None:
            self._parar.clear()
            self._tarefa = asyncio.create_task(self._rodar(), name="gravador-de-logs")

    async def parar(self) -> None:
        """Encerra drenando o que sobrou — o log do erro que derrubou o processo é
        justamente o que não pode se perder no shutdown."""
        self._parar.set()
        if self._tarefa is not None:
            await asyncio.wait([self._tarefa], timeout=5)
            self._tarefa = None
        await self._drenar()

    async def _rodar(self) -> None:
        proxima_limpeza = datetime.now(timezone.utc)
        while not self._parar.is_set():
            try:
                await asyncio.wait_for(self._parar.wait(), timeout=self._intervalo)
            except asyncio.TimeoutError:
                pass
            await self._drenar()

            agora = datetime.now(timezone.utc)
            if agora >= proxima_limpeza:
                await self._limpar_antigos()
                proxima_limpeza = agora + timedelta(hours=6)

    async def _drenar(self) -> None:
        lote: list[RegistroLog] = []
        while len(lote) < self._lote_maximo:
            try:
                lote.append(self._coletor.fila.get_nowait())
            except asyncio.QueueEmpty:
                break
        if not lote:
            return
        try:
            async with self._sessionmaker() as session:
                session.add_all(
                    [
                        LogAplicacaoORM(
                            id=r.id,
                            criado_em=r.criado_em.replace(tzinfo=None),
                            nivel=r.nivel.value,
                            logger=r.logger,
                            mensagem=r.mensagem,
                            correlacao_id=r.correlacao_id,
                            rota=r.rota,
                            metodo=r.metodo,
                            status_code=r.status_code,
                            duracao_ms=r.duracao_ms,
                            tenant_id=r.tenant_id,
                            excecao=r.excecao,
                            metadados=r.metadados,
                        )
                        for r in lote
                    ]
                )
                await session.commit()
        except Exception as erro:  # noqa: BLE001
            # Nunca via logging: gravar o fracasso de gravar log entraria em laço.
            print(f"[logs] falha ao gravar lote de {len(lote)} registros: {erro}", file=sys.stderr)

    async def _limpar_antigos(self) -> None:
        from sqlalchemy import delete

        corte = (datetime.now(timezone.utc) - timedelta(days=self._retencao_dias)).replace(
            tzinfo=None
        )
        try:
            async with self._sessionmaker() as session:
                await session.execute(
                    delete(LogAplicacaoORM).where(LogAplicacaoORM.criado_em < corte)
                )
                await session.commit()
        except Exception as erro:  # noqa: BLE001
            print(f"[logs] falha ao limpar logs antigos: {erro}", file=sys.stderr)


def configurar_logging(*, nivel: str = "INFO", formato_json: bool = False) -> None:
    """Configura o logging do processo. Sem isso, o Python usa o ``lastResort`` (WARNING
    no stderr, sem timestamp) e metade dos ``logger.info`` do código simplesmente sumia."""
    raiz = logging.getLogger()
    if raiz.handlers:
        # Uvicorn já configurou: só ajusta o nível para não perder os INFO da aplicação.
        raiz.setLevel(nivel.upper())
        return
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(
        logging.Formatter(
            '{"ts":"%(asctime)s","nivel":"%(levelname)s","logger":"%(name)s",'
            '"msg":"%(message)s"}'
            if formato_json
            else "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
        )
    )
    raiz.addHandler(console)
    raiz.setLevel(nivel.upper())
