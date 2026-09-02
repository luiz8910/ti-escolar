"""Onboarding do WhatsApp de uma escola (§9e.3).

O que se testa aqui é sobretudo **a ordem e as falhas silenciosas**. O go-live do canal
já custou três dias de depuração por passos que não dão erro em lugar nenhum — app não
publicado, WABA não inscrita no app, `phone_number_id` não cadastrado na escola. O
diagnóstico existe para transformar cada um deles numa linha vermelha; os testes existem
para que ele não passe a mentir.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.onboarding_use_cases import (
    CadastrarNumeroDaEscola,
    ConcluirOnboardingDaEscola,
    ConfirmarCodigoDeVerificacao,
    DesvincularNumeroDaEscola,
    DiagnosticarWhatsAppDaEscola,
    EscolaNaoEncontrada,
    InscreverNumeroNaCloudApi,
    OnboardingRecusado,
    PedirCodigoDeVerificacao,
    PermissaoOnboardingNegada,
)
from app.domain.entities import (
    CategoriaTemplate,
    EtapaOnboarding,
    MessageTemplate,
    NumeroNaMeta,
    Papel,
    StatusTemplate,
    Tenant,
    Usuario,
    Waba,
)
from app.infrastructure.channel.meta_numeros import (
    GestorDeNumerosAusente,
    ProvisionamentoIndisponivel,
    etapa_da_meta,
    numero_da_meta,
    separar_e164,
)
from tests.fakes import (
    WABA_PADRAO_ID,
    FakeCatalogoTemplates,
    FakeGestorDeNumeros,
    FakeTemplateRepo,
    FakeTenantRepoCompleto,
    FakeWabaRepo,
    template_aprovado,
    waba_padrao,
)


def _super_admin() -> Usuario:
    return Usuario(
        nome="Super",
        email="super@ti.com",
        senha_hash="x",
        papel=Papel.SUPER_ADMIN,
        tenant_id=None,
    )


def _admin_da_escola(tenant_id) -> Usuario:
    return Usuario(
        nome="Secretaria",
        email="sec@escola.com",
        senha_hash="x",
        papel=Papel.TENANT_ADMIN,
        tenant_id=tenant_id,
    )


def _escola(**kwargs) -> Tenant:
    padrao = {
        "nome": "EM Rosa Cury",
        "slug": "rosacury",
        "waba_id": WABA_PADRAO_ID,
    }
    padrao.update(kwargs)
    return Tenant(**padrao)


def _template_global(nome: str = "aviso_geral") -> MessageTemplate:
    return MessageTemplate(
        tenant_id=None,
        nome=nome,
        idioma="pt_BR",
        categoria=CategoriaTemplate.UTILITY,
        corpo="Olá! A {{1}} informa: {{2}} Fale com a secretaria se precisar.",
    )


def _montar(escola: Tenant, *, numeros=None, wabas=None):
    numeros = numeros or FakeGestorDeNumeros()
    return (
        FakeTenantRepoCompleto([escola]),
        wabas or FakeWabaRepo(),
        numeros,
    )


# --------------------------------------------------------------------------- #
# Tradução do estado da Meta
# --------------------------------------------------------------------------- #
def test_verificar_nao_e_registrar():
    """A distinção que custou um passo de go-live: código conferido ≠ número no ar.

    Depois do código o número fica ``VERIFIED`` mas com ``status`` ainda pendente — e
    continua mudo até o ``POST /register``. Mapear isso para "pronto" liberaria um disparo
    que morre na Graph API.
    """
    assert (
        etapa_da_meta(status="PENDING", verificacao="VERIFIED")
        is EtapaOnboarding.NAO_REGISTRADO
    )
    assert (
        etapa_da_meta(status="PENDING", verificacao="NOT_VERIFIED")
        is EtapaOnboarding.NAO_VERIFICADO
    )
    assert (
        etapa_da_meta(status="CONNECTED", verificacao="EXPIRED")
        is EtapaOnboarding.REGISTRADO
    )


def test_status_desconhecido_falha_fechado():
    """Estado novo da Meta nunca vira REGISTRADO por omissão."""
    assert (
        etapa_da_meta(status="ALGO_QUE_A_META_INVENTOU", verificacao="VERIFIED")
        is EtapaOnboarding.DESCONHECIDA
    )


def test_retrato_do_numero_preserva_o_bruto():
    """O mapeamento é nosso e pode ficar velho; quem depura precisa do original."""
    numero = numero_da_meta(
        {
            "id": "123",
            "display_phone_number": "+55 15 99753-6978",
            "verified_name": "TI-Escolar",
            "status": "CONNECTED",
            "code_verification_status": "EXPIRED",
            "name_status": "AVAILABLE_WITHOUT_REVIEW",
            "quality_rating": "GREEN",
        }
    )
    assert numero.pronto_para_atender
    assert "status=CONNECTED" in numero.bruto
    assert "verificacao=EXPIRED" in numero.bruto


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("+55 15 99753-6978", ("55", "15997536978")),
        ("+5515997536978", ("55", "15997536978")),
    ],
)
def test_separar_e164_quebra_o_codigo_do_pais(entrada, esperado):
    assert separar_e164(entrada) == esperado


def test_separar_e164_recusa_pais_nao_suportado():
    """Adivinhar o prefixo de outro país erraria — códigos têm 1, 2 ou 3 dígitos."""
    with pytest.raises(ProvisionamentoIndisponivel, match="só números do Brasil"):
        separar_e164("+1 415 555 0123")


# --------------------------------------------------------------------------- #
# Permissão
# --------------------------------------------------------------------------- #
async def test_admin_da_escola_nao_cadastra_numero():
    """O teto de números é do portfólio: cadastrar consome a vaga da próxima escola."""
    escola = _escola()
    tenants, wabas, numeros = _montar(escola)
    caso = CadastrarNumeroDaEscola(tenants=tenants, wabas=wabas, numeros=numeros)
    with pytest.raises(PermissaoOnboardingNegada):
        await caso.executar(
            solicitante=_admin_da_escola(escola.id),
            tenant_id=escola.id,
            numero_e164="+5515999990000",
        )


async def test_escola_inexistente():
    tenants, wabas, numeros = _montar(_escola())
    caso = CadastrarNumeroDaEscola(tenants=tenants, wabas=wabas, numeros=numeros)
    with pytest.raises(EscolaNaoEncontrada):
        await caso.executar(
            solicitante=_super_admin(),
            tenant_id=uuid4(),
            numero_e164="+5515999990000",
        )


# --------------------------------------------------------------------------- #
# Os quatro passos, na ordem que a Meta impõe
# --------------------------------------------------------------------------- #
async def test_cadastro_grava_o_id_no_tenant_na_mesma_operacao():
    """O passo que separava "número existe na Meta" de "escola recebe mensagem".

    Cadastrar lá e esquecer de colar o ``phone_number_id`` aqui produz o pior estado do
    go-live: número conectado e inbound descartado em silêncio.
    """
    escola = _escola()
    tenants, wabas, numeros = _montar(escola)
    caso = CadastrarNumeroDaEscola(tenants=tenants, wabas=wabas, numeros=numeros)

    criado = await caso.executar(
        solicitante=_super_admin(),
        tenant_id=escola.id,
        numero_e164="+55 15 99753-6978",
    )

    salva = await tenants.obter(escola.id)
    assert salva.meta_phone_number_id == criado.phone_number_id
    assert salva.whatsapp_numero == "+5515997536978"
    assert criado.etapa is EtapaOnboarding.NAO_VERIFICADO


async def test_nome_de_exibicao_cai_no_nome_da_escola():
    """É o nome que os pais veem — genérico é o que a revisão da Meta recusa."""
    escola = _escola()
    tenants, wabas, numeros = _montar(escola)
    caso = CadastrarNumeroDaEscola(tenants=tenants, wabas=wabas, numeros=numeros)

    criado = await caso.executar(
        solicitante=_super_admin(), tenant_id=escola.id, numero_e164="+5515999990000"
    )
    assert criado.nome_exibicao == "EM Rosa Cury"


async def test_escola_sem_conta_e_recusada_antes_de_chamar_a_meta():
    """Sem WABA não há onde o número morar — recusar aqui dá a causa por extenso."""
    escola = _escola(waba_id=None)
    tenants, wabas, numeros = _montar(escola)
    caso = CadastrarNumeroDaEscola(tenants=tenants, wabas=wabas, numeros=numeros)

    with pytest.raises(OnboardingRecusado, match="não está em nenhuma conta"):
        await caso.executar(
            solicitante=_super_admin(), tenant_id=escola.id, numero_e164="+5515999990000"
        )
    assert numeros.numeros == {}


async def test_conta_sem_id_da_meta_e_recusada():
    escola = _escola()
    wabas = FakeWabaRepo([Waba(id=WABA_PADRAO_ID, meta_waba_id="", nome="Sem id")])
    tenants, _, numeros = _montar(escola)
    caso = CadastrarNumeroDaEscola(tenants=tenants, wabas=wabas, numeros=numeros)

    with pytest.raises(OnboardingRecusado, match="sem o id da Meta"):
        await caso.executar(
            solicitante=_super_admin(), tenant_id=escola.id, numero_e164="+5515999990000"
        )


async def test_escola_que_ja_tem_numero_nao_ganha_outro():
    """Trocar o número custa a identidade do canal para os pais — não é um clique."""
    escola = _escola(meta_phone_number_id="123", whatsapp_numero="+5515999990000")
    tenants, wabas, numeros = _montar(escola)
    caso = CadastrarNumeroDaEscola(tenants=tenants, wabas=wabas, numeros=numeros)

    with pytest.raises(OnboardingRecusado, match="já tem o número"):
        await caso.executar(
            solicitante=_super_admin(), tenant_id=escola.id, numero_e164="+5515999991111"
        )


async def test_fluxo_completo_ate_registrado():
    """Cadastrar → pedir código → confirmar → inscrever, na única ordem que a Meta aceita."""
    escola = _escola()
    tenants, wabas, numeros = _montar(escola)
    args = {"tenants": tenants, "wabas": wabas, "numeros": numeros}
    super_admin = _super_admin()

    await CadastrarNumeroDaEscola(**args).executar(
        solicitante=super_admin, tenant_id=escola.id, numero_e164="+5515999990000"
    )
    await PedirCodigoDeVerificacao(**args).executar(
        solicitante=super_admin, tenant_id=escola.id, metodo="VOICE"
    )
    verificado = await ConfirmarCodigoDeVerificacao(**args).executar(
        solicitante=super_admin, tenant_id=escola.id, codigo="123456"
    )
    assert verificado.etapa is EtapaOnboarding.NAO_REGISTRADO

    registrado = await InscreverNumeroNaCloudApi(**args).executar(
        solicitante=super_admin, tenant_id=escola.id, pin="654321"
    )
    assert registrado.pronto_para_atender
    assert numeros.codigos_pedidos == [(registrado.phone_number_id, "VOICE")]


async def test_passos_sem_numero_sao_recusados():
    """Pedir código de um número que não existe é o erro que a Meta devolveria opaco."""
    escola = _escola()
    tenants, wabas, numeros = _montar(escola)
    with pytest.raises(OnboardingRecusado, match="ainda não tem número"):
        await PedirCodigoDeVerificacao(
            tenants=tenants, wabas=wabas, numeros=numeros
        ).executar(solicitante=_super_admin(), tenant_id=escola.id)


async def test_desvincular_nao_toca_na_meta():
    """``deregister`` por engano derruba o canal de uma escola em produção."""
    escola = _escola(meta_phone_number_id="pnid-9")
    tenants, wabas, numeros = _montar(escola)
    numeros.registrar_numero(
        NumeroNaMeta(phone_number_id="pnid-9", etapa=EtapaOnboarding.REGISTRADO)
    )

    await DesvincularNumeroDaEscola(
        tenants=tenants, wabas=wabas, numeros=numeros
    ).executar(solicitante=_super_admin(), tenant_id=escola.id)

    assert (await tenants.obter(escola.id)).meta_phone_number_id == ""
    # O número continua lá: soltar o vínculo é decisão nossa, desregistrar é da Meta.
    assert await numeros.descrever(phone_number_id="pnid-9") is not None


# --------------------------------------------------------------------------- #
# Conclusão: os dois passos sem tela no console
# --------------------------------------------------------------------------- #
async def test_conclusao_inscreve_a_conta_e_replica_os_templates():
    """Sem estes dois, a escola nasce com o webhook mudo e sem template aprovado."""
    escola = _escola(meta_phone_number_id="pnid-1")
    tenants, wabas, numeros = _montar(escola)
    templates = FakeTemplateRepo(_template_global())
    catalogo = FakeCatalogoTemplates()

    resultado = await ConcluirOnboardingDaEscola(
        tenants=tenants,
        wabas=wabas,
        numeros=numeros,
        templates=templates,
        catalogo=catalogo,
    ).executar(solicitante=_super_admin(), tenant_id=escola.id)

    assert resultado.conta_inscrita_no_app
    assert numeros.contas_inscritas == ["900900900"]
    assert resultado.templates_submetidos == 1
    assert resultado.perfil_atualizado
    assert resultado.avisos == []


async def test_conclusao_reporta_falha_sem_abortar_os_outros_passos():
    """Um passo falho não pode anular os que deram certo — nem sumir da tela."""
    escola = _escola(meta_phone_number_id="pnid-1")
    tenants, wabas, _ = _montar(escola)
    numeros = FakeGestorDeNumeros(erro=RuntimeError("token sem escopo"))
    templates = FakeTemplateRepo(_template_global())

    resultado = await ConcluirOnboardingDaEscola(
        tenants=tenants,
        wabas=wabas,
        numeros=numeros,
        templates=templates,
        catalogo=FakeCatalogoTemplates(),
    ).executar(solicitante=_super_admin(), tenant_id=escola.id)

    assert not resultado.conta_inscrita_no_app
    assert any("token sem escopo" in a for a in resultado.avisos)
    # A replicação, que não depende do gestor de números, seguiu.
    assert resultado.templates_submetidos == 1


# --------------------------------------------------------------------------- #
# Diagnóstico
# --------------------------------------------------------------------------- #
def _diagnostico(escola, *, numeros, templates=None, canal="meta", wabas=None):
    return DiagnosticarWhatsAppDaEscola(
        tenants=FakeTenantRepoCompleto([escola]),
        wabas=wabas or FakeWabaRepo(),
        numeros=numeros,
        templates=templates or FakeTemplateRepo(),
        canal=canal,
    )


async def test_diagnostico_de_escola_pronta():
    escola = _escola(meta_phone_number_id="pnid-1")
    numeros = FakeGestorDeNumeros()
    numeros.registrar_numero(
        NumeroNaMeta(
            phone_number_id="pnid-1",
            numero_exibicao="+55 15 99753-6978",
            nome_exibicao="EM Rosa Cury",
            etapa=EtapaOnboarding.REGISTRADO,
            status_nome="APPROVED",
            qualidade="GREEN",
        )
    )
    templates = FakeTemplateRepo(template_aprovado(_template_global()))

    resultado = await _diagnostico(
        escola, numeros=numeros, templates=templates
    ).executar(solicitante=_super_admin(), tenant_id=escola.id)

    assert resultado.pronta
    assert resultado.pendencias == []


async def test_diagnostico_acusa_canal_em_demo():
    """Com o canal em demo nada abaixo foi conferido — e o painel precisa dizer isso.

    É a falha silenciosa nº 1 do go-live: `MESSAGE_CHANNEL=meta` sem token sobe no demo,
    o inbound é atendido, cobra LLM, e a resposta se perde.
    """
    escola = _escola(meta_phone_number_id="pnid-1")
    resultado = await _diagnostico(
        escola, numeros=GestorDeNumerosAusente("sem token"), canal="demo"
    ).executar(solicitante=_super_admin(), tenant_id=escola.id)

    canal = next(p for p in resultado.passos if p.chave == "canal")
    assert not canal.concluido
    assert "canal demo" in canal.detalhe


async def test_diagnostico_acusa_escola_sem_phone_number_id():
    """Sem o id, o inbound da escola é **descartado** — proposital e fácil de esquecer."""
    escola = _escola()
    resultado = await _diagnostico(escola, numeros=FakeGestorDeNumeros()).executar(
        solicitante=_super_admin(), tenant_id=escola.id
    )

    passo = next(p for p in resultado.passos if p.chave == "numero")
    assert not passo.concluido
    assert passo.acao == "cadastrar_numero"
    assert "não recebe mensagem" in passo.detalhe


async def test_diagnostico_distingue_verificado_de_registrado():
    escola = _escola(meta_phone_number_id="pnid-1")
    numeros = FakeGestorDeNumeros()
    numeros.registrar_numero(
        NumeroNaMeta(phone_number_id="pnid-1", etapa=EtapaOnboarding.NAO_REGISTRADO)
    )

    resultado = await _diagnostico(escola, numeros=numeros).executar(
        solicitante=_super_admin(), tenant_id=escola.id
    )

    passo = next(p for p in resultado.passos if p.chave == "registro")
    assert not passo.concluido
    assert passo.acao == "registrar_numero"
    assert "verificar não é registrar" in passo.detalhe.lower()


async def test_diagnostico_acusa_id_que_a_meta_nao_reconhece():
    """Id copiado da conta errada: gravado aqui, inexistente lá."""
    escola = _escola(meta_phone_number_id="id-que-nao-existe")
    resultado = await _diagnostico(escola, numeros=FakeGestorDeNumeros()).executar(
        solicitante=_super_admin(), tenant_id=escola.id
    )

    passo = next(p for p in resultado.passos if p.chave == "numero")
    assert not passo.concluido
    assert "a Meta não" in passo.detalhe


async def test_diagnostico_cobra_template_aprovado_na_conta_da_escola():
    """Aprovação é **por conta**: um global aprovado na conta A não existe na B (§9a-ter)."""
    escola = _escola(meta_phone_number_id="pnid-1")
    numeros = FakeGestorDeNumeros()
    numeros.registrar_numero(
        NumeroNaMeta(phone_number_id="pnid-1", etapa=EtapaOnboarding.REGISTRADO)
    )
    outra_conta = uuid4()
    templates = FakeTemplateRepo(
        template_aprovado(_template_global(), waba_id=outra_conta)
    )

    resultado = await _diagnostico(
        escola, numeros=numeros, templates=templates
    ).executar(solicitante=_super_admin(), tenant_id=escola.id)

    passo = next(p for p in resultado.passos if p.chave == "templates")
    assert not passo.concluido
    assert passo.acao == "replicar_templates"


async def test_diagnostico_e_so_do_super_admin():
    escola = _escola()
    with pytest.raises(PermissaoOnboardingNegada):
        await _diagnostico(escola, numeros=FakeGestorDeNumeros()).executar(
            solicitante=_admin_da_escola(escola.id), tenant_id=escola.id
        )


async def test_gestor_ausente_nao_derruba_o_diagnostico():
    """Sem token não dá para perguntar — e o painel deve dizer isso, não explodir."""
    escola = _escola(meta_phone_number_id="pnid-1")
    resultado = await _diagnostico(
        escola, numeros=GestorDeNumerosAusente("modo demo"), canal="demo"
    ).executar(solicitante=_super_admin(), tenant_id=escola.id)

    assert resultado.numero is None
    assert not resultado.pronta


async def test_gestor_ausente_recusa_escrita_com_a_causa():
    with pytest.raises(ProvisionamentoIndisponivel, match="modo demo"):
        await GestorDeNumerosAusente("modo demo").adicionar(
            meta_waba_id="1", codigo_pais="55", numero="1599", nome_exibicao="X"
        )


def test_status_template_importado_do_enum():
    """Sanidade do import — o diagnóstico depende deste enum para decidir aprovação."""
    assert StatusTemplate.APROVADO.value == "aprovado"


def test_waba_padrao_tem_id_da_meta():
    assert waba_padrao().meta_waba_id == "900900900"
