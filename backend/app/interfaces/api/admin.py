"""Rotas de administração: autenticação, usuários, grupos e disparo a grupos.

Autenticação por **JWT (HS256)**: o ``POST /login`` devolve um token; as demais rotas
exigem ``Authorization: Bearer <token>``. O token carrega o id do usuário e expira
conforme ``JWT_EXPIRA_MINUTOS``.
"""

from __future__ import annotations

from collections import Counter
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.application.admin_use_cases import (
    AdicionarContatoAoGrupo,
    AtualizarUsuario,
    DadosUsuario,
    AutenticarUsuario,
    CriarGrupo,
    CriarUsuario,
    EnviarBroadcastParaGrupo,
)
from app.application.auditoria_use_cases import ListarAuditoria, RegistrarAuditoria
from app.application.paginacao import POR_PAGINA_MAXIMO, POR_PAGINA_PADRAO
from app.application.use_cases import VerificarRecebimentoBroadcast
from app.application.tenant_use_cases import (
    AtualizarEscola,
    BloquearEscola,
    CancelarEscola,
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
    ObterFichaFinanceira,
    ReativarEscola,
    RemoverEscola,
)
from app.config import Settings
from app.domain.entities import (
    AtorAuditoria,
    Cargo,
    OrigemParametro,
    Papel,
    ParametroTemplate,
    PlanoTenant,
    Tenant,
    Turno,
    Usuario,
)
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
from app.interfaces.api.rate_limit import limitar_login
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
    AtualizarUsuarioEntrada,
    AuditoriaPaginaSaida,
    AvisoLicencaSaida,
    BloqueioEntrada,
    BroadcastDetalheSaida,
    BroadcastResumoSaida,
    BroadcastsPaginaSaida,
    CancelamentoEntrada,
    ContatoEntrada,
    ContatoSaida,
    ConversaDetalheSaida,
    ConversaResumoSaida,
    ConversasPaginaSaida,
    CriarUsuarioEntrada,
    DestinatarioBroadcastSaida,
    EnvioGrupoEntrada,
    ParametroTemplateEntrada,
    EnvioGrupoSaida,
    EscolaEntrada,
    EscolaResumoSaida,
    EscolaSaida,
    ExpedienteSaida,
    FichaFinanceiraSaida,
    GrupoEntrada,
    GrupoSaida,
    LicencaEntrada,
    LicencaSaida,
    LoginEntrada,
    MensagemConversaSaida,
    MetricasUsoSaida,
    NaoEntregaSaida,
    PaginaMeta,
    RegistroAuditoriaSaida,
    TokenSaida,
    UsuarioSaida,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/admin", tags=["admin"])

# auto_error=False: deixamos a checagem para ``usuario_autenticado`` devolver 401 limpo.
_bearer = HTTPBearer(auto_error=False)


def _meta(pagina) -> PaginaMeta:
    """Traduz a ``Pagina`` do domínio no metadado que o painel consome."""
    return PaginaMeta(
        pagina=pagina.pagina,
        por_pagina=pagina.por_pagina,
        total=pagina.total,
        total_paginas=pagina.total_paginas,
    )


def _usuario_saida(u: Usuario, *, tenant_nome: str = "") -> UsuarioSaida:
    return UsuarioSaida(
        id=u.id,
        nome=u.nome,
        email=u.email,
        papel=u.papel.value,
        tenant_id=u.tenant_id,
        tenant_nome=tenant_nome,
        cargo=u.cargo.value if u.cargo else "",
        cargo_rotulo=u.cargo.rotulo if u.cargo else "",
        gere_usuarios=u.gere_usuarios,
        telefone=u.telefone,
        endereco=u.endereco,
        turno=u.turno.value if u.turno else "",
        ativo=u.ativo,
        criado_em=u.criado_em,
    )


def _enum_opcional(valor: str | None, enum_cls, rotulo: str):
    """Converte string em enum, tratando "" como ausente e erro como 400."""
    if valor is None or valor == "":
        return None
    try:
        return enum_cls(valor)
    except ValueError as e:
        aceitos = ", ".join(m.value for m in enum_cls)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{rotulo} inválido: {valor}. Use um de: {aceitos}.",
        ) from e


def _exige_gestao_de_usuarios(usuario: Usuario) -> None:
    """A secretaria opera a escola, mas **não mexe em contas** (§2.4 do plano)."""
    if not usuario.gere_usuarios:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="A secretaria não tem permissão para gerenciar usuários.",
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
    """Recusa operações (disparos) de uma escola bloqueada ou cancelada."""
    escola = await tenants.obter(tenant_id)
    if escola is not None and escola.acesso_suspenso:
        rotulo = "Escola cancelada" if escola.cancelado else "Escola bloqueada"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{rotulo}: {escola.motivo_suspensao}",
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
    request: Request,
    payload: LoginEntrada,
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
    settings: Settings = Depends(get_settings_dep),
) -> TokenSaida:
    # Antes de tocar no banco: sem isto, o PBKDF2 encarece cada tentativa mas não limita
    # quantas o atacante faz contra as senhas de admin (item 5 do checklist).
    await limitar_login(request, identificador=payload.email, escopo="admin", settings=settings)

    usuario = await AutenticarUsuario(usuarios=usuarios).executar(
        email=payload.email, senha=payload.senha
    )
    if usuario is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Credenciais inválidas")

    # Admin de escola bloqueada/cancelada não acessa o painel (o super admin segue entrando).
    escola = None
    if not usuario.eh_super_admin and usuario.tenant_id is not None:
        escola = await tenants.obter(usuario.tenant_id)
        if escola is not None and escola.acesso_suspenso:
            rotulo = "Escola cancelada" if escola.cancelado else "Escola bloqueada"
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"{rotulo}: {escola.motivo_suspensao}",
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
    return TokenSaida(
        access_token=token,
        expira_em=expira_em,
        usuario=_usuario_saida(usuario, tenant_nome=escola.nome if escola else ""),
    )


@router.post("/usuarios", response_model=UsuarioSaida, status_code=status.HTTP_201_CREATED)
async def criar_usuario(
    payload: CriarUsuarioEntrada,
    criador: Usuario = Depends(usuario_autenticado),
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> UsuarioSaida:
    _exige_gestao_de_usuarios(criador)
    try:
        usuario = await CriarUsuario(usuarios=usuarios).executar(
            criador=criador,
            nome=payload.nome,
            email=payload.email,
            senha=payload.senha,
            papel=Papel(payload.papel),
            tenant_id=payload.tenant_id,
            cargo=_enum_opcional(payload.cargo, Cargo, "Cargo"),
            dados=DadosUsuario(
                telefone=payload.telefone,
                endereco=payload.endereco,
                turno=_enum_opcional(payload.turno, Turno, "Turno"),
            ),
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
        metadados={
            "usuario_id": str(usuario.id),
            "papel": usuario.papel.value,
            "cargo": usuario.cargo.value if usuario.cargo else "",
        },
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


@router.put("/usuarios/{usuario_id}", response_model=UsuarioSaida)
async def atualizar_usuario(
    usuario_id: UUID,
    payload: AtualizarUsuarioEntrada,
    editor: Usuario = Depends(usuario_autenticado),
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> UsuarioSaida:
    """Edita nome, senha, situação, cargo e contato. A escola nunca muda aqui.

    O ``papel`` acompanha o cargo — não é editável por si. Editar a **própria** conta é
    permitido (nome, senha, contato), mas trocar o próprio cargo não: promover-se é o
    ataque óbvio, e rebaixar-se sozinho deixa a escola sem ninguém no topo.
    """
    # A secretaria pode editar a própria conta (trocar a senha), mas não mexer em outras.
    if usuario_id != editor.id:
        _exige_gestao_de_usuarios(editor)
    # Os três campos de contato andam juntos: só monta `dados` se algum veio no corpo,
    # senão uma edição de nome apagaria o telefone por omissão.
    contato = (payload.telefone, payload.endereco, payload.turno)
    dados = (
        DadosUsuario(
            telefone=payload.telefone or "",
            endereco=payload.endereco or "",
            turno=_enum_opcional(payload.turno, Turno, "Turno"),
        )
        if any(c is not None for c in contato)
        else None
    )
    try:
        usuario = await AtualizarUsuario(usuarios=usuarios).executar(
            editor=editor,
            usuario_id=usuario_id,
            nome=payload.nome,
            senha=payload.senha,
            ativo=payload.ativo,
            cargo=_enum_opcional(payload.cargo, Cargo, "Cargo"),
            dados=dados,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await _auditar_usuario(
        auditoria,
        usuario=editor,
        acao="usuario.atualizar",
        tenant_id=usuario.tenant_id,
        descricao=f"Atualizou o usuário {usuario.email}",
        metadados={
            "usuario_id": str(usuario.id),
            "ativo": usuario.ativo,
            "cargo": usuario.cargo.value if usuario.cargo else "",
            # Só o fato, nunca a senha — nem o tamanho dela.
            "senha_alterada": bool(payload.senha),
        },
    )
    return _usuario_saida(usuario)


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


def _parametro(entrada: ParametroTemplateEntrada) -> ParametroTemplate:
    """Traduz o DTO para o domínio. Origem desconhecida vira ``texto``, que é inerte —
    cair em ``responsavel`` por engano mandaria o nome de outra pessoa no lugar."""
    try:
        origem = OrigemParametro(entrada.origem)
    except ValueError:
        origem = OrigemParametro.TEXTO
    return ParametroTemplate(origem=origem, texto=entrada.texto)


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
            parametros=[_parametro(p) for p in payload.parametros],
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
        valor_mensal_centavos=t.valor_mensal_centavos,
        valor_anual_centavos=t.valor_anual_centavos,
        cancelado_em=t.cancelado_em,
        motivo_cancelamento=t.motivo_cancelamento,
    )


def _expediente_saida(t: Tenant) -> ExpedienteSaida:
    """Expediente da secretaria pronto para o painel (§6j)."""
    return ExpedienteSaida(
        dias=list(t.expediente_dias),
        inicio=t.expediente_inicio.strftime("%H:%M"),
        fim=t.expediente_fim.strftime("%H:%M"),
        timezone=t.expediente_timezone,
        descricao=t.descricao_expediente,
        aberto_agora=t.dentro_do_expediente(),
    )


def _escola_saida(t: Tenant) -> EscolaSaida:
    return EscolaSaida(
        id=t.id,
        nome=t.nome,
        slug=t.slug,
        whatsapp_numero=t.whatsapp_numero,
        meta_phone_number_id=t.meta_phone_number_id,
        waba_id=t.waba_id,
        telefone_contato=t.telefone_contato,
        expediente=_expediente_saida(t),
        criado_em=t.criado_em,
        licenca=_licenca_saida(t),
    )


@router.post("/escolas", response_model=EscolaSaida, status_code=status.HTTP_201_CREATED)
async def criar_escola(
    payload: EscolaEntrada,
    criador: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> EscolaSaida:
    try:
        escola = await CriarEscola(tenants=tenants).executar(
            criador=criador,
            nome=payload.nome,
            slug=payload.slug,
            whatsapp_numero=payload.whatsapp_numero,
            telefone_contato=payload.telefone_contato,
            meta_phone_number_id=payload.meta_phone_number_id,
            waba_id=payload.waba_id,
            expediente_dias=payload.expediente_dias,
            expediente_inicio=payload.expediente_inicio,
            expediente_fim=payload.expediente_fim,
            expediente_timezone=payload.expediente_timezone,
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
            whatsapp_numero=r.tenant.whatsapp_numero,
            meta_phone_number_id=r.tenant.meta_phone_number_id,
            waba_id=r.tenant.waba_id,
            telefone_contato=r.tenant.telefone_contato,
            expediente=_expediente_saida(r.tenant),
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
            criador=criador,
            tenant_id=tenant_id,
            nome=payload.nome,
            slug=payload.slug,
            whatsapp_numero=payload.whatsapp_numero,
            telefone_contato=payload.telefone_contato,
            meta_phone_number_id=payload.meta_phone_number_id,
            waba_id=payload.waba_id,
            expediente_dias=payload.expediente_dias,
            expediente_inicio=payload.expediente_inicio,
            expediente_fim=payload.expediente_fim,
            expediente_timezone=payload.expediente_timezone,
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


@router.post("/escolas/{tenant_id}/cancelar", response_model=EscolaSaida)
async def cancelar_escola(
    tenant_id: UUID,
    payload: CancelamentoEntrada,
    criador: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> EscolaSaida:
    """Cancela (churn) a escola: registra a saída e suspende o acesso."""
    try:
        escola = await CancelarEscola(tenants=tenants).executar(
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


@router.post("/escolas/{tenant_id}/reativar", response_model=EscolaSaida)
async def reativar_escola(
    tenant_id: UUID,
    criador: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
) -> EscolaSaida:
    """Reverte um cancelamento, reativando a escola."""
    try:
        escola = await ReativarEscola(tenants=tenants).executar(
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
            valor_mensal_centavos=payload.valor_mensal_centavos,
            valor_anual_centavos=payload.valor_anual_centavos,
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


@router.get("/escolas/{tenant_id}/ficha-financeira", response_model=FichaFinanceiraSaida)
async def obter_ficha_financeira(
    tenant_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    tenants: SqlTenantRepository = Depends(get_tenant_repo),
    settings: Settings = Depends(get_settings_dep),
) -> FichaFinanceiraSaida:
    """Ficha financeira/histórico da escola: ciclo de vida, cobrança, uso e saúde."""
    try:
        ficha = await ObterFichaFinanceira(tenants=tenants).executar(
            solicitante=solicitante,
            tenant_id=tenant_id,
            limite_diario_meta=settings.meta_daily_tier_limit,
        )
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    if ficha is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Escola não encontrada")
    t = ficha.tenant
    return FichaFinanceiraSaida(
        tenant_id=t.id,
        nome=t.nome,
        slug=t.slug,
        criado_em=t.criado_em,
        dias_de_casa=ficha.dias_de_casa,
        cancelado_em=t.cancelado_em,
        motivo_cancelamento=t.motivo_cancelamento,
        status=t.status.value,
        plano=t.plano.value,
        licenca_expira_em=t.licenca_expira_em,
        dias_para_expirar=t.dias_para_expirar,
        status_pagamento=ficha.status_pagamento.value,
        valor_mensal_centavos=t.valor_mensal_centavos,
        valor_anual_centavos=t.valor_anual_centavos,
        mrr_centavos=t.mrr_centavos,
        arr_centavos=t.arr_centavos,
        receita_acumulada_centavos=ficha.receita_acumulada_centavos,
        meses_ativos=ficha.meses_ativos,
        uso=MetricasUsoSaida(
            total_usuarios_ativos=ficha.uso.total_usuarios_ativos,
            total_contatos=ficha.uso.total_contatos,
            total_alunos=ficha.uso.total_alunos,
            total_conversas=ficha.uso.total_conversas,
            total_broadcasts=ficha.uso.total_broadcasts,
        ),
        limite_diario_meta=ficha.limite_diario_meta,
        health_score=ficha.health_score,
    )


# --------------------------------------------------------------------------- #
# Visualização: conversas (inbound) e mensagens em massa (outbound) da escola
# --------------------------------------------------------------------------- #
@router.get("/escolas/{tenant_id}/conversas", response_model=ConversasPaginaSaida)
async def listar_conversas(
    tenant_id: UUID,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA_PADRAO, ge=1, le=POR_PAGINA_MAXIMO),
    usuario: Usuario = Depends(usuario_autenticado),
    conversas: SqlConversaRepository = Depends(get_conversa_repo),
) -> ConversasPaginaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    resultado = await ListarConversasDaEscola(conversas=conversas).executar(
        tenant_id=tenant_id, pagina=pagina, por_pagina=por_pagina
    )
    itens = [
        ConversaResumoSaida(
            id=r.conversa.id,
            contato=r.conversa.contato,
            criado_em=r.conversa.criado_em,
            total_mensagens=r.total_mensagens,
            ultima_mensagem=r.ultima_mensagem,
            ultima_em=r.ultima_em,
            encerrada_em=r.conversa.encerrada_em,
        )
        for r in resultado.itens
    ]
    return ConversasPaginaSaida(itens=itens, meta=_meta(resultado))


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
        encerrada_em=resultado.conversa.encerrada_em,
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


@router.get("/escolas/{tenant_id}/broadcasts", response_model=BroadcastsPaginaSaida)
async def listar_broadcasts(
    tenant_id: UUID,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA_PADRAO, ge=1, le=POR_PAGINA_MAXIMO),
    usuario: Usuario = Depends(usuario_autenticado),
    broadcasts: SqlBroadcastRepository = Depends(get_broadcast_repo),
    session: AsyncSession = Depends(get_session),
) -> BroadcastsPaginaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    resultado = await ListarBroadcastsDaEscola(
        broadcasts=broadcasts, templates=SqlTemplateRepository(session)
    ).executar(tenant_id=tenant_id, pagina=pagina, por_pagina=por_pagina)
    itens = [
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
        for item in resultado.itens
    ]
    return BroadcastsPaginaSaida(itens=itens, meta=_meta(resultado))


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
@router.get("/escolas/{tenant_id}/auditoria", response_model=AuditoriaPaginaSaida)
async def listar_auditoria(
    tenant_id: UUID,
    pagina: int = Query(1, ge=1),
    por_pagina: int = Query(POR_PAGINA_PADRAO, ge=1, le=POR_PAGINA_MAXIMO),
    usuario: Usuario = Depends(usuario_autenticado),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
    usuarios: SqlUsuarioRepository = Depends(get_usuario_repo),
) -> AuditoriaPaginaSaida:
    """Log de auditoria da escola: ações de usuários logados e da LLM (mais recentes primeiro)."""
    _exige_acesso_tenant(usuario, tenant_id)
    resultado = await ListarAuditoria(auditoria=auditoria, usuarios=usuarios).executar(
        tenant_id=tenant_id, pagina=pagina, por_pagina=por_pagina
    )
    itens = [
        RegistroAuditoriaSaida(
            id=r.id,
            tenant_id=r.tenant_id,
            ator=r.ator.value,
            ator_id=r.ator_id,
            ator_nome=r.ator_nome,
            ator_perfil_id=r.ator_perfil_id,
            acao=r.acao,
            descricao=r.descricao,
            metadados=r.metadados,
            criado_em=r.criado_em,
        )
        for r in resultado.itens
    ]
    return AuditoriaPaginaSaida(itens=itens, meta=_meta(resultado))
