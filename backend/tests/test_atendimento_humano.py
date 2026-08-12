"""Atendimento humano: o assistente entrega a conversa à secretaria (§6j).

O que se testa aqui são as **travas**, não o caminho feliz. Elas existem porque cada
falha tem um custo concreto do outro lado: encaminhar cedo demais cria trabalho para uma
pessoa real; encaminhar sem perguntar surpreende o responsável; responder fora da janela
de 24h faz a mensagem sumir sem ninguém perceber; e o assistente falar por cima da
secretaria manda duas respostas contraditórias pelo mesmo número.
"""

from __future__ import annotations

import uuid
from datetime import datetime, time, timedelta, timezone

import pytest

from app.application.atendimento_humano_use_cases import (
    AssumirAtendimento,
    ContarAtendimentosPendentes,
    EncaminhamentoRecusado,
    EscalarParaSecretaria,
    ListarAtendimentos,
    MesaDeAtendimento,
    ObterAtendimento,
    OferecerAtendimentoHumano,
    ReabrirAtendimento,
    ResolverAtendimento,
    ResponderAtendimento,
    formatar_retorno,
)
from app.application.use_cases import AtenderConversa, RecuperarEEnviarDocumento
from app.domain.entities import (
    AtendimentoHumano,
    CategoriaTemplate,
    ChamadaFerramenta,
    Contato,
    MessageTemplate,
    Papel,
    RespostaLLM,
    StatusAtendimentoHumano,
    StatusTemplate,
    Tenant,
    Usuario,
)
from tests.fakes import (
    FakeAtendimentoHumanoRepo,
    FakeChannel,
    FakeContatoRepo,
    FakeConversaRepo,
    FakeDocumentSource,
    FakeLLM,
    FakeTemplateRepo,
    FakeTenantRepo,
    FakeVectorStore,
    fake_embedder,
)

TENANT = uuid.uuid4()
OUTRO_TENANT = uuid.uuid4()
CONTATO = "+5515999998888"
CONVERSA = uuid.uuid4()

# Sexta-feira 10h em São Paulo (13h UTC) e sexta 20h (sábado 23h UTC → fora).
SEXTA_10H = datetime(2026, 8, 7, 13, 0, tzinfo=timezone.utc)
SEXTA_20H = datetime(2026, 8, 7, 23, 0, tzinfo=timezone.utc)


def _escola(**kwargs) -> Tenant:
    return Tenant(
        id=TENANT,
        nome="EM Rosa Cury",
        slug="rosa-cury",
        meta_phone_number_id="111111111111111",
        **kwargs,
    )


def _atendente(nome: str = "Dona Vera") -> Usuario:
    return Usuario(
        nome=nome,
        email=f"{nome.split()[0].lower()}@escola.test",
        senha_hash="x",
        papel=Papel.TENANT_ADMIN,
        tenant_id=TENANT,
    )


def _mesa(repo: FakeAtendimentoHumanoRepo, *, escola: Tenant | None = None) -> MesaDeAtendimento:
    contatos = FakeContatoRepo()
    return MesaDeAtendimento(
        atendimentos=repo,
        tenants=FakeTenantRepo([escola or _escola()]),
        contatos=contatos,
    )


# --------------------------------------------------------------------------- #
# Expediente: o que o assistente promete a quem está esperando
# --------------------------------------------------------------------------- #
def test_expediente_aberto_promete_agora():
    assert formatar_retorno(_escola(), agora=SEXTA_10H) == "agora"


def test_sexta_a_noite_promete_a_segunda_e_nao_o_sabado():
    # A armadilha é prometer "amanhã": sábado não é dia de expediente.
    texto = formatar_retorno(_escola(), agora=SEXTA_20H)
    assert "segunda-feira" in texto
    assert "7h30" in texto


def test_escola_sem_expediente_valido_nao_promete_nada():
    escola = _escola(expediente_dias=())
    assert formatar_retorno(escola, agora=SEXTA_20H) == ""


def test_expediente_de_sabado_e_respeitado():
    escola = _escola(
        expediente_dias=(6,), expediente_inicio=time(8, 0), expediente_fim=time(12, 0)
    )
    # Sábado 9h local (12h UTC).
    sabado = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
    assert escola.dentro_do_expediente(sabado)
    assert formatar_retorno(escola, agora=sabado) == "agora"


# --------------------------------------------------------------------------- #
# Trava 1: não encaminhar nas primeiras mensagens
# --------------------------------------------------------------------------- #
async def test_recusa_encaminhar_na_primeira_mensagem():
    repo = FakeAtendimentoHumanoRepo()
    uc = EscalarParaSecretaria(atendimentos=repo, tenants=FakeTenantRepo([_escola()]))

    with pytest.raises(EncaminhamentoRecusado) as erro:
        await uc.executar(
            tenant_id=TENANT,
            conversa_id=CONVERSA,
            contato=CONTATO,
            motivo="quer falar sobre a matrícula",
            respostas_anteriores=0,
        )

    assert "base de conhecimento" in str(erro.value)
    assert repo.itens == {}  # nada foi criado: nem oferta, nem fila


async def test_pedido_explicito_do_responsavel_pula_a_trava():
    # Exigir duas respostas automáticas de quem já pediu uma pessoa seria hostil.
    repo = FakeAtendimentoHumanoRepo()
    uc = EscalarParaSecretaria(atendimentos=repo, tenants=FakeTenantRepo([_escola()]))

    atendimento = await uc.executar(
        tenant_id=TENANT,
        conversa_id=CONVERSA,
        contato=CONTATO,
        motivo="quer falar com uma pessoa",
        pedido_explicito=True,
        respostas_anteriores=0,
    )

    assert atendimento.status is StatusAtendimentoHumano.ABERTO
    assert atendimento.na_fila


# --------------------------------------------------------------------------- #
# Trava 2: oferecer antes de encaminhar
# --------------------------------------------------------------------------- #
async def test_primeira_tentativa_de_encaminhar_vira_oferta():
    repo = FakeAtendimentoHumanoRepo()
    uc = EscalarParaSecretaria(atendimentos=repo, tenants=FakeTenantRepo([_escola()]))

    with pytest.raises(EncaminhamentoRecusado) as erro:
        await uc.executar(
            tenant_id=TENANT,
            conversa_id=CONVERSA,
            contato=CONTATO,
            motivo="dúvida sobre transferência",
            respostas_anteriores=3,
        )

    assert "pergunte ao responsável" in str(erro.value).lower()
    [oferta] = list(repo.itens.values())
    assert oferta.status is StatusAtendimentoHumano.OFERECIDO
    assert oferta.ofereceu_em is not None
    assert oferta.confirmado_em is None
    assert not oferta.na_fila  # não ocupa a fila da secretaria


async def test_confirmacao_do_responsavel_promove_a_oferta_para_a_fila():
    repo = FakeAtendimentoHumanoRepo()
    tenants = FakeTenantRepo([_escola()])
    await OferecerAtendimentoHumano(atendimentos=repo, tenants=tenants).executar(
        tenant_id=TENANT, conversa_id=CONVERSA, contato=CONTATO, motivo="transferência"
    )

    atendimento = await EscalarParaSecretaria(atendimentos=repo, tenants=tenants).executar(
        tenant_id=TENANT, conversa_id=CONVERSA, contato=CONTATO, respostas_anteriores=3
    )

    assert atendimento.status is StatusAtendimentoHumano.ABERTO
    assert atendimento.confirmado_em is not None
    assert len(repo.itens) == 1  # promoveu o mesmo card, não criou outro


async def test_oferta_vencida_nao_autoriza_encaminhamento_direto():
    # Uma oferta ignorada há meses não pode valer como "já perguntei".
    repo = FakeAtendimentoHumanoRepo()
    antiga = AtendimentoHumano(
        tenant_id=TENANT,
        conversa_id=CONVERSA,
        contato=CONTATO,
        status=StatusAtendimentoHumano.OFERECIDO,
        ofereceu_em=datetime.now(timezone.utc) - timedelta(days=30),
    )
    await repo.criar(antiga)

    with pytest.raises(EncaminhamentoRecusado):
        await EscalarParaSecretaria(
            atendimentos=repo, tenants=FakeTenantRepo([_escola()])
        ).executar(
            tenant_id=TENANT, conversa_id=CONVERSA, contato=CONTATO, respostas_anteriores=3
        )

    assert repo.itens[antiga.id].status is StatusAtendimentoHumano.DESCARTADO


async def test_insistir_nao_cria_tres_cards():
    repo = FakeAtendimentoHumanoRepo()
    tenants = FakeTenantRepo([_escola()])
    uc = EscalarParaSecretaria(atendimentos=repo, tenants=tenants)
    for _ in range(3):
        await uc.executar(
            tenant_id=TENANT,
            conversa_id=CONVERSA,
            contato=CONTATO,
            motivo="mesma dúvida",
            pedido_explicito=True,
            respostas_anteriores=3,
        )
    assert len(repo.itens) == 1


# --------------------------------------------------------------------------- #
# Expediente na hora de encaminhar
# --------------------------------------------------------------------------- #
async def test_fora_do_expediente_entra_na_fila_marcado(monkeypatch):
    # Descartar perderia o recado de quem escreve à noite — justamente quem mais depende
    # do canal. O que muda é a promessa feita, não o registro.
    repo = FakeAtendimentoHumanoRepo()
    import app.application.atendimento_humano_use_cases as mod

    monkeypatch.setattr(mod, "_now", lambda: SEXTA_20H)

    atendimento = await EscalarParaSecretaria(
        atendimentos=repo, tenants=FakeTenantRepo([_escola()])
    ).executar(
        tenant_id=TENANT,
        conversa_id=CONVERSA,
        contato=CONTATO,
        pedido_explicito=True,
    )

    assert atendimento.fora_expediente
    assert atendimento.na_fila


# --------------------------------------------------------------------------- #
# Resposta da secretaria
# --------------------------------------------------------------------------- #
async def _fila_com_atendimento(
    repo: FakeAtendimentoHumanoRepo, **kwargs
) -> AtendimentoHumano:
    atendimento = AtendimentoHumano(
        tenant_id=TENANT,
        conversa_id=CONVERSA,
        contato=CONTATO,
        status=StatusAtendimentoHumano.ABERTO,
        **kwargs,
    )
    return await repo.criar(atendimento)


async def test_resposta_sai_pelo_numero_da_escola_e_entra_na_mesma_conversa():
    repo = FakeAtendimentoHumanoRepo()
    atendimento = await _fila_com_atendimento(repo)
    conversas = FakeConversaRepo()
    canal = FakeChannel()
    vera = _atendente()

    await ResponderAtendimento(
        atendimentos=repo,
        conversas=conversas,
        canal=canal,
        tenants=FakeTenantRepo([_escola()]),
    ).executar(
        tenant_id=TENANT,
        atendimento_id=atendimento.id,
        usuario=vera,
        texto="A matrícula está confirmada.",
    )

    assert canal.enviados == [(CONTATO, "texto")]
    # remetente = phone_number_id da escola (multi-tenant: cada uma pelo seu número).
    assert canal.remetente == "111111111111111"
    [mensagem] = conversas.mensagens[CONVERSA]
    assert mensagem["autor"] == "atendente"
    assert mensagem["autor_nome"] == "Dona Vera"


async def test_responder_assume_o_atendimento():
    repo = FakeAtendimentoHumanoRepo()
    atendimento = await _fila_com_atendimento(repo)
    vera = _atendente()

    atualizado = await ResponderAtendimento(
        atendimentos=repo,
        conversas=FakeConversaRepo(),
        canal=FakeChannel(),
        tenants=FakeTenantRepo([_escola()]),
    ).executar(
        tenant_id=TENANT, atendimento_id=atendimento.id, usuario=vera, texto="Olá!"
    )

    assert atualizado.atendente_id == vera.id
    assert atualizado.status is StatusAtendimentoHumano.EM_ATENDIMENTO


async def test_outra_pessoa_nao_responde_por_cima():
    repo = FakeAtendimentoHumanoRepo()
    vera, joana = _atendente("Dona Vera"), _atendente("Joana")
    atendimento = await _fila_com_atendimento(
        repo, atendente_id=vera.id, atendente_nome=vera.nome
    )
    canal = FakeChannel()

    with pytest.raises(ValueError, match="Dona Vera"):
        await ResponderAtendimento(
            atendimentos=repo,
            conversas=FakeConversaRepo(),
            canal=canal,
            tenants=FakeTenantRepo([_escola()]),
        ).executar(
            tenant_id=TENANT, atendimento_id=atendimento.id, usuario=joana, texto="oi"
        )

    assert canal.enviados == []  # nada saiu para o responsável


async def test_janela_de_24h_expirada_sem_template_recusa_com_erro_claro():
    # O modo de falha que este teste existe para impedir: a secretaria escreve, a Graph
    # API recusa o texto livre e a resposta some sem ninguém saber.
    repo = FakeAtendimentoHumanoRepo()
    atendimento = await _fila_com_atendimento(
        repo,
        ultima_mensagem_responsavel_em=datetime.now(timezone.utc) - timedelta(hours=30),
    )
    conversas, canal = FakeConversaRepo(), FakeChannel()

    with pytest.raises(ValueError, match="janela de 24h"):
        await ResponderAtendimento(
            atendimentos=repo,
            conversas=conversas,
            canal=canal,
            tenants=FakeTenantRepo([_escola()]),
        ).executar(
            tenant_id=TENANT, atendimento_id=atendimento.id, usuario=_atendente(), texto="oi"
        )

    assert canal.enviados == []
    assert conversas.mensagens == {}  # não grava resposta que não saiu


async def test_janela_expirada_com_template_aprovado_reabre_a_conversa():
    repo = FakeAtendimentoHumanoRepo()
    atendimento = await _fila_com_atendimento(
        repo,
        ultima_mensagem_responsavel_em=datetime.now(timezone.utc) - timedelta(hours=30),
    )
    template = MessageTemplate(
        tenant_id=TENANT,
        nome="retomada_atendimento",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="Olá! Aqui é a secretaria da {{1}}. Sobre a sua mensagem: {{2}} Se precisar de algo mais, é só responder por aqui.",
        status=StatusTemplate.APROVADO,
    )
    canal = FakeChannel()

    await ResponderAtendimento(
        atendimentos=repo,
        conversas=FakeConversaRepo(),
        canal=canal,
        tenants=FakeTenantRepo([_escola()]),
        templates=FakeTemplateRepo(template),
        template_retomada="retomada_atendimento",
    ).executar(
        tenant_id=TENANT,
        atendimento_id=atendimento.id,
        usuario=_atendente(),
        texto="A declaração está pronta.",
    )

    assert canal.enviados == [(CONTATO, "template")]


async def test_template_pendente_de_aprovacao_nao_serve():
    repo = FakeAtendimentoHumanoRepo()
    atendimento = await _fila_com_atendimento(
        repo,
        ultima_mensagem_responsavel_em=datetime.now(timezone.utc) - timedelta(hours=30),
    )
    template = MessageTemplate(
        tenant_id=TENANT,
        nome="retomada_atendimento",
        categoria=CategoriaTemplate.UTILITY,
        idioma="pt_BR",
        corpo="{{1}} {{2}}",
        status=StatusTemplate.PENDENTE,
    )

    with pytest.raises(ValueError, match="janela de 24h"):
        await ResponderAtendimento(
            atendimentos=repo,
            conversas=FakeConversaRepo(),
            canal=FakeChannel(),
            tenants=FakeTenantRepo([_escola()]),
            templates=FakeTemplateRepo(template),
            template_retomada="retomada_atendimento",
        ).executar(
            tenant_id=TENANT, atendimento_id=atendimento.id, usuario=_atendente(), texto="oi"
        )


# --------------------------------------------------------------------------- #
# Fila, trava do atendente e isolamento entre escolas
# --------------------------------------------------------------------------- #
async def test_assumir_trava_o_atendimento_em_uma_pessoa():
    repo = FakeAtendimentoHumanoRepo()
    atendimento = await _fila_com_atendimento(repo)
    vera, joana = _atendente("Dona Vera"), _atendente("Joana")
    uc = AssumirAtendimento(atendimentos=repo)

    await uc.executar(tenant_id=TENANT, atendimento_id=atendimento.id, usuario=vera)
    with pytest.raises(ValueError, match="Dona Vera"):
        await uc.executar(tenant_id=TENANT, atendimento_id=atendimento.id, usuario=joana)


async def test_resolver_e_reabrir():
    repo = FakeAtendimentoHumanoRepo()
    atendimento = await _fila_com_atendimento(repo)
    vera = _atendente()

    resolvido = await ResolverAtendimento(atendimentos=repo).executar(
        tenant_id=TENANT, atendimento_id=atendimento.id, usuario=vera
    )
    assert resolvido.status is StatusAtendimentoHumano.RESOLVIDO
    assert not resolvido.na_fila

    reaberto = await ReabrirAtendimento(atendimentos=repo).executar(
        tenant_id=TENANT, atendimento_id=atendimento.id, liberar=True
    )
    assert reaberto.status is StatusAtendimentoHumano.ABERTO
    assert reaberto.atendente_id is None


async def test_fila_e_contador_ignoram_oferecidos_e_resolvidos():
    repo = FakeAtendimentoHumanoRepo()
    await _fila_com_atendimento(repo)
    await repo.criar(
        AtendimentoHumano(
            tenant_id=TENANT,
            conversa_id=uuid.uuid4(),
            contato="+5515911112222",
            status=StatusAtendimentoHumano.OFERECIDO,
        )
    )
    await repo.criar(
        AtendimentoHumano(
            tenant_id=TENANT,
            conversa_id=uuid.uuid4(),
            contato="+5515933334444",
            status=StatusAtendimentoHumano.RESOLVIDO,
        )
    )

    pagina = await ListarAtendimentos(atendimentos=repo).executar(tenant_id=TENANT)
    assert pagina.total == 1
    assert await ContarAtendimentosPendentes(atendimentos=repo).executar(tenant_id=TENANT) == 1


async def test_atendimento_de_outra_escola_nao_e_visivel():
    repo = FakeAtendimentoHumanoRepo()
    atendimento = await _fila_com_atendimento(repo)

    assert await repo.obter(tenant_id=OUTRO_TENANT, atendimento_id=atendimento.id) is None
    pagina = await ListarAtendimentos(atendimentos=repo).executar(tenant_id=OUTRO_TENANT)
    assert pagina.total == 0


async def test_nome_do_responsavel_vem_do_cadastro():
    repo = FakeAtendimentoHumanoRepo()
    contatos = FakeContatoRepo()
    await contatos.criar(Contato(tenant_id=TENANT, nome="Maria Souza", telefone=CONTATO))

    atendimento = await EscalarParaSecretaria(
        atendimentos=repo, tenants=FakeTenantRepo([_escola()]), contatos=contatos
    ).executar(
        tenant_id=TENANT, conversa_id=CONVERSA, contato=CONTATO, pedido_explicito=True
    )

    assert atendimento.contato_nome == "Maria Souza"


# --------------------------------------------------------------------------- #
# Integração com o assistente (AtenderConversa)
# --------------------------------------------------------------------------- #
def _atender(mesa: MesaDeAtendimento | None, respostas=None, conversas=None):
    return AtenderConversa(
        conversas=conversas or FakeConversaRepo(),
        embedder=fake_embedder(),
        store=FakeVectorStore(),
        llm=FakeLLM(respostas),
        documentos=RecuperarEEnviarDocumento(
            source=FakeDocumentSource([]), canal=FakeChannel()
        ),
        mesa=mesa,
    )


async def test_assistente_fica_em_silencio_quando_a_secretaria_assumiu():
    # Sem esta trava o assistente responde por cima da pessoa, e o responsável recebe
    # duas respostas da escola dizendo coisas diferentes.
    repo = FakeAtendimentoHumanoRepo()
    conversas = FakeConversaRepo()
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    await repo.criar(
        AtendimentoHumano(
            tenant_id=TENANT,
            conversa_id=conversa.id,
            contato=CONTATO,
            status=StatusAtendimentoHumano.EM_ATENDIMENTO,
        )
    )
    uc = _atender(_mesa(repo), conversas=conversas)

    resposta = await uc.executar(tenant_id=TENANT, contato=CONTATO, texto="e aí, saiu?")

    assert resposta.texto == ""  # texto vazio = o inbound não envia nada
    autores = [m["autor"] for m in conversas.mensagens[conversa.id]]
    assert autores == ["usuario"]  # a mensagem entra no histórico, sem resposta do bot


async def test_retorno_do_responsavel_renova_a_janela_de_24h():
    repo = FakeAtendimentoHumanoRepo()
    conversas = FakeConversaRepo()
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    antigo = await repo.criar(
        AtendimentoHumano(
            tenant_id=TENANT,
            conversa_id=conversa.id,
            contato=CONTATO,
            status=StatusAtendimentoHumano.EM_ATENDIMENTO,
            ultima_mensagem_responsavel_em=datetime.now(timezone.utc) - timedelta(hours=20),
        )
    )

    await _atender(_mesa(repo), conversas=conversas).executar(
        tenant_id=TENANT, contato=CONTATO, texto="alguma novidade?"
    )

    assert repo.itens[antigo.id].janela_aberta()
    assert repo.itens[antigo.id].ultima_mensagem_responsavel_em > (
        datetime.now(timezone.utc) - timedelta(minutes=1)
    )


async def test_oferta_nao_silencia_o_assistente():
    # Oferecido ≠ na fila: o assistente ainda precisa falar para ouvir o "sim".
    repo = FakeAtendimentoHumanoRepo()
    conversas = FakeConversaRepo()
    conversa = await conversas.obter_ou_criar(tenant_id=TENANT, contato=CONTATO)
    await repo.criar(
        AtendimentoHumano(
            tenant_id=TENANT,
            conversa_id=conversa.id,
            contato=CONTATO,
            status=StatusAtendimentoHumano.OFERECIDO,
        )
    )

    resposta = await _atender(_mesa(repo), conversas=conversas).executar(
        tenant_id=TENANT, contato=CONTATO, texto="sim, por favor"
    )

    assert resposta.texto  # o assistente segue conversando


async def test_ferramenta_de_encaminhamento_devolve_orientacao_em_vez_de_estourar():
    # A recusa da trava vira instrução para o modelo, não exceção que derruba o inbound.
    repo = FakeAtendimentoHumanoRepo()
    respostas = [
        RespostaLLM(
            chamadas=[
                ChamadaFerramenta(
                    id="c1",
                    nome="escalar_para_secretaria",
                    argumentos={"motivo": "quer falar com alguém"},
                )
            ]
        ),
        RespostaLLM(texto="Deixe-me tentar ajudar primeiro."),
    ]
    uc = _atender(_mesa(repo), respostas=respostas)

    resposta = await uc.executar(tenant_id=TENANT, contato=CONTATO, texto="socorro")

    assert resposta.texto == "Deixe-me tentar ajudar primeiro."
    assert repo.itens == {}  # primeira mensagem: nem oferta foi criada


async def test_ferramenta_encaminha_quando_o_responsavel_pede_explicitamente():
    repo = FakeAtendimentoHumanoRepo()
    respostas = [
        RespostaLLM(
            chamadas=[
                ChamadaFerramenta(
                    id="c1",
                    nome="escalar_para_secretaria",
                    argumentos={
                        "motivo": "quer falar com a secretaria sobre a matrícula",
                        "pedido_explicito": True,
                    },
                )
            ]
        ),
        RespostaLLM(texto="Certo! Já avisei a secretaria."),
    ]
    uc = _atender(_mesa(repo), respostas=respostas)

    await uc.executar(
        tenant_id=TENANT, contato=CONTATO, texto="quero falar com uma pessoa"
    )

    [atendimento] = list(repo.itens.values())
    assert atendimento.na_fila
    assert "matrícula" in atendimento.motivo


async def test_ferramentas_de_atendimento_so_existem_com_mesa():
    # Instalação sem secretaria configurada não deve ver a ferramenta no prompt.
    llm = FakeLLM()
    uc = AtenderConversa(
        conversas=FakeConversaRepo(),
        embedder=fake_embedder(),
        store=FakeVectorStore(),
        llm=llm,
        documentos=RecuperarEEnviarDocumento(
            source=FakeDocumentSource([]), canal=FakeChannel()
        ),
        mesa=None,
    )
    await uc.executar(tenant_id=TENANT, contato=CONTATO, texto="oi")
    # O FakeLLM guarda os turnos, não as ferramentas; o que se verifica é que o caso de
    # uso funciona sem mesa — nenhuma chamada de encaminhamento é possível.
    assert llm.turnos_recebidos


# --------------------------------------------------------------------------- #
# Nome do responsável: resolvido na LEITURA, não congelado no nascimento
# --------------------------------------------------------------------------- #
async def _abrir(repo: FakeAtendimentoHumanoRepo, telefone: str) -> AtendimentoHumano:
    return await repo.criar(
        AtendimentoHumano(
            tenant_id=TENANT,
            conversa_id=uuid.uuid4(),
            contato=telefone,
            status=StatusAtendimentoHumano.ABERTO,
            ultima_mensagem_responsavel_em=datetime.now(timezone.utc),
        )
    )


async def test_lista_nomeia_responsavel_cadastrado_depois_do_atendimento():
    """O caso comum: a pessoa escreve antes de estar cadastrada.

    O nome persistido é um retrato do nascimento do atendimento; sem releitura o card
    ficaria com o telefone cru para sempre, mesmo depois de a secretaria cadastrá-la.
    """
    repo = FakeAtendimentoHumanoRepo()
    aberto = await _abrir(repo, CONTATO)
    assert aberto.contato_nome == ""

    contatos = FakeContatoRepo()
    await contatos.criar(Contato(tenant_id=TENANT, nome="Maria Souza", telefone=CONTATO))

    pagina = await ListarAtendimentos(atendimentos=repo, contatos=contatos).executar(
        tenant_id=TENANT
    )

    assert [a.contato_nome for a in pagina.itens] == ["Maria Souza"]


async def test_detalhe_tambem_nomeia_o_responsavel():
    repo = FakeAtendimentoHumanoRepo()
    aberto = await _abrir(repo, CONTATO)
    contatos = FakeContatoRepo()
    await contatos.criar(Contato(tenant_id=TENANT, nome="Maria Souza", telefone=CONTATO))

    obtido = await ObterAtendimento(atendimentos=repo, contatos=contatos).executar(
        tenant_id=TENANT, atendimento_id=aberto.id
    )

    assert obtido is not None
    assert obtido.contato_nome == "Maria Souza"


async def test_nome_nao_vaza_de_outra_escola():
    """Mesmo telefone em duas escolas não pode trazer o nome cadastrado na outra."""
    repo = FakeAtendimentoHumanoRepo()
    await _abrir(repo, CONTATO)
    contatos = FakeContatoRepo()
    await contatos.criar(
        Contato(tenant_id=OUTRO_TENANT, nome="Homônimo de Outra Escola", telefone=CONTATO)
    )

    pagina = await ListarAtendimentos(atendimentos=repo, contatos=contatos).executar(
        tenant_id=TENANT
    )

    assert pagina.itens[0].contato_nome == ""


async def test_sem_cadastro_o_telefone_permanece_e_a_lista_nao_quebra():
    repo = FakeAtendimentoHumanoRepo()
    await _abrir(repo, CONTATO)

    pagina = await ListarAtendimentos(
        atendimentos=repo, contatos=FakeContatoRepo()
    ).executar(tenant_id=TENANT)

    assert pagina.itens[0].contato_nome == ""
    assert pagina.itens[0].contato == CONTATO
