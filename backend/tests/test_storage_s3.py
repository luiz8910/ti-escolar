"""O adaptador S3 contra um serviço S3 **de verdade** (MinIO), não contra um mock.

Esta escolha é o motivo de o adaptador existir. O `storage.py` registrava, desde o começo,
por que ele nunca tinha sido escrito: sem credencial para testar contra o serviço real, ele
"iria para produção sem nunca ter escrito um byte". Um mock de boto3 não teria resolvido —
ele confirmaria que chamamos `put_object`, que é justamente a parte que não erra; o que erra
é o contrato (a exceção de chave inexistente, o `delete` que responde sucesso para o que não
existe, o corpo que precisa ser lido antes de fechar).

Pula sozinho quando não há MinIO: `docker compose up minio`, ou o serviço do CI.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.infrastructure.storage_s3 import S3ArquivoStorage

# Sem `pytestmark` global: o arquivo mistura testes async (contra o MinIO) e síncronos
# (a fábrica), e o mark global faria os síncronos avisarem a cada execução.
# `asyncio_mode = "auto"` no pyproject já cuida dos async.

_ENDPOINT = os.getenv("S3_ENDPOINT_URL", "")
_BUCKET = os.getenv("S3_BUCKET_DOCUMENTOS", "ti-escolar-docs")

sem_minio = pytest.mark.skipif(
    not _ENDPOINT, reason="S3_ENDPOINT_URL não definido — suba o MinIO para rodar."
)


def _storage() -> S3ArquivoStorage:
    return S3ArquivoStorage(
        bucket=_BUCKET,
        region=os.getenv("AWS_REGION", "sa-east-1"),
        access_key=os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"),
        secret_key=os.getenv("AWS_SECRET_ACCESS_KEY", "minioadmin"),
        endpoint_url=_ENDPOINT,
    )


@sem_minio
async def test_guarda_le_e_remove():
    s = _storage()
    chave = f"doc/{uuid.uuid4()}/2026/08/{uuid.uuid4().hex}"
    conteudo = b"%PDF-1.4 atestado de exemplo"

    await s.guardar(chave=chave, conteudo=conteudo, mime="application/pdf")
    assert await s.ler(chave=chave) == conteudo
    assert await s.remover(chave=chave) is True
    assert await s.ler(chave=chave) is None


@sem_minio
async def test_ler_chave_inexistente_devolve_none():
    """A porta promete `None`, não exceção: o expurgo pode ter passado por ali, e quem
    chama já trata o caso. Deixar o `NoSuchKey` subir viraria erro 500 no download."""
    assert await _storage().ler(chave=f"doc/{uuid.uuid4()}/inexistente") is None


@sem_minio
async def test_remover_o_que_nao_existe_devolve_false():
    """`DeleteObject` responde 204 mesmo para chave inexistente — sozinho ele diria `True`
    sempre. É por isso que o adaptador faz `head` antes: sem isso, o expurgo relataria como
    apagado o que nunca existiu, e a retenção pareceria em dia sem estar."""
    assert await _storage().remover(chave=f"doc/{uuid.uuid4()}/nunca-existiu") is False


@sem_minio
async def test_conteudo_binario_sobrevive_intacto():
    """Bytes de imagem passam por serialização de rede; um byte trocado corrompe a foto."""
    s = _storage()
    chave = f"doc/{uuid.uuid4()}/2026/08/{uuid.uuid4().hex}"
    conteudo = bytes(range(256)) * 40  # todos os valores possíveis, inclusive nulos
    await s.guardar(chave=chave, conteudo=conteudo, mime="image/png")
    assert await s.ler(chave=chave) == conteudo
    await s.remover(chave=chave)


@sem_minio
async def test_sobrescrever_a_mesma_chave_mantem_o_ultimo():
    """Reentrega do webhook reprocessa a mesma mídia. No Postgres isso era ON CONFLICT DO
    NOTHING; no S3 o PUT sobrescreve — e como o conteúdo é o mesmo arquivo, tanto faz."""
    s = _storage()
    chave = f"doc/{uuid.uuid4()}/2026/08/{uuid.uuid4().hex}"
    await s.guardar(chave=chave, conteudo=b"primeiro", mime="text/plain")
    await s.guardar(chave=chave, conteudo=b"segundo", mime="text/plain")
    assert await s.ler(chave=chave) == b"segundo"
    await s.remover(chave=chave)


# --------------------------------------------------------------------------- #
# A fábrica — roda sempre, não depende do MinIO
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "pedido, bucket, esperado",
    [
        ("postgres", "", "postgres"),
        ("postgres", "algum-bucket", "postgres"),
        # O caso perigoso: pediu s3, não deu bucket. Cai no Postgres — e o boot grita.
        ("s3", "", "postgres"),
        ("s3", "ti-escolar-docs", "s3"),
    ],
)
def test_storage_efetivo_nao_mente(pedido, bucket, esperado):
    """Espelha `canal_efetivo`, e pela mesma lição: uma env que pede um adaptador e recebe
    outro, em silêncio, foi o que deixou o WhatsApp fora do ar sem ninguém perceber. Aqui o
    preço seria atestado de menor no banco errado."""
    from app.config import Settings
    from app.infrastructure.factories import storage_efetivo

    s = Settings(arquivo_storage=pedido, s3_bucket_documentos=bucket)
    assert storage_efetivo(s) == esperado


def test_chave_leva_o_tenant_e_nada_de_pessoal():
    """O tenant no prefixo dá lifecycle e inventário por escola no S3, e torna a remoção
    de um tenant uma exclusão por prefixo. O UUID não é dado pessoal — nome de aluno ou
    responsável, que apareceria em log, seria."""
    from app.infrastructure.storage import nova_chave

    tenant = uuid.uuid4()
    chave = nova_chave(tenant)
    assert chave.startswith(f"doc/{tenant}/")
    assert len(chave.rsplit("/", 1)[-1]) >= 20  # token imprevisível, não sequencial
    assert nova_chave(tenant) != nova_chave(tenant)
