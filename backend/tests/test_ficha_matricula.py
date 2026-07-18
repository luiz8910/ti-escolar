"""Testa a ficha de matrícula digital (§D1/D2/D3): CRUD com campos sensíveis, obrigação
de cor/raça, isolamento por tenant e leitura por IA (prévia → confirmação).
"""

from __future__ import annotations

import uuid

import pytest

from app.application.ficha_use_cases import (
    ConfirmarFichaMatricula,
    ObterFichaMatricula,
    PrevisualizarFichaMatricula,
    RemoverFichaMatricula,
    SalvarFichaMatricula,
)
from app.domain.entities import Aluno
from app.infrastructure.llm.fake_provider import FakeLLMProvider
from tests.fakes import FakeAlunoRepo, FakeFichaMatriculaRepo

TENANT = uuid.uuid4()
SALA = uuid.uuid4()


async def _cenario():
    fichas = FakeFichaMatriculaRepo()
    alunos = FakeAlunoRepo()
    aluno = await alunos.criar(Aluno(tenant_id=TENANT, nome="João da Silva", sala_id=SALA))
    return fichas, alunos, aluno


# --------------------------- D1/D2 CRUD --------------------------- #
async def test_salvar_ficha_com_campos_sensiveis():
    fichas, alunos, aluno = await _cenario()
    ficha = await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT,
        aluno_id=aluno.id,
        campos={
            "cor_raca": "Parda",
            "cpf": "123.456.789-00",
            "bolsa_familia": "sim",
            "nis": "12345678901",
            "deficiencia": "Nenhuma",
            "laudo_cid": "em investigação",
            "alergia": "Amendoim",
            "autorizacao_van": "sim",
            "autorizacao_imagem": "não",
        },
    )
    assert ficha.cor_raca == "Parda"
    assert ficha.bolsa_familia is True
    assert ficha.autorizacao_van is True
    assert ficha.autorizacao_imagem is False
    assert ficha.aluno_nome == "João da Silva"


async def test_salvar_ficha_faz_upsert():
    fichas, alunos, aluno = await _cenario()
    salvar = SalvarFichaMatricula(fichas=fichas, alunos=alunos)
    await salvar.executar(tenant_id=TENANT, aluno_id=aluno.id, campos={"cor_raca": "Branca"})
    await salvar.executar(
        tenant_id=TENANT, aluno_id=aluno.id, campos={"cor_raca": "Preta", "alergia": "Lactose"}
    )
    ficha = await ObterFichaMatricula(fichas=fichas).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    )
    assert ficha.cor_raca == "Preta"
    assert ficha.alergia == "Lactose"
    # Upsert: continua uma única ficha para o aluno.
    assert len(fichas.fichas) == 1


async def test_remover_ficha():
    fichas, alunos, aluno = await _cenario()
    await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, campos={"cor_raca": "Amarela"}
    )
    assert await RemoverFichaMatricula(fichas=fichas).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    )
    assert await ObterFichaMatricula(fichas=fichas).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    ) is None


# --------------------------- exceções --------------------------- #
async def test_salvar_ficha_sem_cor_raca_falha():
    fichas, alunos, aluno = await _cenario()
    with pytest.raises(ValueError):
        await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
            tenant_id=TENANT, aluno_id=aluno.id, campos={"cpf": "000"}
        )


async def test_salvar_ficha_aluno_de_outro_tenant_falha():
    fichas, alunos, aluno = await _cenario()
    with pytest.raises(ValueError):
        await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
            tenant_id=uuid.uuid4(), aluno_id=aluno.id, campos={"cor_raca": "Parda"}
        )


# --------------------------- D3 leitura por IA --------------------------- #
async def test_previa_ficha_por_ia_extrai_campos():
    previa = await PrevisualizarFichaMatricula(llm=FakeLLMProvider()).executar(
        tenant_id=TENANT,
        conteudo="cor_raca: Parda\ndata_nascimento: 2015-03-02\nautorizacao_van: sim",
    )
    assert previa.valido
    assert previa.campos["cor_raca"] == "Parda"
    assert previa.campos["autorizacao_van"] is True


async def test_previa_ficha_sem_cor_raca_gera_aviso():
    previa = await PrevisualizarFichaMatricula(llm=FakeLLMProvider()).executar(
        tenant_id=TENANT, conteudo="cpf: 123\nendereco: Rua A, 100"
    )
    assert any("cor/ra" in a.lower() for a in previa.avisos)


async def test_confirmar_ficha_persiste_apos_revisao():
    fichas, alunos, aluno = await _cenario()
    previa = await PrevisualizarFichaMatricula(llm=FakeLLMProvider()).executar(
        tenant_id=TENANT, conteudo="cor_raca: Branca\nalergia: Poeira"
    )
    ficha = await ConfirmarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, campos=previa.campos
    )
    assert ficha.cor_raca == "Branca"
    assert ficha.alergia == "Poeira"


async def test_previa_ficha_conteudo_vazio_falha():
    with pytest.raises(ValueError):
        await PrevisualizarFichaMatricula(llm=FakeLLMProvider()).executar(
            tenant_id=TENANT, conteudo="   "
        )


class _LLMSemJson:
    async def gerar(self, *, sistema, mensagens):
        return "desculpe, não consegui ler a ficha"

    async def gerar_com_ferramentas(self, *, sistema, turnos, ferramentas):  # pragma: no cover
        raise NotImplementedError


async def test_previa_ficha_resposta_invalida_falha():
    with pytest.raises(ValueError):
        await PrevisualizarFichaMatricula(llm=_LLMSemJson()).executar(
            tenant_id=TENANT, conteudo="cor_raca: Parda"
        )
