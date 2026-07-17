"""Rotas de cadastro escolar: CRUD de pais/responsáveis e de salas (turmas),
vínculo pai↔sala e relatório de pais por sala.

Reaproveita a autenticação por JWT (``Authorization: Bearer``) e o controle de tenant
do módulo ``admin``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.cadastro_use_cases import (
    AtribuirProfessorASala,
    AtualizarAluno,
    AtualizarPai,
    AtualizarProfessor,
    AtualizarSala,
    CadastrarAluno,
    CadastrarPai,
    CadastrarProfessor,
    CoberturaDeContatosDaSala,
    CriarSala,
    DesvincularPaiDaSala,
    DesvincularResponsavelDoAluno,
    ListarAlunos,
    ListarPais,
    ListarProfessores,
    ListarSalas,
    ListarSeriesDoProfessor,
    NotificarProfessorContatosFaltantes,
    ObterAluno,
    ObterProfessor,
    ObterSala,
    RelatorioPaisDaSala,
    RemoverAluno,
    RemoverPai,
    RemoverProfessor,
    RemoverProfessorDaSala,
    RemoverSala,
    ResumoCoberturaDasSalas,
    VincularPaiASala,
    VincularResponsavelAoAluno,
)
from app.application.importacao_use_cases import (
    ConfirmarImportacaoAlunos,
    PrevisualizarImportacaoAlunos,
)
from app.domain.entities import (
    Aluno,
    CoberturaContatosSala,
    Contato,
    LinhaImportacaoAluno,
    PreviaImportacaoAlunos,
    Professor,
    ResponsavelImportado,
    ResultadoImportacaoAlunos,
    Sala,
    Usuario,
)
from app.domain.ports import LLMProvider, MessageChannel
from app.infrastructure.db.repositories_admin import (
    SqlAlunoRepository,
    SqlContatoRepository,
    SqlProfessorRepository,
    SqlSalaRepository,
)
from app.interfaces.api.admin import _exige_acesso_tenant, usuario_autenticado
from app.interfaces.deps import (
    get_aluno_repo,
    get_canal,
    get_contato_repo,
    get_llm,
    get_professor_repo,
    get_sala_repo,
)
from app.interfaces.dto import (
    AlunoAtualizar,
    AlunoEntrada,
    AlunoResumoSaida,
    AlunoSaida,
    AtribuirProfessorEntrada,
    CoberturaSalaSaida,
    ImportacaoConfirmarEntrada,
    ImportacaoPreviaEntrada,
    ImportacaoPreviaSaida,
    ImportacaoResultadoSaida,
    LinhaImportacaoAlunoDTO,
    NotificarProfessorEntrada,
    NotificarProfessorSaida,
    PaiAtualizar,
    PaiEntrada,
    PaiSaida,
    ProfessorAtualizar,
    ProfessorEntrada,
    ProfessorSaida,
    ResponsavelImportadoDTO,
    SalaAtualizar,
    SalaEntrada,
    SalaSaida,
    VinculoPaiEntrada,
)

router = APIRouter(prefix="/api/admin", tags=["cadastro"])


def _pai_saida(c: Contato) -> PaiSaida:
    return PaiSaida(id=c.id, nome=c.nome, telefone=c.telefone)


def _sala_saida(s: Sala) -> SalaSaida:
    return SalaSaida(
        id=s.id,
        nome=s.nome,
        descricao=s.descricao,
        total_pais=len(s.pais),
        pais=[_pai_saida(c) for c in s.pais],
        professor_id=s.professor_id,
        professor_nome=s.professor_nome,
    )


def _professor_saida(p: Professor) -> ProfessorSaida:
    return ProfessorSaida(
        id=p.id, nome=p.nome, telefone=p.telefone, tem_acesso=p.tem_acesso
    )


def _cobertura_saida(c: CoberturaContatosSala) -> CoberturaSalaSaida:
    return CoberturaSalaSaida(
        sala_id=c.sala_id,
        sala_nome=c.sala_nome,
        total_alunos=c.total_alunos,
        total_sem_contato=c.total_sem_contato,
        alunos_sem_contato=[
            AlunoResumoSaida(id=a.id, nome=a.nome, matricula=a.matricula)
            for a in c.alunos_sem_contato
        ],
    )


def _aluno_saida(a: Aluno) -> AlunoSaida:
    return AlunoSaida(
        id=a.id,
        nome=a.nome,
        matricula=a.matricula,
        ativo=a.ativo,
        sala_id=a.sala_id,
        sala_nome=a.sala_nome,
        responsaveis=[_pai_saida(c) for c in a.responsaveis],
    )


def _linha_importacao_saida(linha: LinhaImportacaoAluno) -> LinhaImportacaoAlunoDTO:
    return LinhaImportacaoAlunoDTO(
        nome=linha.nome,
        serie=linha.serie,
        matricula=linha.matricula,
        responsaveis=[
            ResponsavelImportadoDTO(nome=r.nome, telefone=r.telefone, aviso=r.aviso)
            for r in linha.responsaveis
        ],
        erros=linha.erros,
        avisos=linha.avisos,
        serie_nova=linha.serie_nova,
        valido=linha.valido,
    )


def _previa_importacao_saida(previa: PreviaImportacaoAlunos) -> ImportacaoPreviaSaida:
    return ImportacaoPreviaSaida(
        linhas=[_linha_importacao_saida(linha) for linha in previa.linhas],
        series_existentes=previa.series_existentes,
        series_novas=previa.series_novas,
        total_validos=previa.total_validos,
    )


def _linha_importacao_entrada(dto: LinhaImportacaoAlunoDTO) -> LinhaImportacaoAluno:
    """Reconstrói a linha revisada e **revalida no servidor** (não confia no cliente)."""
    linha = LinhaImportacaoAluno(
        nome=dto.nome.strip(),
        serie=dto.serie.strip(),
        matricula=dto.matricula.strip(),
        responsaveis=[
            ResponsavelImportado(nome=r.nome.strip(), telefone=r.telefone.strip(), aviso=r.aviso)
            for r in dto.responsaveis
        ],
        avisos=list(dto.avisos),
        serie_nova=dto.serie_nova,
    )
    if not linha.nome:
        linha.erros.append("Nome do aluno ausente.")
    if not linha.serie:
        linha.erros.append("Série/turma ausente.")
    return linha


def _resultado_importacao_saida(r: ResultadoImportacaoAlunos) -> ImportacaoResultadoSaida:
    return ImportacaoResultadoSaida(
        criados=r.criados,
        ignorados=r.ignorados,
        series_criadas=r.series_criadas,
        erros=r.erros,
    )


# --------------------------------------------------------------------------- #
# Pais / responsáveis (CRUD)
# --------------------------------------------------------------------------- #
@router.post("/pais", response_model=PaiSaida, status_code=status.HTTP_201_CREATED)
async def cadastrar_pai(
    payload: PaiEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> PaiSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        contato = await CadastrarPai(contatos=contatos, salas=salas).executar(
            tenant_id=payload.tenant_id,
            nome=payload.nome,
            telefone=payload.telefone,
            sala_ids=payload.sala_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _pai_saida(contato)


@router.get("/pais/tenant/{tenant_id}", response_model=list[PaiSaida])
async def listar_pais(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> list[PaiSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    return [_pai_saida(c) for c in await ListarPais(contatos=contatos).executar(tenant_id=tenant_id)]


@router.put("/pais/{contato_id}", response_model=PaiSaida)
async def atualizar_pai(
    contato_id: UUID,
    payload: PaiAtualizar,
    usuario: Usuario = Depends(usuario_autenticado),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> PaiSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        contato = await AtualizarPai(contatos=contatos).executar(
            tenant_id=payload.tenant_id,
            contato_id=contato_id,
            nome=payload.nome,
            telefone=payload.telefone,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _pai_saida(contato)


@router.delete("/pais/{contato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_pai(
    contato_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverPai(contatos=contatos).executar(
        tenant_id=tenant_id, contato_id=contato_id
    )
    if not removido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Responsável não encontrado")


# --------------------------------------------------------------------------- #
# Salas / turmas (CRUD)
# --------------------------------------------------------------------------- #
@router.post("/salas", response_model=SalaSaida, status_code=status.HTTP_201_CREATED)
async def criar_sala(
    payload: SalaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> SalaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    sala = await CriarSala(salas=salas).executar(
        tenant_id=payload.tenant_id, nome=payload.nome, descricao=payload.descricao
    )
    return _sala_saida(sala)


@router.get("/salas/tenant/{tenant_id}", response_model=list[SalaSaida])
async def listar_salas(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> list[SalaSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    return [_sala_saida(s) for s in await ListarSalas(salas=salas).executar(tenant_id=tenant_id)]


@router.get("/salas/{sala_id}", response_model=SalaSaida)
async def obter_sala(
    sala_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> SalaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        sala = await ObterSala(salas=salas).executar(tenant_id=tenant_id, sala_id=sala_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _sala_saida(sala)


@router.put("/salas/{sala_id}", response_model=SalaSaida)
async def atualizar_sala(
    sala_id: UUID,
    payload: SalaAtualizar,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> SalaSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        sala = await AtualizarSala(salas=salas).executar(
            tenant_id=payload.tenant_id,
            sala_id=sala_id,
            nome=payload.nome,
            descricao=payload.descricao,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _sala_saida(sala)


@router.delete("/salas/{sala_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_sala(
    sala_id: UUID,
    tenant_id: UUID,
    mover_para: UUID | None = None,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> None:
    """Remove uma série. Sem ``mover_para``, exclui os alunos da série; com ``mover_para``,
    transfere os alunos para a série indicada antes de remover esta."""
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        removido = await RemoverSala(salas=salas, alunos=alunos).executar(
            tenant_id=tenant_id, sala_id=sala_id, mover_para=mover_para
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if not removido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sala não encontrada")


# --------------------------------------------------------------------------- #
# Vínculo pai ↔ sala e relatório de pais por sala
# --------------------------------------------------------------------------- #
@router.post("/salas/{sala_id}/pais", status_code=status.HTTP_204_NO_CONTENT)
async def vincular_pai(
    sala_id: UUID,
    payload: VinculoPaiEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> None:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        await VincularPaiASala(salas=salas).executar(
            tenant_id=payload.tenant_id, sala_id=sala_id, contato_id=payload.contato_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete("/salas/{sala_id}/pais/{contato_id}", status_code=status.HTTP_204_NO_CONTENT)
async def desvincular_pai(
    sala_id: UUID,
    contato_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        await DesvincularPaiDaSala(salas=salas).executar(
            tenant_id=tenant_id, sala_id=sala_id, contato_id=contato_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get("/salas/{sala_id}/pais", response_model=list[PaiSaida])
async def relatorio_pais_da_sala(
    sala_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> list[PaiSaida]:
    """Relatório/lista dos pais/responsáveis vinculados a uma sala específica."""
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        pais = await RelatorioPaisDaSala(salas=salas).executar(tenant_id=tenant_id, sala_id=sala_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return [_pai_saida(c) for c in pais]


# --------------------------------------------------------------------------- #
# Cobertura de contatos da turma e notificação ao professor
# --------------------------------------------------------------------------- #
@router.get("/salas/tenant/{tenant_id}/cobertura", response_model=list[CoberturaSalaSaida])
async def cobertura_das_salas(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> list[CoberturaSalaSaida]:
    """Cobertura de contatos de todas as turmas: quantos alunos estão sem responsável
    com telefone (WhatsApp) vinculado."""
    _exige_acesso_tenant(usuario, tenant_id)
    coberturas = await ResumoCoberturaDasSalas(salas=salas, alunos=alunos).executar(
        tenant_id=tenant_id
    )
    return [_cobertura_saida(c) for c in coberturas]


@router.get("/salas/{sala_id}/cobertura", response_model=CoberturaSalaSaida)
async def cobertura_da_sala(
    sala_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> CoberturaSalaSaida:
    """Cobertura de contatos de uma turma, com a lista de alunos sem contato."""
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        cobertura = await CoberturaDeContatosDaSala(salas=salas, alunos=alunos).executar(
            tenant_id=tenant_id, sala_id=sala_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _cobertura_saida(cobertura)


@router.post("/salas/{sala_id}/notificar-professor", response_model=NotificarProfessorSaida)
async def notificar_professor(
    sala_id: UUID,
    payload: NotificarProfessorEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
    canal: MessageChannel = Depends(get_canal),
) -> NotificarProfessorSaida:
    """Dispara ao professor um aviso pedindo os contatos de responsáveis faltantes."""
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        cobertura, id_externo = await NotificarProfessorContatosFaltantes(
            salas=salas, alunos=alunos, canal=canal
        ).executar(
            tenant_id=payload.tenant_id,
            sala_id=sala_id,
            telefone_professor=payload.telefone,
            mensagem=payload.mensagem,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return NotificarProfessorSaida(
        enviado=True,
        id_externo=id_externo,
        telefone=payload.telefone,
        total_sem_contato=cobertura.total_sem_contato,
        cobertura=_cobertura_saida(cobertura),
    )


# --------------------------------------------------------------------------- #
# Alunos (CRUD) — responsáveis N:N, série 1:1
# --------------------------------------------------------------------------- #
@router.post("/alunos", response_model=AlunoSaida, status_code=status.HTTP_201_CREATED)
async def cadastrar_aluno(
    payload: AlunoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> AlunoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        aluno = await CadastrarAluno(alunos=alunos, salas=salas).executar(
            tenant_id=payload.tenant_id,
            nome=payload.nome,
            sala_id=payload.sala_id,
            matricula=payload.matricula,
            responsavel_ids=payload.responsavel_ids,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _aluno_saida(aluno)


@router.get("/alunos/tenant/{tenant_id}", response_model=list[AlunoSaida])
async def listar_alunos(
    tenant_id: UUID,
    sala_id: UUID | None = None,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> list[AlunoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    encontrados = await ListarAlunos(alunos=alunos).executar(tenant_id=tenant_id, sala_id=sala_id)
    return [_aluno_saida(a) for a in encontrados]


@router.get("/alunos/{aluno_id}", response_model=AlunoSaida)
async def obter_aluno(
    aluno_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> AlunoSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        aluno = await ObterAluno(alunos=alunos).executar(tenant_id=tenant_id, aluno_id=aluno_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _aluno_saida(aluno)


@router.put("/alunos/{aluno_id}", response_model=AlunoSaida)
async def atualizar_aluno(
    aluno_id: UUID,
    payload: AlunoAtualizar,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> AlunoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        aluno = await AtualizarAluno(alunos=alunos, salas=salas).executar(
            tenant_id=payload.tenant_id,
            aluno_id=aluno_id,
            nome=payload.nome,
            sala_id=payload.sala_id,
            matricula=payload.matricula,
            ativo=payload.ativo,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _aluno_saida(aluno)


@router.delete("/alunos/{aluno_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_aluno(
    aluno_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverAluno(alunos=alunos).executar(tenant_id=tenant_id, aluno_id=aluno_id)
    if not removido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Aluno não encontrado")


@router.post("/alunos/{aluno_id}/responsaveis", status_code=status.HTTP_204_NO_CONTENT)
async def vincular_responsavel(
    aluno_id: UUID,
    payload: VinculoPaiEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> None:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        await VincularResponsavelAoAluno(alunos=alunos).executar(
            tenant_id=payload.tenant_id, aluno_id=aluno_id, contato_id=payload.contato_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.delete(
    "/alunos/{aluno_id}/responsaveis/{contato_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def desvincular_responsavel(
    aluno_id: UUID,
    contato_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        await DesvincularResponsavelDoAluno(alunos=alunos).executar(
            tenant_id=tenant_id, aluno_id=aluno_id, contato_id=contato_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


# --------------------------------------------------------------------------- #
# Professores (CRUD) e atribuição à série (Sala.professor_id)
# --------------------------------------------------------------------------- #
@router.post("/professores", response_model=ProfessorSaida, status_code=status.HTTP_201_CREATED)
async def cadastrar_professor(
    payload: ProfessorEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> ProfessorSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        professor = await CadastrarProfessor(professores=professores).executar(
            tenant_id=payload.tenant_id,
            nome=payload.nome,
            telefone=payload.telefone,
            senha=payload.senha,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _professor_saida(professor)


@router.get("/professores/tenant/{tenant_id}", response_model=list[ProfessorSaida])
async def listar_professores(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> list[ProfessorSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    encontrados = await ListarProfessores(professores=professores).executar(tenant_id=tenant_id)
    return [_professor_saida(p) for p in encontrados]


@router.get("/professores/{professor_id}", response_model=ProfessorSaida)
async def obter_professor(
    professor_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> ProfessorSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        professor = await ObterProfessor(professores=professores).executar(
            tenant_id=tenant_id, professor_id=professor_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _professor_saida(professor)


@router.get("/professores/{professor_id}/series", response_model=list[SalaSaida])
async def series_do_professor(
    professor_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> list[SalaSaida]:
    """Séries (turmas) sob responsabilidade de um professor (um professor → N séries)."""
    _exige_acesso_tenant(usuario, tenant_id)
    encontradas = await ListarSeriesDoProfessor(salas=salas).executar(
        tenant_id=tenant_id, professor_id=professor_id
    )
    return [_sala_saida(s) for s in encontradas]


@router.put("/professores/{professor_id}", response_model=ProfessorSaida)
async def atualizar_professor(
    professor_id: UUID,
    payload: ProfessorAtualizar,
    usuario: Usuario = Depends(usuario_autenticado),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> ProfessorSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        professor = await AtualizarProfessor(professores=professores).executar(
            tenant_id=payload.tenant_id,
            professor_id=professor_id,
            nome=payload.nome,
            telefone=payload.telefone,
            senha=payload.senha,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _professor_saida(professor)


@router.delete("/professores/{professor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_professor(
    professor_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    professores: SqlProfessorRepository = Depends(get_professor_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    removido = await RemoverProfessor(professores=professores).executar(
        tenant_id=tenant_id, professor_id=professor_id
    )
    if not removido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Professor não encontrado")


@router.put("/salas/{sala_id}/professor", response_model=SalaSaida)
async def definir_professor_da_sala(
    sala_id: UUID,
    payload: AtribuirProfessorEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> SalaSaida:
    """Atribui (ou remove, com ``professor_id=null``) o professor responsável pela série."""
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        if payload.professor_id is None:
            sala = await RemoverProfessorDaSala(salas=salas).executar(
                tenant_id=payload.tenant_id, sala_id=sala_id
            )
        else:
            sala = await AtribuirProfessorASala(salas=salas).executar(
                tenant_id=payload.tenant_id, sala_id=sala_id, professor_id=payload.professor_id
            )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _sala_saida(sala)


# --------------------------------------------------------------------------- #
# Importação de alunos em massa (planilha/PDF normalizados pela LLM)
# --------------------------------------------------------------------------- #
@router.post("/alunos/importar/previa", response_model=ImportacaoPreviaSaida)
async def previa_importacao_alunos(
    payload: ImportacaoPreviaEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    llm: LLMProvider = Depends(get_llm),
    salas: SqlSalaRepository = Depends(get_sala_repo),
) -> ImportacaoPreviaSaida:
    """Etapa 1: a LLM normaliza o conteúdo e devolvemos as linhas para revisão."""
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        previa = await PrevisualizarImportacaoAlunos(llm=llm, salas=salas).executar(
            tenant_id=payload.tenant_id, conteudo=payload.conteudo
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _previa_importacao_saida(previa)


@router.post("/alunos/importar/confirmar", response_model=ImportacaoResultadoSaida)
async def confirmar_importacao_alunos(
    payload: ImportacaoConfirmarEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
    salas: SqlSalaRepository = Depends(get_sala_repo),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> ImportacaoResultadoSaida:
    """Etapa 2: persiste as linhas revisadas (séries, responsáveis e alunos)."""
    _exige_acesso_tenant(usuario, payload.tenant_id)
    linhas = [_linha_importacao_entrada(linha) for linha in payload.linhas]
    resultado = await ConfirmarImportacaoAlunos(
        alunos=alunos, salas=salas, contatos=contatos
    ).executar(
        tenant_id=payload.tenant_id,
        linhas=linhas,
        criar_series_ausentes=payload.criar_series_ausentes,
    )
    return _resultado_importacao_saida(resultado)
