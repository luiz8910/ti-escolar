"""Testa a fila de impressão: criação com parâmetros, resolução do professor,
filtro por status, transições de status, remoção e isolamento por tenant.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.impressao_use_cases import (
    AtualizarStatusImpressao,
    ListarFilaImpressao,
    ObterSolicitacaoImpressao,
    RemoverSolicitacaoImpressao,
    SolicitarImpressao,
)
from app.domain.entities import Professor, StatusImpressao
from tests.fakes import FakeProfessorRepo, FakeSolicitacaoImpressaoRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


async def test_solicitar_impressao_com_parametros_e_professor():
    solicitacoes = FakeSolicitacaoImpressaoRepo()
    professores = FakeProfessorRepo()
    prof = await professores.criar(
        Professor(tenant_id=TENANT, nome="Prof. Ana", telefone="+5511999990000")
    )

    solicitacao = await SolicitarImpressao(
        solicitacoes=solicitacoes, professores=professores
    ).executar(
        tenant_id=TENANT,
        arquivo_nome="prova_2bim_5A.pdf",
        professor_id=prof.id,
        copias=30,
        colorido=False,
        frente_verso=True,
        observacao="Grampear por aluno",
    )

    assert solicitacao.status == StatusImpressao.PENDENTE
    assert solicitacao.professor_nome == "Prof. Ana"
    assert solicitacao.copias == 30
    assert solicitacao.frente_verso is True


async def test_arquivo_e_copias_validados():
    solicitacoes = FakeSolicitacaoImpressaoRepo()
    with pytest.raises(ValueError):
        await SolicitarImpressao(solicitacoes=solicitacoes).executar(
            tenant_id=TENANT, arquivo_nome="  "
        )
    with pytest.raises(ValueError):
        await SolicitarImpressao(solicitacoes=solicitacoes).executar(
            tenant_id=TENANT, arquivo_nome="x.pdf", copias=0
        )


async def test_professor_de_outro_tenant_falha():
    solicitacoes = FakeSolicitacaoImpressaoRepo()
    professores = FakeProfessorRepo()
    prof = await professores.criar(
        Professor(tenant_id=OUTRO_TENANT, nome="Prof. Externo", telefone="+5511900000000")
    )
    with pytest.raises(ValueError):
        await SolicitarImpressao(
            solicitacoes=solicitacoes, professores=professores
        ).executar(tenant_id=TENANT, arquivo_nome="x.pdf", professor_id=prof.id)


async def test_listar_fila_e_filtrar_por_status():
    solicitacoes = FakeSolicitacaoImpressaoRepo()
    solicitar = SolicitarImpressao(solicitacoes=solicitacoes)
    a = await solicitar.executar(tenant_id=TENANT, arquivo_nome="a.pdf")
    await solicitar.executar(tenant_id=TENANT, arquivo_nome="b.pdf")

    await AtualizarStatusImpressao(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, solicitacao_id=a.id, status=StatusImpressao.CONCLUIDA
    )

    todas = await ListarFilaImpressao(solicitacoes=solicitacoes).executar(tenant_id=TENANT)
    assert len(todas) == 2

    pendentes = await ListarFilaImpressao(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, status=StatusImpressao.PENDENTE
    )
    assert len(pendentes) == 1
    assert pendentes[0].arquivo_nome == "b.pdf"


async def test_transicao_de_status():
    solicitacoes = FakeSolicitacaoImpressaoRepo()
    s = await SolicitarImpressao(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, arquivo_nome="lista_chamada.pdf"
    )
    atualizada = await AtualizarStatusImpressao(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, solicitacao_id=s.id, status=StatusImpressao.EM_PROCESSO
    )
    assert atualizada.status == StatusImpressao.EM_PROCESSO


async def test_remover_e_isolamento_por_tenant():
    solicitacoes = FakeSolicitacaoImpressaoRepo()
    s = await SolicitarImpressao(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, arquivo_nome="atividade.pdf"
    )
    # Outro tenant não acessa nem remove.
    with pytest.raises(ValueError):
        await ObterSolicitacaoImpressao(solicitacoes=solicitacoes).executar(
            tenant_id=OUTRO_TENANT, solicitacao_id=s.id
        )
    assert not await RemoverSolicitacaoImpressao(solicitacoes=solicitacoes).executar(
        tenant_id=OUTRO_TENANT, solicitacao_id=s.id
    )
    assert await RemoverSolicitacaoImpressao(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, solicitacao_id=s.id
    )
