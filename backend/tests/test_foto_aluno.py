"""Foto do aluno (§2.3 do plano de 10/08): opcional, validada e sem lixo no storage.

A foto é **opcional** por decisão do produto: foto de criança eleva o risco LGPD e um
campo obrigatório travaria o cadastro de quem não a tem no dia da matrícula. O que se
testa aqui é o que sobra de risco — arquivo que não deveria entrar, e imagem de criança
que fica no storage sem ninguém apontar para ela.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.foto_aluno_use_cases import (
    DefinirFotoDoAluno,
    ObterFotoDoAluno,
    RemoverFotoDoAluno,
)
from app.domain.entities import TAMANHO_MAXIMO_FOTO, Aluno
from app.infrastructure.storage import ArquivoStorageMemoria
from tests.fakes import FakeAlunoRepo

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()
SALA = uuid.uuid4()
JPEG = b"\xff\xd8\xff\xe0conteudo-da-foto"


async def _cenario():
    alunos = FakeAlunoRepo()
    storage = ArquivoStorageMemoria()
    aluno = await alunos.criar(Aluno(tenant_id=TENANT, nome="João", sala_id=SALA))
    return alunos, storage, aluno


async def test_aluno_nasce_sem_foto():
    _, _, aluno = await _cenario()
    assert aluno.foto_chave == ""


async def test_definir_e_ler_a_foto():
    alunos, storage, aluno = await _cenario()

    salvo = await DefinirFotoDoAluno(alunos=alunos, storage=storage).executar(
        tenant_id=TENANT, aluno_id=aluno.id, conteudo=JPEG, mime="image/jpeg"
    )
    assert salvo.foto_chave

    arquivo = await ObterFotoDoAluno(alunos=alunos, storage=storage).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    )
    assert arquivo is not None
    assert arquivo.conteudo == JPEG


async def test_a_chave_nao_carrega_o_nome_do_aluno():
    """A chave aparece em log e em URL; o conteúdo é dado pessoal de menor."""
    alunos, storage, aluno = await _cenario()
    salvo = await DefinirFotoDoAluno(alunos=alunos, storage=storage).executar(
        tenant_id=TENANT, aluno_id=aluno.id, conteudo=JPEG, mime="image/jpeg"
    )
    assert "joão" not in salvo.foto_chave.lower()
    assert salvo.foto_chave.startswith(f"foto/{TENANT}/")


async def test_trocar_a_foto_apaga_a_anterior():
    """Imagem de criança que ninguém referencia é dado pessoal sem finalidade."""
    alunos, storage, aluno = await _cenario()
    definir = DefinirFotoDoAluno(alunos=alunos, storage=storage)
    primeira = await definir.executar(
        tenant_id=TENANT, aluno_id=aluno.id, conteudo=JPEG, mime="image/jpeg"
    )
    chave_antiga = primeira.foto_chave

    segunda = await definir.executar(
        tenant_id=TENANT, aluno_id=aluno.id, conteudo=b"\x89PNGoutra", mime="image/png"
    )

    assert segunda.foto_chave != chave_antiga
    assert await storage.ler(chave=chave_antiga) is None


async def test_remover_apaga_os_bytes_e_a_referencia():
    alunos, storage, aluno = await _cenario()
    salvo = await DefinirFotoDoAluno(alunos=alunos, storage=storage).executar(
        tenant_id=TENANT, aluno_id=aluno.id, conteudo=JPEG, mime="image/jpeg"
    )
    chave = salvo.foto_chave

    sem_foto = await RemoverFotoDoAluno(alunos=alunos, storage=storage).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    )

    assert sem_foto.foto_chave == ""
    assert await storage.ler(chave=chave) is None


async def test_remover_sem_foto_e_silencioso():
    """Clicar duas vezes em "remover" não pode virar erro na cara da secretaria."""
    alunos, storage, aluno = await _cenario()
    resultado = await RemoverFotoDoAluno(alunos=alunos, storage=storage).executar(
        tenant_id=TENANT, aluno_id=aluno.id
    )
    assert resultado.foto_chave == ""


async def test_pdf_nao_e_foto():
    """Aceitar PDF aqui criaria "foto" que a tela não exibe."""
    alunos, storage, aluno = await _cenario()
    with pytest.raises(ValueError, match="imagem"):
        await DefinirFotoDoAluno(alunos=alunos, storage=storage).executar(
            tenant_id=TENANT,
            aluno_id=aluno.id,
            conteudo=b"%PDF-1.4",
            mime="application/pdf",
        )


async def test_arquivo_acima_do_teto_e_recusado():
    alunos, storage, aluno = await _cenario()
    with pytest.raises(ValueError, match="5 MB"):
        await DefinirFotoDoAluno(alunos=alunos, storage=storage).executar(
            tenant_id=TENANT,
            aluno_id=aluno.id,
            conteudo=b"x" * (TAMANHO_MAXIMO_FOTO + 1),
            mime="image/jpeg",
        )


async def test_arquivo_vazio_e_recusado():
    alunos, storage, aluno = await _cenario()
    with pytest.raises(ValueError, match="vazio"):
        await DefinirFotoDoAluno(alunos=alunos, storage=storage).executar(
            tenant_id=TENANT, aluno_id=aluno.id, conteudo=b"", mime="image/jpeg"
        )


async def test_foto_nao_atravessa_tenant():
    alunos, storage, aluno = await _cenario()
    await DefinirFotoDoAluno(alunos=alunos, storage=storage).executar(
        tenant_id=TENANT, aluno_id=aluno.id, conteudo=JPEG, mime="image/jpeg"
    )

    with pytest.raises(ValueError):
        await DefinirFotoDoAluno(alunos=alunos, storage=storage).executar(
            tenant_id=OUTRO_TENANT, aluno_id=aluno.id, conteudo=JPEG, mime="image/jpeg"
        )
    assert (
        await ObterFotoDoAluno(alunos=alunos, storage=storage).executar(
            tenant_id=OUTRO_TENANT, aluno_id=aluno.id
        )
        is None
    )


async def test_foto_expurgada_do_storage_nao_derruba_a_leitura():
    """O metadado pode sobreviver aos bytes; a tela mostra "sem foto", não um erro."""
    alunos, storage, aluno = await _cenario()
    salvo = await DefinirFotoDoAluno(alunos=alunos, storage=storage).executar(
        tenant_id=TENANT, aluno_id=aluno.id, conteudo=JPEG, mime="image/jpeg"
    )
    await storage.remover(chave=salvo.foto_chave)

    assert (
        await ObterFotoDoAluno(alunos=alunos, storage=storage).executar(
            tenant_id=TENANT, aluno_id=aluno.id
        )
        is None
    )
