"""Documentos que os responsáveis enviam pelo WhatsApp (§6k).

O que se testa aqui é o que protege a escola e o responsável: a **allowlist de MIME** e o
**teto de tamanho** (o inbound é público — quem descobre o número manda o que quiser), a
**deduplicação** da reentrega do webhook, o **isolamento entre escolas** e o **expurgo por
prazo de retenção**, que é o que impede um repositório de atestado médico de criança de
virar passivo permanente.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.application.atendimento_humano_use_cases import MesaDeAtendimento
from app.application.documentos_use_cases import (
    BaixarDocumentoRecebido,
    ClassificarDocumento,
    ExpurgarDocumentosVencidos,
    ListarDocumentosRecebidos,
    ReceberDocumentoDoResponsavel,
    ReceberMidiaDoResponsavel,
    sugerir_categoria,
)
from app.application.inbound_use_cases import ProcessarInboundMeta
from app.application.use_cases import AtenderConversa, RecuperarEEnviarDocumento
from app.domain.entities import (
    TAMANHO_MAXIMO_DOCUMENTO,
    ArquivoBaixado,
    AtendimentoHumano,
    CategoriaDocumento,
    Contato,
    StatusAtendimentoHumano,
    StatusDocumento,
    Tenant,
)
from app.infrastructure.storage import ArquivoStorageMemoria
from tests.fakes import (
    FakeAtendimentoHumanoRepo,
    FakeChannel,
    FakeContatoRepo,
    FakeConversaRepo,
    FakeDocumentoRecebidoRepo,
    FakeDocumentSource,
    FakeFonteMidia,
    FakeLLM,
    FakeTenantRepo,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()
CONTATO = "+5515999998888"
PID = "111111111111111"

JPEG = ArquivoBaixado(conteudo=b"\xff\xd8\xff" + b"x" * 500, mime="image/jpeg")
PDF = ArquivoBaixado(conteudo=b"%PDF-1.4" + b"y" * 900, mime="application/pdf", nome="rg.pdf")


def _escola() -> Tenant:
    return Tenant(
        id=TENANT, nome="EM Rosa Cury", slug="rosa-cury", meta_phone_number_id=PID
    )


def _recepcao(repo=None, storage=None, contatos=None, retencao_dias=365):
    return ReceberDocumentoDoResponsavel(
        documentos=repo or FakeDocumentoRecebidoRepo(),
        storage=storage or ArquivoStorageMemoria(),
        contatos=contatos,
        retencao_dias=retencao_dias,
    )


# --------------------------------------------------------------------------- #
# Sugestão de finalidade (heurística, sem LLM)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "legenda,esperado",
    [
        ("segue o atestado do João", CategoriaDocumento.ATESTADO),
        ("foto do RG dele", CategoriaDocumento.MATRICULA),
        ("comprovante do pix da APM", CategoriaDocumento.COMPROVANTE),
        ("oi, tudo bem?", None),
        ("", None),
    ],
)
def test_sugestao_de_categoria_pela_legenda(legenda, esperado):
    assert sugerir_categoria(legenda) is esperado


# --------------------------------------------------------------------------- #
# Recepção: allowlist, teto e dedupe
# --------------------------------------------------------------------------- #
async def test_arquivo_valido_e_guardado_com_prazo_de_retencao():
    repo, storage = FakeDocumentoRecebidoRepo(), ArquivoStorageMemoria()
    contatos = FakeContatoRepo()
    await contatos.criar(Contato(tenant_id=TENANT, nome="Maria Souza", telefone=CONTATO))

    resultado = await _recepcao(repo, storage, contatos).executar(
        tenant_id=TENANT,
        conversa_id=uuid.uuid4(),
        contato=CONTATO,
        arquivo=JPEG,
        media_id="mid.1",
        legenda="atestado do João",
    )

    doc = resultado.documento
    assert resultado.aceito
    assert doc.contato_nome == "Maria Souza"
    assert doc.categoria is CategoriaDocumento.ATESTADO
    assert doc.categoria_sugerida is CategoriaDocumento.ATESTADO
    # Prazo obrigatório: sem ele o atestado ficaria guardado para sempre.
    assert doc.expira_em is not None and doc.expira_em > datetime.now(timezone.utc)
    # Os bytes vão para o storage, nunca para o metadado.
    assert await storage.ler(chave=doc.chave_storage) == JPEG.conteudo


async def test_tipo_fora_da_allowlist_e_recusado():
    # O inbound é público: quem descobre o número da escola manda o que quiser.
    storage = ArquivoStorageMemoria()
    executavel = ArquivoBaixado(conteudo=b"MZ...", mime="application/x-msdownload")

    resultado = await _recepcao(storage=storage).executar(
        tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=executavel
    )

    assert resultado.documento is None
    assert "tipo não aceito" in resultado.recusado
    assert storage.arquivos == {}  # nada foi gravado


async def test_arquivo_acima_do_teto_e_recusado():
    storage = ArquivoStorageMemoria()
    gigante = ArquivoBaixado(
        conteudo=b"x" * (TAMANHO_MAXIMO_DOCUMENTO + 1), mime="application/pdf"
    )

    resultado = await _recepcao(storage=storage).executar(
        tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=gigante
    )

    assert resultado.documento is None
    assert "grande demais" in resultado.recusado
    assert storage.arquivos == {}


async def test_arquivo_vazio_e_recusado():
    resultado = await _recepcao().executar(
        tenant_id=TENANT,
        conversa_id=uuid.uuid4(),
        contato=CONTATO,
        arquivo=ArquivoBaixado(conteudo=b"", mime="image/png"),
    )
    assert resultado.documento is None


async def test_reentrega_do_webhook_nao_duplica_o_arquivo():
    repo, storage = FakeDocumentoRecebidoRepo(), ArquivoStorageMemoria()
    uc = _recepcao(repo, storage)
    conversa = uuid.uuid4()

    primeiro = await uc.executar(
        tenant_id=TENANT, conversa_id=conversa, contato=CONTATO, arquivo=JPEG, media_id="mid.7"
    )
    segundo = await uc.executar(
        tenant_id=TENANT, conversa_id=conversa, contato=CONTATO, arquivo=JPEG, media_id="mid.7"
    )

    assert segundo.duplicado
    assert segundo.documento.id == primeiro.documento.id
    assert len(repo.itens) == 1
    assert len(storage.arquivos) == 1


# --------------------------------------------------------------------------- #
# Download, classificação e isolamento
# --------------------------------------------------------------------------- #
async def test_download_devolve_os_bytes_guardados():
    repo, storage = FakeDocumentoRecebidoRepo(), ArquivoStorageMemoria()
    doc = (
        await _recepcao(repo, storage).executar(
            tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=PDF
        )
    ).documento

    arquivo = await BaixarDocumentoRecebido(documentos=repo, storage=storage).executar(
        tenant_id=TENANT, documento_id=doc.id
    )

    assert arquivo.conteudo == PDF.conteudo
    assert arquivo.mime == "application/pdf"
    assert arquivo.nome == "rg.pdf"


async def test_download_de_outra_escola_nao_entrega_nada():
    repo, storage = FakeDocumentoRecebidoRepo(), ArquivoStorageMemoria()
    doc = (
        await _recepcao(repo, storage).executar(
            tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=JPEG
        )
    ).documento

    assert (
        await BaixarDocumentoRecebido(documentos=repo, storage=storage).executar(
            tenant_id=OUTRO_TENANT, documento_id=doc.id
        )
        is None
    )


async def test_arquivo_ja_expurgado_nao_entrega_bytes():
    # Metadado sem conteúdo: o download precisa recusar, e não devolver vazio.
    repo, storage = FakeDocumentoRecebidoRepo(), ArquivoStorageMemoria()
    doc = (
        await _recepcao(repo, storage).executar(
            tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=JPEG
        )
    ).documento
    await storage.remover(chave=doc.chave_storage)

    assert (
        await BaixarDocumentoRecebido(documentos=repo, storage=storage).executar(
            tenant_id=TENANT, documento_id=doc.id
        )
        is None
    )


async def test_classificar_marca_processado_e_registra_a_data():
    repo = FakeDocumentoRecebidoRepo()
    doc = (
        await _recepcao(repo).executar(
            tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=JPEG
        )
    ).documento

    atualizado = await ClassificarDocumento(documentos=repo).executar(
        tenant_id=TENANT,
        documento_id=doc.id,
        categoria=CategoriaDocumento.MATRICULA,
        status=StatusDocumento.PROCESSADO,
    )

    assert atualizado.categoria is CategoriaDocumento.MATRICULA
    assert atualizado.status is StatusDocumento.PROCESSADO
    assert atualizado.processado_em is not None


async def test_listagem_e_escopada_por_escola():
    repo = FakeDocumentoRecebidoRepo()
    await _recepcao(repo).executar(
        tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=JPEG
    )

    minha = await ListarDocumentosRecebidos(documentos=repo).executar(tenant_id=TENANT)
    alheia = await ListarDocumentosRecebidos(documentos=repo).executar(
        tenant_id=OUTRO_TENANT
    )
    assert minha.total == 1
    assert alheia.total == 0


# --------------------------------------------------------------------------- #
# Expurgo (LGPD)
# --------------------------------------------------------------------------- #
async def test_expurgo_apaga_bytes_e_metadado_do_que_venceu():
    repo, storage = FakeDocumentoRecebidoRepo(), ArquivoStorageMemoria()
    vencido = (
        await _recepcao(repo, storage, retencao_dias=0).executar(
            tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=JPEG
        )
    ).documento
    vigente = (
        await _recepcao(repo, storage, retencao_dias=365).executar(
            tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=PDF
        )
    ).documento

    resultado = await ExpurgarDocumentosVencidos(documentos=repo, storage=storage).executar()

    assert resultado.removidos == 1
    # Apaga os dois: manter "havia um atestado do aluno X" sem o arquivo continuaria
    # sendo tratamento de dado sensível, só que inútil.
    assert vencido.id not in repo.itens
    assert await storage.ler(chave=vencido.chave_storage) is None
    assert vigente.id in repo.itens
    assert await storage.ler(chave=vigente.chave_storage) is not None


async def test_expurgo_continua_apos_falha_em_um_arquivo():
    class StorageQueFalha(ArquivoStorageMemoria):
        async def remover(self, *, chave):
            raise RuntimeError("objeto travado no storage")

    repo, storage = FakeDocumentoRecebidoRepo(), StorageQueFalha()
    for _ in range(3):
        await _recepcao(repo, storage, retencao_dias=0).executar(
            tenant_id=TENANT, conversa_id=uuid.uuid4(), contato=CONTATO, arquivo=JPEG
        )

    resultado = await ExpurgarDocumentosVencidos(documentos=repo, storage=storage).executar()

    # Um item problemático não pode congelar a rotina e deixar o passivo crescer calado.
    assert resultado.falhas == 3
    assert resultado.removidos == 0


# --------------------------------------------------------------------------- #
# Orquestração do inbound
# --------------------------------------------------------------------------- #
def _midias(fonte, repo=None, storage=None, conversas=None, mesa=None):
    return ReceberMidiaDoResponsavel(
        fonte=fonte,
        recepcao=_recepcao(repo, storage),
        conversas=conversas or FakeConversaRepo(),
        mesa=mesa,
    )


async def test_recebimento_confirma_ao_responsavel_e_entra_na_conversa():
    conversas = FakeConversaRepo()
    repo = FakeDocumentoRecebidoRepo()
    uc = _midias(FakeFonteMidia({"mid.1": JPEG}), repo, conversas=conversas)

    resposta = await uc.executar(
        tenant_id=TENANT, contato=CONTATO, media_id="mid.1", legenda="atestado do João"
    )

    assert "Recebemos o seu arquivo" in resposta
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    autores = [m["autor"] for m in conversas.mensagens[conversa.id]]
    assert autores == ["usuario", "bot"]
    assert len(repo.itens) == 1


async def test_falha_no_download_pede_reenvio_em_outro_formato():
    conversas = FakeConversaRepo()
    uc = _midias(FakeFonteMidia({}), conversas=conversas)

    resposta = await uc.executar(tenant_id=TENANT, contato=CONTATO, media_id="mid.perdida")

    assert "reenvie" in resposta.lower()
    # O histórico registra a tentativa mesmo sem o arquivo — é o que permite cobrar.
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    assert len(conversas.mensagens[conversa.id]) == 2


async def test_reentrega_nao_confirma_de_novo():
    # Confirmar duas vezes faria o responsável achar que enviou o documento em duplicidade.
    conversas = FakeConversaRepo()
    repo = FakeDocumentoRecebidoRepo()
    fonte = FakeFonteMidia({"mid.9": PDF})
    uc = _midias(fonte, repo, conversas=conversas)

    primeira = await uc.executar(tenant_id=TENANT, contato=CONTATO, media_id="mid.9")
    segunda = await uc.executar(tenant_id=TENANT, contato=CONTATO, media_id="mid.9")

    assert primeira
    assert segunda == ""
    assert len(repo.itens) == 1


async def test_arquivo_e_amarrado_ao_atendimento_aberto():
    # Quem está atendendo não deveria ter de procurar o documento em outra tela.
    conversas = FakeConversaRepo()
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    fila = FakeAtendimentoHumanoRepo()
    atendimento = await fila.criar(
        AtendimentoHumano(
            tenant_id=TENANT,
            conversa_id=conversa.id,
            contato=CONTATO,
            status=StatusAtendimentoHumano.EM_ATENDIMENTO,
            ultima_mensagem_responsavel_em=datetime.now(timezone.utc) - timedelta(hours=20),
        )
    )
    repo = FakeDocumentoRecebidoRepo()
    mesa = MesaDeAtendimento(atendimentos=fila, tenants=FakeTenantRepo([_escola()]))

    await _midias(
        FakeFonteMidia({"mid.5": PDF}), repo, conversas=conversas, mesa=mesa
    ).executar(tenant_id=TENANT, contato=CONTATO, media_id="mid.5")

    [documento] = list(repo.itens.values())
    assert documento.atendimento_id == atendimento.id
    # Enviar arquivo é atividade do responsável: renova a janela de 24h de quem responde.
    assert fila.itens[atendimento.id].janela_aberta()


# --------------------------------------------------------------------------- #
# Webhook: o envelope de mídia da Meta
# --------------------------------------------------------------------------- #
class CanalEspiao:
    def __init__(self) -> None:
        self.textos: list[dict] = []

    async def enviar_texto(self, *, contato, texto, remetente=None) -> str:
        self.textos.append({"contato": contato, "texto": texto, "remetente": remetente})
        return "wamid.r"

    async def enviar_template(self, **kw) -> str:
        return "x"

    async def enviar_documento(self, **kw) -> str:
        return "x"


class FakeTenantRepoInbound:
    def __init__(self, tenants) -> None:
        self.tenants = tenants

    async def por_meta_phone_number_id(self, phone_number_id):
        return next(
            (t for t in self.tenants if t.meta_phone_number_id == phone_number_id), None
        )


def _payload(tipo: str, corpo: dict, *, wamid="wamid.M") -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": PID},
                            "messages": [
                                {
                                    "id": wamid,
                                    "from": "5515999998888",
                                    "type": tipo,
                                    tipo: corpo,
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }


def _inbound(fonte, repo, conversas):
    atender = AtenderConversa(
        conversas=conversas,
        embedder=fake_embedder(),
        store=FakeVectorStore(),
        llm=FakeLLM(),
        documentos=RecuperarEEnviarDocumento(
            source=FakeDocumentSource([]), canal=FakeChannel()
        ),
    )
    canal = CanalEspiao()
    uc = ProcessarInboundMeta(
        tenants=FakeTenantRepoInbound([_escola()]),
        atender=atender,
        canal=canal,
        midias=_midias(fonte, repo, conversas=conversas),
    )
    return uc, canal


async def test_webhook_com_imagem_guarda_o_arquivo_e_responde():
    repo, conversas = FakeDocumentoRecebidoRepo(), FakeConversaRepo()
    uc, canal = _inbound(FakeFonteMidia({"mid.img": JPEG}), repo, conversas)

    resultado = await uc.executar(
        payload=_payload("image", {"id": "mid.img", "caption": "atestado do João"})
    )

    assert resultado.documentos == 1
    assert resultado.respondidas == 1
    assert len(repo.itens) == 1
    assert "Recebemos" in canal.textos[0]["texto"]
    # Sai pelo número da própria escola (multi-tenant).
    assert canal.textos[0]["remetente"] == PID


async def test_webhook_com_documento_preserva_o_nome_do_arquivo():
    repo, conversas = FakeDocumentoRecebidoRepo(), FakeConversaRepo()
    uc, _ = _inbound(FakeFonteMidia({"mid.pdf": PDF}), repo, conversas)

    await uc.executar(
        payload=_payload(
            "document", {"id": "mid.pdf", "filename": "rg.pdf", "caption": "documento"}
        )
    )

    [documento] = list(repo.itens.values())
    assert documento.nome_arquivo == "rg.pdf"


async def test_audio_continua_ignorado():
    # Sem transcrição, áudio é um arquivo que alguém precisa parar para ouvir.
    repo, conversas = FakeDocumentoRecebidoRepo(), FakeConversaRepo()
    uc, canal = _inbound(FakeFonteMidia({"mid.ogg": JPEG}), repo, conversas)

    resultado = await uc.executar(payload=_payload("audio", {"id": "mid.ogg"}))

    assert resultado.ignoradas == 1
    assert resultado.documentos == 0
    assert repo.itens == {}
    assert canal.textos == []


async def test_texto_continua_indo_para_o_assistente():
    repo, conversas = FakeDocumentoRecebidoRepo(), FakeConversaRepo()
    uc, canal = _inbound(FakeFonteMidia({}), repo, conversas)

    resultado = await uc.executar(
        payload={
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "metadata": {"phone_number_id": PID},
                                "messages": [
                                    {
                                        "id": "wamid.T",
                                        "from": "5515999998888",
                                        "type": "text",
                                        "text": {"body": "Qual o horário?"},
                                    }
                                ],
                            }
                        }
                    ]
                }
            ]
        }
    )

    assert resultado.documentos == 0
    assert resultado.respondidas == 1
    assert repo.itens == {}
