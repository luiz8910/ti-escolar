"""Contas do WhatsApp Business (WABA) — cadastro do super admin.

Poucas linhas na tabela e raras mutações: uma conta nova a cada lote de escolas. Ainda
assim tem tela e API porque o alternativo é `INSERT` à mão no banco de produção, no dia em
que a conta seguinte precisa entrar — e esse dia é justamente o de pressa.

**Só super admin.** A conta é ativo compartilhado entre escolas: quem pode editá-la pode
redirecionar o catálogo de templates de todas as outras.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.domain.entities import Usuario, Waba
from app.infrastructure.db.repositories import SqlWabaRepository
from app.interfaces.api.admin import _exige_super_admin, usuario_autenticado
from app.interfaces.deps import get_waba_repo
from app.interfaces.dto import WabaEntrada, WabaSaida

router = APIRouter(prefix="/api/admin/wabas", tags=["wabas"])


def _saida(waba: Waba, total_escolas: int) -> WabaSaida:
    return WabaSaida(
        id=waba.id,
        nome=waba.nome,
        meta_waba_id=waba.meta_waba_id,
        meta_business_id=waba.meta_business_id,
        ativo=waba.ativo,
        total_escolas=total_escolas,
        criado_em=waba.criado_em,
        atualizado_em=waba.atualizado_em,
    )


@router.get("", response_model=list[WabaSaida])
async def listar_wabas(
    solicitante: Usuario = Depends(usuario_autenticado),
    wabas: SqlWabaRepository = Depends(get_waba_repo),
) -> list[WabaSaida]:
    _exige_super_admin(solicitante)
    contagem = await wabas.total_escolas()
    return [_saida(w, contagem.get(w.id, 0)) for w in await wabas.listar()]


@router.post("", response_model=WabaSaida, status_code=status.HTTP_201_CREATED)
async def criar_waba(
    payload: WabaEntrada,
    solicitante: Usuario = Depends(usuario_autenticado),
    wabas: SqlWabaRepository = Depends(get_waba_repo),
) -> WabaSaida:
    _exige_super_admin(solicitante)
    nome = payload.nome.strip()
    if not nome:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="A conta precisa de um nome para ser reconhecida no painel.",
        )
    meta_waba_id = _normalizar_id(payload.meta_waba_id)
    if meta_waba_id and await wabas.por_meta_id(meta_waba_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Já existe uma conta cadastrada com este id da Meta.",
        )
    criada = await wabas.salvar(
        Waba(
            meta_waba_id=meta_waba_id,
            nome=nome,
            meta_business_id=_normalizar_id(payload.meta_business_id),
            ativo=payload.ativo,
        )
    )
    return _saida(criada, 0)


@router.put("/{waba_id}", response_model=WabaSaida)
async def atualizar_waba(
    waba_id: UUID,
    payload: WabaEntrada,
    solicitante: Usuario = Depends(usuario_autenticado),
    wabas: SqlWabaRepository = Depends(get_waba_repo),
) -> WabaSaida:
    _exige_super_admin(solicitante)
    conta = await wabas.obter(waba_id)
    if conta is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada."
        )
    meta_waba_id = _normalizar_id(payload.meta_waba_id)
    if meta_waba_id:
        outra = await wabas.por_meta_id(meta_waba_id)
        if outra is not None and outra.id != waba_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Já existe uma conta cadastrada com este id da Meta.",
            )
    conta.nome = payload.nome.strip() or conta.nome
    conta.meta_waba_id = meta_waba_id
    conta.meta_business_id = _normalizar_id(payload.meta_business_id)
    conta.ativo = payload.ativo
    salva = await wabas.salvar(conta)
    contagem = await wabas.total_escolas()
    return _saida(salva, contagem.get(salva.id, 0))


@router.delete("/{waba_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_waba(
    waba_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    wabas: SqlWabaRepository = Depends(get_waba_repo),
) -> None:
    """Remove a conta — **recusado** enquanto houver escola nela.

    Apagar arrastaria as escolas para ``waba_id = NULL`` (a FK não é cascata) e, com elas,
    o endereço do catálogo: o disparo por template pararia sem nada dizer o porquê. Quem
    quer parar de usar uma conta a **desativa**.
    """
    _exige_super_admin(solicitante)
    contagem = await wabas.total_escolas()
    if contagem.get(waba_id, 0) > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Esta conta ainda atende {contagem[waba_id]} escola(s). Mova-as para "
                "outra conta antes de remover, ou apenas desative esta."
            ),
        )
    if not await wabas.remover(waba_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Conta não encontrada."
        )


def _normalizar_id(bruto: str) -> str:
    """Ids da Meta são numéricos; guardar com espaço ou traço quebra a URL da Graph API."""
    return "".join(c for c in (bruto or "") if c.isdigit())
