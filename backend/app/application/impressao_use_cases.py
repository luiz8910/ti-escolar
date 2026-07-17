"""Casos de uso da fila de impressão (solicitações dos professores à secretaria).

A camada de aplicação só orquestra ``SolicitacaoImpressaoRepository`` (e, opcionalmente,
``ProfessorRepository`` para denormalizar o nome do professor). Sem framework/ORM/SDK.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import (
    CotaImpressao,
    LinhaRelatorioImpressao,
    RelatorioImpressao,
    SolicitacaoImpressao,
    StatusImpressao,
    _now,
)
from app.domain.ports import (
    CotaImpressaoRepository,
    ProfessorRepository,
    SolicitacaoImpressaoRepository,
)


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


# --------------------------------------------------------------------------- #
# B2 · Cota (franquia mensal) e relatório de impressões por professor
# --------------------------------------------------------------------------- #
class DefinirCotaImpressao:
    """Define/atualiza (upsert) a franquia mensal de cópias de um professor.

    ``limite_mensal <= 0`` significa **sem limite**. Valida que o professor pertence
    ao tenant.
    """

    def __init__(
        self,
        *,
        cotas: CotaImpressaoRepository,
        professores: ProfessorRepository,
    ) -> None:
        self._cotas = cotas
        self._professores = professores

    async def executar(
        self, *, tenant_id: UUID, professor_id: UUID, limite_mensal: int
    ) -> CotaImpressao:
        professor = await self._professores.obter(
            tenant_id=tenant_id, professor_id=professor_id
        )
        if professor is None:
            raise ValueError("Professor não encontrado para o tenant.")
        cota = CotaImpressao(
            tenant_id=tenant_id,
            professor_id=professor_id,
            limite_mensal=max(0, limite_mensal),
            atualizado_em=_now(),
        )
        salva = await self._cotas.definir(cota)
        salva.professor_nome = professor.nome
        return salva


class ListarCotasImpressao:
    """Lista as cotas do tenant com o nome do professor resolvido."""

    def __init__(
        self,
        *,
        cotas: CotaImpressaoRepository,
        professores: ProfessorRepository,
    ) -> None:
        self._cotas = cotas
        self._professores = professores

    async def executar(self, *, tenant_id: UUID) -> list[CotaImpressao]:
        cotas = await self._cotas.listar(tenant_id=tenant_id)
        nomes = {
            p.id: p.nome
            for p in await self._professores.listar(tenant_id=tenant_id)
        }
        for cota in cotas:
            cota.professor_nome = nomes.get(cota.professor_id, "")
        return cotas


class RemoverCotaImpressao:
    def __init__(self, *, cotas: CotaImpressaoRepository) -> None:
        self._cotas = cotas

    async def executar(self, *, tenant_id: UUID, professor_id: UUID) -> bool:
        return await self._cotas.remover(tenant_id=tenant_id, professor_id=professor_id)


class RelatorioImpressaoMensal:
    """Relatório de impressões de uma competência (mês ``YYYY-MM``), por professor.

    Soma as **cópias** das solicitações **não canceladas** criadas no mês e cruza com a
    franquia (cota) de cada professor, sinalizando quem excedeu ("bateu a meta"). Inclui
    professores com cota definida mesmo sem solicitações no mês.
    """

    def __init__(
        self,
        *,
        solicitacoes: SolicitacaoImpressaoRepository,
        cotas: CotaImpressaoRepository,
        professores: ProfessorRepository,
    ) -> None:
        self._solicitacoes = solicitacoes
        self._cotas = cotas
        self._professores = professores

    async def executar(
        self, *, tenant_id: UUID, competencia: str
    ) -> RelatorioImpressao:
        todas = await self._solicitacoes.listar(tenant_id=tenant_id)
        cotas = {
            c.professor_id: c.limite_mensal
            for c in await self._cotas.listar(tenant_id=tenant_id)
        }
        nomes = {
            p.id: p.nome
            for p in await self._professores.listar(tenant_id=tenant_id)
        }

        # Agrega consumo por professor no mês (ignora canceladas).
        consumo: dict[UUID | None, dict] = {}
        for s in todas:
            if s.criado_em.strftime("%Y-%m") != competencia:
                continue
            if s.status == StatusImpressao.CANCELADA:
                continue
            item = consumo.setdefault(
                s.professor_id,
                {"solicitacoes": 0, "copias": 0, "nome": s.professor_nome},
            )
            item["solicitacoes"] += 1
            item["copias"] += s.copias
            if s.professor_nome:
                item["nome"] = s.professor_nome

        # Professores com cota, ainda que sem consumo no mês.
        professores_relevantes = set(consumo.keys()) | set(cotas.keys())

        linhas: list[LinhaRelatorioImpressao] = []
        for professor_id in professores_relevantes:
            dados = consumo.get(professor_id, {"solicitacoes": 0, "copias": 0, "nome": ""})
            nome = nomes.get(professor_id) or dados["nome"] or "Sem professor"
            linhas.append(
                LinhaRelatorioImpressao(
                    professor_id=professor_id,
                    professor_nome=nome,
                    total_solicitacoes=dados["solicitacoes"],
                    total_copias=dados["copias"],
                    limite_mensal=cotas.get(professor_id, 0),
                )
            )
        linhas.sort(key=lambda linha: linha.professor_nome.lower())
        return RelatorioImpressao(
            tenant_id=tenant_id, competencia=competencia, linhas=linhas
        )
