"""Paginação — contrato único das listagens (item 7 do checklist de pré-deploy).

Antes, toda listagem devolvia a tabela inteira: ``listar(tenant_id=...)`` sem teto. Numa
escola com um ano de uso, abrir o histórico de conversas puxava tudo numa requisição — e
o custo cresce em silêncio, porque no mês de implantação a tela é rápida.

Duas decisões:

- **Página pequena por padrão (10).** Quem abre uma listagem está procurando algo
  recente; quem precisa de volume usa o seletor de itens por página.
- **Ordem por ``criado_em`` decrescente.** O mais novo primeiro é o que serve tanto para
  operar quanto para investigar. Ordem estável e previsível também é o que torna o
  ``OFFSET`` honesto de uma página para outra.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar("T")

POR_PAGINA_PADRAO = 10
# Teto para um `?por_pagina=100000` não transformar a listagem no próximo incidente.
POR_PAGINA_MAXIMO = 200
# Opções oferecidas no seletor do painel (o front importa a mesma lista via DTO).
TAMANHOS_DE_PAGINA = (10, 25, 50, 100)


def normalizar_paginacao(pagina: int | None, por_pagina: int | None) -> tuple[int, int]:
    """Página ≥ 1 e tamanho dentro do teto.

    Ausente ou ``0`` significa "não informado" e cai no padrão; valor negativo é hostil e
    vira o mínimo. A origem é o cliente — nada aqui pode ser assumido como válido.
    """
    p = max(1, int(pagina or 1))
    tamanho = int(por_pagina or POR_PAGINA_PADRAO)
    return p, max(1, min(tamanho, POR_PAGINA_MAXIMO))


@dataclass(frozen=True)
class Pagina(Generic[T]):
    """Uma página de resultados com o total, para o painel montar o paginador."""

    itens: list[T] = field(default_factory=list)
    total: int = 0
    pagina: int = 1
    por_pagina: int = POR_PAGINA_PADRAO

    @property
    def total_paginas(self) -> int:
        if self.por_pagina <= 0:
            return 1
        return max(1, -(-self.total // self.por_pagina))

    @property
    def tem_proxima(self) -> bool:
        return self.pagina < self.total_paginas
