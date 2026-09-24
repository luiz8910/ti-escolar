"""Normalização e validação dos formatos brasileiros do cadastro escolar.

Fica na camada de aplicação, e não no domínio, porque são **regras de formato de
documento** (CPF, data, e-mail) e não invariantes de negócio: quem decide se um campo é
obrigatório é o caso de uso.

O par ``normalizar_*`` sempre devolve o valor **canônico**, não o digitado. Guardar CPF
ora como ``123.456.789-09`` ora como ``12345678909`` inviabiliza a busca por documento e a
checagem de duplicidade — que é justamente o motivo de pedir o CPF.
"""

from __future__ import annotations

import re
from datetime import date

# Formato aceito e devolvido para datas: ISO (``YYYY-MM-DD``). É o que o ``<input
# type="date">`` do painel envia e o que ordena corretamente como texto.
_ISO = "%Y-%m-%d"


def somente_digitos(bruto: str) -> str:
    return re.sub(r"\D", "", bruto or "")


class TelefoneInvalido(ValueError):
    """Telefone que não dá para levar a E.164 — erro de digitação, não "não encontrado"."""


def normalizar_telefone(bruto: str) -> tuple[str, str]:
    """Normaliza um telefone para E.164. Retorna ``(e164, aviso)``.

    ``e164`` vazio quando não há telefone ou o formato não é reconhecível (com o motivo em
    ``aviso``).

    **Sem ``+``, o número é brasileiro:** DDD + número (10/11 dígitos) ganha o ``+55``, e
    12/13 dígitos começando em 55 já trazem o DDI. É como a secretaria digita — "(15)
    99753-6978" — e o E.164 é o que o webhook entrega, então é nele que a conversa casa.
    **Com ``+``, o DDI foi informado** e é respeitado (8 a 15 dígitos): é a porta para o
    número estrangeiro, que antes ganhava um 55 na frente e virava outro telefone.

    Devolve aviso em vez de levantar porque nasceu para a **importação em massa**, onde
    uma linha ruim não pode derrubar a planilha inteira. Quem valida um campo só —
    cadastro de professor, de responsável — transforma o aviso em erro.
    """
    digitos = somente_digitos(bruto)
    if not digitos:
        return "", ""
    if (bruto or "").strip().startswith("+"):
        if 8 <= len(digitos) <= 15:
            return "+" + digitos, ""
    elif digitos.startswith("55") and len(digitos) in (12, 13):
        return "+" + digitos, ""
    elif len(digitos) in (10, 11):
        return "+55" + digitos, ""
    return "", f"Telefone em formato não reconhecido: {bruto.strip()}"


def telefone_ou_erro(bruto: str, *, campo: str) -> str:
    """``normalizar_telefone`` para quem valida um campo só: aviso vira ``TelefoneInvalido``."""
    e164, aviso = normalizar_telefone(bruto)
    if aviso:
        raise TelefoneInvalido(
            f"{campo} inválido: informe DDD + número (ex.: 15 99753-6978) ou, se for de "
            "fora do Brasil, o número com + e o código do país (ex.: +14155238886)."
        )
    return e164


def _digito_verificador(digitos: str, peso_inicial: int) -> int:
    soma = sum(int(d) * p for d, p in zip(digitos, range(peso_inicial, 1, -1)))
    resto = (soma * 10) % 11
    return 0 if resto == 10 else resto


def cpf_valido(cpf: str) -> bool:
    """Confere os dois dígitos verificadores do CPF.

    Rejeita as sequências de dígito repetido (``111.111.111-11`` e companhia): elas
    **passam** no algoritmo dos verificadores, e é exatamente o que alguém digita para
    escapar de um campo obrigatório.
    """
    digitos = somente_digitos(cpf)
    if len(digitos) != 11 or digitos == digitos[0] * 11:
        return False
    return (
        _digito_verificador(digitos[:9], 10) == int(digitos[9])
        and _digito_verificador(digitos[:10], 11) == int(digitos[10])
    )


def normalizar_cpf(bruto: str, *, campo: str = "CPF", obrigatorio: bool = False) -> str:
    """CPF em 11 dígitos, sem pontuação. Vazio é aceito quando não obrigatório.

    Levanta ``ValueError`` com mensagem para a tela — a validação existe para pegar o
    dígito trocado na hora da digitação, não depois, na secretaria, com o aluno na fila.
    """
    digitos = somente_digitos(bruto)
    if not digitos:
        if obrigatorio:
            raise ValueError(f"{campo} é obrigatório.")
        return ""
    if not cpf_valido(digitos):
        raise ValueError(f"{campo} inválido: confira os dígitos.")
    return digitos


def formatar_cpf(digitos: str) -> str:
    """``12345678909`` → ``123.456.789-09``. Só para exibição."""
    d = somente_digitos(digitos)
    if len(d) != 11:
        return d
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"


def normalizar_data(
    bruto: str, *, campo: str = "Data", obrigatorio: bool = False
) -> str:
    """Data em ISO (``YYYY-MM-DD``). Aceita também ``DD/MM/AAAA``, que é como a
    secretaria digita quando cola de uma planilha.

    Data futura é recusada nos campos de nascimento — mas isso é decisão do caso de uso,
    não daqui; aqui só se garante que a data existe (31/02 não passa).
    """
    texto = (bruto or "").strip()
    if not texto:
        if obrigatorio:
            raise ValueError(f"{campo} é obrigatória.")
        return ""
    for formato in (_ISO, "%d/%m/%Y"):
        try:
            return date.strftime(_parse(texto, formato), _ISO)
        except ValueError:
            continue
    raise ValueError(f"{campo} inválida: use AAAA-MM-DD ou DD/MM/AAAA.")


def _parse(texto: str, formato: str) -> date:
    from datetime import datetime

    return datetime.strptime(texto, formato).date()


def data_nao_futura(iso: str, *, campo: str = "Data") -> str:
    """Recusa data no futuro. Nascimento no futuro é sempre erro de digitação."""
    if iso and _parse(iso, _ISO) > date.today():
        raise ValueError(f"{campo} não pode estar no futuro.")
    return iso


_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+\.[^@\s]+$")


def normalizar_email(bruto: str, *, campo: str = "E-mail") -> str:
    """E-mail em minúsculas, sem espaços. Vazio é aceito.

    A checagem é deliberadamente frouxa (tem ``@``, tem domínio com ponto): validar
    e-mail por regex estrita reprova endereços válidos, e aqui o campo é de contato —
    ninguém autentica por ele.
    """
    texto = (bruto or "").strip().lower()
    if not texto:
        return ""
    if not _EMAIL.match(texto):
        raise ValueError(f"{campo} inválido.")
    return texto
