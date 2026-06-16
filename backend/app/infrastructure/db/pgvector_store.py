"""VectorStore sobre pgvector (busca por similaridade de cosseno)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.entities import ResultadoBusca, TipoConhecimento, TrechoConhecimento
from app.infrastructure.db.models import ConhecimentoORM


class PgVectorStore:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def indexar(self, trecho: TrechoConhecimento, embedding: list[float]) -> None:
        self._s.add(
            ConhecimentoORM(
                id=trecho.id,
                tenant_id=trecho.tenant_id,
                fonte_id=trecho.fonte_id,
                tipo=trecho.tipo.value,
                titulo=trecho.titulo,
                conteudo=trecho.conteudo,
                embedding=embedding,
                criado_em=trecho.criado_em or datetime.now(timezone.utc),
            )
        )
        await self._s.flush()

    async def remover_por_fonte(self, *, tenant_id: uuid.UUID, fonte_id: uuid.UUID) -> int:
        stmt = delete(ConhecimentoORM).where(
            ConhecimentoORM.tenant_id == tenant_id,
            ConhecimentoORM.fonte_id == fonte_id,
        )
        resultado = await self._s.execute(stmt)
        await self._s.flush()
        return int(resultado.rowcount or 0)

    async def buscar(
        self, *, tenant_id: uuid.UUID, embedding: list[float], k: int = 4
    ) -> list[ResultadoBusca]:
        distancia = ConhecimentoORM.embedding.cosine_distance(embedding)
        stmt = (
            select(ConhecimentoORM, distancia.label("dist"))
            .where(ConhecimentoORM.tenant_id == tenant_id)
            .order_by(distancia)
            .limit(k)
        )
        rows = (await self._s.execute(stmt)).all()
        resultados: list[ResultadoBusca] = []
        for orm, dist in rows:
            trecho = TrechoConhecimento(
                id=orm.id,
                tenant_id=orm.tenant_id,
                tipo=TipoConhecimento(orm.tipo),
                titulo=orm.titulo,
                conteudo=orm.conteudo,
                criado_em=orm.criado_em,
            )
            resultados.append(ResultadoBusca(trecho=trecho, score=1.0 - float(dist)))
        return resultados
