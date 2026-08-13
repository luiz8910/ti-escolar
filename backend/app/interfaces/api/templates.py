"""Rotas do catálogo de templates (HSM).

**Dois escopos com donos diferentes** (§9a): o template **global** é do catálogo
compartilhado e só o super admin mexe — a WABA é ativo comum a todas as escolas, e deixar
uma escola alterar o que as outras usam seria dar a ela uma alavanca sobre o canal delas.
O template **da escola** é criado pelo admin dela, com o nome prefixado pelo slug, de modo
que o estrago (nome ocupado, rejeição) fica contido.

A submissão é síncrona só até a Meta aceitar **receber** o template; a aprovação é
assíncrona e chega pelo webhook. Por isso nenhuma rota aqui devolve "pronto para usar" —
quem responde isso é ``status``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.templates_use_cases import (
    CatalogoIndisponivelEmTodasAsContas,
    CriarTemplate,
    ListarTemplates,
    ObterTemplate,
    PermissaoTemplateNegada,
    RemoverTemplate,
    ReplicarTemplates,
    SemContaWhatsApp,
    SincronizarTemplates,
    TemplateNaoEncontrado,
)
from app.application.validacao_template import TemplateInvalido
from app.domain.entities import CategoriaTemplate, MessageTemplate, Usuario, Waba
from app.infrastructure.channel.meta_templates import CatalogoTemplatesIndisponivel
from app.infrastructure.db.repositories import SqlTemplateRepository, SqlWabaRepository
from app.interfaces.api.admin import (
    _exige_acesso_tenant,
    _exige_super_admin,
    usuario_autenticado,
)
from app.interfaces.deps import (
    get_criar_template,
    get_remover_template,
    get_replicar_templates,
    get_sincronizar_templates,
    get_template_repo,
    get_waba_repo,
)
from app.interfaces.dto import (
    ReplicacaoTemplatesSaida,
    SincronizacaoTemplatesSaida,
    TemplateEntrada,
    TemplateNaWabaSaida,
    TemplateSaida,
)

router = APIRouter(prefix="/api/admin/templates", tags=["templates"])


def _saida(template: MessageTemplate, contas: dict[UUID, Waba]) -> TemplateSaida:
    return TemplateSaida(
        id=template.id,
        tenant_id=template.tenant_id,
        escopo=template.escopo,
        nome=template.nome,
        categoria=template.categoria.value,
        idioma=template.idioma,
        corpo=template.corpo,
        status=template.status.value,
        utilizavel=template.utilizavel,
        contas=[
            TemplateNaWabaSaida(
                waba_id=entrada.waba_id,
                # A conta pode ter sido removida depois da submissão; o nome cru evita
                # que a linha suma da tela sem explicação.
                waba_nome=contas[entrada.waba_id].nome
                if entrada.waba_id in contas
                else "conta removida",
                status=entrada.status.value,
                meta_template_id=entrada.meta_template_id,
                motivo_rejeicao=entrada.motivo_rejeicao,
                atualizado_em=entrada.atualizado_em,
            )
            for entrada in template.wabas
        ],
        exemplos=list(template.exemplos),
        criado_em=template.criado_em,
        atualizado_em=template.atualizado_em,
    )


async def _contas(wabas: SqlWabaRepository) -> dict[UUID, Waba]:
    """Índice das contas para nomear as entradas. Uma consulta por requisição — são
    poucas linhas, e o alternativo seria um SELECT por template na listagem."""
    return {c.id: c for c in await wabas.listar()}


def _categoria(bruto: str) -> CategoriaTemplate:
    try:
        return CategoriaTemplate((bruto or "").lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Categoria de template inválida: {bruto!r}.",
        ) from exc


@router.get("", response_model=list[TemplateSaida])
async def listar_templates(
    tenant_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    templates: SqlTemplateRepository = Depends(get_template_repo),
    wabas: SqlWabaRepository = Depends(get_waba_repo),
) -> list[TemplateSaida]:
    _exige_acesso_tenant(solicitante, tenant_id)
    encontrados = await ListarTemplates(templates=templates).executar(tenant_id=tenant_id)
    contas = await _contas(wabas)
    return [_saida(t, contas) for t in encontrados]


@router.get("/{template_id}", response_model=TemplateSaida)
async def obter_template(
    template_id: UUID,
    tenant_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    templates: SqlTemplateRepository = Depends(get_template_repo),
    wabas: SqlWabaRepository = Depends(get_waba_repo),
) -> TemplateSaida:
    _exige_acesso_tenant(solicitante, tenant_id)
    try:
        template = await ObterTemplate(templates=templates).executar(
            tenant_id=tenant_id, template_id=template_id
        )
    except TemplateNaoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _saida(template, await _contas(wabas))


@router.post("", response_model=TemplateSaida, status_code=status.HTTP_201_CREATED)
async def criar_template(
    payload: TemplateEntrada,
    solicitante: Usuario = Depends(usuario_autenticado),
    uc: CriarTemplate = Depends(get_criar_template),
    wabas: SqlWabaRepository = Depends(get_waba_repo),
) -> TemplateSaida:
    if payload.tenant_id is not None:
        _exige_acesso_tenant(solicitante, payload.tenant_id)
    try:
        template = await uc.executar(
            usuario=solicitante,
            nome=payload.nome,
            corpo=payload.corpo,
            categoria=_categoria(payload.categoria),
            exemplos=payload.exemplos,
            idioma=payload.idioma,
            tenant_id=payload.tenant_id,
        )
    except PermissaoTemplateNegada as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TemplateInvalido as exc:
        # 422 e não 400: é o corpo que não passa nas regras da Meta, e a mensagem já vem
        # escrita para a secretaria ler.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except TemplateNaoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except SemContaWhatsApp as exc:
        # 409 e não 502: nada falhou do lado da Meta — falta cadastro nosso, e quem lê
        # precisa saber que a correção é no painel, não uma tentativa de novo.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (CatalogoTemplatesIndisponivel, CatalogoIndisponivelEmTodasAsContas) as exc:
        # 502: quem recusou foi a Meta (ou falta configuração nossa para falar com ela).
        # 400 daria a entender que o texto está errado, que é justamente o que não é.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return _saida(template, await _contas(wabas))


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_template(
    template_id: UUID,
    tenant_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    uc: RemoverTemplate = Depends(get_remover_template),
) -> None:
    _exige_acesso_tenant(solicitante, tenant_id)
    try:
        await uc.executar(
            usuario=solicitante, tenant_id=tenant_id, template_id=template_id
        )
    except PermissaoTemplateNegada as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except TemplateNaoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except CatalogoTemplatesIndisponivel as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.post("/sincronizar", response_model=SincronizacaoTemplatesSaida)
async def sincronizar_templates(
    solicitante: Usuario = Depends(usuario_autenticado),
    uc: SincronizarTemplates = Depends(get_sincronizar_templates),
) -> SincronizacaoTemplatesSaida:
    # Super admin: a sincronização é cross-tenant por natureza (percorre todas as contas)
    # e um admin de escola não deveria conseguir mexer no status dos templates das outras.
    _exige_super_admin(solicitante)
    try:
        resultado = await uc.executar()
    except CatalogoTemplatesIndisponivel as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return SincronizacaoTemplatesSaida(
        verificados=resultado.verificados,
        atualizados=resultado.atualizados,
        desconhecidos=resultado.desconhecidos,
    )


@router.post("/replicar", response_model=ReplicacaoTemplatesSaida)
async def replicar_templates(
    solicitante: Usuario = Depends(usuario_autenticado),
    uc: ReplicarTemplates = Depends(get_replicar_templates),
) -> ReplicacaoTemplatesSaida:
    """Leva os templates globais para as contas que ainda não os têm.

    O passo obrigatório depois de cadastrar uma conta nova: sem ele, as escolas dela ficam
    sem nenhum template aprovado e o primeiro disparo é que descobre.
    """
    _exige_super_admin(solicitante)
    try:
        resultado = await uc.executar()
    except SemContaWhatsApp as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except CatalogoTemplatesIndisponivel as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return ReplicacaoTemplatesSaida(
        submetidos=resultado.submetidos,
        falhas=resultado.falhas,
        ja_existiam=resultado.ja_existiam,
    )
