"""Rotas da progressão de série e do ciclo de vida do responsável (§F1).

Escopadas por tenant e protegidas pela autenticação por JWT do módulo ``admin``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.progressao_use_cases import (
    PromoverTurmas,
    SincronizarSituacaoDosResponsaveis,
)
from app.domain.entities import Usuario
from app.infrastructure.db.repositories_admin import (
    SqlAlunoRepository,
    SqlContatoRepository,
    SqlSalaRepository,
)
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import get_aluno_repo, get_contato_repo, get_sala_repo
from app.interfaces.dto import (
    InativarResponsaveisEntrada,
    PromoverTurmasEntrada,
    ResponsavelInativadoSaida,
    SincronizacaoResponsaveisSaida,
    ResultadoPromocaoSaida,
)

router = APIRouter(prefix="/api/admin/progressao", tags=["progressao"])


@router.post("/promover", response_model=list[ResultadoPromocaoSaida])
async def promover_turmas(
    payload: PromoverTurmasEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
    salas: SqlSalaRepository = Depends(get_sala_repo),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> list[ResultadoPromocaoSaida]:
    """Promove os alunos das séries (origem → destino; destino nulo = última série).

    A sincronização da situação dos responsáveis roda **junto**, na mesma operação: a
    virada de ano é o momento em que famílias inteiras deixam de ter aluno na escola, e
    era isso que dependia de alguém lembrar de clicar no botão abaixo.
    """
    _exige_acesso_tenant(usuario, payload.tenant_id)
    promocoes = [(p.origem_sala_id, p.destino_sala_id) for p in payload.promocoes]
    try:
        resultados = await PromoverTurmas(
            alunos=alunos, salas=salas, contatos=contatos
        ).executar(tenant_id=payload.tenant_id, promocoes=promocoes)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return [
        ResultadoPromocaoSaida(
            origem_sala_id=r.origem_sala_id,
            origem_sala_nome=r.origem_sala_nome,
            destino_sala_id=r.destino_sala_id,
            destino_sala_nome=r.destino_sala_nome,
            alunos_promovidos=r.alunos_promovidos,
            alunos_formados=r.alunos_formados,
        )
        for r in resultados
    ]


@router.post("/inativar-responsaveis", response_model=SincronizacaoResponsaveisSaida)
async def inativar_responsaveis(
    payload: InativarResponsaveisEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> SincronizacaoResponsaveisSaida:
    """Alinha a situação dos responsáveis com a dos alunos, na escola inteira.

    Desde 12/ago/2026 isto acontece **sozinho** na promoção de turmas e ao desativar ou
    reativar um aluno. A rota permanece como **reprocessamento**: serve para conferir a
    escola inteira depois de uma importação em massa ou de um ajuste feito no banco.

    A URL manteve o nome ``inativar-responsaveis`` por compatibilidade, mas a operação é
    bidirecional — ver ``SincronizarSituacaoDosResponsaveis``.
    """
    _exige_acesso_tenant(usuario, payload.tenant_id)
    resultado = await SincronizarSituacaoDosResponsaveis(
        alunos=alunos, contatos=contatos
    ).executar(tenant_id=payload.tenant_id)
    saida = lambda r: ResponsavelInativadoSaida(  # noqa: E731
        contato_id=r.contato_id, nome=r.nome, telefone=r.telefone
    )
    return SincronizacaoResponsaveisSaida(
        inativados=[saida(r) for r in resultado.inativados],
        reativados=[saida(r) for r in resultado.reativados],
    )
