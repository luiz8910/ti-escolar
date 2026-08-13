"""Testa o cadastro de professores e a atribuição à série (Sala.professor_id)."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest

from app.application.cadastro_use_cases import (
    AtribuirProfessorASala,
    AtualizarProfessor,
    CadastrarProfessor,
    CriarSala,
    DadosProfessor,
    ListarEventuaisDisponiveis,
    ListarProfessores,
    ListarSeriesDoProfessor,
    ObterProfessor,
    RemoverProfessor,
    RemoverProfessorDaSala,
)
from app.application.validacao import cpf_valido, normalizar_data, normalizar_email
from tests.fakes import FakeProfessorRepo, FakeSalaRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


def _repos() -> tuple[FakeProfessorRepo, FakeSalaRepo]:
    professores = FakeProfessorRepo()
    salas = FakeSalaRepo()
    salas.professores = professores  # o fake resolve o nome do professor ao atribuir
    return professores, salas


# --------------------------- professores (CRUD) --------------------------- #
async def test_cadastrar_professor():
    professores, _ = _repos()
    prof = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Prof. Ana", telefone="+5511988880001"
    )
    assert prof.nome == "Prof. Ana"
    listados = await ListarProfessores(professores=professores).executar(tenant_id=TENANT)
    assert [p.id for p in listados] == [prof.id]


async def test_telefone_duplicado_no_tenant_falha():
    professores, _ = _repos()
    cadastrar = CadastrarProfessor(professores=professores)
    await cadastrar.executar(tenant_id=TENANT, nome="Ana", telefone="+5511988880001")
    with pytest.raises(ValueError, match="telefone"):
        await cadastrar.executar(tenant_id=TENANT, nome="Outra", telefone="+5511988880001")


async def test_mesmo_telefone_em_tenants_diferentes_e_permitido():
    professores, _ = _repos()
    cadastrar = CadastrarProfessor(professores=professores)
    await cadastrar.executar(tenant_id=TENANT, nome="Ana", telefone="+5511988880001")
    await cadastrar.executar(tenant_id=OUTRO_TENANT, nome="Ana", telefone="+5511988880001")


async def test_atualizar_professor_mantendo_unicidade():
    professores, _ = _repos()
    cadastrar = CadastrarProfessor(professores=professores)
    p1 = await cadastrar.executar(tenant_id=TENANT, nome="Ana", telefone="+5511988880001")
    await cadastrar.executar(tenant_id=TENANT, nome="Bia", telefone="+5511988880002")

    atualizar = AtualizarProfessor(professores=professores)
    atualizado = await atualizar.executar(
        tenant_id=TENANT, professor_id=p1.id, nome="Ana S.", telefone="+5511988880009"
    )
    assert atualizado.nome == "Ana S."

    with pytest.raises(ValueError, match="telefone"):
        await atualizar.executar(
            tenant_id=TENANT, professor_id=p1.id, nome="Ana S.", telefone="+5511988880002"
        )


# --------------------- atribuição professor ↔ série ----------------------- #
async def test_atribuir_professor_a_serie_e_listar_series():
    professores, salas = _repos()
    prof = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Prof. Ana", telefone="+5511988880001"
    )
    sala_a = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    sala_b = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="5ª série A")

    # Um professor pode conduzir várias séries.
    for sala in (sala_a, sala_b):
        s = await AtribuirProfessorASala(salas=salas).executar(
            tenant_id=TENANT, sala_id=sala.id, professor_id=prof.id
        )
        assert s.professor_id == prof.id
        assert s.professor_nome == "Prof. Ana"

    series = await ListarSeriesDoProfessor(salas=salas).executar(
        tenant_id=TENANT, professor_id=prof.id
    )
    assert {s.id for s in series} == {sala_a.id, sala_b.id}


async def test_reatribuir_substitui_o_professor_anterior():
    professores, salas = _repos()
    p1 = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511988880001"
    )
    p2 = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Bia", telefone="+5511988880002"
    )
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")

    await AtribuirProfessorASala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, professor_id=p1.id
    )
    s = await AtribuirProfessorASala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, professor_id=p2.id
    )
    assert s.professor_id == p2.id


async def test_remover_professor_da_serie():
    professores, salas = _repos()
    prof = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511988880001"
    )
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    await AtribuirProfessorASala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, professor_id=prof.id
    )

    s = await RemoverProfessorDaSala(salas=salas).executar(tenant_id=TENANT, sala_id=sala.id)
    assert s.professor_id is None
    assert s.professor_nome == ""


async def test_atribuir_professor_de_outro_tenant_falha():
    professores, salas = _repos()
    prof_outro = await CadastrarProfessor(professores=professores).executar(
        tenant_id=OUTRO_TENANT, nome="Intruso", telefone="+5511988880007"
    )
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    with pytest.raises(ValueError):
        await AtribuirProfessorASala(salas=salas).executar(
            tenant_id=TENANT, sala_id=sala.id, professor_id=prof_outro.id
        )


async def test_remover_professor():
    professores, _ = _repos()
    prof = await CadastrarProfessor(professores=professores).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511988880001"
    )
    assert await RemoverProfessor(professores=professores).executar(
        tenant_id=TENANT, professor_id=prof.id
    )
    assert await ListarProfessores(professores=professores).executar(tenant_id=TENANT) == []
    with pytest.raises(ValueError):
        await ObterProfessor(professores=professores).executar(
            tenant_id=TENANT, professor_id=prof.id
        )


# --------------------------------------------------------------------------- #
# Cadastro funcional (Fase 2): CPF, datas, contato e o vínculo titular/eventual
# --------------------------------------------------------------------------- #
# CPFs sintaticamente válidos (dígitos verificadores corretos) para os testes.
CPF_OK = "52998224725"
CPF_OUTRO = "16899535009"


async def _cadastrar(professores, **kwargs):
    dados = DadosProfessor(**kwargs.pop("dados", {}))
    return await CadastrarProfessor(professores=professores).executar(
        tenant_id=kwargs.pop("tenant_id", TENANT),
        nome=kwargs.pop("nome", "Prof. Ana"),
        telefone=kwargs.pop("telefone", "+5515999990001"),
        dados=dados,
        **kwargs,
    )


async def test_cadastro_normaliza_cpf_data_e_telefone_2():
    """O que se guarda é o valor canônico, não o digitado — senão a busca por documento
    e a checagem de duplicidade não funcionam."""
    professores, _ = _repos()

    prof = await _cadastrar(
        professores,
        dados={
            "cpf": "529.982.247-25",
            "data_nascimento": "07/03/1985",
            "telefone_2": "(15) 98888-7777",
            "email": "  Ana@Escola.TEST ",
            "matricula": " 12345 ",
        },
    )

    assert prof.cpf == CPF_OK
    assert prof.data_nascimento == "1985-03-07"
    assert prof.telefone_2 == "+5515988887777"
    assert prof.email == "ana@escola.test"
    assert prof.matricula == "12345"


async def test_cpf_invalido_e_recusado():
    """Pega o dígito trocado na digitação, não depois com o professor na fila."""
    professores, _ = _repos()
    with pytest.raises(ValueError, match="CPF"):
        await _cadastrar(professores, dados={"cpf": "529.982.247-24"})


async def test_cpf_de_digito_repetido_e_recusado():
    """111.111.111-11 passa no algoritmo dos verificadores — é o que se digita para
    escapar de um campo obrigatório."""
    professores, _ = _repos()
    with pytest.raises(ValueError):
        await _cadastrar(professores, dados={"cpf": "111.111.111-11"})


async def test_cpf_duplicado_no_mesmo_tenant_e_recusado():
    professores, _ = _repos()
    await _cadastrar(professores, dados={"cpf": CPF_OK})

    with pytest.raises(ValueError, match="CPF"):
        await _cadastrar(
            professores,
            nome="Prof. Beto",
            telefone="+5515999990002",
            dados={"cpf": CPF_OK},
        )


async def test_cpf_igual_em_outra_escola_e_permitido():
    """O mesmo professor pode dar aula em duas escolas da plataforma."""
    professores, _ = _repos()
    await _cadastrar(professores, dados={"cpf": CPF_OK})

    outro = await _cadastrar(professores, tenant_id=OUTRO_TENANT, dados={"cpf": CPF_OK})

    assert outro.cpf == CPF_OK


async def test_varios_professores_sem_cpf_convivem():
    """O CPF é opcional; a unicidade não pode transformar "sem CPF" em duplicado."""
    professores, _ = _repos()
    await _cadastrar(professores, nome="A", telefone="+5515999990001")
    await _cadastrar(professores, nome="B", telefone="+5515999990002")

    assert len(await ListarProfessores(professores=professores).executar(tenant_id=TENANT)) == 2


async def test_data_de_nascimento_futura_e_recusada():
    professores, _ = _repos()
    futuro = (date.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ValueError, match="futuro"):
        await _cadastrar(professores, dados={"data_nascimento": futuro})


async def test_telefone_2_em_formato_irreconhecivel_e_recusado():
    professores, _ = _repos()
    with pytest.raises(ValueError, match="Telefone 2"):
        await _cadastrar(professores, dados={"telefone_2": "123"})


async def test_professor_nasce_titular():
    """A migration marca os já cadastrados como titulares, e o cadastro segue a mesma
    regra: marcar todo mundo como eventual convocaria quem está em sala."""
    professores, _ = _repos()
    prof = await _cadastrar(professores)
    assert prof.titular is True
    assert prof.eh_eventual is False


async def test_eventuais_disponiveis_traz_so_quem_da_para_chamar():
    """A lista da chamada de falta (§I1): eventual E com telefone."""
    professores, _ = _repos()
    await _cadastrar(professores, nome="Titular", telefone="+5515999990001")
    await _cadastrar(
        professores,
        nome="Eventual com telefone",
        telefone="+5515999990002",
        dados={"titular": False},
    )
    sem_telefone = await _cadastrar(
        professores, nome="Eventual sem telefone", telefone="", dados={"titular": False}
    )
    assert sem_telefone.telefone == ""

    eventuais = await ListarEventuaisDisponiveis(professores=professores).executar(
        tenant_id=TENANT
    )

    assert [p.nome for p in eventuais] == ["Eventual com telefone"]


async def test_atualizar_troca_vinculo_e_revalida_cpf():
    professores, _ = _repos()
    prof = await _cadastrar(professores, dados={"cpf": CPF_OK})
    outro = await _cadastrar(
        professores, nome="Outro", telefone="+5515999990002", dados={"cpf": CPF_OUTRO}
    )

    atualizado = await AtualizarProfessor(professores=professores).executar(
        tenant_id=TENANT,
        professor_id=prof.id,
        nome=prof.nome,
        telefone=prof.telefone,
        dados=DadosProfessor(cpf=CPF_OK, titular=False, educacao_fisica=True),
    )
    assert atualizado.titular is False
    assert atualizado.educacao_fisica is True
    assert atualizado.cpf == CPF_OK  # manter o próprio CPF não é duplicidade

    with pytest.raises(ValueError, match="CPF"):
        await AtualizarProfessor(professores=professores).executar(
            tenant_id=TENANT,
            professor_id=prof.id,
            nome=prof.nome,
            telefone=prof.telefone,
            dados=DadosProfessor(cpf=outro.cpf),
        )


async def test_atualizar_sem_dados_preserva_o_cadastro_funcional():
    """Quem edita só o nome não pode perder CPF e matrícula por omissão."""
    professores, _ = _repos()
    prof = await _cadastrar(professores, dados={"cpf": CPF_OK, "matricula": "999"})

    atualizado = await AtualizarProfessor(professores=professores).executar(
        tenant_id=TENANT,
        professor_id=prof.id,
        nome="Prof. Ana Maria",
        telefone=prof.telefone,
    )

    assert atualizado.nome == "Prof. Ana Maria"
    assert atualizado.cpf == CPF_OK
    assert atualizado.matricula == "999"


# --------------------------------------------------------------------------- #
# Validação de formato (usada também por responsáveis e alunos, adiante)
# --------------------------------------------------------------------------- #
def test_cpf_valido_confere_os_dois_digitos():
    assert cpf_valido("529.982.247-25")
    assert cpf_valido("16899535009")
    # Um dígito verificador trocado.
    assert not cpf_valido("52998224724")
    # Curto, longo e repetido.
    assert not cpf_valido("5299822472")
    assert not cpf_valido("529982247250")
    assert not cpf_valido("00000000000")


def test_normalizar_data_aceita_os_dois_formatos_e_recusa_data_inexistente():
    assert normalizar_data("2026-02-28") == "2026-02-28"
    assert normalizar_data("28/02/2026") == "2026-02-28"
    with pytest.raises(ValueError):
        normalizar_data("31/02/2026")
    with pytest.raises(ValueError):
        normalizar_data("ontem")
    assert normalizar_data("") == ""


def test_normalizar_email_recusa_o_que_nao_e_endereco():
    assert normalizar_email(" Ana@Escola.TEST ") == "ana@escola.test"
    assert normalizar_email("") == ""
    with pytest.raises(ValueError):
        normalizar_email("ana arroba escola")


async def test_telefone_digitado_com_mascara_vira_e164():
    """A máscara da tela é conforto de digitação; o dado guardado é a chave da conversa.

    Sem normalizar aqui, "(15) 99999-0001" ficaria no banco como foi digitado: o inbound
    procura o remetente em E.164 e não reconheceria o professor, e a Graph API recusaria
    o envio.
    """
    professores, _ = _repos()
    prof = await _cadastrar(professores, nome="Carla", telefone="(15) 99999-0001")
    assert prof.telefone == "+5515999990001"


async def test_mesmo_numero_em_formatos_diferentes_e_recusado():
    professores, _ = _repos()
    await _cadastrar(professores, nome="Carla", telefone="+5515999990001")

    with pytest.raises(ValueError, match="telefone"):
        await _cadastrar(professores, nome="Outra", telefone="(15) 99999-0001")
