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
    ListarTemplates,
    PermissaoTemplateNegada,
    RemoverTemplate,
    SincronizarTemplates,
)
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
    TemplateRemoto,
    Tenant,
    Usuario,
)
from tests.fakes import FakeCatalogoTemplates, FakeTemplateRepo

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


def _escola(tenant_id=TENANT, slug="rosacury") -> Tenant:
    return Tenant(id=tenant_id, nome="EM Rosa Cury", slug=slug)


def _criar(templates=None, catalogo=None, tenants=None) -> CriarTemplate:
    return CriarTemplate(
        templates=templates or FakeTemplateRepo(),
        catalogo=catalogo or FakeCatalogoTemplates(),
        tenants=tenants or FakeTenantRepo([_escola()]),
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
    assert template.meta_template_id == "meta-1"
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

    async def submeter(template):
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
        await RemoverTemplate(templates=repo, catalogo=catalogo).executar(
            usuario=_admin_escola(), tenant_id=TENANT, template_id=global_.id
        )
    assert catalogo.removidos == []  # nem chegou a tocar na Meta


@pytest.mark.asyncio
async def test_remover_apaga_na_meta_e_no_catalogo():
    repo = FakeTemplateRepo()
    meu = await repo.salvar(
        MessageTemplate(tenant_id=TENANT, nome="rosacury_festa",
                        categoria=CategoriaTemplate.UTILITY, idioma="pt_BR", corpo=CORPO_OK)
    )
    catalogo = FakeCatalogoTemplates()
    await RemoverTemplate(templates=repo, catalogo=catalogo).executar(
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
            {"changes": [{"field": "message_template_status_update", "value": valor}]}
        ]
    }


@pytest.mark.asyncio
async def test_webhook_aprova_template_pelo_meta_id():
    repo = FakeTemplateRepo()
    await repo.salvar(
        MessageTemplate(nome="retomada_atendimento", categoria=CategoriaTemplate.UTILITY,
                        idioma="pt_BR", corpo=CORPO_OK, status=StatusTemplate.PENDENTE,
                        meta_template_id="777")
    )
    n = await AtualizarStatusTemplateMeta(templates=repo).executar(
        payload=_evento(message_template_id=777, event="APPROVED", reason="NONE")
    )
    assert n == 1
    assert repo.templates[0].status is StatusTemplate.APROVADO
    assert repo.templates[0].motivo_rejeicao == ""


@pytest.mark.asyncio
async def test_webhook_rejeita_e_guarda_o_motivo():
    """'Rejeitado' sem motivo é o estado em que se resubmete o mesmo erro."""
    repo = FakeTemplateRepo()
    await repo.salvar(
        MessageTemplate(nome="aviso_geral", categoria=CategoriaTemplate.UTILITY,
                        idioma="pt_BR", corpo=CORPO_OK, status=StatusTemplate.PENDENTE)
    )
    await AtualizarStatusTemplateMeta(templates=repo).executar(
        payload=_evento(
            message_template_name="aviso_geral",
            message_template_language="pt_BR",
            event="REJECTED",
            reason="INVALID_FORMAT",
        )
    )
    assert repo.templates[0].status is StatusTemplate.REJEITADO
    assert repo.templates[0].motivo_rejeicao == "INVALID_FORMAT"


@pytest.mark.asyncio
async def test_webhook_pausado_nao_conta_como_aprovado():
    """PAUSED é aprovado-e-caído-por-qualidade: enviar falha na Graph API."""
    repo = FakeTemplateRepo()
    await repo.salvar(
        MessageTemplate(nome="aviso_geral", categoria=CategoriaTemplate.UTILITY,
                        idioma="pt_BR", corpo=CORPO_OK, status=StatusTemplate.APROVADO)
    )
    await AtualizarStatusTemplateMeta(templates=repo).executar(
        payload=_evento(message_template_name="aviso_geral", event="PAUSED")
    )
    assert repo.templates[0].utilizavel is False
    assert "qualidade" in repo.templates[0].motivo_rejeicao


@pytest.mark.asyncio
async def test_webhook_status_desconhecido_nao_libera_envio():
    """Falhar fechado: status novo não pode virar 'aprovado' por omissão."""
    repo = FakeTemplateRepo()
    await repo.salvar(
        MessageTemplate(nome="aviso_geral", categoria=CategoriaTemplate.UTILITY,
                        idioma="pt_BR", corpo=CORPO_OK, status=StatusTemplate.PENDENTE)
    )
    await AtualizarStatusTemplateMeta(templates=repo).executar(
        payload=_evento(message_template_name="aviso_geral", event="ALGO_NOVO_DA_META")
    )
    assert repo.templates[0].utilizavel is False


@pytest.mark.asyncio
async def test_webhook_ignora_template_fora_do_catalogo():
    repo = FakeTemplateRepo()
    n = await AtualizarStatusTemplateMeta(templates=repo).executar(
        payload=_evento(message_template_name="criado_no_manager", event="APPROVED")
    )
    assert n == 0


@pytest.mark.asyncio
async def test_webhook_ignora_outros_campos_do_envelope():
    """O mesmo POST carrega status de entrega e mensagens — não pode confundir."""
    repo = FakeTemplateRepo()
    payload = {"entry": [{"changes": [{"field": "messages", "value": {"messages": []}}]}]}
    assert await AtualizarStatusTemplateMeta(templates=repo).executar(payload=payload) == 0


@pytest.mark.asyncio
async def test_webhook_aplica_reclassificacao_de_categoria():
    repo = FakeTemplateRepo()
    await repo.salvar(
        MessageTemplate(nome="aviso_geral", categoria=CategoriaTemplate.UTILITY,
                        idioma="pt_BR", corpo=CORPO_OK, status=StatusTemplate.APROVADO)
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
    await AtualizarStatusTemplateMeta(templates=repo).executar(payload=payload)
    assert repo.templates[0].categoria is CategoriaTemplate.MARKETING


# --------------------------------------------------------------------------- #
# Sincronização (rede de segurança do webhook)
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_sincronizacao_aplica_status_da_meta():
    repo = FakeTemplateRepo()
    await repo.salvar(
        MessageTemplate(nome="retomada_atendimento", categoria=CategoriaTemplate.UTILITY,
                        idioma="pt_BR", corpo=CORPO_OK, status=StatusTemplate.PENDENTE)
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
    resultado = await SincronizarTemplates(templates=repo, catalogo=catalogo).executar()

    assert resultado.verificados == 2
    assert resultado.atualizados == 1
    # hello_world existe na Meta e não no catálogo: contado, não importado às cegas.
    assert resultado.desconhecidos == 1
    assert repo.templates[0].status is StatusTemplate.APROVADO
    assert repo.templates[0].meta_template_id == "42"


@pytest.mark.asyncio
async def test_sincronizacao_sem_mudanca_nao_regrava():
    repo = FakeTemplateRepo()
    await repo.salvar(
        MessageTemplate(nome="aviso_geral", categoria=CategoriaTemplate.UTILITY,
                        idioma="pt_BR", corpo=CORPO_OK, status=StatusTemplate.APROVADO)
    )
    catalogo = FakeCatalogoTemplates(
        remotos=[
            TemplateRemoto(nome="aviso_geral", idioma="pt_BR",
                           status=StatusTemplate.APROVADO,
                           categoria=CategoriaTemplate.UTILITY)
        ]
    )
    resultado = await SincronizarTemplates(templates=repo, catalogo=catalogo).executar()
    assert resultado.atualizados == 0
