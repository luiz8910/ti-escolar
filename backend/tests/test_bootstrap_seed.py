"""Política do seed de demonstração (§ item 1 do checklist de produção).

O que se verifica aqui é uma regra de operação, não de negócio: em que ambiente é
aceitável despejar escola fictícia e senhas de exemplo no banco. Antes disso o seed
rodava no ``CMD`` do container, ou seja, em produção, a cada deploy.
"""

from __future__ import annotations

from app.bootstrap import (
    CAMPOS_SENHA_DEMO,
    avaliar_seed,
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
