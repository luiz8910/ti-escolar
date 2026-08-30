"""Provisionamento de escola em ambiente real (``app.provisionar``).

O que se testa aqui é o **portão**: quem pode virar login de produção e o que vira slug.
O corpo do provisionamento fala com o Postgres e é exercitado em ambiente, não em teste
unitário — mas a política que o protege não pode depender disso, porque é justamente ela
que impede o repeteco do seed em produção (senha versionada dentro do banco real).
"""

from __future__ import annotations

import pytest

from app.bootstrap import CAMPOS_SENHA_DEMO, valor_default
from app.config import Settings
from app.provisionar import (
    CONHECIMENTO_DEMO,
    ProvisionamentoRecusado,
    normalizar_e164,
    normalizar_slug,
    senha_do_ambiente,
    so_digitos,
)


def _settings() -> Settings:
    return Settings(_env_file=None)


def test_senha_ausente_e_recusada(monkeypatch):
    """Sem senha explícita não há provisionamento — nunca um default."""
    monkeypatch.delenv("PROVISIONAR_ADMIN_SENHA", raising=False)
    with pytest.raises(ProvisionamentoRecusado, match="PROVISIONAR_ADMIN_SENHA"):
        senha_do_ambiente(_settings())


def test_senha_de_exemplo_do_repositorio_e_recusada(monkeypatch):
    """É a regra do ``avaliar_seed`` sobrevivendo a um caminho novo.

    O seed é proibido em produção porque cria logins com senha versionada. Um
    provisionamento que aceitasse a mesma senha reabriria o buraco por outra porta.
    """
    for campo in CAMPOS_SENHA_DEMO:
        exemplo = valor_default(campo)
        if not exemplo:
            continue
        monkeypatch.setenv("PROVISIONAR_ADMIN_SENHA", exemplo)
        with pytest.raises(ProvisionamentoRecusado, match="senha de exemplo"):
            senha_do_ambiente(_settings())


def test_senha_curta_e_recusada(monkeypatch):
    """O painel dá acesso a documento de menor (§17) — 12 caracteres é o piso."""
    monkeypatch.setenv("PROVISIONAR_ADMIN_SENHA", "curta123")
    with pytest.raises(ProvisionamentoRecusado, match="12 caracteres"):
        senha_do_ambiente(_settings())


def test_senha_propria_e_aceita(monkeypatch):
    monkeypatch.setenv("PROVISIONAR_ADMIN_SENHA", "correta-cavalo-bateria-grampo")
    assert senha_do_ambiente(_settings()) == "correta-cavalo-bateria-grampo"


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        ("Escola Demonstração", "escola-demo"),
        ("EM Rosa Cury", "em-rosa-cury"),
        ("  Colégio  São   José ", "colegio-sao-jose"),
    ],
)
def test_slug_sem_acento_nem_separador_repetido(entrada, esperado):
    """O slug prefixa o nome do template na Meta — acento ali vira nome inválido."""
    resultado = normalizar_slug(entrada)
    # "Escola Demonstração" deriva "escola-demonstracao"; o apelido curto é escolhido à
    # mão. O que o teste garante é a forma, não o apelido.
    if entrada == "Escola Demonstração":
        assert resultado == "escola-demonstracao"
    else:
        assert resultado == esperado


def test_e164_normaliza_pontuacao():
    assert normalizar_e164("+55 (15) 99753-6978") == "+5515997536978"
    assert normalizar_e164("") == ""


def test_phone_number_id_fica_so_com_digitos():
    """Espaço ou traço no id quebra a URL da Graph API — e o erro não menciona o id."""
    assert so_digitos(" 1231892910008454 ") == "1231892910008454"


def test_conhecimento_demo_nao_menciona_escola_ficticia():
    """A base é genérica de propósito: ela vai para um banco real.

    Endereços e nomes inventados ("escola.test") no banco de produção são exatamente o
    lixo indistinguível do verdadeiro que este módulo existe para não criar.
    """
    textos = " ".join(conteudo for _, _, conteudo in CONHECIMENTO_DEMO).lower()
    assert ".test" not in textos
    assert "escola demonstração" not in textos
    assert len(CONHECIMENTO_DEMO) >= 5
