"""Testa a progressão de série e o ciclo de vida do responsável (§F1): promoção para a
série seguinte, formatura na última série (ex-aluno) e a **sincronização automática** da
situação dos responsáveis — que deixou de depender de alguém clicar num botão.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.cadastro_use_cases import DesativarAluno, ReativarAluno
from app.application.progressao_use_cases import (
    PromoverSerie,
    PromoverTurmas,
    SincronizarSituacaoDosResponsaveis,
)
from app.domain.entities import Aluno, Contato, Sala
from tests.fakes import FakeAlunoRepo, FakeContatoRepo, FakeSalaRepo

TENANT = uuid.uuid4()


def _repos():
    alunos = FakeAlunoRepo()
    salas = FakeSalaRepo()
    contatos = FakeContatoRepo()
    alunos.contatos = contatos
    salas.contatos = contatos
    return alunos, salas, contatos


async def test_promover_move_ativos_para_serie_seguinte():
    alunos, salas, _ = _repos()
    quinto = await salas.criar(Sala(tenant_id=TENANT, nome="5º A"))
    sexto = await salas.criar(Sala(tenant_id=TENANT, nome="6º A"))
    ativo = await alunos.criar(Aluno(tenant_id=TENANT, nome="João", sala_id=quinto.id))
    exaluno = await alunos.criar(
        Aluno(tenant_id=TENANT, nome="Antigo", sala_id=quinto.id, ativo=False)
    )

    resultado = await PromoverSerie(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, origem_sala_id=quinto.id, destino_sala_id=sexto.id
    )

    assert resultado.alunos_promovidos == 1
    assert resultado.alunos_formados == 0
    assert (await alunos.obter(tenant_id=TENANT, aluno_id=ativo.id)).sala_id == sexto.id
    # Ex-aluno não é movido.
    assert (await alunos.obter(tenant_id=TENANT, aluno_id=exaluno.id)).sala_id == quinto.id


async def test_promover_ultima_serie_forma_alunos():
    alunos, salas, _ = _repos()
    nono = await salas.criar(Sala(tenant_id=TENANT, nome="9º A"))
    aluno = await alunos.criar(Aluno(tenant_id=TENANT, nome="Maria", sala_id=nono.id))

    resultado = await PromoverSerie(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, origem_sala_id=nono.id, destino_sala_id=None
    )

    assert resultado.alunos_formados == 1
    assert resultado.alunos_promovidos == 0
    atualizado = await alunos.obter(tenant_id=TENANT, aluno_id=aluno.id)
    assert atualizado.ativo is False
    assert atualizado.sala_id == nono.id  # permanece para histórico


async def test_promover_destino_igual_origem_falha():
    alunos, salas, _ = _repos()
    sala = await salas.criar(Sala(tenant_id=TENANT, nome="5º A"))
    with pytest.raises(ValueError):
        await PromoverSerie(alunos=alunos, salas=salas).executar(
            tenant_id=TENANT, origem_sala_id=sala.id, destino_sala_id=sala.id
        )


async def test_promover_turmas_em_lote():
    alunos, salas, _ = _repos()
    s5 = await salas.criar(Sala(tenant_id=TENANT, nome="5º A"))
    s6 = await salas.criar(Sala(tenant_id=TENANT, nome="6º A"))
    s9 = await salas.criar(Sala(tenant_id=TENANT, nome="9º A"))
    await alunos.criar(Aluno(tenant_id=TENANT, nome="A", sala_id=s5.id))
    await alunos.criar(Aluno(tenant_id=TENANT, nome="B", sala_id=s9.id))

    resultados = await PromoverTurmas(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT,
        promocoes=[(s5.id, s6.id), (s9.id, None)],
    )
    assert len(resultados) == 2
    assert resultados[0].alunos_promovidos == 1
    assert resultados[1].alunos_formados == 1


async def test_inativa_responsavel_so_quando_todos_alunos_inativos():
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()

    # Responsável com todos os alunos ex-alunos → inativa.
    pai_ex = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai Ex", telefone="+5511111110000"))
    a1 = Aluno(tenant_id=TENANT, nome="A1", sala_id=sala_id, ativo=False, responsaveis=[pai_ex])
    await alunos.criar(a1)

    # Responsável com um aluno ainda ativo → mantém.
    pai_ativo = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai Ativo", telefone="+5511222220000"))
    a2 = Aluno(tenant_id=TENANT, nome="A2", sala_id=sala_id, ativo=True, responsaveis=[pai_ativo])
    a3 = Aluno(tenant_id=TENANT, nome="A3", sala_id=sala_id, ativo=False, responsaveis=[pai_ativo])
    await alunos.criar(a2)
    await alunos.criar(a3)

    # Responsável sem alunos vinculados → mantém.
    pai_sem = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai Sem", telefone="+5511333330000"))

    resultado = await SincronizarSituacaoDosResponsaveis(
        alunos=alunos, contatos=contatos
    ).executar(tenant_id=TENANT)

    assert [r.contato_id for r in resultado.inativados] == [pai_ex.id]
    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai_ex.id)).ativo is False
    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai_ativo.id)).ativo is True
    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai_sem.id)).ativo is True


async def test_inativar_idempotente():
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()
    pai = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai", telefone="+5511111110000"))
    await alunos.criar(
        Aluno(tenant_id=TENANT, nome="A", sala_id=sala_id, ativo=False, responsaveis=[pai])
    )
    sincronizar = SincronizarSituacaoDosResponsaveis(alunos=alunos, contatos=contatos)
    primeiros = await sincronizar.executar(tenant_id=TENANT)
    assert len(primeiros.inativados) == 1
    # Segunda passada não re-inativa quem já está inativo.
    segundos = await sincronizar.executar(tenant_id=TENANT)
    assert segundos.total == 0


# --------------------------------------------------------------------------- #
# Automação do ciclo de vida (Fase 5 do plano de 10/08)
#
# "Ciclo de vida do responsável deve ser ativado por automação e não disparado por
# clique". O gatilho mora nos dois momentos em que a família de fato muda de estado —
# a virada de ano e a (des)ativação de um aluno —, e não num cron que passaria 364 dias
# por ano recalculando nada.
# --------------------------------------------------------------------------- #
async def _familia(alunos, contatos, *, sala_id, ativo=True, nome="Filho"):
    pai = await contatos.criar(
        Contato(tenant_id=TENANT, nome=f"Pai de {nome}", telefone=f"+55119{abs(hash(nome)) % 10**8:08d}")
    )
    aluno = await alunos.criar(
        Aluno(tenant_id=TENANT, nome=nome, sala_id=sala_id, ativo=ativo, responsaveis=[pai])
    )
    return pai, aluno


async def test_desativar_aluno_inativa_o_responsavel_sem_clique():
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()
    pai, aluno = await _familia(alunos, contatos, sala_id=sala_id)

    await DesativarAluno(alunos=alunos, contatos=contatos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, motivo="mudou de escola"
    )

    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai.id)).ativo is False


async def test_reativar_aluno_devolve_o_responsavel():
    """Sem isto a automação vira armadilha: a rematrícula devolveria o aluno e a família
    ficaria inativa, parando de receber aviso sem ninguém perceber."""
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()
    pai, aluno = await _familia(alunos, contatos, sala_id=sala_id)
    await DesativarAluno(alunos=alunos, contatos=contatos).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    )

    await ReativarAluno(alunos=alunos, contatos=contatos).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    )

    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai.id)).ativo is True


async def test_desativar_um_irmao_nao_inativa_a_familia():
    """O responsável só sai quando **todos** os alunos dele são ex-alunos."""
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()
    pai = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai", telefone="+5511999990001"))
    irmao1 = await alunos.criar(
        Aluno(tenant_id=TENANT, nome="Irmão 1", sala_id=sala_id, responsaveis=[pai])
    )
    await alunos.criar(
        Aluno(tenant_id=TENANT, nome="Irmão 2", sala_id=sala_id, responsaveis=[pai])
    )

    await DesativarAluno(alunos=alunos, contatos=contatos).executar(
        tenant_id=TENANT, aluno_id=irmao1.id
    )

    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai.id)).ativo is True


async def test_desativar_sem_repositorio_de_contatos_nao_quebra():
    """A sincronização é efeito colateral; o caso de uso segue utilizável sem ela."""
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()
    pai, aluno = await _familia(alunos, contatos, sala_id=sala_id)

    resultado = await DesativarAluno(alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    )

    assert resultado.ativo is False
    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai.id)).ativo is True


async def test_sincronizacao_recortada_nao_toca_outras_familias():
    """Desativar um aluno olha só os responsáveis dele — varrer a escola a cada clique
    seria pagar caro por uma mudança que atinge duas ou três pessoas."""
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()
    pai_a, aluno_a = await _familia(alunos, contatos, sala_id=sala_id, nome="A")
    # Outra família já sem aluno ativo, que ficaria "pendente" de sincronização.
    pai_b, _ = await _familia(alunos, contatos, sala_id=sala_id, ativo=False, nome="B")

    await DesativarAluno(alunos=alunos, contatos=contatos).executar(
        tenant_id=TENANT, aluno_id=aluno_a.id
    )

    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai_a.id)).ativo is False
    # A outra família não foi tocada por este clique — ela é alcançada pela promoção de
    # turmas ou pelo reprocessamento manual.
    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai_b.id)).ativo is True


async def test_promover_turmas_sincroniza_no_fim():
    """A virada de ano é o momento em que famílias inteiras deixam de ter aluno."""
    alunos, salas, contatos = _repos()
    ultima = await salas.criar(Sala(tenant_id=TENANT, nome="9º ano"))
    pai = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai", telefone="+5511999990002"))
    await alunos.criar(
        Aluno(tenant_id=TENANT, nome="Formando", sala_id=ultima.id, responsaveis=[pai])
    )

    # destino None = formatura: os alunos viram ex-alunos.
    await PromoverTurmas(alunos=alunos, salas=salas, contatos=contatos).executar(
        tenant_id=TENANT, promocoes=[(ultima.id, None)]
    )

    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai.id)).ativo is False


async def test_promover_sem_contatos_apenas_promove():
    alunos, salas, contatos = _repos()
    ultima = await salas.criar(Sala(tenant_id=TENANT, nome="9º ano"))
    pai = await contatos.criar(Contato(tenant_id=TENANT, nome="Pai", telefone="+5511999990003"))
    await alunos.criar(
        Aluno(tenant_id=TENANT, nome="Formando", sala_id=ultima.id, responsaveis=[pai])
    )

    await PromoverTurmas(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, promocoes=[(ultima.id, None)]
    )

    assert (await contatos.obter(tenant_id=TENANT, contato_id=pai.id)).ativo is True


async def test_reprocessamento_manual_alcanca_a_escola_inteira():
    """A rota manual continua existindo — é o que conserta o que ficou para trás depois
    de uma importação em massa ou de um ajuste feito no banco."""
    alunos, _, contatos = _repos()
    sala_id = uuid.uuid4()
    pai_b, _ = await _familia(alunos, contatos, sala_id=sala_id, ativo=False, nome="B")

    resultado = await SincronizarSituacaoDosResponsaveis(
        alunos=alunos, contatos=contatos
    ).executar(tenant_id=TENANT)

    assert [r.contato_id for r in resultado.inativados] == [pai_b.id]
