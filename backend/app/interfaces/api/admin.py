"""Rotas de administração: autenticação, usuários, grupos e disparo a grupos.

Autenticação (scaffold): credenciais nos cabeçalhos ``X-User-Email`` / ``X-User-Senha``.
JWT/sessão fica no roadmap — aqui o foco é o modelo (super admin, admin de tenant e grupos).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status

from app.application.admin_use_cases import (
    AdicionarContatoAoGrupo,
    AutenticarUsuario,
    CriarGrupo,
    CriarUsuario,
    EnviarBroadcastParaGrupo,
)
from app.domain.entities import Papel, Usuario
from app.infrastructure.db.repositories_admin import SqlGrupoRepository, SqlUsuarioRepository
from app.interfaces.deps import get_enviar_para_grupo, get_grupo_repo, get_usuario_repo
from app.interfaces.dto import (
    ContatoEntrada,
    ContatoSaida,
    CriarUsuarioEntrada,
    EnvioGrupoEntrada,
    EnvioGrupoSaida,
    GrupoEntrada,
    GrupoSaida,
    LoginEntrada,
    UsuarioSaida,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _usuario_saida(u: Usuario) -> UsuarioSaida:
    return UsuarioSaida(
        id=u.id, nome=u.nome, email=u.email, papel=u.papel.value, tenant_id=u.tenant_id
    )


async def usuario_autenticado(
    x_user_email: str = Header(..., alias="X-User-Email"),
    x_user_senha: str = Header(..., alias="X-User-Senha"),
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
) -> Usuario:
    usuario = await AutenticarUsuario(usuarios=usuarios).executar(
        email=x_user_email, senha=x_user_senha
    )
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    return usuario


def _exige_acesso_tenant(usuario: Usuario, tenant_id: UUID) -> None:
    """Super admin acessa qualquer tenant; admin de tenant só o seu."""
    if not usuario.eh_super_admin and usuario.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado ao tenant")


# --------------------------------------------------------------------------- #
# Autenticação e usuários
# --------------------------------------------------------------------------- #
@router.post("/login", response_model=UsuarioSaida)
async def login(
    payload: LoginEntrada,
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
) -> UsuarioSaida:
    usuario = await AutenticarUsuario(usuarios=usuarios).executar(
        email=payload.email, senha=payload.senha
    )
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")
    return _usuario_saida(usuario)


@router.post("/usuarios", response_model=UsuarioSaida, status_code=status.HTTP_201_CREATED)
async def criar_usuario(
    payload: CriarUsuarioEntrada,
    criador: Usuario = Depends(usuario_autenticado),
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
) -> UsuarioSaida:
    try:
        usuario = await CriarUsuario(usuarios=usuarios).executar(
            criador=criador,
            nome=payload.nome,
            email=payload.email,
            senha=payload.senha,
            papel=Papel(payload.papel),
            tenant_id=payload.tenant_id,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _usuario_saida(usuario)


@router.get("/usuarios", response_model=list[UsuarioSaida])
async def listar_usuarios(
    solicitante: Usuario = Depends(usuario_autenticado),
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
) -> list[UsuarioSaida]:
    # Super admin vê todos; admin de tenant vê apenas os do próprio tenant.
    escopo = None if solicitante.eh_super_admin else solicitante.tenant_id
    return [_usuario_saida(u) for u in await usuarios.listar(tenant_id=escopo)]


# --------------------------------------------------------------------------- #
# Grupos e contatos
# --------------------------------------------------------------------------- #
def _grupo_saida(grupo) -> GrupoSaida:
    return GrupoSaida(
        id=grupo.id,
        nome=grupo.nome,
        descricao=grupo.descricao,
        total_membros=len(grupo.membros),
        membros=[ContatoSaida(id=c.id, nome=c.nome, telefone=c.telefone) for c in grupo.membros],
    )


@router.post("/grupos", response_model=GrupoSaida, status_code=status.HTTP_201_CREATED)
async def criar_grupo(
    payload: GrupoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    grupos: SqlGrupoRepository = Depends(get_grupo_repo),
) -> GrupoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    grupo = await CriarGrupo(grupos=grupos).executar(
        tenant_id=payload.tenant_id, nome=payload.nome, descricao=payload.descricao
    )
    return _grupo_saida(grupo)


@router.get("/grupos/{tenant_id}", response_model=list[GrupoSaida])
async def listar_grupos(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    grupos: SqlGrupoRepository = Depends(get_grupo_repo),
) -> list[GrupoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    return [_grupo_saida(g) for g in await grupos.listar(tenant_id=tenant_id)]


@router.post(
    "/grupos/{grupo_id}/contatos",
    response_model=ContatoSaida,
    status_code=status.HTTP_201_CREATED,
)
async def adicionar_contato(
    grupo_id: UUID,
    payload: ContatoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    grupos: SqlGrupoRepository = Depends(get_grupo_repo),
) -> ContatoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        contato = await AdicionarContatoAoGrupo(grupos=grupos).executar(
            tenant_id=payload.tenant_id,
            grupo_id=grupo_id,
            nome=payload.nome,
            telefone=payload.telefone,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return ContatoSaida(id=contato.id, nome=contato.nome, telefone=contato.telefone)


@router.post("/grupos/{grupo_id}/enviar", response_model=EnvioGrupoSaida)
async def enviar_para_grupo(
    grupo_id: UUID,
    payload: EnvioGrupoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    uc: EnviarBroadcastParaGrupo = Depends(get_enviar_para_grupo),
) -> EnvioGrupoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        resultado = await uc.executar(
            tenant_id=payload.tenant_id,
            grupo_id=grupo_id,
            template_id=payload.template_id,
            titulo=payload.titulo,
            mensagem=payload.mensagem,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    b = resultado.broadcast
    from app.interfaces.dto import BroadcastSaida

    return EnvioGrupoSaida(
        grupo_id=resultado.grupo_id,
        total_contatos=resultado.total_contatos,
        broadcast=BroadcastSaida(
            broadcast_id=b.broadcast_id,
            status=b.status.value,
            enviados=b.enviados,
            falhas=b.falhas,
            bloqueados_por_limite=b.bloqueados_por_limite,
            restante_cota=b.restante_cota,
        ),
    )
