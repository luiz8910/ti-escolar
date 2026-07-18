"""Casos de uso da matrícula self-service pelo WhatsApp (§E1).

O responsável inicia a matrícula pelo WhatsApp: o bot envia a **lista de documentos**
(reusa os "atalhos" de inscrição da secretaria), o responsável anexa fotos/scan e a
secretaria imprime apenas para a **assinatura presencial**. Reduz o "pai vem só pra
assinar". Sem framework/ORM/SDK.
"""

from __future__ import annotations

from uuid import UUID

from app.domain.entities import (
    DOCUMENTOS_MATRICULA_EXIGIDOS,
    DocumentoMatricula,
    SolicitacaoMatricula,
    StatusMatricula,
    _now,
)
from app.domain.ports import SolicitacaoMatriculaRepository


def montar_mensagem_documentos(nome_responsavel: str = "") -> str:
    """Texto de boas-vindas + lista de documentos exigidos para a matrícula."""
    saudacao = f"Olá, {nome_responsavel}! " if nome_responsavel.strip() else "Olá! "
    itens = "\n".join(f"• {doc}" for doc in DOCUMENTOS_MATRICULA_EXIGIDOS)
    return (
        f"{saudacao}Vamos iniciar a matrícula. Por gentileza, envie fotos ou PDF dos "
        f"seguintes documentos:\n\n{itens}\n\n"
        "Você pode enviar aos poucos. Ao final, a secretaria confere tudo e chama você "
        "apenas para a assinatura presencial."
    )


class IniciarMatricula:
    """Abre (ou retoma) a solicitação de matrícula de um responsável pelo WhatsApp."""

    def __init__(self, *, matriculas: SolicitacaoMatriculaRepository) -> None:
        self._matriculas = matriculas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        contato_telefone: str,
        nome_responsavel: str = "",
        nome_aluno: str = "",
    ) -> SolicitacaoMatricula:
        telefone = (contato_telefone or "").strip()
        if not telefone:
            raise ValueError("Informe o telefone (WhatsApp) do responsável.")

        # Idempotente: retoma a solicitação em aberto do mesmo responsável, se houver.
        existente = await self._matriculas.por_telefone(
            tenant_id=tenant_id, telefone=telefone
        )
        if existente is not None:
            return existente

        return await self._matriculas.criar(
            SolicitacaoMatricula(
                tenant_id=tenant_id,
                contato_telefone=telefone,
                nome_responsavel=nome_responsavel.strip(),
                nome_aluno=nome_aluno.strip(),
            )
        )


class AnexarDocumentoMatricula:
    """Registra um documento enviado pelo responsável na solicitação de matrícula."""

    def __init__(self, *, matriculas: SolicitacaoMatriculaRepository) -> None:
        self._matriculas = matriculas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        solicitacao_id: UUID,
        nome: str,
        url: str = "",
    ) -> SolicitacaoMatricula:
        nome = (nome or "").strip()
        if not nome:
            raise ValueError("Informe o nome do documento enviado.")

        solicitacao = await self._matriculas.obter(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
        if solicitacao is None:
            raise ValueError("Solicitação de matrícula não encontrada para o tenant.")
        if solicitacao.status == StatusMatricula.CANCELADA:
            raise ValueError("A solicitação de matrícula está cancelada.")

        solicitacao.documentos.append(DocumentoMatricula(nome=nome, url=url.strip()))
        if solicitacao.status == StatusMatricula.INICIADA:
            solicitacao.status = StatusMatricula.DOCUMENTOS_ENVIADOS
        solicitacao.atualizado_em = _now()
        return await self._matriculas.atualizar(solicitacao)


class ListarMatriculas:
    """Lista as solicitações de matrícula do tenant (opcionalmente por status)."""

    def __init__(self, *, matriculas: SolicitacaoMatriculaRepository) -> None:
        self._matriculas = matriculas

    async def executar(
        self, *, tenant_id: UUID, status: StatusMatricula | None = None
    ) -> list[SolicitacaoMatricula]:
        return await self._matriculas.listar(tenant_id=tenant_id, status=status)


class AtualizarStatusMatricula:
    """A secretaria avança/encerra a solicitação (em análise, concluída, cancelada)."""

    def __init__(self, *, matriculas: SolicitacaoMatriculaRepository) -> None:
        self._matriculas = matriculas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        solicitacao_id: UUID,
        status: StatusMatricula,
        observacao: str | None = None,
    ) -> SolicitacaoMatricula:
        solicitacao = await self._matriculas.obter(
            tenant_id=tenant_id, solicitacao_id=solicitacao_id
        )
        if solicitacao is None:
            raise ValueError("Solicitação de matrícula não encontrada para o tenant.")
        solicitacao.status = status
        if observacao is not None:
            solicitacao.observacao = observacao.strip()
        solicitacao.atualizado_em = _now()
        return await self._matriculas.atualizar(solicitacao)
