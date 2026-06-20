"""Testa a importação de alunos em massa: prévia (LLM normaliza, validamos em código)
e confirmação (persistência determinística de séries, responsáveis e alunos)."""

from __future__ import annotations

import uuid

import pytest

from app.application.importacao_use_cases import (
    ConfirmarImportacaoAlunos,
    PrevisualizarImportacaoAlunos,
    _extrair_json_objeto,
    normalizar_telefone,
)
from app.domain.entities import (
    Contato,
    LinhaImportacaoAluno,
    ResponsavelImportado,
    Sala,
)
from app.infrastructure.llm.fake_provider import FakeLLMProvider
from tests.fakes import FakeAlunoRepo, FakeContatoRepo, FakeSalaRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


def _repos() -> tuple[FakeAlunoRepo, FakeContatoRepo, FakeSalaRepo]:
    contatos = FakeContatoRepo()
    salas = FakeSalaRepo()
    salas.contatos = contatos
    alunos = FakeAlunoRepo()
    alunos.contatos = contatos
    return alunos, contatos, salas


class _LLMComPayload:
    """LLM fake que devolve um JSON fixo, para testar o parsing/validação da prévia."""

    def __init__(self, payload: str) -> None:
        self._payload = payload

    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        return self._payload

    async def gerar_com_ferramentas(self, **_):  # pragma: no cover - não usado aqui
        raise NotImplementedError


# ------------------------------ helpers unitários -------------------------- #
def test_normalizar_telefone():
    assert normalizar_telefone("11 99999-0001") == ("+5511999990001", "")
    assert normalizar_telefone("+55 (11) 98888-7777") == ("+5511988887777", "")
    assert normalizar_telefone("") == ("", "")
    e164, aviso = normalizar_telefone("123")
    assert e164 == "" and "não reconhecido" in aviso


def test_extrair_json_tolera_cercas_de_codigo():
    bruto = '```json\n{"alunos": [{"nome": "Ana", "serie": "5º A"}]}\n```'
    dados = _extrair_json_objeto(bruto)
    assert dados["alunos"][0]["nome"] == "Ana"


# --------------------------------- prévia ---------------------------------- #
async def test_previa_normaliza_csv_com_fake_provider():
    alunos, contatos, salas = _repos()
    await salas.criar(Sala(tenant_id=TENANT, nome="5º A"))
    csv = (
        "nome,serie,matricula,responsavel,telefone\n"
        "maria silva,5º A,2026-1,joao silva,11 99999-0001\n"
        "pedro souza,4ª série B,,ana souza,+55 11 98888-7777\n"
    )

    previa = await PrevisualizarImportacaoAlunos(llm=FakeLLMProvider(), salas=salas).executar(
        tenant_id=TENANT, conteudo=csv
    )

    assert len(previa.linhas) == 2
    assert previa.total_validos == 2
    primeira = previa.linhas[0]
    assert primeira.serie == "5º A"
    assert primeira.serie_nova is False
    assert primeira.responsaveis[0].telefone == "+5511999990001"
    # Série citada que ainda não existe no tenant é marcada como nova.
    assert previa.linhas[1].serie_nova is True
    assert previa.series_novas == ["4ª série B"]


async def test_previa_marca_erros_de_linha():
    _, _, salas = _repos()
    payload = (
        '{"alunos": ['
        '{"nome": "", "serie": "5º A"},'
        '{"nome": "Ana", "serie": ""}'
        "]}"
    )
    previa = await PrevisualizarImportacaoAlunos(llm=_LLMComPayload(payload), salas=salas).executar(
        tenant_id=TENANT, conteudo="qualquer"
    )
    assert previa.total_validos == 0
    assert previa.linhas[0].valido is False
    assert any("Nome" in e for e in previa.linhas[0].erros)
    assert any("Série" in e for e in previa.linhas[1].erros)


async def test_previa_conteudo_vazio_falha():
    _, _, salas = _repos()
    with pytest.raises(ValueError, match="conteúdo"):
        await PrevisualizarImportacaoAlunos(llm=FakeLLMProvider(), salas=salas).executar(
            tenant_id=TENANT, conteudo="   "
        )


async def test_previa_json_invalido_falha():
    _, _, salas = _repos()
    with pytest.raises(ValueError, match="interpretar"):
        await PrevisualizarImportacaoAlunos(
            llm=_LLMComPayload("desculpe, não consegui"), salas=salas
        ).executar(tenant_id=TENANT, conteudo="qualquer")


# ------------------------------ confirmação -------------------------------- #
def _linha(nome, serie, *, telefone="", resp_nome="Resp", serie_nova=False):
    responsaveis = []
    if telefone or resp_nome:
        responsaveis.append(ResponsavelImportado(nome=resp_nome, telefone=telefone))
    return LinhaImportacaoAluno(
        nome=nome, serie=serie, responsaveis=responsaveis, serie_nova=serie_nova
    )


async def test_confirmar_cria_serie_responsavel_e_aluno():
    alunos, contatos, salas = _repos()
    linhas = [_linha("Maria", "5º A", telefone="+5511999990001", resp_nome="João")]

    resultado = await ConfirmarImportacaoAlunos(
        alunos=alunos, salas=salas, contatos=contatos
    ).executar(tenant_id=TENANT, linhas=linhas, criar_series_ausentes=True)

    assert resultado.criados == 1
    assert resultado.series_criadas == ["5º A"]
    # Sala, contato e aluno persistidos no tenant.
    sala = (await salas.listar(tenant_id=TENANT))[0]
    aluno = (await alunos.listar(tenant_id=TENANT))[0]
    assert aluno.nome == "Maria"
    assert aluno.sala_id == sala.id
    assert aluno.responsaveis[0].telefone == "+5511999990001"


async def test_confirmar_reaproveita_serie_e_contato_existentes():
    alunos, contatos, salas = _repos()
    sala = await salas.criar(Sala(tenant_id=TENANT, nome="5º A"))
    existente = await contatos.criar(
        Contato(tenant_id=TENANT, nome="João", telefone="+5511999990001")
    )
    # Dois alunos da mesma série compartilhando o mesmo responsável (mesmo telefone).
    linhas = [
        _linha("Maria", "5º a", telefone="+5511999990001"),
        _linha("Pedro", "5º A", telefone="+5511999990001"),
    ]

    resultado = await ConfirmarImportacaoAlunos(
        alunos=alunos, salas=salas, contatos=contatos
    ).executar(tenant_id=TENANT, linhas=linhas, criar_series_ausentes=False)

    assert resultado.criados == 2
    assert resultado.series_criadas == []  # série já existia (match case-insensitive)
    assert len(await contatos.listar(tenant_id=TENANT)) == 1  # contato reaproveitado
    for aluno in await alunos.listar(tenant_id=TENANT):
        assert aluno.sala_id == sala.id
        assert [c.id for c in aluno.responsaveis] == [existente.id]


async def test_confirmar_ignora_invalidos_e_series_ausentes_sem_flag():
    alunos, contatos, salas = _repos()
    linhas = [
        _linha("", "5º A"),  # inválido (sem nome)
        _linha("Pedro", "Série Fantasma"),  # série inexistente, sem permissão de criar
    ]

    resultado = await ConfirmarImportacaoAlunos(
        alunos=alunos, salas=salas, contatos=contatos
    ).executar(tenant_id=TENANT, linhas=linhas, criar_series_ausentes=False)

    assert resultado.criados == 0
    assert resultado.ignorados == 2
    assert any("Série Fantasma" in e for e in resultado.erros)
    assert await alunos.listar(tenant_id=TENANT) == []


async def test_confirmar_isola_por_tenant():
    alunos, contatos, salas = _repos()
    # Série com mesmo nome existe em OUTRO_TENANT; não deve ser reaproveitada.
    await salas.criar(Sala(tenant_id=OUTRO_TENANT, nome="5º A"))
    linhas = [_linha("Maria", "5º A", telefone="+5511999990001")]

    resultado = await ConfirmarImportacaoAlunos(
        alunos=alunos, salas=salas, contatos=contatos
    ).executar(tenant_id=TENANT, linhas=linhas, criar_series_ausentes=True)

    assert resultado.criados == 1
    assert resultado.series_criadas == ["5º A"]  # criou no próprio tenant
    assert len(await salas.listar(tenant_id=TENANT)) == 1
    assert await alunos.listar(tenant_id=OUTRO_TENANT) == []
