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

from app.domain.entities import (
    ResponsavelInativado,
    ResultadoPromocao,
    ResultadoSincronizacao,
)
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

    def __init__(
        self,
        *,
        alunos: AlunoRepository,
        salas: SalaRepository,
        contatos: ContatoRepository | None = None,
    ) -> None:
        self._alunos = alunos
        self._salas = salas
        self._contatos = contatos

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
        # A virada de ano é **o** momento em que famílias inteiras deixam de ter aluno na
        # escola. Sincronizar aqui, na mesma operação, é o que tira a inativação da
        # dependência de alguém lembrar de clicar num botão (apontamento de 10/08). Um cron
        # diário estaria, 364 dias por ano, recalculando nada.
        if self._contatos is not None:
            await SincronizarSituacaoDosResponsaveis(
                alunos=self._alunos, contatos=self._contatos
            ).executar(tenant_id=tenant_id)
        return resultados


class SincronizarSituacaoDosResponsaveis:
    """Alinha o ``ativo`` dos responsáveis com a situação dos alunos deles (§F1).

    Duas regras, simétricas:

    - **inativa** quem tem alunos vinculados e **todos** já são ex-alunos;
    - **reativa** quem está inativo e voltou a ter **algum** aluno ativo.

    A reativação não é enfeite: sem ela a automação viraria uma armadilha. Desativar o
    aluno inativa a família; a rematrícula (``ReativarAluno``) devolveria o aluno e
    deixaria os responsáveis inativos — parando de receber aviso da escola sem ninguém
    perceber. É seguro fazê-lo porque ``Contato.ativo`` **só é mexido por este caso de
    uso**: não há desativação manual de responsável no painel.

    Responsáveis **sem nenhum aluno vinculado são preservados** — podem ser cadastros
    novos, ou de outra finalidade. Idempotente: quem já está no estado certo é ignorado.

    ``contato_ids`` recorta o trabalho. A virada de ano roda sobre a escola inteira; a
    desativação de **um** aluno só precisa olhar os responsáveis dele, e varrer a escola a
    cada clique seria pagar caro por nada.
    """

    def __init__(self, *, alunos: AlunoRepository, contatos: ContatoRepository) -> None:
        self._alunos = alunos
        self._contatos = contatos

    async def executar(
        self, *, tenant_id: UUID, contato_ids: Sequence[UUID] | None = None
    ) -> ResultadoSincronizacao:
        alvo = set(contato_ids) if contato_ids is not None else None
        alunos = await self._alunos.listar(tenant_id=tenant_id)
        # Mapa contato_id → [alunos] a partir dos responsáveis de cada aluno.
        por_contato: dict[UUID, list] = {}
        for aluno in alunos:
            for responsavel in aluno.responsaveis:
                por_contato.setdefault(responsavel.id, []).append(aluno)

        inativados: list[ResponsavelInativado] = []
        reativados: list[ResponsavelInativado] = []
        for contato in await self._contatos.listar(tenant_id=tenant_id):
            if alvo is not None and contato.id not in alvo:
                continue
            alunos_do_contato = por_contato.get(contato.id, [])
            if not alunos_do_contato:
                continue  # sem alunos vinculados: não mexe
            tem_ativo = any(a.ativo for a in alunos_do_contato)
            if contato.ativo and not tem_ativo:
                contato.ativo = False
                await self._contatos.atualizar(contato)
                inativados.append(_resumo(contato))
            elif not contato.ativo and tem_ativo:
                contato.ativo = True
                await self._contatos.atualizar(contato)
                reativados.append(_resumo(contato))
        return ResultadoSincronizacao(inativados=inativados, reativados=reativados)


def _resumo(contato) -> ResponsavelInativado:
    return ResponsavelInativado(
        contato_id=contato.id, nome=contato.nome, telefone=contato.telefone
    )
