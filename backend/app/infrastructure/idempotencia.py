"""Cache de idempotência em memória — descarta reentregas do webhook (§9e.1).

**Escopo declarado:** o cache vive no processo. Ele resolve o caso real e frequente (a Meta
reenvia o mesmo evento em segundos quando o ``200 OK`` demora), mas **não** cobre reentregas
que caiam em outra réplica nem que cheguem depois de um restart. A alternativa durável (uma
tabela de wamids processados, ou Redis) fica de roadmap: exigiria migration e infraestrutura
novas, e o custo de deixar passar uma duplicata rara é uma resposta repetida ao responsável,
não perda de dado.

Implementação: ``OrderedDict`` como LRU limitado, para o cache não crescer sem teto num
processo de longa duração.
"""

from __future__ import annotations

import asyncio
from collections import OrderedDict


class CacheIdempotenciaMemoria:
    """Implementa a porta ``CacheIdempotencia`` com um LRU limitado, no processo."""

    def __init__(self, *, capacidade: int = 5_000) -> None:
        self._capacidade = capacidade
        self._vistas: OrderedDict[str, None] = OrderedDict()
        # O FastAPI atende requisições concorrentes: sem o lock, dois webhooks simultâneos
        # com o mesmo wamid poderiam ambos ver a chave como inédita.
        self._lock = asyncio.Lock()

    async def registrar(self, chave: str) -> bool:
        """``True`` se a chave é inédita; ``False`` se já foi processada."""
        if not chave:
            return True
        async with self._lock:
            if chave in self._vistas:
                self._vistas.move_to_end(chave)
                return False
            self._vistas[chave] = None
            while len(self._vistas) > self._capacidade:
                self._vistas.popitem(last=False)
            return True
