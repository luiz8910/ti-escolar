"""Casos de uso do canal interno professor → secretaria/gestão/pedagógico (§A2/A4).

Substitui o WhatsApp pessoal das professoras por um canal **registrado** e **roteado**
por assunto (``categoria``). A camada de aplicação orquestra
``SolicitacaoInternaRepository`` (e, opcionalmente, ``ProfessorRepository`` para
denormalizar/validar o professor e ``MessageChannel`` para avisar a resposta). Sem
framework/ORM/SDK.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import (
    CategoriaSolicitacao,
    SolicitacaoInterna,
    StatusSolicitacaoInterna,
    _now,
)
from app.domain.ports import (
    MessageChannel,
    ProfessorRepository,
    SolicitacaoInternaRepository,
)


class AbrirSolicitacaoInterna:
    """Um professor abre uma solicitação/recado à escola pelo sistema.

    Quando ``professor_id`` é informado e há ``ProfessorRepository``, valida o professor
    no tenant e grava o nome (exibição). ``categoria`` roteia o pedido (§A4).
    """

    def __init__(
        self,
        *,
        solicitacoes: SolicitacaoInternaRepository,
        professores: ProfessorRepository | None = None,
    ) -> None:
        self._solicitacoes = solicitacoes
        self._professores = professores

    async def executar(
        self,
        *,
        tenant_id: UUID,
        assunto: str,
        corpo: str,
        professor_id: UUID | None = None,
        categoria: CategoriaSolicitacao = CategoriaSolicitacao.SECRETARIA,
    ) -> SolicitacaoInterna:
        assunto = assunto.strip()
        corpo = corpo.strip()
        if not assunto:
            raise ValueError("Informe o assunto da solicitação.")
        if not corpo:
            raise ValueError("Informe o conteúdo da solicitação.")

        professor_nome = ""
        if professor_id is not None and self._professores is not None:
            professor = await self._professores.obter(
                tenant_id=tenant_id, professor_id=professor_id
            )
            if professor is None:
                raise ValueError("Professor não encontrado para o tenant.")
            professor_nome = professor.nome

        return await self._solicitacoes.criar(
            SolicitacaoInterna(
                tenant_id=tenant_id,
                assunto=assunto,
                corpo=corpo,
                professor_id=professor_id,
                professor_nome=professor_nome,
                categoria=categoria,
            )
        )


class ListarSolicitacoesInternas:
    """Lista as solicitações do tenant (visão da escola), com filtros opcionais."""

    def __init__(self, *, solicitacoes: SolicitacaoInternaRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self,
        *,
        tenant_id: UUID,
        categoria: CategoriaSolicitacao | None = None,
        status: StatusSolicitacaoInterna | None = None,
    ) -> list[SolicitacaoInterna]:
        return await self._solicitacoes.listar(
            tenant_id=tenant_id,
            categoria=categoria.value if categoria else None,
            status=status,
        )


class ListarSolicitacoesDoProfessor:
    """Solicitações abertas por um professor específico (visão do próprio professor)."""

    def __init__(self, *, solicitacoes: SolicitacaoInternaRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self, *, tenant_id: UUID, professor_id: UUID
    ) -> list[SolicitacaoInterna]:
        return await self._solicitacoes.listar(
            tenant_id=tenant_id, professor_id=professor_id
        )


class ObterSolicitacaoInterna:
    def __init__(self, *, solicitacoes: SolicitacaoInternaRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self, *, tenant_id: UUID, solicitacao_id: UUID
    ) -> SolicitacaoInterna:
        solicitacao = await self._solicitacoes.obter(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
        if solicitacao is None:
            raise ValueError("Solicitação interna não encontrada para o tenant.")
        return solicitacao


class AtualizarStatusSolicitacaoInterna:
    """A escola muda o status (aberta/em_andamento/resolvida/cancelada)."""

    def __init__(self, *, solicitacoes: SolicitacaoInternaRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(
        self,
        *,
        tenant_id: UUID,
        solicitacao_id: UUID,
        status: StatusSolicitacaoInterna,
    ) -> SolicitacaoInterna:
        solicitacao = await ObterSolicitacaoInterna(
            solicitacoes=self._solicitacoes
        ).executar(tenant_id=tenant_id, solicitacao_id=solicitacao_id)
        solicitacao.status = status
        solicitacao.atualizado_em = _now()
        return await self._solicitacoes.atualizar(solicitacao)


class ResponderSolicitacaoInterna:
    """A escola responde a solicitação e a marca como resolvida.

    Opcionalmente notifica o professor por WhatsApp (``MessageChannel``) de que houve
    resposta — sem substituir o registro no sistema. Falha suave: se o professor não tem
    telefone ou não há canal, apenas grava a resposta.
    """

    def __init__(
        self,
        *,
        solicitacoes: SolicitacaoInternaRepository,
        professores: ProfessorRepository | None = None,
        canal: MessageChannel | None = None,
    ) -> None:
        self._solicitacoes = solicitacoes
        self._professores = professores
        self._canal = canal

    async def executar(
        self,
        *,
        tenant_id: UUID,
        solicitacao_id: UUID,
        resposta: str,
        notificar: bool = False,
    ) -> SolicitacaoInterna:
        resposta = resposta.strip()
        if not resposta:
            raise ValueError("Informe a resposta.")
        solicitacao = await ObterSolicitacaoInterna(
            solicitacoes=self._solicitacoes
        ).executar(tenant_id=tenant_id, solicitacao_id=solicitacao_id)
        solicitacao.resposta = resposta
        solicitacao.status = StatusSolicitacaoInterna.RESOLVIDA
        solicitacao.respondido_em = _now()
        solicitacao.atualizado_em = solicitacao.respondido_em
        atualizada = await self._solicitacoes.atualizar(solicitacao)

        if (
            notificar
            and self._canal is not None
            and self._professores is not None
            and solicitacao.professor_id is not None
        ):
            professor = await self._professores.obter(
                tenant_id=tenant_id, professor_id=solicitacao.professor_id
            )
            if professor is not None and professor.telefone.strip():
                texto = (
                    f'📩 A secretaria respondeu sua solicitação "{solicitacao.assunto}":\n\n'
                    f"{resposta}"
                )
                await self._canal.enviar_texto(
                    contato=professor.telefone, texto=texto
                )
        return atualizada


class RemoverSolicitacaoInterna:
    def __init__(self, *, solicitacoes: SolicitacaoInternaRepository) -> None:
        self._solicitacoes = solicitacoes

    async def executar(self, *, tenant_id: UUID, solicitacao_id: UUID) -> bool:
        return await self._solicitacoes.remover(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
