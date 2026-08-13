"""Validação de template antes de submeter à Meta.

Existe por um motivo econômico, não estético: a WABA é **uma só para todas as escolas**
(§9e), e template recusado conta contra ela. Uma escola que escreva texto promocional e
apanhe três vezes respinga em todas as outras. Então tudo que dá para recusar aqui —
localmente, de graça, com mensagem em português — não vira rejeição lá.

As regras não são inventadas: são as que já nos custaram uma recusa no formulário do
`retomada_atendimento` (docs/producao-whatsapp.md §7.1) mais as documentadas pela Meta.
"""

from __future__ import annotations

import re

from app.domain.entities import CategoriaTemplate

# A Meta aceita minúsculas, dígitos e sublinhado. Nome com maiúscula ou hífen é recusado
# no POST, com um erro genérico que não diz qual foi o problema.
_NOME_VALIDO = re.compile(r"^[a-z0-9_]+$")
_PLACEHOLDER = re.compile(r"\{\{(\d+)\}\}")

NOME_MAX = 512
CORPO_MAX = 1024


class TemplateInvalido(ValueError):
    """Recusa local, antes de gastar uma submissão na Meta."""


def normalizar_nome_template(bruto: str, *, campo: str = "Nome") -> str:
    """Normaliza para o formato que a Meta aceita, sem adivinhar demais.

    Espaço e hífen viram sublinhado (é o que a pessoa quis dizer ao digitar "aviso de
    reunião"), mas acento e cedilha **não** são transliterados: 'reunião' virando
    'reuniao' silenciosamente deixaria o nome no banco diferente do que a secretaria leu
    na tela, e o nome é a chave do envio.
    """
    nome = (bruto or "").strip().lower()
    if not nome:
        raise TemplateInvalido(f"{campo} do template é obrigatório.")
    nome = re.sub(r"[\s\-]+", "_", nome)
    if len(nome) > NOME_MAX:
        raise TemplateInvalido(f"{campo} do template pode ter no máximo {NOME_MAX} caracteres.")
    if not _NOME_VALIDO.match(nome):
        raise TemplateInvalido(
            f"{campo} do template aceita apenas letras minúsculas sem acento, números e "
            "sublinhado (ex.: aviso_reuniao)."
        )
    return nome


def nome_com_prefixo(*, slug: str, nome: str) -> str:
    """Prefixa o nome com o slug da escola (templates específicos).

    O prefixo não é organização: é o que evita a colisão de nomes na WABA compartilhada.
    Idempotente — reprefixar um nome já prefixado só devolveria ``slug_slug_...``.
    """
    prefixo = normalizar_nome_template(slug, campo="Slug da escola")
    nome = normalizar_nome_template(nome)
    if nome == prefixo or nome.startswith(f"{prefixo}_"):
        return nome
    return f"{prefixo}_{nome}"


def placeholders_do_corpo(corpo: str) -> list[int]:
    """Os números dos ``{{n}}`` na ordem em que aparecem."""
    return [int(n) for n in _PLACEHOLDER.findall(corpo or "")]


def validar_corpo_template(corpo: str) -> list[int]:
    """Valida o corpo e devolve os placeholders distintos, em ordem.

    Recusa, em ordem de quanto a Meta se importa:

    1. **Corpo vazio** — nada a revisar.
    2. **Começar ou terminar em variável** — foi exatamente isto que derrubou a primeira
       versão do `retomada_atendimento` ("As variáveis não podem estar no início ou no fim
       do modelo").
    3. **Ser só variável** — um corpo ``{{1}}`` é um "envie qualquer coisa" disfarçado, e a
       Meta recusa justamente para impedir template genérico.
    4. **Numeração fora de ordem ou com buraco** — os parâmetros vão posicionalmente no
       envio, então ``{{1}}, {{3}}`` faria a mensagem sair com o texto no lugar errado.
    """
    corpo = (corpo or "").strip()
    if not corpo:
        raise TemplateInvalido("O corpo do template é obrigatório.")
    if len(corpo) > CORPO_MAX:
        raise TemplateInvalido(
            f"O corpo do template pode ter no máximo {CORPO_MAX} caracteres."
        )

    numeros = placeholders_do_corpo(corpo)
    if numeros:
        sem_variaveis = _PLACEHOLDER.sub("", corpo).strip()
        if not sem_variaveis:
            raise TemplateInvalido(
                "O corpo não pode ser apenas variáveis — a Meta recusa template genérico. "
                "Escreva um texto fixo em volta (ex.: 'Lembrete: {{1}}. Atenciosamente, a "
                "secretaria.')."
            )
        if corpo.startswith("{{") or corpo.endswith("}}"):
            raise TemplateInvalido(
                "O corpo não pode começar nem terminar com uma variável — é uma regra da "
                "Meta. Acrescente uma saudação antes ou uma frase de encerramento depois."
            )

        distintos = sorted(set(numeros))
        if distintos != list(range(1, len(distintos) + 1)):
            esperado = ", ".join(f"{{{{{n}}}}}" for n in range(1, len(distintos) + 1))
            raise TemplateInvalido(
                "As variáveis precisam ser numeradas em sequência a partir de {{1}} "
                f"(esperado: {esperado})."
            )
        return distintos
    return []


def validar_exemplos(*, placeholders: list[int], exemplos: list[str]) -> list[str]:
    """A Meta exige um exemplo por variável quando o corpo tem variáveis.

    Sem amostra o template é recusado de saída — a revisão é humana e o revisor precisa
    ver a mensagem preenchida. Os exemplos **não** são enviados ao responsável.
    """
    exemplos = [(e or "").strip() for e in (exemplos or [])]
    if not placeholders:
        return []
    if len(exemplos) != len(placeholders) or not all(exemplos):
        raise TemplateInvalido(
            f"Informe um exemplo para cada variável do corpo ({len(placeholders)} no "
            "total). A Meta recusa template com variável e sem amostra."
        )
    return exemplos


def validar_categoria(categoria: CategoriaTemplate) -> CategoriaTemplate:
    """`authentication` é para código de verificação (OTP) e não cabe no produto.

    Deixar a opção na tela convidaria a escola a escolher a categoria mais barata para
    mandar aviso, o que a Meta reclassifica — e a reclassificação a gente descobre na
    fatura, não em erro.
    """
    if categoria is CategoriaTemplate.AUTHENTICATION:
        raise TemplateInvalido(
            "A categoria 'authentication' é reservada a códigos de verificação e não se "
            "aplica a avisos escolares. Use 'utility' (ou 'marketing', se for divulgação)."
        )
    return categoria
