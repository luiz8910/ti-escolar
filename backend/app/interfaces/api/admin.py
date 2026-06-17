"""Rotas de administração: autenticação, usuários, grupos e disparo a grupos.

Autenticação por **JWT (HS256)**: o ``POST /login`` devolve um token; as demais rotas
exigem ``Authorization: Bearer <token>``. O token carrega o id do usuário e expira
conforme ``JWT_EXPIRA_MINUTOS``.
"""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.admin_use_cases import (
    AdicionarContatoAoGrupo,
    AutenticarUsuario,
    CriarGrupo,
    CriarUsuario,
    EnviarBroadcastParaGrupo,
)
from app.application.tenant_use_cases import (
    AtualizarEscola,
    CriarEscola,
    ListarBroadcastsDaEscola,
    ListarConversasDaEscola,
    ListarEscolas,
    ObterConversaDaEscola,
    ObterEscola,
    RemoverEscola,
)
from app.config import Settings
from app.domain.entities import Papel, Usuario
from app.infrastructure.db.repositories import SqlBroadcastRepository, SqlConversaRepository
from app.infrastructure.security import criar_token, decodificar_token
from app.infrastructure.db.repositories_admin import (
    SqlGrupoRepository,
    SqlTenantRepository,
    SqlUsuarioRepository,
)
from app.interfaces.deps import (
    get_broadcast_repo,
    get_conversa_repo,
    get_enviar_para_grupo,
    get_grupo_repo,
    get_settings_dep,
    get_tenant_repo,
    get_usuario_repo,
)
from app.interfaces.dto import (
    BroadcastResumoSaida,
    ContatoEntrada,
    ContatoSaida,
    ConversaDetalheSaida,
    ConversaResumoSaida,
    CriarUsuarioEntrada,
    EnvioGrupoEntrada,
    EnvioGrupoSaida,
    EscolaEntrada,
    EscolaResumoSaida,
    EscolaSaida,
    GrupoEntrada,
    GrupoSaida,
    LoginEntrada,
    MensagemConversaSaida,
    TokenSaida,
    UsuarioSaida,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])

# auto_error=False: deixamos a checagem para ``usuario_autenticado`` devolver 401 limpo.
_bearer = HTTPBearer(auto_error=False)


def _usuario_saida(u: Usuario) -> UsuarioSaida:
    return UsuarioSaida(
        id=u.id, nome=u.nome, email=u.email, papel=u.papel.value, tenant_id=u.tenant_id
    )


_NAO_AUTENTICADO = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Não autenticado",
    headers={"WWW-Authenticate": "Bearer"},
)


async def usuario_autenticado(
    credenciais: HTTPAuthorizationCredentials | None = Depends(_bearer),
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
    settings: Settings = Depends(get_settings_dep),
) -> Usuario:
    """Resolve o usuário a partir do JWT em ``Authorization: Bearer <token>``.

    Revalida o usuário no banco (existência e ``ativo``) a cada requisição, de modo que
    desativar um usuário invalida a sessão mesmo com o token ainda no prazo.
    """
    if credenciais is None or not credenciais.credentials:
        raise _NAO_AUTENTICADO

    payload = decodificar_token(credenciais.credentials, segredo=settings.jwt_secret)
    if payload is None or "email" not in payload:
        raise _NAO_AUTENTICADO

    usuario = await usuarios.por_email(payload["email"])
    if usuario is None or not usuario.ativo:
        raise _NAO_AUTENTICADO
    return usuario


def _exige_acesso_tenant(usuario: Usuario, tenant_id: UUID) -> None:
    """Super admin acessa qualquer tenant; admin de tenant só o seu."""
    if not usuario.eh_super_admin and usuario.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acesso negado ao tenant")


def _exige_super_admin(usuario: Usuario) -> None:
    if not usuario.eh_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Apenas o super admin pode gerenciar escolas"
        )


# --------------------------------------------------------------------------- #
# Autenticação e usuários
# --------------------------------------------------------------------------- #
@router.post("/login", response_model=TokenSaida)
async def login(
    payload: LoginEntrada,
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
    settings: Settings = Depends(get_settings_dep),
) -> TokenSaida:
    usuario = await AutenticarUsuario(usuarios=usuarios).executar(
        email=payload.email, senha=payload.senha
    )
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    expira_em = settings.jwt_expira_minutos * 60
    token = criar_token(
        {
            "sub": str(usuario.id),
            "email": usuario.email,
            "papel": usuario.papel.value,
            "tenant_id": str(usuario.tenant_id) if usuario.tenant_id else None,
        },
        segredo=settings.jwt_secret,
        expira_em_segundos=expira_em,
    )
    return TokenSaida(access_token=token, expira_em=expira_em, usuario=_usuario_saida(usuario))


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


# --------------------------------------------------------------------------- #
# Escolas (tenants) — CRUD do super admin
# --------------------------------------------------------------------------- #
def _escola_saida(t) -> EscolaSaida:
    return EscolaSaida(id=t.id, nome=t.nome, slug=t.slug, criado_em=t.criado_em)


@router.post("/escolas", response_model=EscolaSaida, status_code=status.HTTP_201_CREATED)
async def criar_escola(
    payload: EscolaEntrada,
    criador: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> EscolaSaida:
    try:
        escola = await CriarEscola(tenants=tenants).executar(
            criador=criador, nome=payload.nome, slug=payload.slug
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return _escola_saida(escola)


@router.get("/escolas", response_model=list[EscolaResumoSaida])
async def listar_escolas(
    solicitante: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> list[EscolaResumoSaida]:
    try:
        resumos = await ListarEscolas(tenants=tenants).executar(solicitante=solicitante)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    return [
        EscolaResumoSaida(
            id=r.tenant.id,
            nome=r.tenant.nome,
            slug=r.tenant.slug,
            criado_em=r.tenant.criado_em,
            total_conversas=r.total_conversas,
            total_contatos=r.total_contatos,
            total_broadcasts=r.total_broadcasts,
        )
        for r in resumos
    ]


@router.get("/escolas/{tenant_id}", response_model=EscolaSaida)
async def obter_escola(
    tenant_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> EscolaSaida:
    try:
        escola = await ObterEscola(tenants=tenants).executar(
            solicitante=solicitante, tenant_id=tenant_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    if escola is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escola não encontrada")
    return _escola_saida(escola)


@router.put("/escolas/{tenant_id}", response_model=EscolaSaida)
async def atualizar_escola(
    tenant_id: UUID,
    payload: EscolaEntrada,
    criador: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> EscolaSaida:
    try:
        escola = await AtualizarEscola(tenants=tenants).executar(
            criador=criador, tenant_id=tenant_id, nome=payload.nome, slug=payload.slug
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        codigo = (
            status.HTTP_404_NOT_FOUND
            if "não encontrada" in str(e)
            else status.HTTP_400_BAD_REQUEST
        )
        raise HTTPException(status_code=codigo, detail=str(e)) from e
    return _escola_saida(escola)


@router.delete("/escolas/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_escola(
    tenant_id: UUID,
    criador: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> None:
    try:
        removido = await RemoverEscola(tenants=tenants).executar(
            criador=criador, tenant_id=tenant_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    if not removido:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escola não encontrada")


# --------------------------------------------------------------------------- #
# Visualização: conversas (inbound) e mensagens em massa (outbound) da escola
# --------------------------------------------------------------------------- #
@router.get("/escolas/{tenant_id}/conversas", response_model=list[ConversaResumoSaida])
async def listar_conversas(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    conversas: SqlConversaRepository = Depends(get_conversa_repo),
) -> list[ConversaResumoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    resumos = await ListarConversasDaEscola(conversas=conversas).executar(tenant_id=tenant_id)
    return [
        ConversaResumoSaida(
            id=r.conversa.id,
            contato=r.conversa.contato,
            criado_em=r.conversa.criado_em,
            total_mensagens=r.total_mensagens,
            ultima_mensagem=r.ultima_mensagem,
            ultima_em=r.ultima_em,
        )
        for r in resumos
    ]


@router.get(
    "/escolas/{tenant_id}/conversas/{conversa_id}", response_model=ConversaDetalheSaida
)
async def obter_conversa(
    tenant_id: UUID,
    conversa_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    conversas: SqlConversaRepository = Depends(get_conversa_repo),
) -> ConversaDetalheSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    resultado = await ObterConversaDaEscola(conversas=conversas).executar(
        tenant_id=tenant_id, conversa_id=conversa_id
    )
    if resultado is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversa não encontrada")
    return ConversaDetalheSaida(
        id=resultado.conversa.id,
        contato=resultado.conversa.contato,
        criado_em=resultado.conversa.criado_em,
        mensagens=[
            MensagemConversaSaida(
                id=m.id,
                autor=m.autor.value,
                texto=m.texto,
                fontes=m.fontes,
                criado_em=m.criado_em,
            )
            for m in resultado.mensagens
        ],
    )


@router.get("/escolas/{tenant_id}/broadcasts", response_model=list[BroadcastResumoSaida])
async def listar_broadcasts(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    broadcasts: SqlBroadcastRepository = Depends(get_broadcast_repo),
) -> list[BroadcastResumoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    bs = await ListarBroadcastsDaEscola(broadcasts=broadcasts).executar(tenant_id=tenant_id)
    return [
        BroadcastResumoSaida(
            id=b.id,
            titulo=b.titulo,
            status=b.status.value,
            criado_em=b.criado_em,
            agendado_para=b.agendado_para,
            total_destinatarios=len(b.destinatarios),
            por_status=dict(Counter(d.status.value for d in b.destinatarios)),
        )
        for b in bs
    ]
