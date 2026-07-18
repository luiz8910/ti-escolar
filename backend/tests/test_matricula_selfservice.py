"""Testa a matrícula self-service pelo WhatsApp (§E1): início (lista de documentos),
anexo de documentos, avanço de status e exceções.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.matricula_use_cases import (
    AnexarDocumentoMatricula,
    AtualizarStatusMatricula,
    IniciarMatricula,
    ListarMatriculas,
    montar_mensagem_documentos,
)
from app.domain.entities import StatusMatricula
from tests.fakes import FakeSolicitacaoMatriculaRepo

TENANT = uuid.uuid4()
TEL = "+5511999990000"


def test_mensagem_documentos_lista_itens():
    msg = montar_mensagem_documentos(nome_responsavel="Maria")
    assert "Maria" in msg
    assert "Comprovante de residência atualizado" in msg


async def test_iniciar_matricula_cria_solicitacao():
    matriculas = FakeSolicitacaoMatriculaRepo()
    sol = await IniciarMatricula(matriculas=matriculas).executar(
        tenant_id=TENANT, contato_telefone=TEL, nome_responsavel="Maria"
    )
    assert sol.status == StatusMatricula.INICIADA
    assert sol.contato_telefone == TEL


async def test_iniciar_matricula_e_idempotente_por_telefone():
    matriculas = FakeSolicitacaoMatriculaRepo()
    iniciar = IniciarMatricula(matriculas=matriculas)
    a = await iniciar.executar(tenant_id=TENANT, contato_telefone=TEL)
    b = await iniciar.executar(tenant_id=TENANT, contato_telefone=TEL)
    assert a.id == b.id
    assert len(matriculas.solicitacoes) == 1


async def test_anexar_documento_avanca_status():
    matriculas = FakeSolicitacaoMatriculaRepo()
    sol = await IniciarMatricula(matriculas=matriculas).executar(
        tenant_id=TENANT, contato_telefone=TEL
    )
    atualizada = await AnexarDocumentoMatricula(matriculas=matriculas).executar(
        tenant_id=TENANT, solicitacao_id=sol.id, nome="RG do aluno", url="http://x/rg.jpg"
    )
    assert atualizada.status == StatusMatricula.DOCUMENTOS_ENVIADOS
    assert len(atualizada.documentos) == 1
    assert atualizada.documentos[0].nome == "RG do aluno"


async def test_atualizar_status_para_concluida():
    matriculas = FakeSolicitacaoMatriculaRepo()
    sol = await IniciarMatricula(matriculas=matriculas).executar(
        tenant_id=TENANT, contato_telefone=TEL
    )
    concluida = await AtualizarStatusMatricula(matriculas=matriculas).executar(
        tenant_id=TENANT,
        solicitacao_id=sol.id,
        status=StatusMatricula.CONCLUIDA,
        observacao="Documentos conferidos.",
    )
    assert concluida.status == StatusMatricula.CONCLUIDA
    # Concluída sai das "em aberto": um novo início cria outra solicitação.
    nova = await IniciarMatricula(matriculas=matriculas).executar(
        tenant_id=TENANT, contato_telefone=TEL
    )
    assert nova.id != sol.id

    todas = await ListarMatriculas(matriculas=matriculas).executar(tenant_id=TENANT)
    assert len(todas) == 2


# --------------------------- exceções --------------------------- #
async def test_iniciar_matricula_sem_telefone_falha():
    matriculas = FakeSolicitacaoMatriculaRepo()
    with pytest.raises(ValueError):
        await IniciarMatricula(matriculas=matriculas).executar(
            tenant_id=TENANT, contato_telefone="  "
        )


async def test_anexar_documento_sem_nome_falha():
    matriculas = FakeSolicitacaoMatriculaRepo()
    sol = await IniciarMatricula(matriculas=matriculas).executar(
        tenant_id=TENANT, contato_telefone=TEL
    )
    with pytest.raises(ValueError):
        await AnexarDocumentoMatricula(matriculas=matriculas).executar(
            tenant_id=TENANT, solicitacao_id=sol.id, nome="   "
        )


async def test_anexar_documento_solicitacao_inexistente_falha():
    matriculas = FakeSolicitacaoMatriculaRepo()
    with pytest.raises(ValueError):
        await AnexarDocumentoMatricula(matriculas=matriculas).executar(
            tenant_id=TENANT, solicitacao_id=uuid.uuid4(), nome="RG"
        )
