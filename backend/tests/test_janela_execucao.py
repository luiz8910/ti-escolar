"""A grade das tarefas de fundo (`JanelaDeExecucao`).

Value object puro: quando uma tarefa de fundo pode acordar. Nasceu de dois problemas
somados — o intervalo fixo de 30 min podia disparar aviso escolar de madrugada e
mantinha o Postgres serverless acordado 24/7 para descobrir que não havia nada a fazer.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.domain.entities import JanelaDeExecucao

SP = ZoneInfo("America/Sao_Paulo")


SP = ZoneInfo("America/Sao_Paulo")


def test_tres_passadas_entre_7h_e_18h():
    """A do meio é 12h30 — e é exatamente isso que ninguém calcula de cabeça."""
    assert JanelaDeExecucao().horarios() == (time(7, 0), time(12, 30), time(18, 0))


def test_uma_passada_roda_na_abertura():
    """Começo do expediente é a hora mais útil para um disparo travado desde ontem."""
    assert JanelaDeExecucao(passadas=1).horarios() == (time(7, 0),)


def test_passadas_zero_desliga_sem_precisar_de_flag():
    janela = JanelaDeExecucao(passadas=0)
    assert not janela.ativa
    assert janela.proxima_execucao(datetime(2026, 8, 17, 8, 0, tzinfo=SP)) is None


def test_grade_pula_o_fim_de_semana():
    """Sexta depois das 18h só volta na segunda: ~61h sem passada, dentro dos 7 dias
    de validade do disparo."""
    sexta_tarde = datetime(2026, 8, 14, 18, 1, tzinfo=SP)
    proxima = JanelaDeExecucao().proxima_execucao(sexta_tarde)
    assert proxima.astimezone(SP) == datetime(2026, 8, 17, 7, 0, tzinfo=SP)


def test_grade_atravessa_a_meia_noite():
    """Depois da última passada do dia, a próxima é a primeira do dia seguinte."""
    proxima = JanelaDeExecucao().proxima_execucao(datetime(2026, 8, 17, 23, 0, tzinfo=SP))
    assert proxima.astimezone(SP) == datetime(2026, 8, 18, 7, 0, tzinfo=SP)


def test_fuso_invalido_cai_no_padrao_e_a_descricao_nao_mente():
    """A tarefa roda em Brasília; a descrição do boot precisa dizer isso, não o que
    foi digitado — senão o log esconde justamente o erro que existe para revelar."""
    janela = JanelaDeExecucao(timezone="Marte/Olympus")
    assert "America/Sao_Paulo" in janela.descricao
    assert janela.proxima_execucao(datetime(2026, 8, 17, 8, 0, tzinfo=SP)) is not None
