"""Armazenamento dos arquivos recebidos — implementações de ``ArquivoStorage`` (§6k).

**Estado atual, dito sem rodeio:** o único adaptador de produção é o Postgres (``bytea``).
Ele foi escolhido para começar porque não pede infra nova nem credencial nova, e porque a
alternativa — um bucket S3-compatível — não pode ser implementada às cegas: sem as chaves
para testar contra o serviço real, o adaptador iria para produção sem nunca ter escrito um
byte de verdade.

**Por que isso não pode ficar assim:** o que se guarda aqui é atestado médico de criança e
documento de matrícula, e o Neon cobra por GB. Uma escola em época de matrícula sobe
centenas de fotos; dez escolas fazem isso todo fevereiro.

**Destino decidido: Amazon S3** (Fase 0 de ``docs/plano-correcoes-teste-10-08.md``), bucket
``ti-escolar-190446415519-sa-east-1-an`` em ``sa-east-1`` — mesma região do Fly (``gru``) e
do Neon. Este docstring apontava o **Cloudflare R2**, pelo egress gratuito; a escolha mudou
e o senão fica registrado: a AWS cobra egress, e como o §6k proíbe URL pública **todo
download passa pela API — paga-se saída duas vezes** (S3 → Fly → navegador). Na escala do
TI-Escolar isso é da ordem de poucos dólares ao mês, e o S3 dá em troca três coisas que
pesam mais aqui: **lifecycle** nativo como rede de segurança do prazo de retenção (§6k),
**SSE-KMS** com chave própria — auditoria por objeto e *crypto-shredding* se um dia for
preciso inutilizar o acervo — e **versionamento/Object Lock** maduros para quando a
política de backup sair do papel. R2 volta a fazer sentido se o egress virar linha de
custo real.

**Os buckets existem desde 29/ago/2026** — ``ti-escolar-190446415519-sa-east-1-an``
(produção) e ``ti-escolar-homolog-190446415519-sa-east-1-an`` (homolog), em ``sa-east-1`` e
com configuração idêntica: acesso público bloqueado nas quatro chaves **e também no nível da
conta**, ACLs desligadas (``BucketOwnerEnforced``), política que nega qualquer acesso com
``aws:SecureTransport = false``, e duas regras de lifecycle:
``rede-de-seguranca-doc-395d`` no prefixo ``doc/`` — ``DOCUMENTO_RETENCAO_DIAS`` (365) mais
30 de folga — e ``rede-de-seguranca-impressao-180d`` no ``impressao/``. Elas filtram por
prefixo de propósito: a foto do aluno mora em ``foto/`` e vive enquanto ele estiver
matriculado, e uma regra sem prefixo apagaria a foto de quem está na escola.

Para os documentos, o lifecycle é **rede de segurança, não mecanismo**: ele expira por idade
do objeto, enquanto o ``expira_em`` do §6k é por documento e apaga o metadado junto. Para a
fila de impressão **ainda não é assim** — a solicitação não tem ``expira_em`` nem expurgo de
aplicação, então a regra de 180 dias é hoje o único descarte automático dali, e um pedido
esquecido na fila por meio ano perde o arquivo com a linha intacta. O conserto é dar
``expira_em`` à solicitação; até lá, a folga larga é o que segura.

**Criptografia: SSE-KMS com a chave gerenciada** ``aws/s3``, não com CMK própria — decisão de
29/ago/2026 para não pagar a chave antes de o adaptador existir. É o senão a registrar: sem
CMK não há política de chave própria nem *crypto-shredding*, que foi metade do argumento para
preferir o S3 ao R2. Trocar depois só vale para objetos novos.

**Duas escolhas do bucket que o adaptador não pode desfazer:** acesso público bloqueado nas
quatro chaves (§6k — os bytes saem pelo endpoint autenticado da API, que audita
``documento.baixar``; **nada de URL pré-assinada**, que passaria por fora do escopo por
tenant e da auditoria) e **versionamento desativado de propósito** — com versionamento,
``DeleteObject`` só cria um *delete marker* e o atestado sobreviveria ao expurgo de
``DOCUMENTO_RETENCAO_DIAS``.

**O que ainda falta:** a credencial IAM escopada só nesse ARN, cadastrada nas envs do Render
e da Fly (`docs/pendencias-externas.md` §2), e a migração dos bytes que já estão no ``bytea``.
O adaptador (``storage_s3.py``, extra ``s3`` do ``boto3``) e a fábrica
``criar_arquivo_storage(settings, session)`` escolhendo pelo ``ARQUIVO_STORAGE``
(``postgres`` | ``s3``) já existem — e, enquanto a chave não entrar, ``storage_efetivo``
devolve ``postgres`` e **grita no boot e no `/health`**, porque uma env que pede um adaptador
e recebe outro em silêncio foi o que deixou o WhatsApp fora do ar sem ninguém notar.

``ArquivoStorageMemoria`` cobre teste e execução sem banco.
"""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models import ArquivoArmazenadoORM

logger = logging.getLogger("storage")


def nova_chave(tenant_id: UUID, prefixo: str = "doc") -> str:
    """Chave opaca e imprevisível para um arquivo: ``{prefixo}/{tenant}/{ano}/{mes}/{token}``.

    Nada de nome do responsável ou do aluno na chave: ela aparece em log e em URL, e o
    conteúdo aqui é dado sensível de menor. ``token_urlsafe`` porque um id sequencial
    permitiria varrer os arquivos das outras escolas por tentativa.

    **O prefixo é finalidade + tenant**, e isso não é organização de pasta — é o que
    decide o que a regra de lifecycle do bucket apaga:

    - ``doc/{tenant}`` — documentos dos responsáveis; regra de **395 dias**
    - ``impressao/{tenant}`` — fila de impressão; regra de **180 dias**
    - ``foto/{tenant}`` — foto do aluno; **sem regra**, vive enquanto ele estiver matriculado
    - ``kb/{tenant}`` — fontes da base de conhecimento; **sem regra** (o FAQ não expira)

    Até 30/ago/2026 os documentos e os arquivos de impressão dividiam o prefixo ``doc/``
    sem tenant. A regra de 395 dias criada para os documentos teria apagado também os
    arquivos de impressão — que não têm ``expira_em`` nem expurgo de aplicação —, deixando
    a linha em ``solicitacoes_impressao`` apontando para um objeto inexistente e o download
    devolvendo 404 sem explicação. O tenant no prefixo dá de graça o inventário por escola
    e transforma a remoção de um tenant em exclusão por prefixo.

    A finalidade e o tenant são **parâmetros separados** de propósito: montar o prefixo
    na mão no chamador (``nova_chave(f"doc/{tenant}")``) deixa a finalidade errada passar
    sem erro, e o sintoma só aparece meses depois, quando o lifecycle apaga o arquivo da
    fila de impressão junto com os documentos.
    """
    return (
        f"{prefixo}/{tenant_id}/{datetime.now(timezone.utc):%Y/%m}/"
        f"{secrets.token_urlsafe(24)}"
    )


class PostgresArquivoStorage:
    """Bytes em ``arquivos_armazenados`` (``bytea``), na sessão da requisição."""

    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def guardar(self, *, chave: str, conteudo: bytes, mime: str) -> None:
        # ON CONFLICT: reentrega do webhook pode reprocessar a mesma mídia, e falhar por
        # chave duplicada perderia o documento em vez de aproveitá-lo.
        stmt = (
            insert(ArquivoArmazenadoORM)
            .values(
                chave=chave,
                conteudo=conteudo,
                mime=mime,
                tamanho=len(conteudo),
                criado_em=datetime.now(timezone.utc),
            )
            .on_conflict_do_nothing(index_elements=["chave"])
        )
        await self._s.execute(stmt)
        await self._s.flush()

    async def ler(self, *, chave: str) -> bytes | None:
        stmt = select(ArquivoArmazenadoORM.conteudo).where(
            ArquivoArmazenadoORM.chave == chave
        )
        return (await self._s.execute(stmt)).scalar_one_or_none()

    async def remover(self, *, chave: str) -> bool:
        resultado = await self._s.execute(
            delete(ArquivoArmazenadoORM).where(ArquivoArmazenadoORM.chave == chave)
        )
        await self._s.flush()
        return bool(resultado.rowcount)

    async def listar_chaves(
        self, *, prefixo: str = "", criado_antes_de: datetime, limite: int = 500
    ) -> list[str]:
        stmt = (
            select(ArquivoArmazenadoORM.chave)
            .where(ArquivoArmazenadoORM.criado_em < criado_antes_de)
            .order_by(ArquivoArmazenadoORM.criado_em)
            .limit(limite)
        )
        if prefixo:
            # `like` com o prefixo literal: a chave é gerada por `nova_chave`, então não
            # há curinga de usuário entrando aqui.
            stmt = stmt.where(ArquivoArmazenadoORM.chave.like(f"{prefixo}%"))
        return list((await self._s.execute(stmt)).scalars().all())


class ArquivoStorageMemoria:
    """Armazenamento em memória — testes e execução local sem banco."""

    def __init__(self) -> None:
        self.arquivos: dict[str, tuple[bytes, str]] = {}
        # Carimbo de quando cada chave entrou, para o corte por idade de `listar_chaves`.
        # Os testes ajustam este dicionário para simular um arquivo antigo.
        self.criado_em: dict[str, datetime] = {}

    async def guardar(self, *, chave: str, conteudo: bytes, mime: str) -> None:
        self.arquivos[chave] = (conteudo, mime)
        self.criado_em.setdefault(chave, datetime.now(timezone.utc))

    async def ler(self, *, chave: str) -> bytes | None:
        item = self.arquivos.get(chave)
        return item[0] if item else None

    async def remover(self, *, chave: str) -> bool:
        self.criado_em.pop(chave, None)
        return self.arquivos.pop(chave, None) is not None

    async def listar_chaves(
        self, *, prefixo: str = "", criado_antes_de: datetime, limite: int = 500
    ) -> list[str]:
        chaves = [
            chave
            for chave in self.arquivos
            if chave.startswith(prefixo)
            and self.criado_em.get(chave, datetime.now(timezone.utc)) < criado_antes_de
        ]
        chaves.sort(key=lambda c: self.criado_em.get(c, datetime.now(timezone.utc)))
        return chaves[:limite]
