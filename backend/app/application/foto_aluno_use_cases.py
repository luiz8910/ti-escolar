"""Foto do aluno: guardar, ler e remover (Fase 2 do plano de 10/08).

**A foto é opcional** (decisão D). Foto de criança eleva o risco LGPD e um campo
obrigatório travaria o cadastro de quem não a tem no dia da matrícula.

Reusa a porta ``ArquivoStorage`` dos documentos recebidos (§6k): os bytes não moram no
cadastro do aluno — ``Aluno.foto_chave`` guarda só a referência. É a mesma separação
entre negócio e infraestrutura que permite trocar o armazenamento sem tocar em ``alunos``.

As mesmas duas defesas do §6k, com a régua mais apertada: allowlist de MIME (só imagem) e
teto de tamanho. Aqui o upload é autenticado — não é o inbound público —, mas um
formulário de painel também aceita o que mandarem nele.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import MIMES_FOTO, TAMANHO_MAXIMO_FOTO, Aluno, ArquivoBaixado
from app.domain.ports import AlunoRepository, ArquivoStorage
from app.infrastructure.storage import nova_chave


class DefinirFotoDoAluno:
    """Guarda (ou troca) a foto de um aluno.

    Troca **apaga a anterior**: manter a foto antiga no storage seria guardar imagem de
    criança que ninguém mais referencia — dado pessoal sem finalidade, que é exatamente o
    que a LGPD chama de tratamento indevido.
    """

    def __init__(self, *, alunos: AlunoRepository, storage: ArquivoStorage) -> None:
        self._alunos = alunos
        self._storage = storage

    async def executar(
        self, *, tenant_id: UUID, aluno_id: UUID, conteudo: bytes, mime: str
    ) -> Aluno:
        if mime not in MIMES_FOTO:
            raise ValueError(
                "A foto precisa ser uma imagem JPEG, PNG ou WebP."
            )
        if not conteudo:
            raise ValueError("Arquivo vazio.")
        if len(conteudo) > TAMANHO_MAXIMO_FOTO:
            raise ValueError("A foto passa do limite de 5 MB.")

        aluno = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None:
            raise ValueError("Aluno não encontrado para o tenant.")

        anterior = aluno.foto_chave
        chave = nova_chave(f"foto/{tenant_id}")
        await self._storage.guardar(chave=chave, conteudo=conteudo, mime=mime)
        aluno.foto_chave = chave
        salvo = await self._alunos.atualizar(aluno)
        if anterior:
            # Depois de gravar a nova e apontar para ela: falhar aqui deixa um órfão, o
            # que é bem melhor que apagar a antiga e a nova não ter entrado.
            await self._storage.remover(chave=anterior)
        return salvo


class ObterFotoDoAluno:
    """Bytes da foto, para o endpoint autenticado servir. ``None`` = sem foto."""

    def __init__(self, *, alunos: AlunoRepository, storage: ArquivoStorage) -> None:
        self._alunos = alunos
        self._storage = storage

    async def executar(
        self, *, tenant_id: UUID, aluno_id: UUID
    ) -> ArquivoBaixado | None:
        aluno = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None or not aluno.foto_chave:
            return None
        conteudo = await self._storage.ler(chave=aluno.foto_chave)
        if conteudo is None:
            return None
        # O mime não é guardado no aluno: a tela só precisa exibir, e todo formato da
        # allowlist é imagem. `image/*` genérico bastaria, mas JPEG cobre o caso comum e
        # os navegadores farejam o resto.
        return ArquivoBaixado(
            conteudo=conteudo, mime="image/jpeg", nome=f"foto-{aluno_id}.jpg"
        )


class RemoverFotoDoAluno:
    """Apaga a foto e a referência. É o "sem foto" explícito da secretaria."""

    def __init__(self, *, alunos: AlunoRepository, storage: ArquivoStorage) -> None:
        self._alunos = alunos
        self._storage = storage

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID) -> Aluno:
        aluno = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        if not aluno.foto_chave:
            return aluno
        chave, aluno.foto_chave = aluno.foto_chave, ""
        salvo = await self._alunos.atualizar(aluno)
        await self._storage.remover(chave=chave)
        return salvo
