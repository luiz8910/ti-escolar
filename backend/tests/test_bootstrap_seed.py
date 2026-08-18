"""Política do seed de demonstração (§ item 1 do checklist de produção).

O que se verifica aqui é uma regra de operação, não de negócio: em que ambiente é
aceitável despejar escola fictícia e senhas de exemplo no banco. Antes disso o seed
rodava no ``CMD`` do container, ou seja, em produção, a cada deploy.
"""

from __future__ import annotations

import pytest

from app.bootstrap import (
    CAMPOS_SENHA_DEMO,
    ConfiguracaoInsegura,
    avaliar_seed,
    exigencias_de_producao,
    exigir_producao_segura,
    segredos_com_valor_default,
    valor_default,
)
from app.config import Settings

# Senhas próprias, para isolar a regra que está sob teste em cada caso.
_SENHAS_PROPRIAS = {
    "super_admin_senha": "S3nh4-forte-do-super",
    "demo_admin_senha": "S3nh4-forte-do-admin",
    "demo_professor_senha": "S3nh4-forte-do-prof",
}


def _settings(**kwargs) -> Settings:
    base = {"app_env": "development", "seed_demo": True, **_SENHAS_PROPRIAS}
    base.update(kwargs)
    return Settings(**base)


def test_producao_nunca_semeia_mesmo_com_flag_ligada():
    decisao = avaliar_seed(_settings(app_env="production", seed_demo=True))
    assert not decisao.permitido
    assert "production" in decisao.motivo


def test_producao_reconhece_grafias_alternativas():
    for grafia in ("production", "producao", "prod", "PRODUCTION"):
        assert not avaliar_seed(_settings(app_env=grafia, seed_demo=True)).permitido


def test_sem_flag_nao_semeia_nem_em_desenvolvimento():
    """O default é fechado: ambiente novo não semeia por omissão."""
    decisao = avaliar_seed(_settings(seed_demo=False))
    assert not decisao.permitido
    assert "SEED_DEMO" in decisao.motivo


def test_homologacao_com_senha_de_exemplo_e_recusada():
    decisao = avaliar_seed(
        _settings(app_env="staging", super_admin_senha=valor_default("super_admin_senha"))
    )
    assert not decisao.permitido
    assert "super_admin_senha" in decisao.motivo


def test_homologacao_com_senhas_proprias_semeia():
    decisao = avaliar_seed(_settings(app_env="staging"))
    assert decisao.permitido


def test_desenvolvimento_aceita_senha_de_exemplo():
    """O banco local é o container descartável do compose — exigir senha forte ali só
    atrapalharia quem clonou o repositório."""
    padroes = {campo: valor_default(campo) for campo in CAMPOS_SENHA_DEMO}
    decisao = avaliar_seed(_settings(app_env="development", **padroes))
    assert decisao.permitido


def test_deteccao_de_segredo_default_e_por_campo():
    settings = _settings(demo_admin_senha=valor_default("demo_admin_senha"))
    assert segredos_com_valor_default(settings, CAMPOS_SENHA_DEMO) == ["demo_admin_senha"]


# --------------------------------------------------------------------------- #
# Guardas de boot em produção (§15, itens 18.5–18.7 do checklist)
# --------------------------------------------------------------------------- #
_PRODUCAO_OK = {
    "app_env": "production",
    "jwt_secret": "segredo-forte-de-verdade",
    "meta_webhook_verify_token": "token-forte-de-verdade",
    "meta_validate_signature": True,
}


def test_producao_bem_configurada_sobe():
    assert exigencias_de_producao(Settings(**_PRODUCAO_OK)) == []
    exigir_producao_segura(Settings(**_PRODUCAO_OK))  # não levanta


def test_desenvolvimento_aceita_todos_os_defaults():
    """Os defaults são o que faz o projeto subir com um `git clone`. Recusá-los em
    desenvolvimento atrapalharia sem proteger nada — o banco é container descartável."""
    assert exigencias_de_producao(Settings(app_env="development")) == []


def test_jwt_secret_de_exemplo_derruba_producao():
    """Quem leu o repositório forja um token de super admin e entra em todas as escolas."""
    s = Settings(**{**_PRODUCAO_OK, "jwt_secret": valor_default("jwt_secret")})
    assert any("JWT_SECRET" in p for p in exigencias_de_producao(s))
    with pytest.raises(ConfiguracaoInsegura, match="JWT_SECRET"):
        exigir_producao_segura(s)


def test_verify_token_de_exemplo_derruba_producao():
    s = Settings(
        **{
            **_PRODUCAO_OK,
            "meta_webhook_verify_token": valor_default("meta_webhook_verify_token"),
        }
    )
    with pytest.raises(ConfiguracaoInsegura, match="META_WEBHOOK_VERIFY_TOKEN"):
        exigir_producao_segura(s)


def test_assinatura_desligada_derruba_producao():
    """Não é segredo default, é proteção desligada — mas o efeito é o mesmo: endpoint
    público aceitando qualquer POST, com status de entrega e conversas forjáveis."""
    s = Settings(**{**_PRODUCAO_OK, "meta_validate_signature": False})
    with pytest.raises(ConfiguracaoInsegura, match="META_VALIDATE_SIGNATURE"):
        exigir_producao_segura(s)


def test_lista_todas_as_pendencias_de_uma_vez():
    """Quem configura um ambiente novo prefere corrigir três coisas juntas a descobrir
    uma por deploy."""
    s = Settings(
        app_env="production",
        jwt_secret=valor_default("jwt_secret"),
        meta_webhook_verify_token=valor_default("meta_webhook_verify_token"),
        meta_validate_signature=False,
    )
    assert len(exigencias_de_producao(s)) == 3
