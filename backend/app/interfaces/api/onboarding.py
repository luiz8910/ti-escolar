"""Onboarding do WhatsApp de uma escola — as rotas do roteiro de go-live (§9e.3).

Cada rota aqui é **um passo do console da Meta** que deixou de precisar do console. A
ordem é a que a Meta impõe e não é negociável: cadastrar → pedir código → confirmar →
inscrever. O diagnóstico (`GET`) diz em qual delas a escola está, perguntando à Meta.

**Só super admin.** O teto de números é do portfólio (§9e.3): cadastrar um número consome
a vaga da escola seguinte, e o número vive numa conta compartilhada por todas. Não é
operação de tenant.

**Erros da Meta chegam como 502, não 500.** A distinção importa para quem opera: 502 com
a frase que a Meta escreveu ("número já em uso", "chip ainda ativo no WhatsApp") é um
próximo passo; 500 é um chamado para nós.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.application.onboarding_use_cases import (
    CadastrarNumeroDaEscola,
    ConcluirOnboardingDaEscola,
    ConfirmarCodigoDeVerificacao,
    DesvincularNumeroDaEscola,
    DiagnosticarWhatsAppDaEscola,
    DiagnosticoWhatsApp,
    EscolaNaoEncontrada,
    InscreverNumeroNaCloudApi,
    OnboardingRecusado,
    PedirCodigoDeVerificacao,
    PermissaoOnboardingNegada,
)
from app.domain.entities import NumeroNaMeta, Usuario
from app.infrastructure.channel.meta_numeros import ProvisionamentoIndisponivel
from app.interfaces.api.admin import usuario_autenticado
from app.interfaces.deps import (
    get_cadastrar_numero,
    get_concluir_onboarding,
    get_confirmar_codigo,
    get_desvincular_numero,
    get_diagnostico_whatsapp,
    get_inscrever_numero,
    get_pedir_codigo,
)
from app.interfaces.dto import (
    CadastroNumeroEntrada,
    CodigoVerificacaoEntrada,
    ConclusaoOnboardingSaida,
    ConfirmacaoCodigoEntrada,
    DiagnosticoWhatsAppSaida,
    NumeroNaMetaSaida,
    PassoOnboardingSaida,
    RegistroNumeroEntrada,
)

logger = logging.getLogger("onboarding.api")
router = APIRouter(prefix="/api/admin/escolas/{tenant_id}/whatsapp", tags=["onboarding"])


def _numero_saida(numero: NumeroNaMeta | None) -> NumeroNaMetaSaida | None:
    if numero is None:
        return None
    return NumeroNaMetaSaida(
        phone_number_id=numero.phone_number_id,
        numero_exibicao=numero.numero_exibicao,
        nome_exibicao=numero.nome_exibicao,
        etapa=numero.etapa.value,
        status_nome=numero.status_nome,
        qualidade=numero.qualidade,
        bruto=numero.bruto,
        pronto_para_atender=numero.pronto_para_atender,
    )


def _diagnostico_saida(d: DiagnosticoWhatsApp) -> DiagnosticoWhatsAppSaida:
    return DiagnosticoWhatsAppSaida(
        tenant_id=d.tenant_id,
        escola=d.escola,
        canal=d.canal,
        conta_id=d.conta.id if d.conta else None,
        conta_nome=d.conta.nome if d.conta else "",
        meta_waba_id=d.conta.meta_waba_id if d.conta else "",
        numero=_numero_saida(d.numero),
        passos=[
            PassoOnboardingSaida(
                chave=p.chave,
                titulo=p.titulo,
                concluido=p.concluido,
                detalhe=p.detalhe,
                acao=p.acao,
                manual=p.manual,
            )
            for p in d.passos
        ],
        pronta=d.pronta,
    )


def _traduzir(erro: Exception) -> HTTPException:
    """Converte as exceções do caso de uso em status que dizem de quem é o problema."""
    if isinstance(erro, PermissaoOnboardingNegada):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(erro))
    if isinstance(erro, EscolaNaoEncontrada):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(erro))
    if isinstance(erro, OnboardingRecusado):
        # Pré-condição nossa: falta escolher a conta, o número já existe, etc.
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(erro))
    if isinstance(erro, ProvisionamentoIndisponivel):
        # A Meta recusou (ou o canal está em demo). 502 diz "o problema é lá fora", e o
        # detalhe carrega a frase que a Meta escreveu — que é o próximo passo de quem opera.
        return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(erro))
    raise erro


@router.get("", response_model=DiagnosticoWhatsAppSaida)
async def diagnosticar(
    tenant_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    caso: DiagnosticarWhatsAppDaEscola = Depends(get_diagnostico_whatsapp),
) -> DiagnosticoWhatsAppSaida:
    """O que falta para esta escola atender no WhatsApp — conferido **contra a Meta**."""
    try:
        return _diagnostico_saida(
            await caso.executar(solicitante=solicitante, tenant_id=tenant_id)
        )
    except Exception as erro:  # noqa: BLE001 — `_traduzir` re-levanta o que não conhece
        raise _traduzir(erro) from erro


@router.post("/numero", response_model=NumeroNaMetaSaida, status_code=status.HTTP_201_CREATED)
async def cadastrar_numero(
    tenant_id: UUID,
    payload: CadastroNumeroEntrada,
    solicitante: Usuario = Depends(usuario_autenticado),
    caso: CadastrarNumeroDaEscola = Depends(get_cadastrar_numero),
) -> NumeroNaMetaSaida:
    """Cria o número na conta da escola e grava o ``phone_number_id`` no tenant.

    Os dois juntos de propósito: cadastrar na Meta e esquecer de colar o id aqui produz um
    número conectado cujo inbound é descartado em silêncio.
    """
    try:
        criado = await caso.executar(
            solicitante=solicitante,
            tenant_id=tenant_id,
            numero_e164=payload.numero_e164,
            nome_exibicao=payload.nome_exibicao,
        )
    except Exception as erro:  # noqa: BLE001
        raise _traduzir(erro) from erro
    saida = _numero_saida(criado)
    assert saida is not None
    return saida


@router.post("/codigo", response_model=NumeroNaMetaSaida | None)
async def pedir_codigo(
    tenant_id: UUID,
    payload: CodigoVerificacaoEntrada,
    solicitante: Usuario = Depends(usuario_autenticado),
    caso: PedirCodigoDeVerificacao = Depends(get_pedir_codigo),
) -> NumeroNaMetaSaida | None:
    """Dispara o código de 6 dígitos para o chip (SMS ou ligação).

    ⚠️ **Não repita à toa.** A Meta trava a verificação por horas depois de alguns
    reenvios falhos, e é justamente a tentativa seguinte que se perde. Duas falhas ⇒
    esperar (docs/producao-whatsapp.md §2.1).
    """
    try:
        return _numero_saida(
            await caso.executar(
                solicitante=solicitante,
                tenant_id=tenant_id,
                metodo=payload.metodo,
                idioma=payload.idioma,
            )
        )
    except Exception as erro:  # noqa: BLE001
        raise _traduzir(erro) from erro


@router.post("/verificar", response_model=NumeroNaMetaSaida)
async def confirmar_codigo(
    tenant_id: UUID,
    payload: ConfirmacaoCodigoEntrada,
    solicitante: Usuario = Depends(usuario_autenticado),
    caso: ConfirmarCodigoDeVerificacao = Depends(get_confirmar_codigo),
) -> NumeroNaMetaSaida:
    """Confere o código recebido no chip. Verificado ≠ registrado — falta o passo seguinte."""
    try:
        saida = _numero_saida(
            await caso.executar(
                solicitante=solicitante, tenant_id=tenant_id, codigo=payload.codigo
            )
        )
    except Exception as erro:  # noqa: BLE001
        raise _traduzir(erro) from erro
    assert saida is not None
    return saida


@router.post("/registrar", response_model=NumeroNaMetaSaida)
async def registrar_numero(
    tenant_id: UUID,
    payload: RegistroNumeroEntrada,
    solicitante: Usuario = Depends(usuario_autenticado),
    caso: InscreverNumeroNaCloudApi = Depends(get_inscrever_numero),
) -> NumeroNaMetaSaida:
    """Inscreve o número na Cloud API com o PIN de duas etapas — é aqui que ele passa a falar.

    O PIN **não é guardado** por nós: a Meta o exige de novo para reinscrever o número e
    não o exibe outra vez. Gerenciador de senhas, não banco.
    """
    try:
        saida = _numero_saida(
            await caso.executar(
                solicitante=solicitante, tenant_id=tenant_id, pin=payload.pin
            )
        )
    except Exception as erro:  # noqa: BLE001
        raise _traduzir(erro) from erro
    assert saida is not None
    return saida


@router.post("/concluir", response_model=ConclusaoOnboardingSaida)
async def concluir(
    tenant_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    caso: ConcluirOnboardingDaEscola = Depends(get_concluir_onboarding),
) -> ConclusaoOnboardingSaida:
    """Inscreve a conta no app e replica os templates globais nela.

    Os dois passos sem tela no console — e sem os quais a escola nasce com o webhook mudo
    (§5.1) e sem nenhum template aprovado (§7). Idempotente: pode ser clicado de novo.
    """
    try:
        resultado = await caso.executar(solicitante=solicitante, tenant_id=tenant_id)
    except Exception as erro:  # noqa: BLE001
        raise _traduzir(erro) from erro
    return ConclusaoOnboardingSaida(
        conta_inscrita_no_app=resultado.conta_inscrita_no_app,
        templates_submetidos=resultado.templates_submetidos,
        templates_ja_existiam=resultado.templates_ja_existiam,
        templates_com_falha=resultado.templates_com_falha,
        perfil_atualizado=resultado.perfil_atualizado,
        avisos=resultado.avisos,
    )


@router.delete("/numero", status_code=status.HTTP_204_NO_CONTENT)
async def desvincular_numero(
    tenant_id: UUID,
    solicitante: Usuario = Depends(usuario_autenticado),
    caso: DesvincularNumeroDaEscola = Depends(get_desvincular_numero),
) -> None:
    """Solta o ``phone_number_id`` do tenant — **sem tocar na Meta**.

    Para o caso de o id ter sido cadastrado na escola errada. Não desregistra o número:
    um ``deregister`` por engano derruba o canal de uma escola em produção, e essa decisão
    fica no console, com a fricção que ele impõe.
    """
    try:
        await caso.executar(solicitante=solicitante, tenant_id=tenant_id)
    except Exception as erro:  # noqa: BLE001
        raise _traduzir(erro) from erro
