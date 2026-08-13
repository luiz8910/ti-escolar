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
    CriarTemplate,
    ListarTemplates,
    ObterTemplate,
    PermissaoTemplateNegada,
    RemoverTemplate,
    SincronizarTemplates,
    TemplateNaoEncontrado,
)
from app.application.validacao_template import TemplateInvalido
from app.domain.entities import CategoriaTemplate, MessageTemplate, Usuario
from app.infrastructure.channel.meta_templates import CatalogoTemplatesIndisponivel
from app.infrastructure.db.repositories import SqlTemplateRepository
from app.interfaces.api.admin import (
    _exige_acesso_tenant,
    _exige_super_admin,
    usuario_autenticado,
)
from app.interfaces.deps import (
    get_criar_template,
    get_remover_template,
    get_sincronizar_templates,
    get_template_repo,
)
from app.interfaces.dto import (
    SincronizacaoTemplatesSaida,
    TemplateEntrada,
    TemplateSaida,
)

router = APIRouter(prefix="/api/admin/templates", tags=["templates"])


def _saida(template: MessageTemplate) -> TemplateSaida:
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
        meta_template_id=template.meta_template_id,
        motivo_rejeicao=template.motivo_rejeicao,
        exemplos=list(template.exemplos),
        criado_em=template.criado_em,
        atualizado_em=template.atualizado_em,
    )


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
) -> list[TemplateSaida]:
    _exige_acesso_tenant(solicitante, tenant_id)
    encontrados = await ListarTemplates(templates=templates).executar(tenant_id=tenant_id)
    return [_saida(t) for t in encontrados]


@router.get("/{template_id}", response_model=TemplateSaida)
async def obter_template(
    template_id: UUID,
    tenant_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    templates: SqlTemplateRepository = Depends(get_template_repo),
) -> TemplateSaida:
    _exige_acesso_tenant(solicitante, tenant_id)
    try:
        template = await ObterTemplate(templates=templates).executar(
            tenant_id=tenant_id, template_id=template_id
        )
    except TemplateNaoEncontrado as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _saida(template)


@router.post("", response_model=TemplateSaida, status_code=status.HTTP_201_CREATED)
async def criar_template(
    payload: TemplateEntrada,
    solicitante: Usuario = Depends(usuario_autenticado),
    uc: CriarTemplate = Depends(get_criar_template),
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
    except CatalogoTemplatesIndisponivel as exc:
        # 502: quem recusou foi a Meta (ou falta configuração nossa para falar com ela).
        # 400 daria a entender que o texto está errado, que é justamente o que não é.
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    return _saida(template)


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
    # Super admin: a sincronização é cross-tenant por natureza (a WABA é uma só) e um
    # admin de escola não deveria conseguir mexer no status dos templates das outras.
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
