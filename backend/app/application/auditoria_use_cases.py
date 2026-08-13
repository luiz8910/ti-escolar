"""Casos de uso da auditoria de ações (usuários logados no admin e ações da LLM).

Registrar é deliberadamente tolerante a falhas: auditar nunca deve derrubar a ação de
negócio que está sendo auditada. A consulta é escopada por ``tenant_id`` (a escola).
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.application.paginacao import (
    POR_PAGINA_PADRAO,
    Pagina,
    normalizar_paginacao,
)
from app.domain.entities import AtorAuditoria, RegistroAuditoria
from app.domain.ports import AuditLogRepository, UsuarioRepository

logger = logging.getLogger("auditoria")


class RegistrarAuditoria:
    """Grava uma ação no log de auditoria.

    Falhas ao auditar são apenas logadas (não propagadas): o registro de auditoria é
    secundário em relação à ação de negócio.
    """

    def __init__(self, *, auditoria: AuditLogRepository) -> None:
        self._auditoria = auditoria

    async def executar(
        self,
        *,
        ator: AtorAuditoria,
        acao: str,
        tenant_id: UUID | None = None,
        ator_id: str = "",
        ator_nome: str = "",
        descricao: str = "",
        metadados: dict | None = None,
    ) -> RegistroAuditoria | None:
        registro = RegistroAuditoria(
            ator=ator,
            acao=acao,
            tenant_id=tenant_id,
            ator_id=ator_id,
            ator_nome=ator_nome,
            descricao=descricao,
            metadados=metadados or {},
        )
        try:
            return await self._auditoria.registrar(registro)
        except Exception:  # noqa: BLE001 — auditar não pode quebrar a ação auditada
            logger.exception("Falha ao registrar auditoria (acao=%s)", acao)
            return None


class ListarAuditoria:
    """Página do log, com o **ator identificado** — não só um id cru.

    Um log de auditoria em que se lê "usuário 8f3c-…" não serve para auditar nada: quem
    consulta quer saber *quem*, e quer poder abrir o perfil dessa pessoa para ver cargo e
    situação. Por isso o nome é resolvido **na leitura**, contra o cadastro atual:

    - o ``ator_nome`` gravado é um retrato do momento da ação, e um nome corrigido depois
      (casamento, erro de digitação) faria a mesma pessoa aparecer com dois nomes no log;
    - registro anterior à existência do campo ficaria anônimo para sempre;
    - e só quem ainda tem conta ganha ``ator_perfil_id`` — linkar para uma conta que não
      existe mais é pior do que exibir texto puro.

    A resolução é **em lote** (`por_ids`, uma consulta por página): uma página com dez
    atores diferentes não pode virar dez idas ao banco.
    """

    def __init__(
        self,
        *,
        auditoria: AuditLogRepository,
        usuarios: UsuarioRepository | None = None,
    ) -> None:
        self._auditoria = auditoria
        self._usuarios = usuarios

    async def executar(
        self, *, tenant_id: UUID, pagina: int = 1, por_pagina: int = POR_PAGINA_PADRAO
    ) -> Pagina[RegistroAuditoria]:
        pagina, por_pagina = normalizar_paginacao(pagina, por_pagina)
        itens = await self._auditoria.listar(
            tenant_id=tenant_id, pagina=pagina, por_pagina=por_pagina
        )
        await self._identificar_atores(itens)
        total = await self._auditoria.contar(tenant_id=tenant_id)
        return Pagina(itens=itens, total=total, pagina=pagina, por_pagina=por_pagina)

    async def _identificar_atores(self, itens: list[RegistroAuditoria]) -> None:
        if self._usuarios is None:
            return
        ids: dict[str, UUID] = {}
        for registro in itens:
            if registro.ator is not AtorAuditoria.USUARIO or not registro.ator_id:
                continue
            try:
                ids[registro.ator_id] = UUID(registro.ator_id)
            except ValueError:
                # `ator_id` é texto livre na porta (a LLM guarda telefone ali). Um valor
                # que não é UUID simplesmente não tem perfil — não é erro.
                continue
        if not ids:
            return

        encontrados = {
            str(u.id): u for u in await self._usuarios.por_ids(list(ids.values()))
        }
        for registro in itens:
            usuario = encontrados.get(registro.ator_id)
            if usuario is None:
                continue
            registro.ator_nome = usuario.nome
            registro.ator_perfil_id = str(usuario.id)
