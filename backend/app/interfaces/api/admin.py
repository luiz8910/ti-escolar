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
from app.application.auditoria_use_cases import ListarAuditoria, RegistrarAuditoria
from app.application.use_cases import VerificarRecebimentoBroadcast
from app.application.tenant_use_cases import (
    AtualizarEscola,
    BloquearEscola,
    CriarEscola,
    DefinirLicenca,
    DesbloquearEscola,
    ListarBroadcastsDaEscola,
    ListarConversasDaEscola,
    ListarEscolas,
    NotificarLicencasAVencer,
    ObterBroadcastDaEscola,
    ObterConversaDaEscola,
    ObterEscola,
    RemoverEscola,
)
from app.config import Settings
from app.domain.entities import AtorAuditoria, Papel, PlanoTenant, Tenant, Usuario
from app.infrastructure.db.repositories import (
    SqlBroadcastRepository,
    SqlConversaRepository,
    SqlTemplateRepository,
)
from app.infrastructure.security import criar_token, decodificar_token
from app.infrastructure.db.repositories_admin import (
    SqlAuditLogRepository,
    SqlContatoRepository,
    SqlGrupoRepository,
    SqlTenantRepository,
    SqlUsuarioRepository,
)
from app.interfaces.deps import (
    get_audit_repo,
    get_broadcast_repo,
    get_contato_repo,
    get_conversa_repo,
    get_enviar_para_grupo,
    get_grupo_repo,
    get_notificar_licencas,
    get_session,
    get_settings_dep,
    get_tenant_repo,
    get_usuario_repo,
)
from app.interfaces.dto import (
    AvisoLicencaSaida,
    BloqueioEntrada,
    BroadcastDetalheSaida,
    BroadcastResumoSaida,
    ContatoEntrada,
    ContatoSaida,
    ConversaDetalheSaida,
    ConversaResumoSaida,
    CriarUsuarioEntrada,
    DestinatarioBroadcastSaida,
    EnvioGrupoEntrada,
    EnvioGrupoSaida,
    EscolaEntrada,
    EscolaResumoSaida,
    EscolaSaida,
    GrupoEntrada,
    GrupoSaida,
    LicencaEntrada,
    LicencaSaida,
    LoginEntrada,
    MensagemConversaSaida,
    NaoEntregaSaida,
    RegistroAuditoriaSaida,
    TokenSaida,
    UsuarioSaida,
)
from sqlalchemy.ext.asyncio import AsyncSession

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


async def _exige_tenant_ativo(tenant_id: UUID, tenants: SqlTenantRepository) -> None:
    """Recusa operações (disparos) de uma escola bloqueada."""
    escola = await tenants.obter(tenant_id)
    if escola is not None and escola.bloqueado:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Escola bloqueada: {escola.motivo_bloqueio}",
        )


async def _auditar_usuario(
    auditoria: SqlAuditLogRepository,
    *,
    usuario: Usuario,
    acao: str,
    tenant_id: UUID | None = None,
    descricao: str = "",
    metadados: dict | None = None,
) -> None:
    """Registra, na auditoria, uma ação feita por um usuário logado no painel."""
    await RegistrarAuditoria(auditoria=auditoria).executar(
        ator=AtorAuditoria.USUARIO,
        acao=acao,
        tenant_id=tenant_id if tenant_id is not None else usuario.tenant_id,
        ator_id=str(usuario.id),
        ator_nome=usuario.nome,
        descricao=descricao,
        metadados=metadados or {},
    )


# --------------------------------------------------------------------------- #
# Autenticação e usuários
# --------------------------------------------------------------------------- #
@router.post("/login", response_model=TokenSaida)
async def login(
    payload: LoginEntrada,
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
    settings: Settings = Depends(get_settings_dep),
) -> TokenSaida:
    usuario = await AutenticarUsuario(usuarios=usuarios).executar(
        email=payload.email, senha=payload.senha
    )
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    # Admin de escola bloqueada não acessa o painel (o super admin continua entrando).
    if not usuario.eh_super_admin and usuario.tenant_id is not None:
        escola = await tenants.obter(usuario.tenant_id)
        if escola is not None and escola.bloqueado:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Escola bloqueada: {escola.motivo_bloqueio}",
            )

    await _auditar_usuario(
        auditoria, usuario=usuario, acao="login", descricao="Entrou no painel"
    )

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
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
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
    await _auditar_usuario(
        auditoria,
        usuario=criador,
        acao="usuario.criar",
        tenant_id=usuario.tenant_id,
        descricao=f"Criou o usuário {usuario.email} ({usuario.papel.value})",
        metadados={"usuario_id": str(usuario.id), "papel": usuario.papel.value},
    )
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
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> GrupoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    grupo = await CriarGrupo(grupos=grupos).executar(
        tenant_id=payload.tenant_id, nome=payload.nome, descricao=payload.descricao
    )
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="grupo.criar",
        tenant_id=payload.tenant_id,
        descricao=f"Criou o grupo '{grupo.nome}'",
        metadados={"grupo_id": str(grupo.id)},
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
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> EnvioGrupoSaida:
    _exige_acesso_tenant(usuario, payload.tenant_id)
    await _exige_tenant_ativo(payload.tenant_id, tenants)
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
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="broadcast.grupo.enviar",
        tenant_id=payload.tenant_id,
        descricao=f"Disparou '{payload.titulo}' para um grupo ({resultado.total_contatos} contato(s))",
        metadados={
            "grupo_id": str(grupo_id),
            "broadcast_id": str(b.broadcast_id),
            "enviados": b.enviados,
            "falhas": b.falhas,
            "bloqueados_por_limite": b.bloqueados_por_limite,
        },
    )
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
def _licenca_saida(t: Tenant) -> LicencaSaida:
    return LicencaSaida(
        status=t.status.value,
        motivo_bloqueio=t.motivo_bloqueio,
        bloqueado_em=t.bloqueado_em,
        plano=t.plano.value,
        licenca_expira_em=t.licenca_expira_em,
        dias_para_expirar=t.dias_para_expirar,
        licenca_expirada=t.licenca_expirada,
    )


def _escola_saida(t: Tenant) -> EscolaSaida:
    return EscolaSaida(
        id=t.id, nome=t.nome, slug=t.slug, criado_em=t.criado_em, licenca=_licenca_saida(t)
    )


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
            licenca=_licenca_saida(r.tenant),
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
# Licenciamento / cobrança / bloqueio (super admin)
# --------------------------------------------------------------------------- #
@router.post("/escolas/{tenant_id}/bloquear", response_model=EscolaSaida)
async def bloquear_escola(
    tenant_id: UUID,
    payload: BloqueioEntrada,
    criador: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> EscolaSaida:
    try:
        escola = await BloquearEscola(tenants=tenants).executar(
            criador=criador, tenant_id=tenant_id, motivo=payload.motivo
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


@router.post("/escolas/{tenant_id}/desbloquear", response_model=EscolaSaida)
async def desbloquear_escola(
    tenant_id: UUID,
    criador: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> EscolaSaida:
    try:
        escola = await DesbloquearEscola(tenants=tenants).executar(
            criador=criador, tenant_id=tenant_id
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _escola_saida(escola)


@router.put("/escolas/{tenant_id}/licenca", response_model=EscolaSaida)
async def definir_licenca(
    tenant_id: UUID,
    payload: LicencaEntrada,
    criador: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> EscolaSaida:
    try:
        plano = PlanoTenant(payload.plano)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Plano inválido (use mensal ou anual)."
        ) from e
    try:
        escola = await DefinirLicenca(tenants=tenants).executar(
            criador=criador,
            tenant_id=tenant_id,
            plano=plano,
            licenca_expira_em=payload.licenca_expira_em,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return _escola_saida(escola)


@router.post("/licencas/notificar-vencimento", response_model=list[AvisoLicencaSaida])
async def notificar_vencimento(
    solicitante: Usuario = Depends(usuario_autenticado),
    uc: NotificarLicencasAVencer = Depends(get_notificar_licencas),
    settings: Settings = Depends(get_settings_dep),
) -> list[AvisoLicencaSaida]:
    _exige_super_admin(solicitante)
    avisos = await uc.executar(dias_aviso=settings.license_warning_days)
    return [
        AvisoLicencaSaida(
            tenant_id=a.tenant.id,
            nome=a.tenant.nome,
            dias_para_expirar=a.dias_para_expirar,
            destinatarios=a.destinatarios,
        )
        for a in avisos
    ]


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
    session: AsyncSession = Depends(get_session),
) -> list[BroadcastResumoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    itens = await ListarBroadcastsDaEscola(
        broadcasts=broadcasts, templates=SqlTemplateRepository(session)
    ).executar(tenant_id=tenant_id)
    return [
        BroadcastResumoSaida(
            id=item.broadcast.id,
            titulo=item.broadcast.titulo,
            status=item.broadcast.status.value,
            template_nome=item.template_nome,
            criado_em=item.broadcast.criado_em,
            agendado_para=item.broadcast.agendado_para,
            total_destinatarios=len(item.broadcast.destinatarios),
            por_status=dict(Counter(d.status.value for d in item.broadcast.destinatarios)),
        )
        for item in itens
    ]


@router.get(
    "/escolas/{tenant_id}/broadcasts/{broadcast_id}", response_model=BroadcastDetalheSaida
)
async def obter_broadcast(
    tenant_id: UUID,
    broadcast_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    broadcasts: SqlBroadcastRepository = Depends(get_broadcast_repo),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
    session: AsyncSession = Depends(get_session),
) -> BroadcastDetalheSaida:
    """Detalhe de um disparo: template, destinatários (com o nome do responsável) e status."""
    _exige_acesso_tenant(usuario, tenant_id)
    detalhe = await ObterBroadcastDaEscola(
        broadcasts=broadcasts, contatos=contatos, templates=SqlTemplateRepository(session)
    ).executar(tenant_id=tenant_id, broadcast_id=broadcast_id)
    if detalhe is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Disparo não encontrado"
        )
    b = detalhe.broadcast
    return BroadcastDetalheSaida(
        id=b.id,
        titulo=b.titulo,
        status=b.status.value,
        template_nome=detalhe.template_nome,
        criado_em=b.criado_em,
        agendado_para=b.agendado_para,
        total_destinatarios=len(detalhe.destinatarios),
        por_status=dict(Counter(d.status.value for d in detalhe.destinatarios)),
        destinatarios=[
            DestinatarioBroadcastSaida(
                contato=d.contato,
                nome=d.nome,
                status=d.status.value,
                atualizado_em=d.atualizado_em,
            )
            for d in detalhe.destinatarios
        ],
    )


@router.get(
    "/escolas/{tenant_id}/broadcasts/{broadcast_id}/nao-entregues",
    response_model=list[NaoEntregaSaida],
)
async def listar_nao_entregues(
    tenant_id: UUID,
    broadcast_id: UUID,
    apos_minutos: int = 60,
    usuario: Usuario = Depends(usuario_autenticado),
    broadcasts: SqlBroadcastRepository = Depends(get_broadcast_repo),
    contatos: SqlContatoRepository = Depends(get_contato_repo),
) -> list[NaoEntregaSaida]:
    """Confirmação de recebimento: responsáveis que não confirmaram a entrega do aviso.

    Sinaliza falhas de envio e mensagens enviadas há mais de ``apos_minutos`` ainda sem
    confirmação de entrega (``delivered``/``read``) pela Meta.
    """
    _exige_acesso_tenant(usuario, tenant_id)
    avisos = await VerificarRecebimentoBroadcast(
        broadcasts=broadcasts, contatos=contatos
    ).executar(tenant_id=tenant_id, broadcast_id=broadcast_id, apos_minutos=apos_minutos)
    return [
        NaoEntregaSaida(
            contato=a.contato,
            nome=a.nome,
            status=a.status.value,
            motivo=a.motivo,
            atualizado_em=a.atualizado_em,
        )
        for a in avisos
    ]


# --------------------------------------------------------------------------- #
# Auditoria de ações (usuários logados + LLM) da escola
# --------------------------------------------------------------------------- #
@router.get(
    "/escolas/{tenant_id}/auditoria", response_model=list[RegistroAuditoriaSaida]
)
async def listar_auditoria(
    tenant_id: UUID,
    limite: int = 200,
    usuario: Usuario = Depends(usuario_autenticado),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> list[RegistroAuditoriaSaida]:
    """Log de auditoria da escola: ações de usuários logados e da LLM (mais recentes primeiro)."""
    _exige_acesso_tenant(usuario, tenant_id)
    limite = max(1, min(limite, 500))
    registros = await ListarAuditoria(auditoria=auditoria).executar(
        tenant_id=tenant_id, limite=limite
    )
    return [
        RegistroAuditoriaSaida(
            id=r.id,
            tenant_id=r.tenant_id,
            ator=r.ator.value,
            ator_id=r.ator_id,
            ator_nome=r.ator_nome,
            acao=r.acao,
            descricao=r.descricao,
            metadados=r.metadados,
            criado_em=r.criado_em,
        )
        for r in registros
    ]
