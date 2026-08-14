"""Catálogo de templates: validação local, escopos, permissões e o webhook de status.

O que se testa aqui é sobretudo **o que a Meta recusaria**. Toda regra validada localmente
é uma rejeição que não acontece na WABA — que é compartilhada por todas as escolas, e onde
rejeição repetida penaliza todo mundo.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.application.templates_use_cases import (
    AtualizarStatusTemplateMeta,
    CriarTemplate,
    ImportarTemplateDaMeta,
    ListarTemplates,
    PermissaoTemplateNegada,
    RemoverTemplate,
    ReplicarTemplates,
    SemContaWhatsApp,
    SincronizarTemplates,
    TemplateNaoEncontrado,
)
from app.application.waba_use_cases import AdotarContaDoWebhook
from app.application.validacao_template import (
    TemplateInvalido,
    nome_com_prefixo,
    normalizar_nome_template,
    validar_corpo_template,
)
from app.domain.entities import (
    CategoriaTemplate,
    MessageTemplate,
    Papel,
    StatusTemplate,
    TemplateNaWaba,
    TemplateRemoto,
    Tenant,
    Usuario,
    Waba,
)
from tests.fakes import (
    WABA_PADRAO_ID,
    FakeCatalogoTemplates,
    FakeTemplateRepo,
    FakeWabaRepo,
    waba_padrao,
)

TENANT = uuid4()
OUTRO_TENANT = uuid4()

CORPO_OK = "Olá, {{1}}! A escola informa: {{2}} Fale com a secretaria se precisar."


class FakeTenantRepo:
    def __init__(self, tenants: list[Tenant]) -> None:
        self._tenants = tenants

    async def obter(self, tenant_id):
        return next((t for t in self._tenants if t.id == tenant_id), None)


def _super_admin() -> Usuario:
    return Usuario(
        nome="Super", email="super@ti.com", senha_hash="x", papel=Papel.SUPER_ADMIN,
        tenant_id=None,
    )


def _admin_escola(tenant_id=TENANT) -> Usuario:
    return Usuario(
        nome="Diretora", email="dir@escola.com", senha_hash="x",
        papel=Papel.TENANT_ADMIN, tenant_id=tenant_id,
    )


def _escola(tenant_id=TENANT, slug="rosacury", waba_id=WABA_PADRAO_ID) -> Tenant:
    return Tenant(id=tenant_id, nome="EM Rosa Cury", slug=slug, waba_id=waba_id)


def _criar(templates=None, catalogo=None, tenants=None, wabas=None) -> CriarTemplate:
    return CriarTemplate(
        templates=templates or FakeTemplateRepo(),
        catalogo=catalogo or FakeCatalogoTemplates(),
        tenants=tenants or FakeTenantRepo([_escola()]),
        wabas=wabas or FakeWabaRepo(),
    )


def _pendente(nome="aviso_geral", **kwargs) -> MessageTemplate:
    """Template já submetido na conta padrão, aguardando revisão."""
    kwargs.setdefault("categoria", CategoriaTemplate.UTILITY)
    kwargs.setdefault("idioma", "pt_BR")
    kwargs.setdefault("corpo", CORPO_OK)
    entradas = kwargs.pop("wabas", None)
    return MessageTemplate(
        nome=nome,
        wabas=entradas
        if entradas is not None
        else [TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.PENDENTE)],
        **kwargs,
    )


# --------------------------------------------------------------------------- #
# Validação local — o que a Meta recusaria
# --------------------------------------------------------------------------- #
def test_corpo_nao_pode_terminar_em_variavel():
    """Foi exatamente isto que derrubou a 1ª versão do retomada_atendimento."""
    with pytest.raises(TemplateInvalido, match="começar nem terminar"):
        validar_corpo_template("Sobre a sua mensagem: {{1}}")


def test_corpo_nao_pode_comecar_em_variavel():
    with pytest.raises(TemplateInvalido, match="começar nem terminar"):
        validar_corpo_template("{{1}}, a reunião foi remarcada.")


def test_corpo_nao_pode_ser_so_variavel():
    """Template 'envie qualquer coisa' é o que a regra da Meta existe para impedir."""
    with pytest.raises(TemplateInvalido, match="apenas variáveis"):
        validar_corpo_template("{{1}}")


def test_variaveis_precisam_ser_sequenciais():
    """{{1}}, {{3}} faria os parâmetros posicionais entrarem no lugar errado."""
    with pytest.raises(TemplateInvalido, match="sequência"):
        validar_corpo_template("Olá {{1}}, veja o aviso {{3}} na secretaria.")


def test_corpo_sem_variavel_e_valido():
    assert validar_corpo_template("A secretaria funciona das 7h30 às 17h.") == []


def test_corpo_valido_devolve_placeholders():
    assert validar_corpo_template(CORPO_OK) == [1, 2]


def test_nome_normaliza_espaco_e_hifen():
    assert normalizar_nome_template(" Aviso de Reuniao ") == "aviso_de_reuniao"
    assert normalizar_nome_template("festa-junina") == "festa_junina"


def test_nome_recusa_acento_sem_transliterar_silenciosamente():
    """Não recusar deixaria o nome no banco diferente do que a secretaria leu na tela."""
    with pytest.raises(TemplateInvalido, match="minúsculas sem acento"):
        normalizar_nome_template("reunião")


def test_prefixo_e_idempotente():
    assert nome_com_prefixo(slug="rosacury", nome="festa") == "rosacury_festa"
    assert nome_com_prefixo(slug="rosacury", nome="rosacury_festa") == "rosacury_festa"


# --------------------------------------------------------------------------- #
# Criação: escopos e permissões
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_super_admin_cria_template_global():
    repo, catalogo = FakeTemplateRepo(), FakeCatalogoTemplates()
    template = await _criar(repo, catalogo).executar(
        usuario=_super_admin(),
        nome="aviso_geral",
        corpo=CORPO_OK,
        categoria=CategoriaTemplate.UTILITY,
        exemplos=["Maria", "a reunião é dia 20/08."],
    )
    assert template.global_ is True
    assert template.nome == "aviso_geral"  # global não leva prefixo
    assert template.status is StatusTemplate.PENDENTE
    assert template.na_waba(WABA_PADRAO_ID).meta_template_id == "meta-1"
    assert catalogo.submetidos[0].exemplos == ["Maria", "a reunião é dia 20/08."]


@pytest.mark.asyncio
async def test_admin_de_escola_nao_cria_global():
    """A WABA é ativo compartilhado: uma escola não altera o que as outras usam."""
    with pytest.raises(PermissaoTemplateNegada):
        await _criar().executar(
            usuario=_admin_escola(),
            nome="aviso_geral",
            corpo=CORPO_OK,
            categoria=CategoriaTemplate.UTILITY,
            exemplos=["Maria", "a reunião é dia 20/08."],
            tenant_id=None,
        )


@pytest.mark.asyncio
async def test_template_da_escola_recebe_prefixo_do_slug():
    """O prefixo é o que evita colisão de nome na WABA compartilhada."""
    template = await _criar().executar(
        usuario=_admin_escola(),
        nome="festa_junina",
        corpo=CORPO_OK,
        categoria=CategoriaTemplate.UTILITY,
        exemplos=["Maria", "a festa é dia 20/08."],
        tenant_id=TENANT,
    )
    assert template.nome == "rosacury_festa_junina"
    assert template.global_ is False


@pytest.mark.asyncio
async def test_nome_duplicado_recusado_antes_de_ir_a_meta():
    repo = FakeTemplateRepo(
        MessageTemplate(
            nome="aviso_geral", categoria=CategoriaTemplate.UTILITY,
            idioma="pt_BR", corpo=CORPO_OK,
        )
    )
    catalogo = FakeCatalogoTemplates()
    with pytest.raises(TemplateInvalido, match="Já existe"):
        await _criar(repo, catalogo).executar(
            usuario=_super_admin(),
            nome="aviso_geral",
            corpo=CORPO_OK,
            categoria=CategoriaTemplate.UTILITY,
            exemplos=["Maria", "aviso."],
        )
    assert catalogo.submetidos == []  # não gastou uma submissão


@pytest.mark.asyncio
async def test_categoria_authentication_recusada():
    with pytest.raises(TemplateInvalido, match="authentication"):
        await _criar().executar(
            usuario=_super_admin(),
            nome="codigo",
            corpo=CORPO_OK,
            categoria=CategoriaTemplate.AUTHENTICATION,
            exemplos=["Maria", "123456"],
        )


@pytest.mark.asyncio
async def test_exemplo_faltando_recusado_antes_da_meta():
    catalogo = FakeCatalogoTemplates()
    with pytest.raises(TemplateInvalido, match="exemplo"):
        await _criar(catalogo=catalogo).executar(
            usuario=_super_admin(),
            nome="aviso_geral",
            corpo=CORPO_OK,
            categoria=CategoriaTemplate.UTILITY,
            exemplos=["só um"],
        )
    assert catalogo.submetidos == []


@pytest.mark.asyncio
async def test_template_recusado_pela_meta_nao_entra_no_catalogo():
    """Gravar antes de submeter deixaria na lista um template que não existe lá."""
    repo = FakeTemplateRepo()
    catalogo = FakeCatalogoTemplates(erro=RuntimeError("Meta recusou"))
    with pytest.raises(RuntimeError):
        await _criar(repo, catalogo).executar(
            usuario=_super_admin(),
            nome="aviso_geral",
            corpo=CORPO_OK,
            categoria=CategoriaTemplate.UTILITY,
            exemplos=["Maria", "aviso."],
        )
    assert repo.templates == []


@pytest.mark.asyncio
async def test_reclassificacao_da_meta_e_persistida():
    """A Meta pode virar utility em marketing na submissão — e isso muda o preço."""
    catalogo = FakeCatalogoTemplates()

    async def submeter(template, *, meta_waba_id=""):
        catalogo.submetidos.append(template)
        return TemplateRemoto(
            nome=template.nome, idioma=template.idioma,
            status=StatusTemplate.PENDENTE, categoria=CategoriaTemplate.MARKETING,
            meta_template_id="meta-9",
        )

    catalogo.submeter = submeter  # type: ignore[method-assign]
    template = await _criar(catalogo=catalogo).executar(
        usuario=_super_admin(),
        nome="aviso_geral",
        corpo=CORPO_OK,
        categoria=CategoriaTemplate.UTILITY,
        exemplos=["Maria", "aviso."],
    )
    assert template.categoria is CategoriaTemplate.MARKETING


# --------------------------------------------------------------------------- #
# Visibilidade e isolamento
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_escola_ve_globais_e_os_proprios_mas_nao_os_de_outra():
    repo = FakeTemplateRepo()
    await repo.salvar(MessageTemplate(nome="global", categoria=CategoriaTemplate.UTILITY,
                                      idioma="pt_BR", corpo=CORPO_OK))
    await repo.salvar(MessageTemplate(tenant_id=TENANT, nome="meu",
                                      categoria=CategoriaTemplate.UTILITY,
                                      idioma="pt_BR", corpo=CORPO_OK))
    await repo.salvar(MessageTemplate(tenant_id=OUTRO_TENANT, nome="alheio",
                                      categoria=CategoriaTemplate.UTILITY,
                                      idioma="pt_BR", corpo=CORPO_OK))

    nomes = [t.nome for t in await ListarTemplates(templates=repo).executar(tenant_id=TENANT)]
    assert nomes == ["global", "meu"]


@pytest.mark.asyncio
async def test_template_da_escola_tem_precedencia_sobre_o_global_de_mesmo_nome():
    repo = FakeTemplateRepo()
    await repo.salvar(MessageTemplate(nome="aviso", categoria=CategoriaTemplate.UTILITY,
                                      idioma="pt_BR", corpo="Global: {{1}} fim."))
    await repo.salvar(MessageTemplate(tenant_id=TENANT, nome="aviso",
                                      categoria=CategoriaTemplate.UTILITY,
                                      idioma="pt_BR", corpo="Da escola: {{1}} fim."))
    achado = await repo.por_nome(tenant_id=TENANT, nome="aviso")
    assert achado is not None and achado.tenant_id == TENANT


@pytest.mark.asyncio
async def test_admin_de_escola_nao_remove_template_global():
    repo = FakeTemplateRepo()
    global_ = await repo.salvar(
        MessageTemplate(nome="aviso_geral", categoria=CategoriaTemplate.UTILITY,
                        idioma="pt_BR", corpo=CORPO_OK)
    )
    catalogo = FakeCatalogoTemplates()
    with pytest.raises(PermissaoTemplateNegada):
        await RemoverTemplate(templates=repo, catalogo=catalogo, wabas=FakeWabaRepo()).executar(
            usuario=_admin_escola(), tenant_id=TENANT, template_id=global_.id
        )
    assert catalogo.removidos == []  # nem chegou a tocar na Meta


@pytest.mark.asyncio
async def test_remover_apaga_na_meta_e_no_catalogo():
    repo = FakeTemplateRepo()
    meu = await repo.salvar(
        _pendente("rosacury_festa", tenant_id=TENANT)
    )
    catalogo = FakeCatalogoTemplates()
    await RemoverTemplate(templates=repo, catalogo=catalogo, wabas=FakeWabaRepo()).executar(
        usuario=_admin_escola(), tenant_id=TENANT, template_id=meu.id
    )
    assert catalogo.removidos == ["rosacury_festa"]
    assert repo.templates == []


# --------------------------------------------------------------------------- #
# Webhook message_template_status_update
# --------------------------------------------------------------------------- #
def _evento(**valor) -> dict:
    return {
        "entry": [
            {
                "id": "900900900",  # id da WABA: é o que diz em qual conta aplicar
                "changes": [
                    {"field": "message_template_status_update", "value": valor}
                ],
            }
        ]
    }


@pytest.mark.asyncio
async def test_webhook_aprova_template_pelo_meta_id():
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente("retomada_atendimento", wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.PENDENTE, meta_template_id="777")])
    )
    n = await AtualizarStatusTemplateMeta(templates=repo, wabas=FakeWabaRepo()).executar(
        payload=_evento(message_template_id=777, event="APPROVED", reason="NONE")
    )
    assert n == 1
    assert repo.templates[0].aprovado_em(WABA_PADRAO_ID)
    assert repo.templates[0].motivo_em(WABA_PADRAO_ID) == ""


@pytest.mark.asyncio
async def test_webhook_rejeita_e_guarda_o_motivo():
    """'Rejeitado' sem motivo é o estado em que se resubmete o mesmo erro."""
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente("aviso_geral", wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.PENDENTE)])
    )
    await AtualizarStatusTemplateMeta(templates=repo, wabas=FakeWabaRepo()).executar(
        payload=_evento(
            message_template_name="aviso_geral",
            message_template_language="pt_BR",
            event="REJECTED",
            reason="INVALID_FORMAT",
        )
    )
    assert repo.templates[0].status_em(WABA_PADRAO_ID) is StatusTemplate.REJEITADO
    assert repo.templates[0].motivo_em(WABA_PADRAO_ID) == "INVALID_FORMAT"


@pytest.mark.asyncio
async def test_webhook_pausado_nao_conta_como_aprovado():
    """PAUSED é aprovado-e-caído-por-qualidade: enviar falha na Graph API."""
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente("aviso_geral", wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)])
    )
    await AtualizarStatusTemplateMeta(templates=repo, wabas=FakeWabaRepo()).executar(
        payload=_evento(message_template_name="aviso_geral", event="PAUSED")
    )
    assert repo.templates[0].utilizavel is False
    assert "qualidade" in repo.templates[0].motivo_em(WABA_PADRAO_ID)


@pytest.mark.asyncio
async def test_webhook_status_desconhecido_nao_libera_envio():
    """Falhar fechado: status novo não pode virar 'aprovado' por omissão."""
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente("aviso_geral", wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.PENDENTE)])
    )
    await AtualizarStatusTemplateMeta(templates=repo, wabas=FakeWabaRepo()).executar(
        payload=_evento(message_template_name="aviso_geral", event="ALGO_NOVO_DA_META")
    )
    assert repo.templates[0].utilizavel is False


@pytest.mark.asyncio
async def test_webhook_ignora_template_fora_do_catalogo():
    repo = FakeTemplateRepo()
    n = await AtualizarStatusTemplateMeta(templates=repo, wabas=FakeWabaRepo()).executar(
        payload=_evento(message_template_name="criado_no_manager", event="APPROVED")
    )
    assert n == 0


@pytest.mark.asyncio
async def test_webhook_ignora_outros_campos_do_envelope():
    """O mesmo POST carrega status de entrega e mensagens — não pode confundir."""
    repo = FakeTemplateRepo()
    payload = {"entry": [{"changes": [{"field": "messages", "value": {"messages": []}}]}]}
    assert await AtualizarStatusTemplateMeta(templates=repo, wabas=FakeWabaRepo()).executar(payload=payload) == 0


@pytest.mark.asyncio
async def test_webhook_aplica_reclassificacao_de_categoria():
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente("aviso_geral", wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)])
    )
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "field": "template_category_update",
                        "value": {
                            "message_template_name": "aviso_geral",
                            "new_category": "MARKETING",
                        },
                    }
                ]
            }
        ]
    }
    await AtualizarStatusTemplateMeta(templates=repo, wabas=FakeWabaRepo()).executar(payload=payload)
    assert repo.templates[0].categoria is CategoriaTemplate.MARKETING


# --------------------------------------------------------------------------- #
# Sincronização (rede de segurança do webhook)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_sincronizacao_aplica_status_da_meta():
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente("retomada_atendimento", wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.PENDENTE)])
    )
    catalogo = FakeCatalogoTemplates(
        remotos=[
            TemplateRemoto(nome="retomada_atendimento", idioma="pt_BR",
                           status=StatusTemplate.APROVADO,
                           categoria=CategoriaTemplate.UTILITY, meta_template_id="42"),
            TemplateRemoto(nome="hello_world", idioma="en_US",
                           status=StatusTemplate.APROVADO,
                           categoria=CategoriaTemplate.UTILITY),
        ]
    )
    resultado = await SincronizarTemplates(templates=repo, catalogo=catalogo, wabas=FakeWabaRepo()).executar()

    assert resultado.verificados == 2
    assert resultado.atualizados == 1
    # hello_world existe na Meta e não no catálogo: contado, não importado às cegas.
    assert resultado.desconhecidos == 1
    assert repo.templates[0].aprovado_em(WABA_PADRAO_ID)
    assert repo.templates[0].na_waba(WABA_PADRAO_ID).meta_template_id == "42"


@pytest.mark.asyncio
async def test_sincronizacao_sem_mudanca_nao_regrava():
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente("aviso_geral", wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)])
    )
    catalogo = FakeCatalogoTemplates(
        remotos=[
            TemplateRemoto(nome="aviso_geral", idioma="pt_BR",
                           status=StatusTemplate.APROVADO,
                           categoria=CategoriaTemplate.UTILITY)
        ]
    )
    resultado = await SincronizarTemplates(templates=repo, catalogo=catalogo, wabas=FakeWabaRepo()).executar()
    assert resultado.atualizados == 0


# --------------------------------------------------------------------------- #
# Várias contas (WABAs) — o que a segunda conta quebrava
# --------------------------------------------------------------------------- #
def _duas_contas() -> FakeWabaRepo:
    return FakeWabaRepo(
        [
            waba_padrao(),
            Waba(id=SEGUNDA_WABA_ID, meta_waba_id="700700700", nome="WABA 2"),
        ]
    )


SEGUNDA_WABA_ID = uuid4()


@pytest.mark.asyncio
async def test_template_global_e_submetido_em_todas_as_contas():
    """O texto é um; as submissões são N. Sem isso, a conta 2 fica sem catálogo."""
    catalogo = FakeCatalogoTemplates()
    template = await _criar(catalogo=catalogo, wabas=_duas_contas()).executar(
        usuario=_super_admin(),
        nome="aviso_geral",
        corpo=CORPO_OK,
        categoria=CategoriaTemplate.UTILITY,
        exemplos=["Maria", "a reunião é dia 20/08."],
    )
    assert catalogo.contas_submetidas == ["900900900", "700700700"]
    assert {e.waba_id for e in template.wabas} == {WABA_PADRAO_ID, SEGUNDA_WABA_ID}
    # Um id por conta: a Meta emite um para cada, e é ele que o webhook devolve.
    assert len({e.meta_template_id for e in template.wabas}) == 2


@pytest.mark.asyncio
async def test_template_da_escola_vai_so_para_a_conta_dela():
    """Ocupar o nome nas outras contas multiplicaria o risco de rejeição à toa."""
    catalogo = FakeCatalogoTemplates()
    escola = _escola(waba_id=SEGUNDA_WABA_ID)
    await _criar(
        catalogo=catalogo, tenants=FakeTenantRepo([escola]), wabas=_duas_contas()
    ).executar(
        usuario=_admin_escola(),
        nome="festa_junina",
        corpo=CORPO_OK,
        categoria=CategoriaTemplate.UTILITY,
        exemplos=["Maria", "a festa é dia 20/06."],
        tenant_id=TENANT,
    )
    assert catalogo.contas_submetidas == ["700700700"]


@pytest.mark.asyncio
async def test_escola_sem_conta_nao_cria_template():
    """Falha explícita e no painel — não uma submissão silenciosa na conta errada."""
    escola = _escola(waba_id=None)
    with pytest.raises(SemContaWhatsApp, match="não está vinculada"):
        await _criar(tenants=FakeTenantRepo([escola])).executar(
            usuario=_admin_escola(),
            nome="festa_junina",
            corpo=CORPO_OK,
            categoria=CategoriaTemplate.UTILITY,
            exemplos=["Maria", "a festa é dia 20/06."],
            tenant_id=TENANT,
        )


@pytest.mark.asyncio
async def test_aprovado_numa_conta_nao_libera_a_outra():
    """A mentira que o modelo por conta veio corrigir: o disparo da escola 2 falharia."""
    template = _pendente(
        "aviso_geral",
        wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
    )
    assert template.aprovado_em(WABA_PADRAO_ID) is True
    assert template.aprovado_em(SEGUNDA_WABA_ID) is False
    # Nunca submetido naquela conta é rascunho, não "pendente de revisão".
    assert template.status_em(SEGUNDA_WABA_ID) is StatusTemplate.RASCUNHO


def test_status_consolidado_e_o_pior_entre_as_contas():
    """Selo otimista convidaria a secretaria de uma escola a um disparo que falha."""
    template = _pendente(
        "aviso_geral",
        wabas=[
            TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO),
            TemplateNaWaba(waba_id=SEGUNDA_WABA_ID, status=StatusTemplate.PENDENTE),
        ],
    )
    assert template.status is StatusTemplate.PENDENTE
    assert template.utilizavel is False


@pytest.mark.asyncio
async def test_falha_numa_conta_nao_desfaz_a_outra():
    """Desfazer gastaria outra submissão para voltar ao início; a conta fica sem entrada."""

    class CatalogoParcial(FakeCatalogoTemplates):
        async def submeter(self, template, *, meta_waba_id=""):
            if meta_waba_id == "700700700":
                raise RuntimeError("timeout falando com a Meta")
            return await super().submeter(template, meta_waba_id=meta_waba_id)

    template = await _criar(catalogo=CatalogoParcial(), wabas=_duas_contas()).executar(
        usuario=_super_admin(),
        nome="aviso_geral",
        corpo=CORPO_OK,
        categoria=CategoriaTemplate.UTILITY,
        exemplos=["Maria", "aviso."],
    )
    assert [e.waba_id for e in template.wabas] == [WABA_PADRAO_ID]
    assert template.status_em(SEGUNDA_WABA_ID) is StatusTemplate.RASCUNHO


@pytest.mark.asyncio
async def test_replicacao_leva_os_globais_para_a_conta_nova():
    """O passo que faz a conta nova herdar o catálogo — sem ele, a escola 21 fica sem nada."""
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente(
            "aviso_geral",
            wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
        )
    )
    # Template de escola: não deve ser replicado.
    await repo.salvar(_pendente("rosacury_festa", tenant_id=TENANT))

    catalogo = FakeCatalogoTemplates()
    resultado = await ReplicarTemplates(
        templates=repo, catalogo=catalogo, wabas=_duas_contas()
    ).executar()

    assert resultado.submetidos == 1
    assert catalogo.contas_submetidas == ["700700700"]
    assert repo.templates[0].status_em(SEGUNDA_WABA_ID) is StatusTemplate.PENDENTE


@pytest.mark.asyncio
async def test_replicacao_e_idempotente():
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente(
            "aviso_geral",
            wabas=[
                TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO),
                TemplateNaWaba(waba_id=SEGUNDA_WABA_ID, status=StatusTemplate.APROVADO),
            ],
        )
    )
    catalogo = FakeCatalogoTemplates()
    resultado = await ReplicarTemplates(
        templates=repo, catalogo=catalogo, wabas=_duas_contas()
    ).executar()
    assert resultado.submetidos == 0
    assert catalogo.contas_submetidas == []


@pytest.mark.asyncio
async def test_webhook_aplica_o_status_na_conta_do_evento():
    """`entry[].id` é a WABA: sem olhá-lo, a aprovação da conta A marcaria a conta B."""
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente(
            "aviso_geral",
            wabas=[
                TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.PENDENTE),
                TemplateNaWaba(waba_id=SEGUNDA_WABA_ID, status=StatusTemplate.PENDENTE),
            ],
        )
    )
    payload = {
        "entry": [
            {
                "id": "700700700",  # conta 2
                "changes": [
                    {
                        "field": "message_template_status_update",
                        "value": {
                            "message_template_name": "aviso_geral",
                            "message_template_language": "pt_BR",
                            "event": "APPROVED",
                        },
                    }
                ],
            }
        ]
    }
    await AtualizarStatusTemplateMeta(templates=repo, wabas=_duas_contas()).executar(
        payload=payload
    )
    assert repo.templates[0].aprovado_em(SEGUNDA_WABA_ID) is True
    assert repo.templates[0].aprovado_em(WABA_PADRAO_ID) is False


@pytest.mark.asyncio
async def test_sincronizacao_percorre_todas_as_contas():
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente(
            "aviso_geral",
            wabas=[
                TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.PENDENTE),
                TemplateNaWaba(waba_id=SEGUNDA_WABA_ID, status=StatusTemplate.PENDENTE),
            ],
        )
    )
    catalogo = FakeCatalogoTemplates(
        remotos=[
            TemplateRemoto(
                nome="aviso_geral", idioma="pt_BR", status=StatusTemplate.APROVADO,
                categoria=CategoriaTemplate.UTILITY,
            )
        ]
    )
    resultado = await SincronizarTemplates(
        templates=repo, catalogo=catalogo, wabas=_duas_contas()
    ).executar()

    # A mesma listagem chega das duas contas: 2 verificados, 1 template atualizado.
    assert resultado.verificados == 2
    assert resultado.atualizados == 1
    assert repo.templates[0].aprovado_em(WABA_PADRAO_ID) is True
    assert repo.templates[0].aprovado_em(SEGUNDA_WABA_ID) is True


# --------------------------------------------------------------------------- #
# Reconhecimento da conta pelo webhook (o fim do META_WABA_ID)
# --------------------------------------------------------------------------- #
def _adotar(wabas, catalogo=None) -> AdotarContaDoWebhook:
    return AdotarContaDoWebhook(wabas=wabas, catalogo=catalogo or FakeCatalogoTemplates())


def _evento_de_conta(waba_id: str) -> dict:
    return {"entry": [{"id": waba_id, "changes": [{"field": "messages", "value": {}}]}]}


@pytest.mark.asyncio
async def test_conta_sem_id_adota_o_do_webhook_confirmado_na_meta():
    """O que substitui a variável de ambiente: o id chega e é conferido antes de gravar."""
    repo = FakeWabaRepo([Waba(meta_waba_id="", nome="WABA principal")])
    catalogo = FakeCatalogoTemplates()
    catalogo.contas_conhecidas = {"2116419572321695": "TI-Escolar"}

    adotada = await _adotar(repo, catalogo).executar(
        payload=_evento_de_conta("2116419572321695")
    )

    assert adotada is not None
    assert adotada.meta_waba_id == "2116419572321695"
    # O nome vem da Meta: é como a conta aparece no WhatsApp Manager, onde alguém confere.
    assert adotada.nome == "TI-Escolar"


@pytest.mark.asyncio
async def test_id_nao_confirmado_pela_meta_nao_e_gravado():
    """A documentação não afirma que `entry[].id` é a WABA — então quem decide é a Meta."""
    repo = FakeWabaRepo([Waba(meta_waba_id="", nome="WABA principal")])
    catalogo = FakeCatalogoTemplates()
    catalogo.contas_conhecidas = {}  # a Meta não reconhece nada

    assert await _adotar(repo, catalogo).executar(
        payload=_evento_de_conta("999999999")
    ) is None
    assert repo.wabas[0].meta_waba_id == ""


@pytest.mark.asyncio
async def test_com_duas_contas_sem_id_nao_adota_nenhuma():
    """Escolher uma seria chute, e o chute erra justamente onde há várias contas."""
    repo = FakeWabaRepo(
        [Waba(meta_waba_id="", nome="Conta A"), Waba(meta_waba_id="", nome="Conta B")]
    )
    assert await _adotar(repo).executar(payload=_evento_de_conta("700700700")) is None
    assert all(w.meta_waba_id == "" for w in repo.wabas)


@pytest.mark.asyncio
async def test_conta_ja_cadastrada_nao_e_tocada():
    """O caso comum: todo evento depois do primeiro não deve escrever nada."""
    repo = FakeWabaRepo([waba_padrao()])
    assert await _adotar(repo).executar(payload=_evento_de_conta("900900900")) is None
    assert repo.wabas[0].nome == "WABA principal"


@pytest.mark.asyncio
async def test_entry_sem_id_numerico_e_ignorada():
    repo = FakeWabaRepo([Waba(meta_waba_id="", nome="WABA principal")])
    payload = {"entry": [{"id": "", "changes": []}, {"changes": []}]}
    assert await _adotar(repo).executar(payload=payload) is None
    assert repo.wabas[0].meta_waba_id == ""


# --------------------------------------------------------------------------- #
# O catálogo não pode afirmar aprovação que a Meta não deu (14/ago/2026)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_sincronizacao_desmente_template_que_nao_existe_na_meta():
    """A falha do primeiro disparo real: 'Aprovado' num template que nunca foi submetido.

    O `aviso_reuniao` entrou no banco pelo seed com `status='aprovado'` e o seed rodou em
    homolog, onde o canal é real. A trava de envio consultou esse dado, liberou, e a Graph
    API recusou os dois destinatários. A reconciliação era de mão única e nunca desmentia.
    """
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente(
            "aviso_reuniao",
            wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
        )
    )
    # A Meta só conhece outro template.
    catalogo = FakeCatalogoTemplates(
        remotos=[
            TemplateRemoto(
                nome="retomada_atendimento", idioma="pt_BR",
                status=StatusTemplate.APROVADO, categoria=CategoriaTemplate.UTILITY,
            )
        ]
    )
    resultado = await SincronizarTemplates(
        templates=repo, catalogo=catalogo, wabas=FakeWabaRepo()
    ).executar()

    assert resultado.desmentidos == 1
    assert repo.templates[0].aprovado_em(WABA_PADRAO_ID) is False
    assert repo.templates[0].status_em(WABA_PADRAO_ID) is StatusTemplate.RASCUNHO
    assert "não existe" in repo.templates[0].motivo_em(WABA_PADRAO_ID).lower()


@pytest.mark.asyncio
async def test_conta_fora_do_ar_nao_desmente_nada():
    """Falha de rede não pode zerar o catálogo de quem está no ar."""
    repo = FakeTemplateRepo()
    await repo.salvar(
        _pendente(
            "aviso_geral",
            wabas=[TemplateNaWaba(waba_id=WABA_PADRAO_ID, status=StatusTemplate.APROVADO)],
        )
    )
    catalogo = FakeCatalogoTemplates(erro=RuntimeError("timeout"))
    resultado = await SincronizarTemplates(
        templates=repo, catalogo=catalogo, wabas=FakeWabaRepo()
    ).executar()

    assert resultado.desmentidos == 0
    assert repo.templates[0].aprovado_em(WABA_PADRAO_ID) is True


@pytest.mark.asyncio
async def test_template_nunca_submetido_naquela_conta_nao_conta_como_desmentido():
    """`RASCUNHO` já significa "não está lá" — desmentir de novo inflaria o número."""
    repo = FakeTemplateRepo()
    await repo.salvar(_pendente("aviso_geral", wabas=[]))
    resultado = await SincronizarTemplates(
        templates=repo, catalogo=FakeCatalogoTemplates(), wabas=FakeWabaRepo()
    ).executar()
    assert resultado.desmentidos == 0


@pytest.mark.asyncio
async def test_importa_template_que_ja_existe_na_meta():
    """Destrava o `retomada_atendimento`, aprovado na Meta e invisível para o catálogo.

    Sem ele no catálogo, `_template_de_retomada` não acha nada e a secretaria não consegue
    responder quem escreveu há mais de 24h (§6j).
    """
    repo = FakeTemplateRepo()
    catalogo = FakeCatalogoTemplates(
        remotos=[
            TemplateRemoto(
                nome="retomada_atendimento", idioma="pt_BR",
                status=StatusTemplate.APROVADO, categoria=CategoriaTemplate.UTILITY,
                meta_template_id="777", corpo="Olá! Aqui é a secretaria da {{1}}: {{2}} Até.",
            )
        ]
    )
    template = await ImportarTemplateDaMeta(
        templates=repo, catalogo=catalogo, wabas=FakeWabaRepo()
    ).executar(usuario=_super_admin(), nome="retomada_atendimento")

    assert template.global_ is True
    assert template.corpo.startswith("Olá! Aqui é a secretaria")
    assert template.aprovado_em(WABA_PADRAO_ID) is True
    # Importar não submete nada: o template já está lá.
    assert catalogo.submetidos == []


@pytest.mark.asyncio
async def test_importar_exige_super_admin():
    with pytest.raises(PermissaoTemplateNegada):
        await ImportarTemplateDaMeta(
            templates=FakeTemplateRepo(),
            catalogo=FakeCatalogoTemplates(),
            wabas=FakeWabaRepo(),
        ).executar(usuario=_admin_escola(), nome="retomada_atendimento")


@pytest.mark.asyncio
async def test_importar_o_que_a_meta_nao_tem_e_recusado():
    with pytest.raises(TemplateNaoEncontrado):
        await ImportarTemplateDaMeta(
            templates=FakeTemplateRepo(),
            catalogo=FakeCatalogoTemplates(remotos=[]),
            wabas=FakeWabaRepo(),
        ).executar(usuario=_super_admin(), nome="nao_existe")


@pytest.mark.asyncio
async def test_importar_sem_corpo_e_recusado():
    """Registro local sem corpo é casca: a tela não mostra o texto e o disparo não sabe
    quantas variáveis pedir."""
    catalogo = FakeCatalogoTemplates(
        remotos=[
            TemplateRemoto(
                nome="sem_corpo", idioma="pt_BR", status=StatusTemplate.APROVADO,
                categoria=CategoriaTemplate.UTILITY, corpo="",
            )
        ]
    )
    with pytest.raises(TemplateInvalido, match="às cegas"):
        await ImportarTemplateDaMeta(
            templates=FakeTemplateRepo(), catalogo=catalogo, wabas=FakeWabaRepo()
        ).executar(usuario=_super_admin(), nome="sem_corpo")
