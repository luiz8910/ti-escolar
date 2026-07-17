"""Casos de uso da progressão de série e do ciclo de vida do responsável (§F1).

Virada de ano: promover os alunos de uma série para a seguinte (ou marcá-los como
ex-alunos na última série) e, em seguida, **inativar os responsáveis que não têm mais
nenhum aluno ativo**. Elimina o retrabalho de "desfazer o contato de cada criança".
A camada de aplicação orquestra ``AlunoRepository``, ``SalaRepository`` e
``ContatoRepository``; sem framework/ORM/SDK.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from app.domain.entities import ResponsavelInativado, ResultadoPromocao
from app.domain.ports import AlunoRepository, ContatoRepository, SalaRepository


async def _obter_sala(salas: SalaRepository, *, tenant_id: UUID, sala_id: UUID):
    sala = await salas.obter(tenant_id=tenant_id, sala_id=sala_id)
    if sala is None:
        raise ValueError("Série/sala não encontrada para o tenant.")
    return sala


class PromoverSerie:
    """Promove os alunos **ativos** de uma série.

    - ``destino_sala_id`` informado → transfere os alunos ativos para a série seguinte;
    - ``destino_sala_id=None`` → **última série**: marca os alunos como ex-alunos
      (``ativo=False``), mantendo-os na própria série para histórico.

    Ex-alunos já existentes na origem são ignorados. A série destino é validada no tenant
    e deve ser diferente da origem.
    """

    def __init__(self, *, alunos: AlunoRepository, salas: SalaRepository) -> None:
        self._alunos = alunos
        self._salas = salas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        origem_sala_id: UUID,
        destino_sala_id: UUID | None = None,
    ) -> ResultadoPromocao:
        origem = await _obter_sala(self._salas, tenant_id=tenant_id, sala_id=origem_sala_id)
        destino = None
        if destino_sala_id is not None:
            if destino_sala_id == origem_sala_id:
                raise ValueError("A série destino deve ser diferente da série de origem.")
            destino = await _obter_sala(
                self._salas, tenant_id=tenant_id, sala_id=destino_sala_id
            )

        alunos = await self._alunos.listar(tenant_id=tenant_id, sala_id=origem_sala_id)
        ativos = [a for a in alunos if a.ativo]

        promovidos = 0
        formados = 0
        for aluno in ativos:
            if destino is not None:
                aluno.sala_id = destino.id
                aluno.sala_nome = destino.nome
                promovidos += 1
            else:
                aluno.ativo = False
                formados += 1
            await self._alunos.atualizar(aluno)

        return ResultadoPromocao(
            origem_sala_id=origem.id,
            origem_sala_nome=origem.nome,
            destino_sala_id=destino.id if destino else None,
            destino_sala_nome=destino.nome if destino else "",
            alunos_promovidos=promovidos,
            alunos_formados=formados,
        )


class PromoverTurmas:
    """Aplica um lote de promoções (mapa origem → destino) na virada de ano.

    Cada item é ``(origem_sala_id, destino_sala_id | None)``. Devolve um resultado por
    série processada.
    """

    def __init__(self, *, alunos: AlunoRepository, salas: SalaRepository) -> None:
        self._alunos = alunos
        self._salas = salas

    async def executar(
        self,
        *,
        tenant_id: UUID,
        promocoes: Sequence[tuple[UUID, UUID | None]],
    ) -> list[ResultadoPromocao]:
        promover = PromoverSerie(alunos=self._alunos, salas=self._salas)
        resultados: list[ResultadoPromocao] = []
        for origem_sala_id, destino_sala_id in promocoes:
            resultados.append(
                await promover.executar(
                    tenant_id=tenant_id,
                    origem_sala_id=origem_sala_id,
                    destino_sala_id=destino_sala_id,
                )
            )
        return resultados


class InativarResponsaveisSemAlunosAtivos:
    """Inativa responsáveis cujos alunos já são **todos** ex-alunos.

    Regra do cliente (§F1): só torna o responsável inativo quando **todos** os seus
    alunos estão inativos. Responsáveis sem nenhum aluno vinculado são preservados
    (podem ser cadastros novos ou de outra finalidade). Idempotente: quem já está
    inativo é ignorado. Devolve os responsáveis efetivamente inativados.
    """

    def __init__(self, *, alunos: AlunoRepository, contatos: ContatoRepository) -> None:
        self._alunos = alunos
        self._contatos = contatos

    async def executar(self, *, tenant_id: UUID) -> list[ResponsavelInativado]:
        alunos = await self._alunos.listar(tenant_id=tenant_id)
        # Mapa contato_id → [alunos] a partir dos responsáveis de cada aluno.
        por_contato: dict[UUID, list] = {}
        for aluno in alunos:
            for responsavel in aluno.responsaveis:
                por_contato.setdefault(responsavel.id, []).append(aluno)

        inativados: list[ResponsavelInativado] = []
        for contato in await self._contatos.listar(tenant_id=tenant_id):
            if not contato.ativo:
                continue
            alunos_do_contato = por_contato.get(contato.id, [])
            if not alunos_do_contato:
                continue  # sem alunos vinculados: não mexe
            if any(a.ativo for a in alunos_do_contato):
                continue  # ainda tem aluno ativo
            contato.ativo = False
            await self._contatos.atualizar(contato)
            inativados.append(
                ResponsavelInativado(
                    contato_id=contato.id, nome=contato.nome, telefone=contato.telefone
                )
            )
        return inativados
