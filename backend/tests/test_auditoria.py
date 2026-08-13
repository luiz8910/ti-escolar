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
    Papel,
    RespostaLLM,
    StatusEntrega,
    StatusTemplate,
    TemplateNaWaba,
    TipoConhecimento,
    TrechoConhecimento,
    Usuario,
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
    WABA_PADRAO_ID,
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

    registros = (await ListarAuditoria(auditoria=repo).executar(tenant_id=TENANT)).itens
    assert [r.acao for r in registros] == ["login"]
    assert registros[0].ator_nome == "Ana"


async def test_listar_ordena_mais_recentes_primeiro_e_respeita_limite():
    repo = FakeAuditLogRepo()
    registrar = RegistrarAuditoria(auditoria=repo)
    for i in range(5):
        await registrar.executar(
            ator=AtorAuditoria.USUARIO, acao=f"acao{i}", tenant_id=TENANT
        )

    pagina = await ListarAuditoria(auditoria=repo).executar(
        tenant_id=TENANT, por_pagina=2
    )
    registros = pagina.itens
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
        wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
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

    itens = (
        await ListarBroadcastsDaEscola(
            broadcasts=repo, templates=FakeTemplateRepo(template)
        ).executar(tenant_id=TENANT)
    ).itens

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


# --------------------------------------------------------------------------- #
# Identificação do ator: nome atual + link para o perfil
# --------------------------------------------------------------------------- #
class FakeUsuarioRepoAuditoria:
    """Só o que a auditoria usa da porta: resolver vários usuários de uma vez."""

    def __init__(self, usuarios: list[Usuario]) -> None:
        self.usuarios = list(usuarios)
        self.consultas = 0

    async def por_ids(self, ids):
        self.consultas += 1
        pedidos = {str(i) for i in ids}
        return [u for u in self.usuarios if str(u.id) in pedidos]


def _usuario(nome: str) -> Usuario:
    return Usuario(
        nome=nome,
        email=f"{nome.lower()}@escola.test",
        senha_hash="x",
        papel=Papel.TENANT_ADMIN,
        tenant_id=TENANT,
    )


async def test_ator_e_reidentificado_pelo_cadastro_atual():
    """O nome gravado é retrato do momento; quem lê o log quer a pessoa de hoje."""
    ana = _usuario("Ana")
    repo = FakeAuditLogRepo()
    await RegistrarAuditoria(auditoria=repo).executar(
        ator=AtorAuditoria.USUARIO,
        acao="login",
        tenant_id=TENANT,
        ator_id=str(ana.id),
        ator_nome="Ana Souza",  # sobrenome de solteira, corrigido depois no cadastro
    )
    ana.nome = "Ana Souza Prado"

    registros = (
        await ListarAuditoria(
            auditoria=repo, usuarios=FakeUsuarioRepoAuditoria([ana])
        ).executar(tenant_id=TENANT)
    ).itens

    assert registros[0].ator_nome == "Ana Souza Prado"
    assert registros[0].ator_perfil_id == str(ana.id)


async def test_ator_sem_conta_nao_ganha_link():
    """Link para uma conta que não existe mais é pior do que texto puro."""
    repo = FakeAuditLogRepo()
    await RegistrarAuditoria(auditoria=repo).executar(
        ator=AtorAuditoria.USUARIO,
        acao="login",
        tenant_id=TENANT,
        ator_id=str(uuid.uuid4()),
        ator_nome="Quem Saiu",
    )

    registros = (
        await ListarAuditoria(
            auditoria=repo, usuarios=FakeUsuarioRepoAuditoria([])
        ).executar(tenant_id=TENANT)
    ).itens

    # O nome gravado sobrevive como fallback histórico; o link, não.
    assert registros[0].ator_nome == "Quem Saiu"
    assert registros[0].ator_perfil_id == ""


async def test_llm_nao_vira_perfil_e_nao_quebra_a_resolucao():
    """A LLM guarda **telefone** em `ator_id`: não é UUID, e isso não é erro."""
    repo = FakeAuditLogRepo()
    await RegistrarAuditoria(auditoria=repo).executar(
        ator=AtorAuditoria.LLM,
        acao="llm.resposta",
        tenant_id=TENANT,
        ator_id="+5515999998888",
        ator_nome="Assistente",
    )

    usuarios = FakeUsuarioRepoAuditoria([])
    registros = (
        await ListarAuditoria(auditoria=repo, usuarios=usuarios).executar(tenant_id=TENANT)
    ).itens

    assert registros[0].ator_perfil_id == ""
    assert usuarios.consultas == 0  # nem chegou a consultar o cadastro


async def test_atores_de_uma_pagina_sao_resolvidos_em_uma_consulta_so():
    """Uma página com vários atores não pode virar uma ida ao banco por linha."""
    ana, bruno = _usuario("Ana"), _usuario("Bruno")
    repo = FakeAuditLogRepo()
    registrar = RegistrarAuditoria(auditoria=repo)
    for autor in (ana, bruno, ana, bruno):
        await registrar.executar(
            ator=AtorAuditoria.USUARIO,
            acao="login",
            tenant_id=TENANT,
            ator_id=str(autor.id),
        )

    usuarios = FakeUsuarioRepoAuditoria([ana, bruno])
    registros = (
        await ListarAuditoria(auditoria=repo, usuarios=usuarios).executar(tenant_id=TENANT)
    ).itens

    assert usuarios.consultas == 1
    assert {r.ator_nome for r in registros} == {"Ana", "Bruno"}


async def test_sem_repositorio_de_usuarios_a_listagem_segue_funcionando():
    """A dependência é opcional: quem só quer o log cru não precisa passá-la."""
    repo = FakeAuditLogRepo()
    await RegistrarAuditoria(auditoria=repo).executar(
        ator=AtorAuditoria.USUARIO, acao="login", tenant_id=TENANT, ator_nome="Ana"
    )

    registros = (await ListarAuditoria(auditoria=repo).executar(tenant_id=TENANT)).itens
    assert registros[0].ator_nome == "Ana"
    assert registros[0].ator_perfil_id == ""
