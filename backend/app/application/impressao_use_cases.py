"""Casos de uso da fila de impressão (solicitações dos professores à secretaria).

A camada de aplicação só orquestra ``SolicitacaoImpressaoRepository`` (e, opcionalmente,
``ProfessorRepository`` para denormalizar o nome do professor). Sem framework/ORM/SDK.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import SolicitacaoImpressao, StatusImpressao, _now
from app.domain.ports import ProfessorRepository, SolicitacaoImpressaoRepository


class SolicitarImpressao:
    """Cria uma solicitação de impressão na fila da secretaria.

    Valida os parâmetros (arquivo e nº de cópias) e, quando um ``professor_id`` é
    informado, resolve/valida o professor no tenant para gravar seu nome (exibição).
    """

    def __init__(
        self,
        *,
        solicitacoes: SolicitacaoImpressaoRepository,
        professores: ProfessorRepository | None = None,
    ) -> None:
        self._solicitacoes = solicitacoes
        self._professores = professores

    async def executar(
        self,
        *,
        tenant_id: UUID,
        arquivo_nome: str,
        professor_id: UUID | None = None,
        arquivo_url: str = "",
        copias: int = 1,
        colorido: bool = False,
        frente_verso: bool = False,
        observacao: str = "",
    ) -> SolicitacaoImpressao:
        arquivo_nome = arquivo_nome.strip()
        if not arquivo_nome:
            raise ValueError("Informe o nome do arquivo a imprimir.")
        if copias < 1:
            raise ValueError("O número de cópias deve ser pelo menos 1.")

        professor_nome = ""
        if professor_id is not None and self._professores is not None:
            professor = await self._professores.obter(
                tenant_id=tenant_id, professor_id=professor_id
            )
            if professor is None:
                raise ValueError("Professor não encontrado para o tenant.")
            professor_nome = professor.nome

        return await self._solicitacoes.criar(
            SolicitacaoImpressao(
                tenant_id=tenant_id,
                arquivo_nome=arquivo_nome,
                professor_id=professor_id,
                professor_nome=professor_nome,
                arquivo_url=arquivo_url.strip(),
                copias=copias,
                colorido=colorido,
                frente_verso=frente_verso,
                observacao=observacao.strip(),
            )
        )


class ListarFilaImpressao:
    """Lista a fila de impressão do tenant, opcionalmente filtrada por status."""

    def __init__(self, *, solicitacoes: SolicitacaoImpressaoRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self, *, tenant_id: UUID, status: StatusImpressao | None = None
    ) -> list[SolicitacaoImpressao]:
        return await self._solicitacoes.listar(tenant_id=tenant_id, status=status)


class ObterSolicitacaoImpressao:
    def __init__(self, *, solicitacoes: SolicitacaoImpressaoRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self, *, tenant_id: UUID, solicitacao_id: UUID
    ) -> SolicitacaoImpressao:
        solicitacao = await self._solicitacoes.obter(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
        if solicitacao is None:
            raise ValueError("Solicitação de impressão não encontrada para o tenant.")
        return solicitacao


class AtualizarStatusImpressao:
    """A secretaria (ou o professor) muda o status da solicitação na fila."""

    def __init__(self, *, solicitacoes: SolicitacaoImpressaoRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self, *, tenant_id: UUID, solicitacao_id: UUID, status: StatusImpressao
    ) -> SolicitacaoImpressao:
        solicitacao = await self._solicitacoes.obter(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
        if solicitacao is None:
            raise ValueError("Solicitação de impressão não encontrada para o tenant.")
        solicitacao.status = status
        solicitacao.atualizado_em = _now()
        return await self._solicitacoes.atualizar(solicitacao)


class RemoverSolicitacaoImpressao:
    def __init__(self, *, solicitacoes: SolicitacaoImpressaoRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(self, *, tenant_id: UUID, solicitacao_id: UUID) -> bool:
        return await self._solicitacoes.remover(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
