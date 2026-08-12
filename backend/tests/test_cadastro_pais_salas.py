"""Testa o cadastro de pais/responsáveis e salas (turmas): CRUD, vínculo e relatório."""

from __future__ import annotations

import uuid

import pytest

from app.application.cadastro_use_cases import (
    AtualizarPai,
    AtualizarSala,
    CadastrarPai,
    CriarSala,
    DadosResponsavel,
    DadosTurma,
    ListarPais,
    RelatorioPaisDaSala,
    RemoverPai,
    RemoverSala,
)
from app.domain.entities import Aluno, TipoFiliacao, Turno
from tests.fakes import FakeAlunoRepo, FakeContatoRepo, FakeSalaRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


def _repos() -> tuple[FakeContatoRepo, FakeSalaRepo]:
    contatos = FakeContatoRepo()
    salas = FakeSalaRepo()
    salas.contatos = contatos  # o fake resolve pais por id ao vincular
    return contatos, salas


# --------------------------- pais (CRUD) ----------------------------------- #
async def test_responsavel_entra_na_turma_pelo_aluno():
    contatos, salas = _repos()
    alunos = FakeAlunoRepo()
    salas.alunos = alunos
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")

    pai = await CadastrarPai(contatos=contatos).executar(
        tenant_id=TENANT, nome="Maria Souza", telefone="+5511999990001"
    )
    # O responsável entra na turma pelo **aluno**, não por um vínculo próprio.
    await alunos.criar(
        Aluno(tenant_id=TENANT, nome="Filho", sala_id=sala.id, responsaveis=[pai])
    )

    assert pai.nome == "Maria Souza"
    pais_da_sala = await RelatorioPaisDaSala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id
    )
    assert [c.id for c in pais_da_sala] == [pai.id]


async def test_telefone_duplicado_no_tenant_falha():
    contatos, salas = _repos()
    cadastrar = CadastrarPai(contatos=contatos)
    await cadastrar.executar(tenant_id=TENANT, nome="Maria", telefone="+5511999990001")
    with pytest.raises(ValueError, match="telefone"):
        await cadastrar.executar(tenant_id=TENANT, nome="Outra", telefone="+5511999990001")


async def test_mesmo_telefone_em_tenants_diferentes_e_permitido():
    contatos, salas = _repos()
    cadastrar = CadastrarPai(contatos=contatos)
    await cadastrar.executar(tenant_id=TENANT, nome="Maria", telefone="+5511999990001")
    # Não deve levantar: o telefone é único só dentro do tenant.
    await cadastrar.executar(tenant_id=OUTRO_TENANT, nome="Maria", telefone="+5511999990001")


async def test_atualizar_pai_mantendo_unicidade_de_telefone():
    contatos, salas = _repos()
    cadastrar = CadastrarPai(contatos=contatos)
    p1 = await cadastrar.executar(tenant_id=TENANT, nome="Maria", telefone="+5511999990001")
    await cadastrar.executar(tenant_id=TENANT, nome="João", telefone="+5511999990002")

    atualizar = AtualizarPai(contatos=contatos)
    atualizado = await atualizar.executar(
        tenant_id=TENANT, contato_id=p1.id, nome="Maria S.", telefone="+5511999990009"
    )
    assert atualizado.nome == "Maria S."
    assert atualizado.telefone == "+5511999990009"

    # Não pode assumir o telefone de outro responsável.
    with pytest.raises(ValueError, match="telefone"):
        await atualizar.executar(
            tenant_id=TENANT, contato_id=p1.id, nome="Maria S.", telefone="+5511999990002"
        )


async def test_remover_pai():
    contatos, salas = _repos()
    pai = await CadastrarPai(contatos=contatos).executar(
        tenant_id=TENANT, nome="Maria", telefone="+5511999990001"
    )
    assert await RemoverPai(contatos=contatos).executar(tenant_id=TENANT, contato_id=pai.id)
    assert (await ListarPais(contatos=contatos).executar(tenant_id=TENANT)).itens == []
    # Remover de novo retorna False.
    assert not await RemoverPai(contatos=contatos).executar(tenant_id=TENANT, contato_id=pai.id)


# --------------------------- turmas (CRUD) --------------------------------- #
async def test_crud_de_turma():
    _, salas = _repos()
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    sala = await AtualizarSala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id, nome="4ª série B - Manhã", descricao="turma da manhã"
    )
    assert sala.nome == "4ª série B - Manhã"
    assert sala.descricao == "turma da manhã"

    assert await RemoverSala(salas=salas, alunos=FakeAlunoRepo()).executar(
        tenant_id=TENANT, sala_id=sala.id
    )


# --------------------------------------------------------------------------- #
# O relatório da turma é DERIVADO dos alunos ativos
#
# Antes havia um vínculo manual (`sala_contatos`), e com ele o estado inconsistente que o
# apontamento de 10/08 mandou tirar da tela: um responsável ligado a uma turma sem nenhum
# filho lá — que a cobertura de contatos contava como se tivesse.
# --------------------------------------------------------------------------- #
def _repos_com_alunos():
    contatos, salas = _repos()
    alunos = FakeAlunoRepo()
    salas.alunos = alunos
    return contatos, salas, alunos


async def test_relatorio_vem_dos_responsaveis_dos_alunos_da_turma():
    contatos, salas, alunos = _repos_com_alunos()
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    mae = await CadastrarPai(contatos=contatos).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511999990003"
    )
    await alunos.criar(
        Aluno(tenant_id=TENANT, nome="Filho", sala_id=sala.id, responsaveis=[mae])
    )

    relatorio = await RelatorioPaisDaSala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id
    )

    assert [c.id for c in relatorio] == [mae.id]


async def test_responsavel_sem_aluno_na_turma_nao_aparece():
    """É o estado que o vínculo manual permitia — e o motivo de ele ter saído."""
    contatos, salas, _ = _repos_com_alunos()
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    await CadastrarPai(contatos=contatos).executar(
        tenant_id=TENANT, nome="Sem filho aqui", telefone="+5511999990004"
    )

    assert await RelatorioPaisDaSala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id
    ) == []


async def test_ex_aluno_nao_mantem_o_responsavel_na_turma():
    """A família de quem já saiu não deve continuar recebendo o aviso da turma."""
    contatos, salas, alunos = _repos_com_alunos()
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    mae = await CadastrarPai(contatos=contatos).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511999990003"
    )
    await alunos.criar(
        Aluno(
            tenant_id=TENANT,
            nome="Ex-aluno",
            sala_id=sala.id,
            responsaveis=[mae],
            ativo=False,
        )
    )

    assert await RelatorioPaisDaSala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id
    ) == []


async def test_irmaos_na_mesma_turma_nao_duplicam_o_responsavel():
    contatos, salas, alunos = _repos_com_alunos()
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="4ª série B")
    mae = await CadastrarPai(contatos=contatos).executar(
        tenant_id=TENANT, nome="Ana", telefone="+5511999990003"
    )
    for nome in ("Gêmeo 1", "Gêmeo 2"):
        await alunos.criar(
            Aluno(tenant_id=TENANT, nome=nome, sala_id=sala.id, responsaveis=[mae])
        )

    relatorio = await RelatorioPaisDaSala(salas=salas).executar(
        tenant_id=TENANT, sala_id=sala.id
    )

    assert len(relatorio) == 1


# --------------------------------------------------------------------------- #
# Cadastro do responsável e termo de guarda (Fase 2 do plano de 10/08)
# --------------------------------------------------------------------------- #
CPF_OK = "52998224725"
CPF_OUTRO = "16899535009"


async def _cadastrar_resp(contatos, salas, **kwargs):
    dados = DadosResponsavel(**kwargs.pop("dados", {}))
    return await CadastrarPai(contatos=contatos).executar(
        tenant_id=kwargs.pop("tenant_id", TENANT),
        nome=kwargs.pop("nome", "Maria Souza"),
        telefone=kwargs.pop("telefone", "+5515999990001"),
        dados=dados,
        **kwargs,
    )


async def test_cadastro_do_responsavel_normaliza_os_formatos():
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()

    pai = await _cadastrar_resp(
        contatos,
        salas,
        dados={
            "cpf": "529.982.247-25",
            "tipo_filiacao": TipoFiliacao.MAE,
            "data_nascimento": "07/03/1985",
            "telefone_2": "(15) 98888-7777",
            "telefone_trabalho": "15 3333-4444",
            "local_trabalho": "  Hospital Central  ",
            "email": " Maria@Escola.TEST ",
        },
    )

    assert pai.cpf == CPF_OK
    assert pai.data_nascimento == "1985-03-07"
    assert pai.telefone_2 == "+5515988887777"
    assert pai.telefone_trabalho == "+551533334444"
    assert pai.local_trabalho == "Hospital Central"
    assert pai.email == "maria@escola.test"


async def test_termo_de_guarda_e_um_responsavel_como_outro_qualquer():
    """O ponto da modelagem: antes era um booleano na ficha, e a pessoa ficava invisível
    para o canal — não recebia disparo nem era reconhecida no WhatsApp."""
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()

    guardia = await _cadastrar_resp(
        contatos,
        salas,
        nome="Tia Joana",
        telefone="+5515999990009",
        dados={"tipo_filiacao": TipoFiliacao.RESPONSAVEL_LEGAL, "cpf": CPF_OUTRO},
    )

    assert guardia.eh_responsavel_legal is True
    # E está na lista de responsáveis do tenant como qualquer outro: é isso que a faz
    # receber aviso e contar na cobertura da turma.
    pagina = await ListarPais(contatos=contatos).executar(tenant_id=TENANT)
    assert guardia.id in [c.id for c in pagina.itens]


async def test_mae_e_pai_nao_sao_responsavel_legal():
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()
    mae = await _cadastrar_resp(contatos, salas, dados={"tipo_filiacao": TipoFiliacao.MAE})
    assert mae.eh_responsavel_legal is False


async def test_cpf_duplicado_no_mesmo_tenant_e_recusado():
    """A mesma pessoa cadastrada duas vezes vira dois destinatários do mesmo aviso."""
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()
    await _cadastrar_resp(contatos, salas, dados={"cpf": CPF_OK})

    with pytest.raises(ValueError, match="CPF"):
        await _cadastrar_resp(
            contatos,
            salas,
            nome="Outra Pessoa",
            telefone="+5515999990002",
            dados={"cpf": CPF_OK},
        )


async def test_cpf_invalido_e_recusado():
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()
    with pytest.raises(ValueError, match="CPF"):
        await _cadastrar_resp(contatos, salas, dados={"cpf": "529.982.247-24"})


async def test_varios_responsaveis_sem_cpf_convivem():
    """O CPF é opcional — a importação em massa e o bot criam contato só com telefone."""
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()
    await _cadastrar_resp(contatos, salas, nome="A", telefone="+5515999990001")
    await _cadastrar_resp(contatos, salas, nome="B", telefone="+5515999990002")

    pagina = await ListarPais(contatos=contatos).executar(tenant_id=TENANT)
    assert pagina.total == 2


async def test_atualizar_sem_dados_preserva_o_cadastro():
    """Quem edita só o nome não pode perder o CPF por omissão."""
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()
    pai = await _cadastrar_resp(
        contatos, salas, dados={"cpf": CPF_OK, "tipo_filiacao": TipoFiliacao.MAE}
    )

    atualizado = await AtualizarPai(contatos=contatos).executar(
        tenant_id=TENANT, contato_id=pai.id, nome="Maria S. Souza", telefone=pai.telefone
    )

    assert atualizado.nome == "Maria S. Souza"
    assert atualizado.cpf == CPF_OK
    assert atualizado.tipo_filiacao is TipoFiliacao.MAE


async def test_atualizar_permite_manter_o_proprio_cpf():
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()
    pai = await _cadastrar_resp(contatos, salas, dados={"cpf": CPF_OK})

    atualizado = await AtualizarPai(contatos=contatos).executar(
        tenant_id=TENANT,
        contato_id=pai.id,
        nome=pai.nome,
        telefone=pai.telefone,
        dados=DadosResponsavel(cpf=CPF_OK, tipo_filiacao=TipoFiliacao.PAI),
    )

    assert atualizado.cpf == CPF_OK
    assert atualizado.tipo_filiacao is TipoFiliacao.PAI


async def test_atualizar_recusa_cpf_de_outro_responsavel():
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()
    pai = await _cadastrar_resp(contatos, salas, dados={"cpf": CPF_OK})
    outro = await _cadastrar_resp(
        contatos, salas, nome="Outro", telefone="+5515999990002", dados={"cpf": CPF_OUTRO}
    )

    with pytest.raises(ValueError, match="CPF"):
        await AtualizarPai(contatos=contatos).executar(
            tenant_id=TENANT,
            contato_id=pai.id,
            nome=pai.nome,
            telefone=pai.telefone,
            dados=DadosResponsavel(cpf=outro.cpf),
        )


async def test_telefone_de_trabalho_invalido_e_recusado():
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()
    with pytest.raises(ValueError, match="Telefone do trabalho"):
        await _cadastrar_resp(contatos, salas, dados={"telefone_trabalho": "123"})


async def test_cpf_igual_em_outra_escola_e_permitido():
    """O mesmo responsável pode ter filhos em duas escolas da plataforma."""
    contatos, salas = FakeContatoRepo(), FakeSalaRepo()
    await _cadastrar_resp(contatos, salas, dados={"cpf": CPF_OK})

    outro = await _cadastrar_resp(
        contatos, salas, tenant_id=OUTRO_TENANT, dados={"cpf": CPF_OK}
    )

    assert outro.cpf == CPF_OK


# --------------------------------------------------------------------------- #
# Turma estruturada (ano · etapa · turma · sala · período)
#
# O nome era texto livre, e "4ª B", "4ª série B" e "4a serie B" conviviam como turmas
# diferentes — com alunos espalhados entre elas.
# --------------------------------------------------------------------------- #
async def _criar_turma(salas, **kwargs):
    return await CriarSala(salas=salas).executar(
        tenant_id=kwargs.pop("tenant_id", TENANT),
        dados=DadosTurma(**kwargs),
    )


async def test_nome_da_turma_e_derivado_de_etapa_e_letra():
    _, salas = _repos()
    turma = await _criar_turma(
        salas, ano_letivo=2026, etapa="4ª série", turma="b", numero_sala="12",
        periodo=Turno.MANHA,
    )
    assert turma.nome == "4ª série B"  # a letra é normalizada em maiúscula
    assert turma.periodo is Turno.MANHA
    assert turma.numero_sala == "12"


async def test_turma_repetida_no_mesmo_ano_e_recusada():
    _, salas = _repos()
    await _criar_turma(salas, ano_letivo=2026, etapa="4ª série", turma="B")
    with pytest.raises(ValueError, match="Já existe a turma"):
        await _criar_turma(salas, ano_letivo=2026, etapa="4ª série", turma="b")


async def test_mesma_turma_em_outro_ano_letivo_e_permitida():
    """É a virada de ano: a 4ª B de 2026 e a de 2027 são turmas diferentes."""
    _, salas = _repos()
    await _criar_turma(salas, ano_letivo=2026, etapa="4ª série", turma="B")
    nova = await _criar_turma(salas, ano_letivo=2027, etapa="4ª série", turma="B")
    assert nova.ano_letivo == 2027


async def test_turma_sem_estrutura_mantem_o_nome_livre():
    """Retrocompatibilidade: o seed e a importação criam turma só com nome."""
    _, salas = _repos()
    turma = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="Turma especial")
    assert turma.nome == "Turma especial"
    assert turma.etapa == ""


async def test_turma_sem_nome_nem_estrutura_e_recusada():
    _, salas = _repos()
    with pytest.raises(ValueError, match="nome"):
        await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="  ")


async def test_atualizar_turma_renomeia_pela_estrutura():
    _, salas = _repos()
    turma = await _criar_turma(salas, ano_letivo=2026, etapa="4ª série", turma="B")

    atualizada = await AtualizarSala(salas=salas).executar(
        tenant_id=TENANT,
        sala_id=turma.id,
        dados=DadosTurma(ano_letivo=2026, etapa="5ª série", turma="A", periodo=Turno.TARDE),
    )

    assert atualizada.nome == "5ª série A"
    assert atualizada.periodo is Turno.TARDE


async def test_atualizar_nao_acusa_a_propria_turma_como_duplicada():
    _, salas = _repos()
    turma = await _criar_turma(salas, ano_letivo=2026, etapa="4ª série", turma="B")

    atualizada = await AtualizarSala(salas=salas).executar(
        tenant_id=TENANT,
        sala_id=turma.id,
        descricao="turma da manhã",
        dados=DadosTurma(ano_letivo=2026, etapa="4ª série", turma="B"),
    )

    assert atualizada.descricao == "turma da manhã"


async def test_grade_invalida_impede_salvar_a_turma():
    """A validação da grade acontece no cadastro, não só na tela."""
    _, salas = _repos()
    with pytest.raises(ValueError, match="depois"):
        await _criar_turma(
            salas,
            ano_letivo=2026,
            etapa="4ª série",
            turma="B",
            grade_horario={"formato": "turno", "inicio": "11:30", "fim": "07:30"},
        )


async def test_grade_e_guardada_normalizada():
    _, salas = _repos()
    turma = await _criar_turma(
        salas,
        ano_letivo=2026,
        etapa="4ª série",
        turma="B",
        grade_horario={
            "formato": "aulas",
            "blocos": [
                {"dia": 2, "inicio": "09:00", "fim": "09:50"},
                {"dia": 1, "inicio": "07:30", "fim": "08:20"},
            ],
        },
    )
    assert [b["dia"] for b in turma.grade_horario["blocos"]] == [1, 2]
