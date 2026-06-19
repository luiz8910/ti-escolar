"""Casos de uso de cadastro escolar: pais/responsáveis (CRUD), salas (CRUD),
vínculo pai↔sala e relatório de pais por sala.

A camada de aplicação apenas orquestra as portas ``ContatoRepository`` e
``SalaRepository``; nenhuma dependência de framework ou ORM.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.domain.entities import Aluno, Contato, Sala
from app.domain.ports import AlunoRepository, ContatoRepository, SalaRepository


# --------------------------------------------------------------------------- #
# Pais / responsáveis (CRUD)
# --------------------------------------------------------------------------- #
class CadastrarPai:
    """Cadastra um pai/responsável e, opcionalmente, já o vincula a salas.

    O telefone é único por tenant (E.164). Vincular a salas na criação atende ao
    fluxo "cadastrar o pai e relacionar com uma sala" em uma única ação.
    """

    def __init__(self, *, contatos: ContatoRepository, salas: SalaRepository) -> None:
        self._contatos = contatos
        self._salas = salas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        nome: str,
        telefone: str,
        sala_ids: Sequence[UUID] = (),
    ) -> Contato:
        if await self._contatos.por_telefone(tenant_id=tenant_id, telefone=telefone):
            raise ValueError("Já existe um responsável com este telefone neste tenant.")

        contato = await self._contatos.criar(
            Contato(tenant_id=tenant_id, nome=nome, telefone=telefone)
        )
        for sala_id in sala_ids:
            await self._salas.vincular_pai(
                tenant_id=tenant_id, sala_id=sala_id, contato_id=contato.id
            )
        return contato


class ListarPais:
    def __init__(self, *, contatos: ContatoRepository) -> None:
        self._contatos = contatos

    async def executar(self, *, tenant_id: UUID) -> list[Contato]:
        return await self._contatos.listar(tenant_id=tenant_id)


class AtualizarPai:
    def __init__(self, *, contatos: ContatoRepository) -> None:
        self._contatos = contatos

    async def executar(
        self, *, tenant_id: UUID, contato_id: UUID, nome: str, telefone: str
    ) -> Contato:
        atual = await self._contatos.obter(tenant_id=tenant_id, contato_id=contato_id)
        if atual is None:
            raise ValueError("Responsável não encontrado para o tenant.")

        # Telefone só pode mudar para um valor ainda não usado por outro responsável.
        if telefone != atual.telefone:
            existente = await self._contatos.por_telefone(tenant_id=tenant_id, telefone=telefone)
            if existente is not None and existente.id != contato_id:
                raise ValueError("Já existe um responsável com este telefone neste tenant.")

        atual.nome = nome
        atual.telefone = telefone
        return await self._contatos.atualizar(atual)


class RemoverPai:
    def __init__(self, *, contatos: ContatoRepository) -> None:
        self._contatos = contatos

    async def executar(self, *, tenant_id: UUID, contato_id: UUID) -> bool:
        return await self._contatos.remover(tenant_id=tenant_id, contato_id=contato_id)


# --------------------------------------------------------------------------- #
# Salas / turmas (CRUD)
# --------------------------------------------------------------------------- #
class CriarSala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, nome: str, descricao: str = "") -> Sala:
        return await self._salas.criar(Sala(tenant_id=tenant_id, nome=nome, descricao=descricao))


class ListarSalas:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID) -> list[Sala]:
        return await self._salas.listar(tenant_id=tenant_id)


class ObterSala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID) -> Sala:
        sala = await self._salas.obter(tenant_id=tenant_id, sala_id=sala_id)
        if sala is None:
            raise ValueError("Sala não encontrada para o tenant.")
        return sala


class AtualizarSala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(
        self, *, tenant_id: UUID, sala_id: UUID, nome: str, descricao: str = ""
    ) -> Sala:
        return await self._salas.atualizar(
            tenant_id=tenant_id, sala_id=sala_id, nome=nome, descricao=descricao
        )


class RemoverSala:
    """Remove uma série/sala decidindo o destino dos alunos.

    Como ``Aluno.sala_id`` é obrigatório, a exclusão precisa de uma estratégia explícita:
    - ``mover_para=None`` → **exclui** os alunos da série junto com ela;
    - ``mover_para=<sala_id>`` → **transfere** os alunos para outra série e então remove a
      série original. A série destino deve existir no tenant e ser diferente da removida
      (crie-a antes, se necessário, via ``CriarSala``).
    """

    def __init__(self, *, salas: SalaRepository, alunos: AlunoRepository) -> None:
        self._salas = salas
        self._alunos = alunos

    async def executar(
        self, *, tenant_id: UUID, sala_id: UUID, mover_para: UUID | None = None
    ) -> bool:
        sala = await self._salas.obter(tenant_id=tenant_id, sala_id=sala_id)
        if sala is None:
            return False

        alunos_da_sala = await self._alunos.listar(tenant_id=tenant_id, sala_id=sala_id)
        if mover_para is not None:
            if mover_para == sala_id:
                raise ValueError("A série destino deve ser diferente da que está sendo removida.")
            await _validar_sala(self._salas, tenant_id=tenant_id, sala_id=mover_para)
            for aluno in alunos_da_sala:
                aluno.sala_id = mover_para
                await self._alunos.atualizar(aluno)
        else:
            for aluno in alunos_da_sala:
                await self._alunos.remover(tenant_id=tenant_id, aluno_id=aluno.id)

        return await self._salas.remover(tenant_id=tenant_id, sala_id=sala_id)


# --------------------------------------------------------------------------- #
# Vínculo pai ↔ sala e relatório
# --------------------------------------------------------------------------- #
class VincularPaiASala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID, contato_id: UUID) -> None:
        await self._salas.vincular_pai(
            tenant_id=tenant_id, sala_id=sala_id, contato_id=contato_id
        )


class DesvincularPaiDaSala:
    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID, contato_id: UUID) -> None:
        await self._salas.desvincular_pai(
            tenant_id=tenant_id, sala_id=sala_id, contato_id=contato_id
        )


class RelatorioPaisDaSala:
    """Lista (relatório) dos pais/responsáveis vinculados a uma sala específica."""

    def __init__(self, *, salas: SalaRepository) -> None:
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, sala_id: UUID) -> list[Contato]:
        return await self._salas.pais(tenant_id=tenant_id, sala_id=sala_id)


# --------------------------------------------------------------------------- #
# Alunos (CRUD + vínculo com responsáveis e série)
# --------------------------------------------------------------------------- #
async def _validar_sala(salas: SalaRepository, *, tenant_id: UUID, sala_id: UUID) -> None:
    """Garante que a série/sala informada pertence ao tenant."""
    if await salas.obter(tenant_id=tenant_id, sala_id=sala_id) is None:
        raise ValueError("Série/sala não encontrada para o tenant.")


class CadastrarAluno:
    """Cadastra um aluno, opcionalmente já com série e responsáveis vinculados."""

    def __init__(self, *, alunos: AlunoRepository, salas: SalaRepository) -> None:
        self._alunos = alunos
        self._salas = salas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        nome: str,
        sala_id: UUID,
        matricula: str = "",
        responsavel_ids: Sequence[UUID] = (),
    ) -> Aluno:
        await _validar_sala(self._salas, tenant_id=tenant_id, sala_id=sala_id)
        aluno = await self._alunos.criar(
            Aluno(tenant_id=tenant_id, nome=nome, sala_id=sala_id, matricula=matricula)
        )
        for contato_id in responsavel_ids:
            await self._alunos.vincular_responsavel(
                tenant_id=tenant_id, aluno_id=aluno.id, contato_id=contato_id
            )
        return await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno.id)


class ListarAlunos:
    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(
        self, *, tenant_id: UUID, sala_id: UUID | None = None
    ) -> list[Aluno]:
        return await self._alunos.listar(tenant_id=tenant_id, sala_id=sala_id)


class ObterAluno:
    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID) -> Aluno:
        aluno = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        return aluno


class AtualizarAluno:
    def __init__(self, *, alunos: AlunoRepository, salas: SalaRepository) -> None:
        self._alunos = alunos
        self._salas = salas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        aluno_id: UUID,
        nome: str,
        sala_id: UUID,
        matricula: str = "",
        ativo: bool = True,
    ) -> Aluno:
        atual = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if atual is None:
            raise ValueError("Aluno não encontrado para o tenant.")
        await _validar_sala(self._salas, tenant_id=tenant_id, sala_id=sala_id)
        atual.nome = nome
        atual.sala_id = sala_id
        atual.matricula = matricula
        atual.ativo = ativo
        return await self._alunos.atualizar(atual)


class RemoverAluno:
    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID) -> bool:
        return await self._alunos.remover(tenant_id=tenant_id, aluno_id=aluno_id)


class VincularResponsavelAoAluno:
    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID, contato_id: UUID) -> None:
        await self._alunos.vincular_responsavel(
            tenant_id=tenant_id, aluno_id=aluno_id, contato_id=contato_id
        )


class DesvincularResponsavelDoAluno:
    def __init__(self, *, alunos: AlunoRepository) -> None:
        self._alunos = alunos

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID, contato_id: UUID) -> None:
        await self._alunos.desvincular_responsavel(
            tenant_id=tenant_id, aluno_id=aluno_id, contato_id=contato_id
        )
