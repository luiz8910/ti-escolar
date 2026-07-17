"""Casos de uso dos avisos temporizados da escola.

Um aviso vigente é respondido automaticamente pelo bot a quem inicia a conversa
(ver a integração em ``ReceberMensagemRecebida``). A camada de aplicação só orquestra
a porta ``AvisoTemporizadoRepository``; sem framework/ORM/SDK.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from app.domain.entities import AvisoTemporizado, _now
from app.domain.ports import AvisoTemporizadoRepository


class CriarAvisoTemporizado:
    def __init__(self, *, avisos: AvisoTemporizadoRepository) -> None:
        self._avisos = avisos

    async def executar(
        self,
        *,
        tenant_id: UUID,
        mensagem: str,
        ativo: bool = True,
        inicia_em: datetime | None = None,
        expira_em: datetime | None = None,
    ) -> AvisoTemporizado:
        mensagem = mensagem.strip()
        if not mensagem:
            raise ValueError("O aviso precisa de uma mensagem.")
        if inicia_em is not None and expira_em is not None and expira_em < inicia_em:
            raise ValueError("A data de expiração deve ser posterior ao início.")
        return await self._avisos.criar(
            AvisoTemporizado(
                tenant_id=tenant_id,
                mensagem=mensagem,
                ativo=ativo,
                inicia_em=inicia_em,
                expira_em=expira_em,
            )
        )


class ListarAvisosTemporizados:
    def __init__(self, *, avisos: AvisoTemporizadoRepository) -> None:
        self._avisos = avisos

    async def executar(self, *, tenant_id: UUID) -> list[AvisoTemporizado]:
        return await self._avisos.listar(tenant_id=tenant_id)


class ObterAvisoTemporizado:
    def __init__(self, *, avisos: AvisoTemporizadoRepository) -> None:
        self._avisos = avisos

    async def executar(self, *, tenant_id: UUID, aviso_id: UUID) -> AvisoTemporizado:
        aviso = await self._avisos.obter(tenant_id=tenant_id, aviso_id=aviso_id)
        if aviso is None:
            raise ValueError("Aviso não encontrado para o tenant.")
        return aviso


class AvisoVigente:
    """Retorna o aviso atualmente vigente do tenant (ou None)."""

    def __init__(self, *, avisos: AvisoTemporizadoRepository) -> None:
        self._avisos = avisos

    async def executar(self, *, tenant_id: UUID) -> AvisoTemporizado | None:
        return await self._avisos.vigente(tenant_id=tenant_id)


class AtualizarAvisoTemporizado:
    def __init__(self, *, avisos: AvisoTemporizadoRepository) -> None:
        self._avisos = avisos

    async def executar(
        self,
        *,
        tenant_id: UUID,
        aviso_id: UUID,
        mensagem: str,
        ativo: bool = True,
        inicia_em: datetime | None = None,
        expira_em: datetime | None = None,
    ) -> AvisoTemporizado:
        atual = await self._avisos.obter(tenant_id=tenant_id, aviso_id=aviso_id)
        if atual is None:
            raise ValueError("Aviso não encontrado para o tenant.")
        mensagem = mensagem.strip()
        if not mensagem:
            raise ValueError("O aviso precisa de uma mensagem.")
        if inicia_em is not None and expira_em is not None and expira_em < inicia_em:
            raise ValueError("A data de expiração deve ser posterior ao início.")
        atual.mensagem = mensagem
        atual.ativo = ativo
        atual.inicia_em = inicia_em
        atual.expira_em = expira_em
        atual.atualizado_em = _now()
        return await self._avisos.atualizar(atual)


class RemoverAvisoTemporizado:
    def __init__(self, *, avisos: AvisoTemporizadoRepository) -> None:
        self._avisos = avisos

    async def executar(self, *, tenant_id: UUID, aviso_id: UUID) -> bool:
        return await self._avisos.remover(tenant_id=tenant_id, aviso_id=aviso_id)
