"""Adaptador S3 de ``ArquivoStorage`` (§6k, Fase 0 do plano de 10/08).

**Por que S3 e não R2**, já que o CLAUDE.md recomendava R2 pelo egress grátis: na escala do
TI-Escolar a diferença é de poucos dólares por mês, e o S3 entrega três coisas que pesam
mais aqui — *lifecycle* nativo como rede de segurança do prazo de retenção, **SSE-KMS com
chave própria** (auditoria por objeto no CloudTrail e a possibilidade de destruir a chave
para inutilizar o acervo) e Object Lock maduro para o dia em que a política de backup sair
do papel. R2 volta a fazer sentido se o egress virar linha de custo real.

**Sem URL pré-assinada, de propósito.** É a tentação óbvia do S3 e vai contra o §6k: uma
presigned URL *é* uma URL pública com prazo, e passaria por fora da autenticação, do escopo
por tenant e da **auditoria de download** — que hoje grava `documento.baixar` a cada acesso.
Os bytes continuam saindo pelo endpoint da API. O custo é pagar egress duas vezes
(S3 → app → navegador), e é um custo aceito conscientemente.

**O boto3 é síncrono**, então cada chamada roda em `asyncio.to_thread`. Sem isso, um upload
de 5 MB travaria o event loop inteiro — e é o mesmo loop que atende o webhook da Meta, que
tem prazo para responder.
"""

from __future__ import annotations

import asyncio
import logging
from functools import lru_cache
from typing import Any

logger = logging.getLogger("storage.s3")


@lru_cache(maxsize=4)
def _cliente(
    *,
    region: str,
    endpoint_url: str,
    access_key: str,
    secret_key: str,
) -> Any:
    """Cliente boto3 memorizado por configuração.

    Criar um cliente custa carregar o modelo de serviço do botocore (dezenas de ms) e
    abrir um pool de conexões; fazer isso por requisição jogaria fora o keep-alive
    justamente no caminho do upload. Clientes boto3 são seguros para uso concorrente.
    """
    import boto3

    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint_url or None,
        aws_access_key_id=access_key or None,
        aws_secret_access_key=secret_key or None,
    )


class S3ArquivoStorage:
    """Bytes num bucket S3; os metadados seguem no Postgres.

    **A atomicidade acabou, e isso é do desenho, não um descuido.** O
    `PostgresArquivoStorage` recebia a sessão da requisição, então bytes e metadado entravam
    na mesma transação: ou os dois existiam ou nenhum. Aqui são sistemas diferentes. A ordem
    é obrigatória — **grava no S3 e só depois commita o metadado** —, porque o inverso
    deixaria `documentos_recebidos` apontando para um objeto inexistente: a secretaria veria
    "documento recebido" e o download daria 404, que é o pior dos dois erros.

    Sobra o caso oposto: objeto no S3 cujo metadado não commitou. Não vaza (a chave é
    imprevisível e o bucket é fechado), mas acumula — é lixo a ser varrido comparando o
    `ListObjectsV2` com `documentos_recebidos.chave_storage`.
    """

    def __init__(
        self,
        *,
        bucket: str,
        region: str,
        access_key: str = "",
        secret_key: str = "",
        endpoint_url: str = "",
        kms_key_id: str = "",
    ) -> None:
        self._bucket = bucket
        self._kms_key_id = kms_key_id
        self._s3 = _cliente(
            region=region,
            endpoint_url=endpoint_url,
            access_key=access_key,
            secret_key=secret_key,
        )

    async def guardar(self, *, chave: str, conteudo: bytes, mime: str) -> None:
        extra: dict[str, Any] = {}
        if self._kms_key_id:
            extra["ServerSideEncryption"] = "aws:kms"
            extra["SSEKMSKeyId"] = self._kms_key_id
        await asyncio.to_thread(
            self._s3.put_object,
            Bucket=self._bucket,
            Key=chave,
            Body=conteudo,
            ContentType=mime or "application/octet-stream",
            **extra,
        )

    async def ler(self, *, chave: str) -> bytes | None:
        def _ler() -> bytes | None:
            try:
                resposta = self._s3.get_object(Bucket=self._bucket, Key=chave)
            except self._s3.exceptions.NoSuchKey:
                # Chave inexistente é resposta normal, não erro: o expurgo pode ter passado
                # por ali. A porta promete `None`, e quem chama já trata.
                return None
            return resposta["Body"].read()

        return await asyncio.to_thread(_ler)

    async def remover(self, *, chave: str) -> bool:
        def _remover() -> bool:
            # `DeleteObject` é idempotente e responde 204 mesmo para chave inexistente, então
            # ele sozinho não sabe dizer se havia algo. O `head` antes é o que mantém honesto
            # o booleano da porta — e o que evita o expurgo relatar como apagado o que nunca
            # existiu. Custa uma chamada a mais numa rotina que roda raramente.
            try:
                self._s3.head_object(Bucket=self._bucket, Key=chave)
            except Exception:  # noqa: BLE001 — 404 e afins: não havia o que remover
                return False
            self._s3.delete_object(Bucket=self._bucket, Key=chave)
            return True

        return await asyncio.to_thread(_remover)
