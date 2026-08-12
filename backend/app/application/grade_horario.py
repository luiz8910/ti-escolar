"""Grade de horário da turma — **dois formatos sobre a mesma coluna JSON**.

Decisão B do plano de 10/08: a escola quis ver os dois funcionando antes de escolher.
Guardá-los no mesmo `grade_horario` é o que torna a escolha barata — descartar um depois é
apagar componente de tela, não migrar dado.

- ``turno``: entrada, saída e o intervalo. É o suficiente para a secretaria hoje, e é o que
  a maioria das escolas de fato tem escrito em algum lugar.
- ``aulas``: a grade aula a aula, um bloco por dia e horário.

O **intervalo é um bloco como outro qualquer** no formato ``aulas`` — o apontamento pedia
"grade de horário com intervalo incluso", e tratá-lo à parte faria a soma da carga horária
ignorá-lo.

A validação mora aqui, e não em Pydantic, porque a mesma grade entra por três caminhos
(painel, seed e futura importação) e a regra precisa valer nos três.
"""

from __future__ import annotations

import re

from app.domain.entities import (
    BLOCO_AULA,
    BLOCO_TIPOS,
    GRADE_AULAS,
    GRADE_FORMATOS,
    GRADE_TURNO,
)

_HORA = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
# Dias no padrão ISO, como `Tenant.expediente_dias` (1 = segunda … 7 = domingo). Manter o
# mesmo padrão evita a conversão silenciosa que erra por um em algum lugar.
_DIAS_VALIDOS = range(1, 8)


def _hora(valor, campo: str, *, obrigatorio: bool = False) -> str:
    texto = str(valor or "").strip()
    if not texto:
        if obrigatorio:
            raise ValueError(f"{campo} é obrigatório na grade.")
        return ""
    if not _HORA.match(texto):
        raise ValueError(f"{campo} inválido: use HH:MM (24h).")
    return texto


def _minutos(hhmm: str) -> int:
    horas, minutos = hhmm.split(":")
    return int(horas) * 60 + int(minutos)


def validar_grade(bruta: dict | None) -> dict:
    """Normaliza e valida a grade. ``None``/vazio devolve ``{}`` — turma sem grade é ok."""
    if not bruta:
        return {}

    formato = str(bruta.get("formato", "") or GRADE_TURNO).strip()
    if formato not in GRADE_FORMATOS:
        aceitos = ", ".join(GRADE_FORMATOS)
        raise ValueError(f"Formato de grade inválido: {formato}. Use um de: {aceitos}.")

    if formato == GRADE_TURNO:
        return _validar_turno(bruta)
    return _validar_aulas(bruta)


def _validar_turno(bruta: dict) -> dict:
    inicio = _hora(bruta.get("inicio"), "Horário de entrada", obrigatorio=True)
    fim = _hora(bruta.get("fim"), "Horário de saída", obrigatorio=True)
    if _minutos(fim) <= _minutos(inicio):
        raise ValueError("O horário de saída precisa ser depois do de entrada.")

    intervalo_inicio = _hora(bruta.get("intervalo_inicio"), "Início do intervalo")
    try:
        intervalo_minutos = int(bruta.get("intervalo_minutos") or 0)
    except (TypeError, ValueError) as e:
        raise ValueError("A duração do intervalo precisa ser um número de minutos.") from e
    if intervalo_minutos < 0:
        raise ValueError("A duração do intervalo não pode ser negativa.")

    if intervalo_inicio:
        fim_intervalo = _minutos(intervalo_inicio) + intervalo_minutos
        # Intervalo fora do turno é erro de digitação, e passaria despercebido: a tela
        # mostraria um recreio às 19h numa turma da manhã.
        if not (_minutos(inicio) <= _minutos(intervalo_inicio) and fim_intervalo <= _minutos(fim)):
            raise ValueError("O intervalo precisa acontecer dentro do turno.")
    elif intervalo_minutos:
        raise ValueError("Informe o horário de início do intervalo.")

    return {
        "formato": GRADE_TURNO,
        "inicio": inicio,
        "fim": fim,
        "intervalo_inicio": intervalo_inicio,
        "intervalo_minutos": intervalo_minutos,
    }


def _validar_aulas(bruta: dict) -> dict:
    blocos_brutos = bruta.get("blocos") or []
    if not isinstance(blocos_brutos, list):
        raise ValueError("A grade aula a aula precisa de uma lista de blocos.")

    blocos: list[dict] = []
    for indice, bloco in enumerate(blocos_brutos, start=1):
        if not isinstance(bloco, dict):
            raise ValueError(f"Bloco {indice} da grade está malformado.")
        try:
            dia = int(bloco.get("dia", 0))
        except (TypeError, ValueError) as e:
            raise ValueError(f"Bloco {indice}: dia da semana inválido.") from e
        if dia not in _DIAS_VALIDOS:
            raise ValueError(f"Bloco {indice}: dia da semana precisa ser de 1 (seg) a 7 (dom).")

        inicio = _hora(bloco.get("inicio"), f"Bloco {indice}: início", obrigatorio=True)
        fim = _hora(bloco.get("fim"), f"Bloco {indice}: fim", obrigatorio=True)
        if _minutos(fim) <= _minutos(inicio):
            raise ValueError(f"Bloco {indice}: o fim precisa ser depois do início.")

        tipo = str(bloco.get("tipo", "") or BLOCO_AULA).strip()
        if tipo not in BLOCO_TIPOS:
            raise ValueError(f"Bloco {indice}: tipo inválido (use aula ou intervalo).")

        blocos.append(
            {
                "dia": dia,
                "inicio": inicio,
                "fim": fim,
                "tipo": tipo,
                "rotulo": str(bloco.get("rotulo", "") or "").strip(),
            }
        )

    _recusar_sobreposicao(blocos)
    blocos.sort(key=lambda b: (b["dia"], b["inicio"]))
    return {"formato": GRADE_AULAS, "blocos": blocos}


def _recusar_sobreposicao(blocos: list[dict]) -> None:
    """Duas aulas ao mesmo tempo na mesma turma é sempre erro de montagem.

    Silenciar isso produziria uma grade que a escola imprime e só descobre errada na
    semana de aula.
    """
    por_dia: dict[int, list[dict]] = {}
    for bloco in blocos:
        por_dia.setdefault(bloco["dia"], []).append(bloco)
    for dia, doDia in por_dia.items():
        ordenados = sorted(doDia, key=lambda b: _minutos(b["inicio"]))
        for anterior, atual in zip(ordenados, ordenados[1:]):
            if _minutos(atual["inicio"]) < _minutos(anterior["fim"]):
                raise ValueError(
                    f"Grade do dia {dia}: {anterior['inicio']}–{anterior['fim']} e "
                    f"{atual['inicio']}–{atual['fim']} se sobrepõem."
                )


def minutos_de_aula(grade: dict) -> int:
    """Carga horária semanal em minutos, **sem** contar intervalo.

    Só o formato ``aulas`` tem o dado; o formato ``turno`` devolve 0 — declarar uma soma
    aproximada ali seria pior que não ter número nenhum.
    """
    if grade.get("formato") != GRADE_AULAS:
        return 0
    return sum(
        _minutos(b["fim"]) - _minutos(b["inicio"])
        for b in grade.get("blocos", [])
        if b.get("tipo") == BLOCO_AULA
    )
