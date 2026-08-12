"""Testa a ficha de matrícula digital (§D1/D2/D3): CRUD com campos sensíveis, os campos
obrigatórios da ficha física, filiação derivada dos responsáveis, isolamento por tenant e
leitura por IA (prévia → confirmação).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.application.ficha_use_cases import (
    ConfirmarFichaMatricula,
    ObterFichaMatricula,
    PrevisualizarFichaMatricula,
    RemoverFichaMatricula,
    SalvarFichaMatricula,
)
from app.domain.entities import Aluno, Contato, TipoFiliacao
from app.infrastructure.llm.fake_provider import FakeLLMProvider
from tests.fakes import FakeAlunoRepo, FakeFichaMatriculaRepo

TENANT = uuid.uuid4()
SALA = uuid.uuid4()


# Os campos que a ficha física marca com asterisco. Quase todo teste precisa deles, então
# ficam num mínimo reaproveitável.
OBRIGATORIOS = {
    "cor_raca": "Parda",
    "cpf": "529.982.247-25",
    "ra_rm": "12.345.678-9",
    "data_nascimento": "02/03/2015",
    "endereco": "Rua das Acácias, 120 — Sorocaba/SP",
    "sexo": "F",
}


def campos(**extras) -> dict:
    return {**OBRIGATORIOS, **extras}


async def _cenario(responsaveis=()):
    fichas = FakeFichaMatriculaRepo()
    alunos = FakeAlunoRepo()
    aluno = await alunos.criar(
        Aluno(
            tenant_id=TENANT,
            nome="João da Silva",
            sala_id=SALA,
            responsaveis=list(responsaveis),
        )
    )
    return fichas, alunos, aluno


# --------------------------- D1/D2 CRUD --------------------------- #
async def test_salvar_ficha_com_campos_sensiveis():
    fichas, alunos, aluno = await _cenario()
    ficha = await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT,
        aluno_id=aluno.id,
        campos=campos(
            bolsa_familia="sim",
            nis="12345678901",
            deficiencia="Nenhuma",
            laudo_status="em_investigacao",
            alergia="Amendoim",
            autorizacao_van="sim",
            autorizacao_imagem="não",
        ),
    )
    assert ficha.cor_raca == "Parda"
    assert ficha.bolsa_familia is True
    assert ficha.autorizacao_van is True
    assert ficha.autorizacao_imagem is False
    assert ficha.aluno_nome == "João da Silva"


async def test_salvar_ficha_faz_upsert():
    fichas, alunos, aluno = await _cenario()
    salvar = SalvarFichaMatricula(fichas=fichas, alunos=alunos)
    await salvar.executar(tenant_id=TENANT, aluno_id=aluno.id, campos=campos(cor_raca="Branca"))
    await salvar.executar(
        tenant_id=TENANT, aluno_id=aluno.id, campos=campos(cor_raca="Preta", alergia="Lactose")
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
        tenant_id=TENANT, aluno_id=aluno.id, campos=campos(cor_raca="Amarela")
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
            tenant_id=uuid.uuid4(), aluno_id=aluno.id, campos=campos()
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
    # A prévia da IA é revisada pela secretaria, que completa o que faltou antes de
    # confirmar — é o ponto do fluxo prévia → confirmação.
    ficha = await ConfirmarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, campos={**campos(), **previa.campos}
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


# --------------------------------------------------------------------------- #
# Campos obrigatórios da ficha física (apontamento de 10/08)
# --------------------------------------------------------------------------- #
async def test_ficha_exige_os_campos_com_asterisco_e_lista_todos_de_uma_vez():
    """Uma mensagem por campo faria a secretaria salvar seis vezes para descobrir o resto."""
    fichas, alunos, aluno = await _cenario()
    with pytest.raises(ValueError) as erro:
        await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
            tenant_id=TENANT, aluno_id=aluno.id, campos={"cor_raca": "Parda"}
        )
    mensagem = str(erro.value)
    for rotulo in ("CPF", "RA/RM", "data de nascimento", "endereço", "sexo"):
        assert rotulo in mensagem


async def test_ficha_normaliza_cpf_e_data():
    fichas, alunos, aluno = await _cenario()
    ficha = await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, campos=campos()
    )
    assert ficha.cpf == "52998224725"
    assert ficha.data_nascimento == "2015-03-02"


async def test_ficha_recusa_cpf_invalido():
    fichas, alunos, aluno = await _cenario()
    with pytest.raises(ValueError, match="CPF"):
        await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
            tenant_id=TENANT, aluno_id=aluno.id, campos=campos(cpf="529.982.247-24")
        )


async def test_ficha_recusa_nascimento_no_futuro():
    fichas, alunos, aluno = await _cenario()
    futuro = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="futuro"):
        await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
            tenant_id=TENANT, aluno_id=aluno.id, campos=campos(data_nascimento=futuro)
        )


# --------------------------------------------------------------------------- #
# Laudo médico: três estados, não um texto livre
# --------------------------------------------------------------------------- #
async def test_laudo_sim_guarda_o_cid():
    fichas, alunos, aluno = await _cenario()
    ficha = await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT,
        aluno_id=aluno.id,
        campos=campos(laudo_status="sim", laudo_cid="F84.0"),
    )
    assert ficha.laudo_status == "sim"
    assert ficha.laudo_cid == "F84.0"


async def test_em_investigacao_limpa_o_cid():
    """Deixar o CID pendurado faria a ficha afirmar um diagnóstico que a escola negou."""
    fichas, alunos, aluno = await _cenario()
    salvar = SalvarFichaMatricula(fichas=fichas, alunos=alunos)
    await salvar.executar(
        tenant_id=TENANT,
        aluno_id=aluno.id,
        campos=campos(laudo_status="sim", laudo_cid="F84.0"),
    )

    ficha = await salvar.executar(
        tenant_id=TENANT,
        aluno_id=aluno.id,
        campos=campos(laudo_status="em_investigacao", laudo_cid="F84.0"),
    )

    assert ficha.laudo_status == "em_investigacao"
    assert ficha.laudo_cid == ""


async def test_status_de_laudo_desconhecido_e_recusado():
    fichas, alunos, aluno = await _cenario()
    with pytest.raises(ValueError, match="laudo"):
        await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
            tenant_id=TENANT, aluno_id=aluno.id, campos=campos(laudo_status="talvez")
        )


# --------------------------------------------------------------------------- #
# Filiação derivada dos responsáveis vinculados (não digitada duas vezes)
# --------------------------------------------------------------------------- #
def _resp(nome, telefone, tipo) -> Contato:
    return Contato(
        tenant_id=TENANT, nome=nome, telefone=telefone, tipo_filiacao=tipo, cpf=""
    )


async def test_filiacao_vem_dos_responsaveis_do_aluno():
    mae = _resp("Ana Souza", "+5515999990001", TipoFiliacao.MAE)
    pai = _resp("Carlos Souza", "+5515999990002", TipoFiliacao.PAI)
    fichas, alunos, aluno = await _cenario([pai, mae])  # ordem invertida de propósito

    ficha = await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, campos=campos()
    )

    # Mãe primeiro, na ordem da ficha física — mesmo tendo sido vinculada depois.
    assert ficha.filiacao1_nome == "Ana Souza"
    assert ficha.filiacao1_telefone == "+5515999990001"
    assert ficha.filiacao2_nome == "Carlos Souza"


async def test_responsavel_legal_vai_para_a_linha_do_termo_de_guarda():
    mae = _resp("Ana Souza", "+5515999990001", TipoFiliacao.MAE)
    avo = _resp("Joana Ribeiro", "+5515999990009", TipoFiliacao.RESPONSAVEL_LEGAL)
    fichas, alunos, aluno = await _cenario([mae, avo])

    ficha = await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, campos=campos()
    )

    assert ficha.responsavel_legal == "Joana Ribeiro"
    assert ficha.termo_guarda is True
    # E não ocupa a linha de filiação, que é de mãe/pai.
    assert ficha.filiacao1_nome == "Ana Souza"
    assert ficha.filiacao2_nome == ""


async def test_filiacao_digitada_a_mao_e_ignorada():
    """A ficha tinha uma segunda cópia dos dados do responsável, livre para divergir.
    Agora ela é derivada: o que vier no corpo não sobrescreve o cadastro."""
    mae = _resp("Ana Souza", "+5515999990001", TipoFiliacao.MAE)
    fichas, alunos, aluno = await _cenario([mae])

    ficha = await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT,
        aluno_id=aluno.id,
        campos=campos(filiacao1_nome="Nome Errado", filiacao1_telefone="+550000000000"),
    )

    assert ficha.filiacao1_nome == "Ana Souza"
    assert ficha.filiacao1_telefone == "+5515999990001"


async def test_aluno_sem_responsavel_zera_a_filiacao():
    fichas, alunos, aluno = await _cenario()
    ficha = await SalvarFichaMatricula(fichas=fichas, alunos=alunos).executar(
        tenant_id=TENANT, aluno_id=aluno.id, campos=campos()
    )
    assert ficha.filiacao1_nome == ""
    assert ficha.responsavel_legal == ""
    assert ficha.termo_guarda is False
