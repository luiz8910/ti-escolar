"""Assinatura do webhook da Meta e postura de segurança do super admin (§9e.2 / §14)."""

from __future__ import annotations

import hashlib
import hmac

from app.application.seguranca_use_cases import (
    JWT_SECRET_PADRAO,
    META_VERIFY_TOKEN_PADRAO,
    AvaliarPosturaSeguranca,
    ConfiguracaoSeguranca,
)
from app.domain.entities import StatusMedida
from app.infrastructure.security import validar_assinatura_meta

SEGREDO = "app-secret-de-teste"
CORPO = b'{"object":"whatsapp_business_account","entry":[]}'


def _assinar(corpo: bytes, segredo: str = SEGREDO) -> str:
    return "sha256=" + hmac.new(segredo.encode(), corpo, hashlib.sha256).hexdigest()


# --------------------------------------------------------------------------- #
# Assinatura do webhook
# --------------------------------------------------------------------------- #


def test_assinatura_valida_e_aceita():
    assert validar_assinatura_meta(
        corpo=CORPO, cabecalho=_assinar(CORPO), app_secret=SEGREDO
    )


def test_assinatura_de_outro_segredo_e_recusada():
    """Quem não tem o app secret não consegue forjar um evento."""
    assert not validar_assinatura_meta(
        corpo=CORPO, cabecalho=_assinar(CORPO, "segredo-do-atacante"), app_secret=SEGREDO
    )


def test_corpo_adulterado_invalida_a_assinatura():
    """Assinatura legítima + corpo trocado (ex.: 'failed' virando 'delivered') não passa."""
    adulterado = CORPO.replace(b"[]", b'[{"forjado":true}]')
    assert not validar_assinatura_meta(
        corpo=adulterado, cabecalho=_assinar(CORPO), app_secret=SEGREDO
    )


def test_cabecalho_ausente_ou_malformado_e_recusado():
    for cabecalho in (None, "", "abc", "sha1=deadbeef", "sha256=", "sha256"):
        assert not validar_assinatura_meta(
            corpo=CORPO, cabecalho=cabecalho, app_secret=SEGREDO
        )


def test_sem_app_secret_nada_e_aceito():
    """Sem a chave do HMAC não há como validar — negar é o comportamento seguro."""
    assert not validar_assinatura_meta(
        corpo=CORPO, cabecalho=_assinar(CORPO), app_secret=""
    )


# --------------------------------------------------------------------------- #
# Postura de segurança
# --------------------------------------------------------------------------- #


def _config(**over) -> ConfiguracaoSeguranca:
    base = dict(
        canal="meta",
        meta_validate_signature=True,
        meta_app_secret_definido=True,
        meta_verify_token_padrao=False,
        jwt_secret_padrao=False,
        jwt_expira_minutos=480,
        cors_liberado=False,
        app_env="production",
        rate_limit_habilitado=True,
        rate_limit_login_tentativas=10,
        rate_limit_inbound_mensagens=20,
        seed_demo_habilitado=False,
    )
    base.update(over)
    return ConfiguracaoSeguranca(**base)


def _medida(postura, chave: str):
    return next(m for m in postura.medidas if m.chave == chave)


def test_ambiente_endurecido_nao_tem_alertas_de_configuracao():
    postura = AvaliarPosturaSeguranca().executar(config=_config())
    assert postura.total_atencao == 0
    assert _medida(postura, "webhook_assinatura").status is StatusMedida.ATIVA


def test_assinatura_desligada_vira_atencao():
    postura = AvaliarPosturaSeguranca().executar(
        config=_config(meta_validate_signature=False)
    )
    medida = _medida(postura, "webhook_assinatura")
    assert medida.status is StatusMedida.ATENCAO
    assert "DESLIGADA" in medida.detalhe


def test_assinatura_ligada_sem_app_secret_vira_atencao():
    postura = AvaliarPosturaSeguranca().executar(
        config=_config(meta_app_secret_definido=False)
    )
    assert _medida(postura, "webhook_assinatura").status is StatusMedida.ATENCAO


def test_segredos_default_sao_sinalizados():
    postura = AvaliarPosturaSeguranca().executar(
        config=_config(jwt_secret_padrao=True, meta_verify_token_padrao=True)
    )
    assert _medida(postura, "jwt_sessao").status is StatusMedida.ATENCAO
    assert _medida(postura, "webhook_verify_token").status is StatusMedida.ATENCAO


def test_cors_liberado_e_ambiente_nao_produtivo_sao_sinalizados():
    postura = AvaliarPosturaSeguranca().executar(
        config=_config(cors_liberado=True, app_env="development")
    )
    assert _medida(postura, "cors").status is StatusMedida.ATENCAO
    assert _medida(postura, "ambiente").status is StatusMedida.ATENCAO


def test_medida_existente_mas_desligada_aparece_como_atencao():
    """O ponto do painel: o caso perigoso não é a medida que falta, é a que existe no
    código e está desligada no ambiente. Um relatório sim/não esconderia justamente ela."""
    postura = AvaliarPosturaSeguranca().executar(
        config=_config(rate_limit_habilitado=False)
    )
    assert _medida(postura, "rate_limit_login").status is StatusMedida.ATENCAO
    assert _medida(postura, "rate_limit_inbound").status is StatusMedida.ATENCAO
    assert not postura.pronto_para_producao


def test_seed_ligado_em_producao_e_alertado():
    """Seed em produção despeja escola fictícia e senha de exemplo no banco real."""
    postura = AvaliarPosturaSeguranca().executar(
        config=_config(seed_demo_habilitado=True, app_env="production")
    )
    assert _medida(postura, "seed_producao").status is StatusMedida.ATENCAO


def test_seed_ligado_fora_de_producao_nao_e_alarme():
    postura = AvaliarPosturaSeguranca().executar(
        config=_config(seed_demo_habilitado=True, app_env="development")
    )
    assert _medida(postura, "seed_producao").status is StatusMedida.ATIVA


def test_toda_medida_declara_o_risco_que_cobre():
    postura = AvaliarPosturaSeguranca().executar(config=_config())
    assert postura.medidas
    for m in postura.medidas:
        assert m.titulo and m.descricao and m.risco and m.categoria


def test_constantes_de_default_batem_com_o_env_example():
    """Se o default mudar no config.py sem atualizar aqui, a auditoria mente."""
    from app.config import Settings

    padrao = Settings(_env_file=None)
    assert padrao.jwt_secret == JWT_SECRET_PADRAO
    assert padrao.meta_webhook_verify_token == META_VERIFY_TOKEN_PADRAO


# --------------------------------------------------------------------------- #
# Checklist de pré-deploy (fonte externa)
# --------------------------------------------------------------------------- #


def _item(postura, numero: int):
    return next(i for i in postura.checklist if i.numero == numero)


def test_checklist_traz_os_nove_itens_na_numeracao_da_fonte():
    """A conferência com a lista de origem é 1:1 — numeração e ordem não podem escorregar."""
    postura = AvaliarPosturaSeguranca().executar(config=_config())
    assert [i.numero for i in postura.checklist] == list(range(1, 10))
    assert postura.checklist_fonte.startswith("https://")


def test_todo_item_declara_exigencia_e_situacao():
    postura = AvaliarPosturaSeguranca().executar(config=_config())
    for i in postura.checklist:
        assert i.titulo and i.exigencia and i.situacao


def test_item_de_checklist_reflete_a_configuracao_viva():
    """O item 5 não é um fato fixo sobre o código: com o limite desligado no ambiente, o
    checklist tem que voltar a acusar dívida."""
    ligado = AvaliarPosturaSeguranca().executar(config=_config())
    assert _item(ligado, 5).status is StatusMedida.ATIVA

    desligado = AvaliarPosturaSeguranca().executar(
        config=_config(rate_limit_habilitado=False)
    )
    assert _item(desligado, 5).status is StatusMedida.ATENCAO


def test_reset_de_senha_e_nao_aplicavel_e_nao_conta_como_divida():
    """Não existe fluxo de reset: marcar como pendente seria alarme falso."""
    postura = AvaliarPosturaSeguranca().executar(config=_config())
    item = _item(postura, 2)
    assert item.status is StatusMedida.NAO_APLICAVEL
    assert postura.checklist_pendentes == sum(
        1
        for i in postura.checklist
        if i.status in (StatusMedida.ATENCAO, StatusMedida.PENDENTE)
    )
    assert item not in [
        i
        for i in postura.checklist
        if i.status in (StatusMedida.ATENCAO, StatusMedida.PENDENTE)
    ]


def test_cors_liberado_rebaixa_o_item_do_checklist():
    """O item 4 acompanha a configuração real, não uma resposta fixa."""
    seguro = AvaliarPosturaSeguranca().executar(config=_config())
    aberto = AvaliarPosturaSeguranca().executar(config=_config(cors_liberado=True))
    assert _item(seguro, 4).status is StatusMedida.ATIVA
    assert _item(aberto, 4).status is StatusMedida.ATENCAO


def test_medidas_relacionadas_apontam_para_chaves_existentes():
    """Referência quebrada tornaria o cruzamento item↔medida inútil no painel."""
    postura = AvaliarPosturaSeguranca().executar(config=_config())
    chaves = {m.chave for m in postura.medidas}
    for i in postura.checklist:
        for chave in i.medidas_relacionadas:
            assert chave in chaves, f"item {i.numero} referencia medida inexistente: {chave}"


def test_checklist_pendente_impede_pronto_para_producao():
    postura = AvaliarPosturaSeguranca().executar(config=_config())
    assert postura.checklist_pendentes > 0
    assert not postura.pronto_para_producao
