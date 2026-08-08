"""Paginação das listagens (item 7 do checklist de pré-deploy).

Todas as listagens devolviam a tabela inteira. O que se garante aqui: o cliente não define
o teto, a contagem é do conjunto **completo** (não da página) e o recorte não perde nem
duplica registro entre páginas.
"""

from __future__ import annotations

import uuid

import pytest

from app.application.auditoria_use_cases import ListarAuditoria, RegistrarAuditoria
from app.application.cadastro_use_cases import CadastrarAluno, CriarSala, ListarAlunos
from app.application.paginacao import (
    POR_PAGINA_MAXIMO,
    POR_PAGINA_PADRAO,
    Pagina,
    normalizar_paginacao,
)
from app.domain.entities import AtorAuditoria
from tests.fakes import FakeAlunoRepo, FakeAuditLogRepo, FakeSalaRepo

TENANT = uuid.uuid4()


# --------------------------------------------------------------------------- #
# Normalização
# --------------------------------------------------------------------------- #
def test_padrao_e_dez_itens():
    assert POR_PAGINA_PADRAO == 10
    assert normalizar_paginacao(None, None) == (1, 10)


def test_cliente_nao_define_o_teto():
    """`?por_pagina=100000` transformaria a listagem no próximo incidente."""
    assert normalizar_paginacao(1, 100_000) == (1, POR_PAGINA_MAXIMO)


def test_valores_hostis_viram_o_minimo():
    assert normalizar_paginacao(-3, -7) == (1, 1)


def test_total_de_paginas_arredonda_para_cima():
    assert Pagina(itens=[], total=21, por_pagina=10).total_paginas == 3
    assert Pagina(itens=[], total=20, por_pagina=10).total_paginas == 2
    # Lista vazia ainda é uma página — senão o paginador exibiria "página 1 de 0".
    assert Pagina(itens=[], total=0, por_pagina=10).total_paginas == 1


def test_tem_proxima_respeita_o_fim_da_lista():
    assert Pagina(itens=[], total=25, pagina=1, por_pagina=10).tem_proxima
    assert not Pagina(itens=[], total=25, pagina=3, por_pagina=10).tem_proxima


# --------------------------------------------------------------------------- #
# Listagem paginada de verdade
# --------------------------------------------------------------------------- #
async def _trinta_alunos() -> tuple[FakeAlunoRepo, FakeSalaRepo]:
    alunos, salas = FakeAlunoRepo(), FakeSalaRepo()
    sala = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="5ª série A")
    for i in range(30):
        await CadastrarAluno(alunos=alunos, salas=salas).executar(
            tenant_id=TENANT, nome=f"Aluno {i:02d}", sala_id=sala.id
        )
    return alunos, salas


@pytest.mark.asyncio
async def test_primeira_pagina_traz_dez_e_o_total_e_do_conjunto_inteiro():
    alunos, _ = await _trinta_alunos()

    pagina = await ListarAlunos(alunos=alunos).executar(tenant_id=TENANT)

    assert len(pagina.itens) == 10
    # O total é dos 30, não dos 10 exibidos — é o que o paginador precisa saber.
    assert pagina.total == 30
    assert pagina.total_paginas == 3


@pytest.mark.asyncio
async def test_paginas_nao_perdem_nem_duplicam_registros():
    alunos, _ = await _trinta_alunos()

    vistos: list[str] = []
    for numero in (1, 2, 3):
        pagina = await ListarAlunos(alunos=alunos).executar(
            tenant_id=TENANT, pagina=numero, por_pagina=10
        )
        vistos.extend(a.nome for a in pagina.itens)

    assert len(vistos) == 30
    assert len(set(vistos)) == 30


@pytest.mark.asyncio
async def test_pagina_alem_do_fim_vem_vazia_sem_erro():
    alunos, _ = await _trinta_alunos()

    pagina = await ListarAlunos(alunos=alunos).executar(tenant_id=TENANT, pagina=99)

    assert pagina.itens == []
    assert pagina.total == 30


@pytest.mark.asyncio
async def test_filtro_e_paginacao_convivem():
    """O total precisa refletir o filtro aplicado, senão o paginador oferece páginas
    que não existem."""
    alunos, salas = await _trinta_alunos()
    outra = await CriarSala(salas=salas).executar(tenant_id=TENANT, nome="6ª série B")
    await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=TENANT, nome="Único", sala_id=outra.id
    )

    pagina = await ListarAlunos(alunos=alunos).executar(tenant_id=TENANT, sala_id=outra.id)

    assert pagina.total == 1
    assert [a.nome for a in pagina.itens] == ["Único"]


@pytest.mark.asyncio
async def test_auditoria_pagina_mais_recentes_primeiro():
    repo = FakeAuditLogRepo()
    registrar = RegistrarAuditoria(auditoria=repo)
    for i in range(15):
        await registrar.executar(
            ator=AtorAuditoria.USUARIO, acao=f"acao.{i:02d}", tenant_id=TENANT
        )

    pagina = await ListarAuditoria(auditoria=repo).executar(tenant_id=TENANT)

    assert pagina.total == 15
    assert len(pagina.itens) == 10
    # Mais recente primeiro: quem abre a auditoria está atrás do que acabou de acontecer.
    assert pagina.itens[0].acao == "acao.14"


@pytest.mark.asyncio
async def test_paginacao_continua_escopada_por_tenant():
    """Paginar não pode virar uma porta lateral para dado de outra escola."""
    alunos, salas = await _trinta_alunos()
    outro_tenant = uuid.uuid4()
    sala_alheia = await CriarSala(salas=salas).executar(
        tenant_id=outro_tenant, nome="Turma da outra escola"
    )
    await CadastrarAluno(alunos=alunos, salas=salas).executar(
        tenant_id=outro_tenant, nome="Aluno alheio", sala_id=sala_alheia.id
    )

    pagina = await ListarAlunos(alunos=alunos).executar(
        tenant_id=TENANT, pagina=1, por_pagina=POR_PAGINA_MAXIMO
    )

    assert pagina.total == 30
    assert all("alheio" not in a.nome for a in pagina.itens)
