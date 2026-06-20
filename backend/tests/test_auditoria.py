"""Observabilidade / histórico: auditoria de ações e detalhe de disparos.

Cobre: registro e consulta do log de auditoria (escopado por tenant), a auditoria
automática da LLM ao atender uma conversa, e o histórico de disparos com nome do
template e do responsável por destinatário.
"""

from __future__ import annotations

import uuid

from app.application.auditoria_use_cases import ListarAuditoria, RegistrarAuditoria
from app.application.tenant_use_cases import (
    ListarBroadcastsDaEscola,
    ObterBroadcastDaEscola,
)
from app.application.use_cases import AtenderConversa, RecuperarEEnviarDocumento
from app.domain.entities import (
    AtorAuditoria,
    Broadcast,
    CategoriaTemplate,
    Contato,
    DestinatarioBroadcast,
    MessageTemplate,
    RespostaLLM,
    StatusEntrega,
    StatusTemplate,
    TipoConhecimento,
    TrechoConhecimento,
)
from tests.fakes import (
    FakeAuditLogRepo,
    FakeBroadcastRepo,
    FakeChannel,
    FakeContatoRepo,
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeTemplateRepo,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()


# --------------------------------------------------------------------------- #
# Registro e consulta do log de auditoria
# --------------------------------------------------------------------------- #
async def test_registrar_e_listar_escopado_por_tenant():
    repo = FakeAuditLogRepo()
    registrar = RegistrarAuditoria(auditoria=repo)

    await registrar.executar(
        ator=AtorAuditoria.USUARIO, acao="login", tenant_id=TENANT, ator_nome="Ana"
    )
    await registrar.executar(
        ator=AtorAuditoria.USUARIO, acao="grupo.criar", tenant_id=OUTRO_TENANT
    )

    registros = await ListarAuditoria(auditoria=repo).executar(tenant_id=TENANT)
    assert [r.acao for r in registros] == ["login"]
    assert registros[0].ator_nome == "Ana"


async def test_listar_ordena_mais_recentes_primeiro_e_respeita_limite():
    repo = FakeAuditLogRepo()
    registrar = RegistrarAuditoria(auditoria=repo)
    for i in range(5):
        await registrar.executar(
            ator=AtorAuditoria.USUARIO, acao=f"acao{i}", tenant_id=TENANT
        )

    registros = await ListarAuditoria(auditoria=repo).executar(tenant_id=TENANT, limite=2)
    assert len(registros) == 2
    # Os mais recentes (acao4, acao3) vêm primeiro.
    assert registros[0].acao == "acao4"
    assert registros[1].acao == "acao3"


class _RepoQuebrado:
    async def registrar(self, registro):
        raise RuntimeError("falha de persistência")

    async def listar(self, *, tenant_id, limite=200):
        return []


async def test_registrar_nao_propaga_falha():
    # Auditar não pode derrubar a ação de negócio: a falha é engolida.
    resultado = await RegistrarAuditoria(auditoria=_RepoQuebrado()).executar(
        ator=AtorAuditoria.USUARIO, acao="login", tenant_id=TENANT
    )
    assert resultado is None


# --------------------------------------------------------------------------- #
# Auditoria automática da LLM ao atender uma conversa
# --------------------------------------------------------------------------- #
async def _store_com_trecho(titulo: str, conteudo: str) -> FakeVectorStore:
    store = FakeVectorStore()
    embedder = fake_embedder()
    trecho = TrechoConhecimento(
        tenant_id=TENANT, tipo=TipoConhecimento.FAQ, titulo=titulo, conteudo=conteudo
    )
    [emb] = await embedder.embed([f"{titulo}\n{conteudo}"])
    await store.indexar(trecho, emb)
    return store


async def test_atender_conversa_registra_auditoria_da_llm():
    store = await _store_com_trecho("Horário", "Das 7h às 12h.")
    auditoria = FakeAuditLogRepo()
    canal = FakeChannel()
    uc = AtenderConversa(
        conversas=FakeConversaRepo(),
        embedder=fake_embedder(),
        store=store,
        llm=FakeLLM([RespostaLLM(texto="A escola abre às 7h.")]),
        documentos=RecuperarEEnviarDocumento(source=FakeDocumentSource(), canal=canal),
        auditoria=auditoria,
    )

    await uc.executar(tenant_id=TENANT, contato="+5511999", texto="Qual o horário?")

    assert len(auditoria.registros) == 1
    reg = auditoria.registros[0]
    assert reg.ator == AtorAuditoria.LLM
    assert reg.acao == "llm.resposta"
    assert reg.tenant_id == TENANT
    assert reg.ator_id == "+5511999"
    assert reg.metadados["pergunta"] == "Qual o horário?"
    assert reg.metadados["resposta"] == "A escola abre às 7h."


async def test_atender_conversa_funciona_sem_auditoria():
    # ``auditoria`` é opcional: sem ela, o atendimento segue normalmente.
    uc = AtenderConversa(
        conversas=FakeConversaRepo(),
        embedder=fake_embedder(),
        store=FakeVectorStore(),
        llm=FakeLLM([RespostaLLM(texto="Olá!")]),
        documentos=RecuperarEEnviarDocumento(
            source=FakeDocumentSource(), canal=FakeChannel()
        ),
    )
    resp = await uc.executar(tenant_id=TENANT, contato="+5511999", texto="oi")
    assert resp.texto == "Olá!"


# --------------------------------------------------------------------------- #
# Histórico de disparos: template e detalhe por destinatário
# --------------------------------------------------------------------------- #
def _template() -> MessageTemplate:
    return MessageTemplate(
        tenant_id=TENANT,
        nome="aviso_reuniao",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá, {{1}}!",
        status=StatusTemplate.APROVADO,
    )


def _broadcast(template_id) -> Broadcast:
    return Broadcast(
        tenant_id=TENANT,
        template_id=template_id,
        titulo="Reunião de pais",
        destinatarios=[
            DestinatarioBroadcast(
                contato="+5511900000001",
                status=StatusEntrega.ENTREGUE,
            ),
            DestinatarioBroadcast(
                contato="+5511900000002",
                status=StatusEntrega.FALHOU,
            ),
        ],
    )


async def test_listar_broadcasts_resolve_nome_do_template():
    template = _template()
    repo = FakeBroadcastRepo()
    await repo.salvar(_broadcast(template.id))

    itens = await ListarBroadcastsDaEscola(
        broadcasts=repo, templates=FakeTemplateRepo(template)
    ).executar(tenant_id=TENANT)

    assert len(itens) == 1
    assert itens[0].template_nome == "aviso_reuniao"


async def test_obter_broadcast_traz_template_e_nome_do_responsavel():
    template = _template()
    broadcast = _broadcast(template.id)
    repo = FakeBroadcastRepo()
    await repo.salvar(broadcast)

    contatos = FakeContatoRepo()
    await contatos.criar(
        Contato(tenant_id=TENANT, nome="Maria", telefone="+5511900000001")
    )

    detalhe = await ObterBroadcastDaEscola(
        broadcasts=repo, contatos=contatos, templates=FakeTemplateRepo(template)
    ).executar(tenant_id=TENANT, broadcast_id=broadcast.id)

    assert detalhe is not None
    assert detalhe.template_nome == "aviso_reuniao"
    por_contato = {d.contato: d for d in detalhe.destinatarios}
    assert por_contato["+5511900000001"].nome == "Maria"
    assert por_contato["+5511900000001"].status == StatusEntrega.ENTREGUE
    assert por_contato["+5511900000002"].nome == ""  # sem contato cadastrado
    assert por_contato["+5511900000002"].status == StatusEntrega.FALHOU


async def test_obter_broadcast_isola_por_tenant():
    template = _template()
    broadcast = _broadcast(template.id)
    repo = FakeBroadcastRepo()
    await repo.salvar(broadcast)

    detalhe = await ObterBroadcastDaEscola(
        broadcasts=repo, contatos=FakeContatoRepo(), templates=FakeTemplateRepo(template)
    ).executar(tenant_id=OUTRO_TENANT, broadcast_id=broadcast.id)
    assert detalhe is None
