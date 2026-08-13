"""Anti-spam e leitura por IA dos documentos recebidos (§4.5 e §4.3, Fase 4 de 10/08).

O inbound é **público**: quem descobre o número da escola manda o que quiser. As defesas
que existiam olhavam o envelope (MIME, 16 MB) — nenhuma olhava de quem vinha nem quantas
vezes.

O que se testa aqui é o equilíbrio: barrar spam **sem** perder o documento de um pai que
trocou de número, e sem bloquear ninguém em silêncio.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.application.documentos_use_cases import (
    BloquearNumero,
    DesbloquearNumero,
    LerDocumentoPorIA,
    ReceberDocumentoDoResponsavel,
    SugerirBloqueios,
)
from app.domain.entities import (
    DESCARTES_PARA_SUGERIR_BLOQUEIO,
    ArquivoBaixado,
    CategoriaDocumento,
    Contato,
    DocumentoRecebido,
    StatusDocumento,
)
from app.infrastructure.llm.leitor_documento import (
    LeitorDocumentoFake,
    montar_documento_lido,
)
from app.infrastructure.storage import ArquivoStorageMemoria
from tests.fakes import (
    FakeContatoRepo,
    FakeDocumentoRecebidoRepo,
    FakeNumeroBloqueadoRepo,
)

TENANT = uuid.uuid4()
CONVERSA = uuid.uuid4()
CONHECIDO = "+5515999990001"
DESCONHECIDO = "+5515900000000"
JPEG = ArquivoBaixado(conteudo=b"\xff\xd8\xffdados", mime="image/jpeg", nome="foto.jpg")


async def _cenario():
    documentos = FakeDocumentoRecebidoRepo()
    storage = ArquivoStorageMemoria()
    contatos = FakeContatoRepo()
    bloqueios = FakeNumeroBloqueadoRepo()
    await contatos.criar(Contato(tenant_id=TENANT, nome="Mãe Conhecida", telefone=CONHECIDO))
    receber = ReceberDocumentoDoResponsavel(
        documentos=documentos, storage=storage, contatos=contatos, bloqueios=bloqueios
    )
    return receber, documentos, storage, bloqueios


async def _receber(receber, contato=CONHECIDO, **kwargs):
    return await receber.executar(
        tenant_id=TENANT, conversa_id=CONVERSA, contato=contato, arquivo=JPEG, **kwargs
    )


# --------------------- camada 1: quarentena por origem --------------------- #
async def test_documento_de_numero_cadastrado_entra_na_fila():
    receber, *_ = await _cenario()
    resultado = await _receber(receber)
    assert resultado.documento.status is StatusDocumento.RECEBIDO


async def test_documento_de_numero_desconhecido_vai_para_quarentena():
    """Fora da fila de trabalho — mas guardado."""
    receber, *_ = await _cenario()
    resultado = await _receber(receber, contato=DESCONHECIDO)
    assert resultado.documento.status is StatusDocumento.QUARENTENA


async def test_quarentena_guarda_o_arquivo():
    """Descartar de saída perderia o documento de um pai que trocou de número — que é
    justamente quem mais precisa dele."""
    receber, _, storage, _ = await _cenario()
    resultado = await _receber(receber, contato=DESCONHECIDO)
    assert resultado.recusado == ""
    assert await storage.ler(chave=resultado.documento.chave_storage) == JPEG.conteudo


# --------------------- camada 2: bloqueio (sempre humano) ------------------- #
async def test_numero_bloqueado_nao_manda_arquivo():
    receber, _, storage, bloqueios = await _cenario()
    await BloquearNumero(bloqueios=bloqueios).executar(
        tenant_id=TENANT, telefone=DESCONHECIDO, motivo="propaganda", por="Secretaria"
    )

    resultado = await _receber(receber, contato=DESCONHECIDO)

    assert resultado.documento is None
    assert "bloqueado" in resultado.recusado
    # E nada foi gravado: o bloqueio corta antes de guardar bytes de quem a escola recusou.
    assert storage.arquivos == {}


async def test_bloqueio_nao_afeta_os_outros_numeros():
    receber, *_rest = await _cenario()
    bloqueios = _rest[-1]
    await BloquearNumero(bloqueios=bloqueios).executar(
        tenant_id=TENANT, telefone=DESCONHECIDO
    )
    resultado = await _receber(receber, contato=CONHECIDO)
    assert resultado.documento is not None


async def test_desbloquear_devolve_o_envio():
    receber, _, _, bloqueios = await _cenario()
    await BloquearNumero(bloqueios=bloqueios).executar(
        tenant_id=TENANT, telefone=DESCONHECIDO
    )
    await DesbloquearNumero(bloqueios=bloqueios).executar(
        tenant_id=TENANT, telefone=DESCONHECIDO
    )
    resultado = await _receber(receber, contato=DESCONHECIDO)
    assert resultado.documento is not None


async def test_bloquear_duas_vezes_atualiza_o_motivo():
    """A secretaria pode clicar duas vezes, ou revisar o motivo depois."""
    _, _, _, bloqueios = await _cenario()
    uc = BloquearNumero(bloqueios=bloqueios)
    await uc.executar(tenant_id=TENANT, telefone=DESCONHECIDO, motivo="primeiro")
    segundo = await uc.executar(tenant_id=TENANT, telefone=DESCONHECIDO, motivo="segundo")
    assert segundo.motivo == "segundo"
    assert len(await bloqueios.listar(tenant_id=TENANT)) == 1


async def test_bloquear_sem_numero_e_recusado():
    _, _, _, bloqueios = await _cenario()
    with pytest.raises(ValueError):
        await BloquearNumero(bloqueios=bloqueios).executar(tenant_id=TENANT, telefone="  ")


# --------------------- a sugestão (decisão C: 3 em 7 dias) ------------------ #
def _descartado(contato: str, *, dias_atras: int = 0) -> DocumentoRecebido:
    return DocumentoRecebido(
        tenant_id=TENANT,
        conversa_id=CONVERSA,
        contato=contato,
        chave_storage="x",
        mime="image/jpeg",
        tamanho=10,
        status=StatusDocumento.DESCARTADO,
        criado_em=datetime.now(timezone.utc) - timedelta(days=dias_atras),
    )


async def _com_descartes(documentos, contato, quantos, *, dias_atras=0):
    for _ in range(quantos):
        await documentos.criar(_descartado(contato, dias_atras=dias_atras))


async def test_sugere_bloqueio_no_limiar():
    _, documentos, _, bloqueios = await _cenario()
    await _com_descartes(documentos, DESCONHECIDO, DESCARTES_PARA_SUGERIR_BLOQUEIO)

    sugestoes = await SugerirBloqueios(
        documentos=documentos, bloqueios=bloqueios
    ).executar(tenant_id=TENANT)

    assert [s.telefone for s in sugestoes] == [DESCONHECIDO]
    assert sugestoes[0].descartados == DESCARTES_PARA_SUGERIR_BLOQUEIO


async def test_abaixo_do_limiar_nao_sugere():
    """Dois descartes é um pai com foto tremida, não spam."""
    _, documentos, _, bloqueios = await _cenario()
    await _com_descartes(documentos, DESCONHECIDO, DESCARTES_PARA_SUGERIR_BLOQUEIO - 1)

    sugestoes = await SugerirBloqueios(
        documentos=documentos, bloqueios=bloqueios
    ).executar(tenant_id=TENANT)

    assert sugestoes == []


async def test_descartes_fora_da_janela_nao_contam():
    """Três descartes espalhados por meses não são reincidência."""
    _, documentos, _, bloqueios = await _cenario()
    await _com_descartes(
        documentos, DESCONHECIDO, DESCARTES_PARA_SUGERIR_BLOQUEIO, dias_atras=30
    )

    sugestoes = await SugerirBloqueios(
        documentos=documentos, bloqueios=bloqueios
    ).executar(tenant_id=TENANT)

    assert sugestoes == []


async def test_quem_ja_esta_bloqueado_nao_vira_sugestao():
    """Seria pedir à secretaria que decidisse duas vezes a mesma coisa."""
    _, documentos, _, bloqueios = await _cenario()
    await _com_descartes(documentos, DESCONHECIDO, DESCARTES_PARA_SUGERIR_BLOQUEIO)
    await BloquearNumero(bloqueios=bloqueios).executar(
        tenant_id=TENANT, telefone=DESCONHECIDO
    )

    sugestoes = await SugerirBloqueios(
        documentos=documentos, bloqueios=bloqueios
    ).executar(tenant_id=TENANT)

    assert sugestoes == []


async def test_sugerir_nao_bloqueia_sozinho():
    """O ponto da decisão C: a aplicação sugere, a pessoa decide."""
    receber, documentos, _, bloqueios = await _cenario()
    await _com_descartes(documentos, DESCONHECIDO, DESCARTES_PARA_SUGERIR_BLOQUEIO + 5)

    await SugerirBloqueios(documentos=documentos, bloqueios=bloqueios).executar(
        tenant_id=TENANT
    )

    assert await bloqueios.listar(tenant_id=TENANT) == []
    # E o número segue conseguindo enviar, porque ninguém decidiu nada ainda.
    assert (await _receber(receber, contato=DESCONHECIDO)).documento is not None


# --------------------- §4.3 leitura por IA (prévia) ------------------------ #
def test_leitura_valida_em_codigo_a_categoria_do_modelo():
    """A LLM não é fonte de verdade — categoria desconhecida vira None em vez de estourar,
    para o palpite errado não esconder o resto do que ela leu."""
    lido = montar_documento_lido(
        {"categoria": "boleto_de_luz", "resumo": "Documento", "aluno_nome": "Ana"}
    )
    assert lido.categoria is None
    assert lido.resumo == "Documento"
    assert lido.aluno_nome == "Ana"


def test_leitura_aceita_categoria_conhecida():
    lido = montar_documento_lido({"categoria": "atestado"})
    assert lido.categoria is CategoriaDocumento.ATESTADO


def test_leitura_ignora_campos_de_ficha_vazios():
    lido = montar_documento_lido(
        {"campos_ficha": {"cpf": "123", "ra_rm": "", "sexo": None}}
    )
    assert lido.campos_ficha == {"cpf": "123"}


async def test_ler_documento_nao_grava_nada():
    """Prévia, não gravação: quem grava é a classificação, com o que a secretaria aprovou."""
    receber, documentos, storage, _ = await _cenario()
    recebido = (await _receber(receber)).documento

    lido = await LerDocumentoPorIA(
        documentos=documentos, storage=storage, leitor=LeitorDocumentoFake()
    ).executar(tenant_id=TENANT, documento_id=recebido.id)

    assert lido.categoria is CategoriaDocumento.ATESTADO
    # O documento no repositório continua com a categoria original.
    guardado = await documentos.obter(tenant_id=TENANT, documento_id=recebido.id)
    assert guardado.categoria == recebido.categoria


async def test_ler_documento_de_outra_escola_nao_devolve_nada():
    receber, documentos, storage, _ = await _cenario()
    recebido = (await _receber(receber)).documento

    lido = await LerDocumentoPorIA(
        documentos=documentos, storage=storage, leitor=LeitorDocumentoFake()
    ).executar(tenant_id=uuid.uuid4(), documento_id=recebido.id)

    assert lido is None


async def test_ler_documento_ja_expurgado_avisa_em_vez_de_quebrar():
    """O metadado sobrevive aos bytes por desenho (§6k)."""
    receber, documentos, storage, _ = await _cenario()
    recebido = (await _receber(receber)).documento
    await storage.remover(chave=recebido.chave_storage)

    lido = await LerDocumentoPorIA(
        documentos=documentos, storage=storage, leitor=LeitorDocumentoFake()
    ).executar(tenant_id=TENANT, documento_id=recebido.id)

    assert lido.erro
    assert lido.vazio
