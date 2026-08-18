"""Armazenamento dos arquivos recebidos — implementações de ``ArquivoStorage`` (§6k).

**Estado atual, dito sem rodeio:** o único adaptador de produção é o Postgres (``bytea``).
Ele foi escolhido para começar porque não pede infra nova nem credencial nova, e porque a
alternativa — um bucket S3-compatível — não pode ser implementada às cegas: sem as chaves
para testar contra o serviço real, o adaptador iria para produção sem nunca ter escrito um
byte de verdade.

**Por que isso não pode ficar assim:** o que se guarda aqui é atestado médico de criança e
documento de matrícula, e o Neon cobra por GB. Uma escola em época de matrícula sobe
centenas de fotos; dez escolas fazem isso todo fevereiro. O adaptador de object storage
(Cloudflare R2, que não cobra egress e mora na conta que já existe por causa da landing
page) é o próximo passo, e a porta existe justamente para que ele entre sem tocar em
``documentos_recebidos``.

``ArquivoStorageMemoria`` cobre teste e execução sem banco.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import ArquivoArmazenadoORM

logger = logging.getLogger("storage")


def nova_chave(tenant_id, prefixo: str = "doc") -> str:
    """Chave opaca e imprevisível para um arquivo: ``{prefixo}/{tenant}/{ano}/{mes}/{token}``.

    Nada de nome do responsável ou do aluno na chave: ela aparece em log e em URL, e o
    conteúdo aqui é dado sensível de menor. ``token_urlsafe`` porque um id sequencial
    permitiria varrer os arquivos das outras escolas por tentativa.

    **O tenant entra no prefixo** (17/ago/2026), e o UUID dele não é dado pessoal. Dá três
    coisas de graça no S3: *lifecycle* e inventário por escola, e a remoção de um tenant
    (`SqlTenantRepository.remover`) vira exclusão por prefixo em vez de varredura. As chaves
    antigas, sem tenant, continuam válidas — a leitura é por chave exata.
    """
    return (
        f"{prefixo}/{tenant_id}/{datetime.now(timezone.utc):%Y/%m}/"
        f"{secrets.token_urlsafe(24)}"
    )


class PostgresArquivoStorage:
    """Bytes em ``arquivos_armazenados`` (``bytea``), na sessão da requisição."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def guardar(self, *, chave: str, conteudo: bytes, mime: str) -> None:
        # ON CONFLICT: reentrega do webhook pode reprocessar a mesma mídia, e falhar por
        # chave duplicada perderia o documento em vez de aproveitá-lo.
        stmt = (
            insert(ArquivoArmazenadoORM)
            .values(
                chave=chave,
                conteudo=conteudo,
                mime=mime,
                tamanho=len(conteudo),
                criado_em=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(index_elements=["chave"])
        )
        await self._s.execute(stmt)
        await self._s.flush()

    async def ler(self, *, chave: str) -> bytes | None:
        stmt = select(ArquivoArmazenadoORM.conteudo).where(
            ArquivoArmazenadoORM.chave == chave
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def remover(self, *, chave: str) -> bool:
        resultado = await self._s.execute(
            delete(ArquivoArmazenadoORM).where(ArquivoArmazenadoORM.chave == chave)
        )
        await self._s.flush()
        return bool(resultado.rowcount)


class ArquivoStorageMemoria:
    """Armazenamento em memória — testes e execução local sem banco."""

    def __init__(self) -> None:
        self.arquivos: dict[str, tuple[bytes, str]] = {}

    async def guardar(self, *, chave: str, conteudo: bytes, mime: str) -> None:
        self.arquivos[chave] = (conteudo, mime)

    async def ler(self, *, chave: str) -> bytes | None:
        item = self.arquivos.get(chave)
        return item[0] if item else None

    async def remover(self, *, chave: str) -> bool:
        return self.arquivos.pop(chave, None) is not None
