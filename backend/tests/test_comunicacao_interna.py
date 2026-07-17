"""Testa o canal interno professor → secretaria/gestão/pedagógico (§A2/A4):
abertura, roteamento por categoria, resposta com notificação, transições de status,
filtros, remoção e isolamento por tenant.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.comunicacao_interna_use_cases import (
    AbrirSolicitacaoInterna,
    AtualizarStatusSolicitacaoInterna,
    ListarSolicitacoesDoProfessor,
    ListarSolicitacoesInternas,
    RemoverSolicitacaoInterna,
    ResponderSolicitacaoInterna,
)
from app.domain.entities import (
    CategoriaSolicitacao,
    Professor,
    StatusSolicitacaoInterna,
)
from tests.fakes import FakeChannel, FakeProfessorRepo, FakeSolicitacaoInternaRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


async def _professor(repo: FakeProfessorRepo, *, tenant=TENANT, tel="+5511999990000"):
    return await repo.criar(Professor(tenant_id=tenant, nome="Prof. Ana", telefone=tel))


async def test_abrir_solicitacao_roteia_por_categoria():
    solicitacoes = FakeSolicitacaoInternaRepo()
    professores = FakeProfessorRepo()
    prof = await _professor(professores)

    s = await AbrirSolicitacaoInterna(
        solicitacoes=solicitacoes, professores=professores
    ).executar(
        tenant_id=TENANT,
        assunto="Falta amanhã",
        corpo="Consulta médica, não poderei comparecer.",
        professor_id=prof.id,
        categoria=CategoriaSolicitacao.GESTAO,
    )

    assert s.status == StatusSolicitacaoInterna.ABERTA
    assert s.categoria == CategoriaSolicitacao.GESTAO
    assert s.professor_nome == "Prof. Ana"


async def test_assunto_e_corpo_obrigatorios():
    solicitacoes = FakeSolicitacaoInternaRepo()
    with pytest.raises(ValueError):
        await AbrirSolicitacaoInterna(solicitacoes=solicitacoes).executar(
            tenant_id=TENANT, assunto="  ", corpo="algo"
        )
    with pytest.raises(ValueError):
        await AbrirSolicitacaoInterna(solicitacoes=solicitacoes).executar(
            tenant_id=TENANT, assunto="Assunto", corpo="   "
        )


async def test_filtrar_por_categoria_e_status():
    solicitacoes = FakeSolicitacaoInternaRepo()
    abrir = AbrirSolicitacaoInterna(solicitacoes=solicitacoes)
    await abrir.executar(
        tenant_id=TENANT, assunto="A", corpo="x", categoria=CategoriaSolicitacao.SECRETARIA
    )
    await abrir.executar(
        tenant_id=TENANT, assunto="B", corpo="y", categoria=CategoriaSolicitacao.PEDAGOGICO
    )

    listar = ListarSolicitacoesInternas(solicitacoes=solicitacoes)
    so_pedagogico = await listar.executar(
        tenant_id=TENANT, categoria=CategoriaSolicitacao.PEDAGOGICO
    )
    assert [s.assunto for s in so_pedagogico] == ["B"]

    abertas = await listar.executar(
        tenant_id=TENANT, status=StatusSolicitacaoInterna.ABERTA
    )
    assert len(abertas) == 2


async def test_responder_marca_resolvida_e_notifica_professor():
    solicitacoes = FakeSolicitacaoInternaRepo()
    professores = FakeProfessorRepo()
    canal = FakeChannel()
    prof = await _professor(professores)
    s = await AbrirSolicitacaoInterna(
        solicitacoes=solicitacoes, professores=professores
    ).executar(tenant_id=TENANT, assunto="Impressão", corpo="Preciso de cópias", professor_id=prof.id)

    resolvida = await ResponderSolicitacaoInterna(
        solicitacoes=solicitacoes, professores=professores, canal=canal
    ).executar(
        tenant_id=TENANT, solicitacao_id=s.id, resposta="Já providenciamos.", notificar=True
    )

    assert resolvida.status == StatusSolicitacaoInterna.RESOLVIDA
    assert resolvida.resposta == "Já providenciamos."
    assert resolvida.respondido_em is not None
    assert canal.enviados == [(prof.telefone, "texto")]


async def test_responder_sem_notificar_nao_envia():
    solicitacoes = FakeSolicitacaoInternaRepo()
    professores = FakeProfessorRepo()
    canal = FakeChannel()
    prof = await _professor(professores)
    s = await AbrirSolicitacaoInterna(
        solicitacoes=solicitacoes, professores=professores
    ).executar(tenant_id=TENANT, assunto="X", corpo="y", professor_id=prof.id)

    await ResponderSolicitacaoInterna(
        solicitacoes=solicitacoes, professores=professores, canal=canal
    ).executar(tenant_id=TENANT, solicitacao_id=s.id, resposta="ok", notificar=False)
    assert canal.enviados == []


async def test_atualizar_status_e_remover():
    solicitacoes = FakeSolicitacaoInternaRepo()
    s = await AbrirSolicitacaoInterna(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, assunto="X", corpo="y"
    )
    atualizada = await AtualizarStatusSolicitacaoInterna(
        solicitacoes=solicitacoes
    ).executar(
        tenant_id=TENANT,
        solicitacao_id=s.id,
        status=StatusSolicitacaoInterna.EM_ANDAMENTO,
    )
    assert atualizada.status == StatusSolicitacaoInterna.EM_ANDAMENTO

    assert await RemoverSolicitacaoInterna(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, solicitacao_id=s.id
    )
    assert await solicitacoes.obter(tenant_id=TENANT, solicitacao_id=s.id) is None


async def test_isolamento_por_tenant():
    solicitacoes = FakeSolicitacaoInternaRepo()
    s = await AbrirSolicitacaoInterna(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, assunto="X", corpo="y"
    )
    # Outro tenant não enxerga nem remove.
    assert await solicitacoes.obter(tenant_id=OUTRO_TENANT, solicitacao_id=s.id) is None
    assert not await RemoverSolicitacaoInterna(solicitacoes=solicitacoes).executar(
        tenant_id=OUTRO_TENANT, solicitacao_id=s.id
    )


async def test_listar_solicitacoes_do_professor():
    solicitacoes = FakeSolicitacaoInternaRepo()
    professores = FakeProfessorRepo()
    prof_a = await _professor(professores, tel="+5511111110000")
    prof_b = await _professor(professores, tel="+5511222220000")
    abrir = AbrirSolicitacaoInterna(solicitacoes=solicitacoes, professores=professores)
    await abrir.executar(tenant_id=TENANT, assunto="A", corpo="x", professor_id=prof_a.id)
    await abrir.executar(tenant_id=TENANT, assunto="B", corpo="y", professor_id=prof_b.id)

    do_a = await ListarSolicitacoesDoProfessor(solicitacoes=solicitacoes).executar(
        tenant_id=TENANT, professor_id=prof_a.id
    )
    assert [s.assunto for s in do_a] == ["A"]
