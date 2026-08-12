"""Grade de horário da turma — os **dois formatos** da decisão B (plano de 10/08).

A escola quis ver os dois funcionando antes de escolher, então ambos gravam na mesma
coluna JSON. Isso é o que torna a escolha barata depois: descartar um é apagar componente
de tela, não migrar dado.

O que se testa aqui é sobretudo o que a validação **recusa** — grade errada não dá erro na
hora, ela sai impressa e a escola descobre na semana de aula.
"""

from __future__ import annotations

import pytest

from app.application.grade_horario import minutos_de_aula, validar_grade


# --------------------------- formato "turno" ------------------------------- #
def test_turno_normaliza_e_devolve_o_formato():
    grade = validar_grade(
        {
            "formato": "turno",
            "inicio": "07:30",
            "fim": "11:30",
            "intervalo_inicio": "09:30",
            "intervalo_minutos": 20,
        }
    )
    assert grade["formato"] == "turno"
    assert grade["inicio"] == "07:30"
    assert grade["intervalo_minutos"] == 20


def test_turno_sem_grade_e_valido():
    """Turma sem grade cadastrada é normal — não é erro."""
    assert validar_grade(None) == {}
    assert validar_grade({}) == {}


def test_saida_antes_da_entrada_e_recusada():
    with pytest.raises(ValueError, match="depois"):
        validar_grade({"formato": "turno", "inicio": "11:30", "fim": "07:30"})


def test_hora_em_formato_errado_e_recusada():
    with pytest.raises(ValueError, match="HH:MM"):
        validar_grade({"formato": "turno", "inicio": "7h30", "fim": "11:30"})
    with pytest.raises(ValueError, match="HH:MM"):
        validar_grade({"formato": "turno", "inicio": "25:00", "fim": "26:00"})


def test_intervalo_fora_do_turno_e_recusado():
    """Passaria despercebido: a tela mostraria um recreio às 19h numa turma da manhã."""
    with pytest.raises(ValueError, match="dentro do turno"):
        validar_grade(
            {
                "formato": "turno",
                "inicio": "07:30",
                "fim": "11:30",
                "intervalo_inicio": "19:00",
                "intervalo_minutos": 20,
            }
        )


def test_intervalo_que_passa_do_fim_do_turno_e_recusado():
    with pytest.raises(ValueError, match="dentro do turno"):
        validar_grade(
            {
                "formato": "turno",
                "inicio": "07:30",
                "fim": "11:30",
                "intervalo_inicio": "11:20",
                "intervalo_minutos": 30,
            }
        )


def test_duracao_de_intervalo_sem_horario_e_recusada():
    with pytest.raises(ValueError, match="início do intervalo"):
        validar_grade(
            {"formato": "turno", "inicio": "07:30", "fim": "11:30", "intervalo_minutos": 20}
        )


# --------------------------- formato "aulas" ------------------------------- #
def _bloco(dia=1, inicio="07:30", fim="08:20", tipo="aula", rotulo=""):
    return {"dia": dia, "inicio": inicio, "fim": fim, "tipo": tipo, "rotulo": rotulo}


def test_aulas_ordena_os_blocos_por_dia_e_horario():
    grade = validar_grade(
        {
            "formato": "aulas",
            "blocos": [
                _bloco(dia=2, inicio="09:00", fim="09:50"),
                _bloco(dia=1, inicio="08:30", fim="09:20"),
                _bloco(dia=1, inicio="07:30", fim="08:20"),
            ],
        }
    )
    assert [(b["dia"], b["inicio"]) for b in grade["blocos"]] == [
        (1, "07:30"),
        (1, "08:30"),
        (2, "09:00"),
    ]


def test_intervalo_e_um_bloco_como_outro_qualquer():
    """"grade de horário com intervalo incluso" — tratá-lo à parte faria a carga horária
    ignorá-lo."""
    grade = validar_grade(
        {
            "formato": "aulas",
            "blocos": [
                _bloco(inicio="07:30", fim="08:20"),
                _bloco(inicio="08:20", fim="08:40", tipo="intervalo", rotulo="Recreio"),
                _bloco(inicio="08:40", fim="09:30"),
            ],
        }
    )
    assert [b["tipo"] for b in grade["blocos"]] == ["aula", "intervalo", "aula"]


def test_aulas_sobrepostas_no_mesmo_dia_sao_recusadas():
    """Duas aulas ao mesmo tempo na mesma turma é sempre erro de montagem."""
    with pytest.raises(ValueError, match="sobrep"):
        validar_grade(
            {
                "formato": "aulas",
                "blocos": [
                    _bloco(inicio="07:30", fim="08:30"),
                    _bloco(inicio="08:00", fim="09:00"),
                ],
            }
        )


def test_mesmo_horario_em_dias_diferentes_e_valido():
    grade = validar_grade(
        {
            "formato": "aulas",
            "blocos": [_bloco(dia=1), _bloco(dia=2), _bloco(dia=3)],
        }
    )
    assert len(grade["blocos"]) == 3


def test_dia_fora_da_semana_e_recusado():
    with pytest.raises(ValueError, match="1 \\(seg\\)"):
        validar_grade({"formato": "aulas", "blocos": [_bloco(dia=8)]})


def test_bloco_terminando_antes_de_comecar_e_recusado():
    with pytest.raises(ValueError, match="depois do início"):
        validar_grade(
            {"formato": "aulas", "blocos": [_bloco(inicio="09:00", fim="08:00")]}
        )


def test_tipo_de_bloco_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="tipo inválido"):
        validar_grade({"formato": "aulas", "blocos": [_bloco(tipo="passeio")]})


def test_formato_desconhecido_e_recusado():
    with pytest.raises(ValueError, match="Formato de grade"):
        validar_grade({"formato": "planilha"})


# --------------------------- carga horária --------------------------------- #
def test_carga_horaria_soma_so_as_aulas():
    grade = validar_grade(
        {
            "formato": "aulas",
            "blocos": [
                _bloco(inicio="07:30", fim="08:20"),  # 50 min
                _bloco(inicio="08:20", fim="08:40", tipo="intervalo"),  # não conta
                _bloco(inicio="08:40", fim="09:30"),  # 50 min
            ],
        }
    )
    assert minutos_de_aula(grade) == 100


def test_carga_horaria_do_formato_turno_e_zero():
    """Declarar uma soma aproximada ali seria pior que não ter número nenhum."""
    grade = validar_grade({"formato": "turno", "inicio": "07:30", "fim": "11:30"})
    assert minutos_de_aula(grade) == 0
