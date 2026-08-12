"""Rotas dos documentos que os responsáveis enviam pelo WhatsApp (§6k).

**O download é o ponto sensível desta rota.** O conteúdo é dado pessoal de criança e, com
frequência, dado de saúde (atestado — LGPD arts. 11 e 14). Daí três escolhas:

- não existe URL pública nem link assinado de longa duração: os bytes saem por este
  endpoint, autenticado e escopado por tenant, ou não saem;
- **todo download é auditado** (§13) — quem baixou o quê, quando;
- a resposta vai como ``attachment`` com ``no-store``, para o arquivo não ficar em cache
  de proxy nem de navegador compartilhado da secretaria.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.application.documentos_use_cases import (
    BaixarDocumentoRecebido,
    BloquearNumero,
    DesbloquearNumero,
    LerDocumentoPorIA,
    ListarNumerosBloqueados,
    SugerirBloqueios,
    ClassificarDocumento,
    ExpurgarDocumentosVencidos,
    ListarDocumentosRecebidos,
    ObterDocumentoRecebido,
)
from app.application.paginacao import POR_PAGINA_PADRAO
from app.domain.entities import (
    CategoriaDocumento,
    DocumentoRecebido,
    StatusDocumento,
    Usuario,
)
from app.infrastructure.db.repositories_admin import (
    SqlAlunoRepository,
    SqlAuditLogRepository,
)
from app.infrastructure.db.repositories_comunicacao import (
    SqlDocumentoRecebidoRepository,
    SqlNumeroBloqueadoRepository,
)
from app.interfaces.api.admin import (
    _auditar_usuario,
    _exige_acesso_tenant,
    _exige_super_admin,
    usuario_autenticado,
)
from app.interfaces.deps import (
    get_aluno_repo,
    get_bloqueio_repo,
    get_ler_documento_ia,
    get_audit_repo,
    get_baixar_documento,
    get_documento_repo,
    get_expurgar_documentos,
)
from app.interfaces.dto import (
    DocumentoClassificacaoEntrada,
    DocumentoLidoSaida,
    DocumentoRecebidoSaida,
    DocumentosPaginaSaida,
    DocumentosPendentesSaida,
    ExpurgoSaida,
    NumeroBloqueadoEntrada,
    NumeroBloqueadoSaida,
    SugestaoBloqueioSaida,
    PaginaMeta,
)

router = APIRouter(prefix="/api/admin/documentos", tags=["documentos-recebidos"])


def _saida(d: DocumentoRecebido) -> DocumentoRecebidoSaida:
    return DocumentoRecebidoSaida(
        id=d.id,
        conversa_id=d.conversa_id,
        contato=d.contato,
        contato_nome=d.contato_nome,
        nome_arquivo=d.nome_arquivo,
        mime=d.mime,
        tamanho=d.tamanho,
        tamanho_legivel=d.tamanho_legivel,
        eh_imagem=d.eh_imagem,
        observacao=d.observacao,
        categoria=d.categoria.value,
        categoria_sugerida=d.categoria_sugerida.value if d.categoria_sugerida else None,
        status=d.status.value,
        aluno_id=d.aluno_id,
        aluno_nome=d.aluno_nome,
        atendimento_id=d.atendimento_id,
        expira_em=d.expira_em,
        processado_em=d.processado_em,
        criado_em=d.criado_em,
    )


def _enum(valor: str | None, tipo, rotulo: str):
    if not valor:
        return None
    try:
        return tipo(valor)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{rotulo} inválido: {valor}"
        ) from e


@router.get("/tenant/{tenant_id}", response_model=DocumentosPaginaSaida)
async def listar(
    tenant_id: UUID,
    categoria: str = Query(""),
    status_filtro: str = Query("", alias="status"),
    aluno_id: UUID | None = None,
    pagina: int = 1,
    por_pagina: int = POR_PAGINA_PADRAO,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlDocumentoRecebidoRepository = Depends(get_documento_repo),
) -> DocumentosPaginaSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    resultado = await ListarDocumentosRecebidos(documentos=repo).executar(
        tenant_id=tenant_id,
        categoria=_enum(categoria, CategoriaDocumento, "Categoria"),
        status=_enum(status_filtro, StatusDocumento, "Status"),
        aluno_id=aluno_id,
        pagina=pagina,
        por_pagina=por_pagina,
    )
    return DocumentosPaginaSaida(
        itens=[_saida(d) for d in resultado.itens],
        meta=PaginaMeta(
            pagina=resultado.pagina,
            por_pagina=resultado.por_pagina,
            total=resultado.total,
            total_paginas=resultado.total_paginas,
        ),
    )


@router.get("/tenant/{tenant_id}/pendentes", response_model=DocumentosPendentesSaida)
async def pendentes(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlDocumentoRecebidoRepository = Depends(get_documento_repo),
) -> DocumentosPendentesSaida:
    """Quantos documentos estão **a conferir**. Consultado em polling pela central de
    notificações, por isso devolve só o número — a listagem é outra rota."""
    _exige_acesso_tenant(usuario, tenant_id)
    total = await repo.contar(tenant_id=tenant_id, status=StatusDocumento.RECEBIDO)
    return DocumentosPendentesSaida(pendentes=total)


@router.get("/{documento_id}", response_model=DocumentoRecebidoSaida)
async def detalhar(
    documento_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlDocumentoRecebidoRepository = Depends(get_documento_repo),
) -> DocumentoRecebidoSaida:
    _exige_acesso_tenant(usuario, tenant_id)
    documento = await ObterDocumentoRecebido(documentos=repo).executar(
        tenant_id=tenant_id, documento_id=documento_id
    )
    if documento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado"
        )
    return _saida(documento)


@router.get("/{documento_id}/arquivo", response_class=Response)
async def baixar(
    documento_id: UUID,
    tenant_id: UUID,
    inline: bool = False,
    usuario: Usuario = Depends(usuario_autenticado),
    uc: BaixarDocumentoRecebido = Depends(get_baixar_documento),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> Response:
    """Os bytes do arquivo. Autenticado, escopado por tenant e **auditado**.

    ``inline=true`` troca o ``Content-Disposition`` para exibição — é o preview pedido no
    apontamento de 10/08 ("preview da imagem e não apenas baixar"). **Só isso muda**:
    autenticação, escopo por tenant, ``no-store`` e auditoria continuam valendo, porque
    visualizar *é* acessar o dado. O registro passa a distinguir `documento.visualizar` de
    `documento.baixar` — sem essa distinção, a auditoria diria que a secretaria baixou
    trinta atestados numa tarde em que ela só olhou a tela.
    """
    _exige_acesso_tenant(usuario, tenant_id)
    arquivo = await uc.executar(tenant_id=tenant_id, documento_id=documento_id)
    if arquivo is None:
        # Cobre as duas causas com a mesma resposta: documento de outra escola e arquivo
        # já expurgado. Distinguir revelaria a existência do documento a quem não deveria.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Arquivo não disponível"
        )
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="documento.visualizar" if inline else "documento.baixar",
        tenant_id=tenant_id,
        descricao=("Visualizou" if inline else "Baixou") + f" o arquivo {arquivo.nome}",
        metadados={"documento_id": str(documento_id), "mime": arquivo.mime},
    )
    disposicao = "inline" if inline else "attachment"
    return Response(
        content=arquivo.conteudo,
        media_type=arquivo.mime,
        headers={
            "Content-Disposition": f'{disposicao}; filename="{arquivo.nome}"',
            # Dado sensível não fica em cache de proxy nem do navegador da secretaria.
            "Cache-Control": "no-store",
        },
    )


@router.post("/{documento_id}/ler", response_model=DocumentoLidoSaida)
async def ler_por_ia(
    documento_id: UUID,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    uc: LerDocumentoPorIA = Depends(get_ler_documento_ia),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> DocumentoLidoSaida:
    """Lê o documento por IA e devolve **sugestões** — nada é gravado (§4.3).

    Sob demanda, a pedido da secretaria: em época de matrícula o volume é alto e a maioria
    dos documentos ela classifica de olho. Auditado como acesso ao conteúdo, porque é
    exatamente isso — o arquivo sai do storage e vai para um provedor externo.
    """
    _exige_acesso_tenant(usuario, tenant_id)
    lido = await uc.executar(tenant_id=tenant_id, documento_id=documento_id)
    if lido is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Documento não encontrado"
        )
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="documento.ler_ia",
        tenant_id=tenant_id,
        descricao="Pediu a leitura do documento por IA",
        metadados={"documento_id": str(documento_id), "erro": lido.erro},
    )
    return DocumentoLidoSaida(
        categoria=lido.categoria.value if lido.categoria else "",
        aluno_nome=lido.aluno_nome,
        resumo=lido.resumo,
        campos_ficha=lido.campos_ficha,
        erro=lido.erro,
    )


# --------------------------------------------------------------------------- #
# §4.5 — anti-spam. A aplicação **sugere**; quem bloqueia é uma pessoa.
# --------------------------------------------------------------------------- #
@router.get("/tenant/{tenant_id}/sugestoes-bloqueio", response_model=list[SugestaoBloqueioSaida])
async def sugestoes_bloqueio(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlDocumentoRecebidoRepository = Depends(get_documento_repo),
    bloqueios: SqlNumeroBloqueadoRepository = Depends(get_bloqueio_repo),
) -> list[SugestaoBloqueioSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    sugestoes = await SugerirBloqueios(documentos=repo, bloqueios=bloqueios).executar(
        tenant_id=tenant_id
    )
    return [
        SugestaoBloqueioSaida(
            telefone=s.telefone,
            descartados=s.descartados,
            contato_nome=s.contato_nome,
            ultimo_em=s.ultimo_em,
        )
        for s in sugestoes
    ]


@router.get("/tenant/{tenant_id}/bloqueados", response_model=list[NumeroBloqueadoSaida])
async def listar_bloqueados(
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    bloqueios: SqlNumeroBloqueadoRepository = Depends(get_bloqueio_repo),
) -> list[NumeroBloqueadoSaida]:
    _exige_acesso_tenant(usuario, tenant_id)
    return [
        NumeroBloqueadoSaida(
            telefone=b.telefone,
            motivo=b.motivo,
            bloqueado_por=b.bloqueado_por,
            bloqueado_em=b.bloqueado_em,
        )
        for b in await ListarNumerosBloqueados(bloqueios=bloqueios).executar(
            tenant_id=tenant_id
        )
    ]


@router.post("/bloqueados", response_model=NumeroBloqueadoSaida, status_code=status.HTTP_201_CREATED)
async def bloquear_numero(
    payload: NumeroBloqueadoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    bloqueios: SqlNumeroBloqueadoRepository = Depends(get_bloqueio_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> NumeroBloqueadoSaida:
    """Recusa **mídia** deste número. O texto continua sendo atendido, e o remetente é
    avisado — bloquear alguém por completo com base num contador é o erro que o produto
    existe para evitar."""
    _exige_acesso_tenant(usuario, payload.tenant_id)
    try:
        bloqueio = await BloquearNumero(bloqueios=bloqueios).executar(
            tenant_id=payload.tenant_id,
            telefone=payload.telefone,
            motivo=payload.motivo,
            por=usuario.nome,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="documento.bloquear_numero",
        tenant_id=payload.tenant_id,
        descricao=f"Bloqueou envio de arquivos de {payload.telefone}",
        metadados={"telefone": payload.telefone, "motivo": payload.motivo},
    )
    return NumeroBloqueadoSaida(
        telefone=bloqueio.telefone,
        motivo=bloqueio.motivo,
        bloqueado_por=bloqueio.bloqueado_por,
        bloqueado_em=bloqueio.bloqueado_em,
    )


@router.delete("/bloqueados/{telefone}", status_code=status.HTTP_204_NO_CONTENT)
async def desbloquear_numero(
    telefone: str,
    tenant_id: UUID,
    usuario: Usuario = Depends(usuario_autenticado),
    bloqueios: SqlNumeroBloqueadoRepository = Depends(get_bloqueio_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> None:
    _exige_acesso_tenant(usuario, tenant_id)
    if not await DesbloquearNumero(bloqueios=bloqueios).executar(
        tenant_id=tenant_id, telefone=telefone
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Número não estava bloqueado"
        )
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="documento.desbloquear_numero",
        tenant_id=tenant_id,
        descricao=f"Liberou envio de arquivos de {telefone}",
        metadados={"telefone": telefone},
    )


@router.put("/{documento_id}", response_model=DocumentoRecebidoSaida)
async def classificar(
    documento_id: UUID,
    tenant_id: UUID,
    payload: DocumentoClassificacaoEntrada,
    usuario: Usuario = Depends(usuario_autenticado),
    repo: SqlDocumentoRecebidoRepository = Depends(get_documento_repo),
    alunos: SqlAlunoRepository = Depends(get_aluno_repo),
    auditoria: SqlAuditLogRepository = Depends(get_audit_repo),
) -> DocumentoRecebidoSaida:
    """A secretaria confirma a finalidade, vincula o aluno e conclui o tratamento."""
    _exige_acesso_tenant(usuario, tenant_id)
    try:
        documento = await ClassificarDocumento(documentos=repo, alunos=alunos).executar(
            tenant_id=tenant_id,
            documento_id=documento_id,
            categoria=_enum(payload.categoria, CategoriaDocumento, "Categoria"),
            status=_enum(payload.status, StatusDocumento, "Status"),
            aluno_id=payload.aluno_id,
            observacao=payload.observacao,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    await _auditar_usuario(
        auditoria,
        usuario=usuario,
        acao="documento.classificar",
        tenant_id=tenant_id,
        descricao=f"Classificou o documento como {documento.categoria.value}",
        metadados={
            "documento_id": str(documento.id),
            "status": documento.status.value,
            "aluno_id": str(documento.aluno_id) if documento.aluno_id else None,
        },
    )
    return _saida(documento)


@router.post("/expurgar", response_model=ExpurgoSaida)
async def expurgar(
    usuario: Usuario = Depends(usuario_autenticado),
    uc: ExpurgarDocumentosVencidos = Depends(get_expurgar_documentos),
) -> ExpurgoSaida:
    """Apaga os arquivos cujo prazo de retenção venceu (LGPD).

    Cross-tenant, por isso é do super admin: retenção é política da plataforma, não de uma
    escola. **[Roadmap]** chamar isto por job agendado — hoje depende de alguém clicar.
    """
    _exige_super_admin(usuario)
    resultado = await uc.executar()
    return ExpurgoSaida(removidos=resultado.removidos, falhas=resultado.falhas)
