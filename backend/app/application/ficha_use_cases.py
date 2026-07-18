"""Casos de uso da ficha de matrícula digital (§D1/D2/D3).

- **D1/D2** — CRUD da ficha rica (frente + verso) com os campos obrigatórios/sensíveis
  (cor/raça obrigatória, Bolsa Família/NIS, deficiência, laudo/CID, alergia, etc.).
- **D3** — leitura por IA: o texto bruto de uma foto/PDF vai à ``LLMProvider``, que
  extrai os campos; o resultado é **validado em código** (a LLM não é fonte de verdade)
  e devolvido para revisão antes de gravar.

Escopado por ``tenant_id``; a ficha é 1:1 com um ``Aluno`` do próprio tenant.
"""

from __future__ import annotations

import json
import re
from uuid import UUID

from app.domain.entities import (
    CAMPOS_FICHA_MATRICULA,
    FichaMatricula,
    PreviaFichaMatricula,
    _now,
)
from app.domain.ports import (
    AlunoRepository,
    FichaMatriculaRepository,
    LLMProvider,
)

# Marcador no prompt de sistema: permite ao adaptador "fake" (demo sem chaves) reconhecer
# a tarefa de leitura de ficha e devolver JSON determinístico.
MARCADOR_FICHA = "FICHA_MATRICULA_JSON_V1"

# Campos booleanos da ficha (coeragidos a partir de texto/JSON).
_CAMPOS_BOOL = frozenset(
    {
        "termo_guarda",
        "autorizacao_van",
        "autorizacao_retirada",
        "autorizacao_imagem",
        "bolsa_familia",
    }
)


def _coerir_bool(valor) -> bool:
    if isinstance(valor, bool):
        return valor
    return str(valor).strip().lower() in {"1", "true", "sim", "s", "yes", "x", "autorizado"}


def _ficha_de_campos(
    *, tenant_id: UUID, aluno_id: UUID, campos: dict, aluno_nome: str = ""
) -> FichaMatricula:
    """Constrói uma ``FichaMatricula`` a partir de um dicionário de campos (revisados)."""
    ficha = FichaMatricula(tenant_id=tenant_id, aluno_id=aluno_id, aluno_nome=aluno_nome)
    for campo in CAMPOS_FICHA_MATRICULA:
        if campo not in campos or campos[campo] is None:
            continue
        valor = campos[campo]
        if campo in _CAMPOS_BOOL:
            setattr(ficha, campo, _coerir_bool(valor))
        elif campo == "dados_extra":
            setattr(ficha, campo, dict(valor) if isinstance(valor, dict) else {})
        else:
            setattr(ficha, campo, str(valor).strip())
    return ficha


class SalvarFichaMatricula:
    """Cria ou atualiza (upsert) a ficha de matrícula de um aluno do tenant.

    Valida que o aluno pertence ao tenant e que ``cor_raca`` (obrigatória, §D2) foi
    informada. ``aluno_nome`` é resolvido para exibição.
    """

    def __init__(
        self, *, fichas: FichaMatriculaRepository, alunos: AlunoRepository
    ) -> None:
        self._fichas = fichas
        self._alunos = alunos

    async def executar(
        self, *, tenant_id: UUID, aluno_id: UUID, campos: dict
    ) -> FichaMatricula:
        aluno = await self._alunos.obter(tenant_id=tenant_id, aluno_id=aluno_id)
        if aluno is None:
            raise ValueError("Aluno não encontrado para o tenant.")

        cor_raca = str(campos.get("cor_raca", "") or "").strip()
        if not cor_raca:
            raise ValueError("O campo cor/raça é obrigatório na ficha de matrícula.")

        ficha = _ficha_de_campos(
            tenant_id=tenant_id, aluno_id=aluno_id, campos=campos, aluno_nome=aluno.nome
        )
        ficha.atualizado_em = _now()
        return await self._fichas.salvar(ficha)


class ObterFichaMatricula:
    """Obtém a ficha de matrícula de um aluno (ou None se ainda não houver)."""

    def __init__(self, *, fichas: FichaMatriculaRepository) -> None:
        self._fichas = fichas

    async def executar(
        self, *, tenant_id: UUID, aluno_id: UUID
    ) -> FichaMatricula | None:
        return await self._fichas.por_aluno(tenant_id=tenant_id, aluno_id=aluno_id)


class RemoverFichaMatricula:
    """Remove a ficha de matrícula de um aluno."""

    def __init__(self, *, fichas: FichaMatriculaRepository) -> None:
        self._fichas = fichas

    async def executar(self, *, tenant_id: UUID, aluno_id: UUID) -> bool:
        return await self._fichas.remover(tenant_id=tenant_id, aluno_id=aluno_id)


# --------------------------------------------------------------------------- #
# D3 — leitura de ficha por IA (foto/PDF → campos), com validação em código
# --------------------------------------------------------------------------- #
def _extrair_json_objeto(texto: str) -> dict:
    """Extrai o objeto JSON da resposta da LLM, tolerando cercas de código e ruído."""
    t = (texto or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    inicio, fim = t.find("{"), t.rfind("}")
    if inicio == -1 or fim == -1 or fim < inicio:
        raise ValueError("A resposta da LLM não contém um JSON de ficha.")
    return json.loads(t[inicio : fim + 1])


def montar_prompt_ficha() -> str:
    campos_txt = ", ".join(c for c in CAMPOS_FICHA_MATRICULA if c != "dados_extra")
    return (
        f"{MARCADOR_FICHA}\n"
        "Você extrai os dados de uma ficha de matrícula escolar brasileira (frente e "
        "verso), a partir do texto de uma foto/PDF possivelmente desorganizado. Responda "
        "ESTRITAMENTE com um JSON válido, sem nenhum texto fora do JSON, no formato "
        '{"campos": {...}} usando as chaves conhecidas quando houver correspondência.\n'
        f"Chaves conhecidas: {campos_txt}.\n"
        "Regras:\n"
        "- Datas no formato YYYY-MM-DD; telefones apenas com dígitos/DDD.\n"
        "- Campos de autorização/termo/Bolsa Família são booleanos (true/false).\n"
        "- 'cor_raca' é obrigatório na ficha; extraia sempre que possível.\n"
        "- Não invente dados que não estejam na ficha; omita as chaves sem informação."
    )


def _validar_campos_ficha(campos: dict) -> PreviaFichaMatricula:
    """Valida/normaliza os campos extraídos pela LLM (a LLM não é fonte de verdade)."""
    limpos: dict = {}
    avisos: list[str] = []
    conhecidos = set(CAMPOS_FICHA_MATRICULA)
    for chave, valor in (campos or {}).items():
        if chave not in conhecidos:
            avisos.append(f"Campo desconhecido ignorado: {chave}.")
            continue
        if chave in _CAMPOS_BOOL:
            limpos[chave] = _coerir_bool(valor)
        elif chave == "dados_extra":
            limpos[chave] = dict(valor) if isinstance(valor, dict) else {}
        else:
            limpos[chave] = str(valor).strip()

    previa = PreviaFichaMatricula(campos=limpos, avisos=avisos)
    if not str(limpos.get("cor_raca", "")).strip():
        previa.avisos.append(
            "Cor/raça não identificada — é obrigatória e precisa ser preenchida na revisão."
        )
    return previa


class PrevisualizarFichaMatricula:
    """Etapa 1 (D3): a LLM extrai os campos da ficha; validamos em código, sem persistir."""

    def __init__(self, *, llm: LLMProvider) -> None:
        self._llm = llm

    async def executar(self, *, tenant_id: UUID, conteudo: str) -> PreviaFichaMatricula:
        conteudo = (conteudo or "").strip()
        if not conteudo:
            raise ValueError("Envie o conteúdo da ficha (texto/OCR do PDF ou foto).")

        bruto = await self._llm.gerar(
            sistema=montar_prompt_ficha(),
            mensagens=[{"role": "user", "content": conteudo}],
        )
        try:
            dados = _extrair_json_objeto(bruto)
        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError(
                "Não foi possível interpretar a ficha enviada. Revise o formato do "
                "documento ou a configuração da LLM."
            ) from e

        campos = dados.get("campos")
        if not isinstance(campos, dict):
            campos = dados if isinstance(dados, dict) else {}
        return _validar_campos_ficha(campos)


class ConfirmarFichaMatricula:
    """Etapa 2 (D3): persiste os campos já revisados (reusa ``SalvarFichaMatricula``)."""

    def __init__(
        self, *, fichas: FichaMatriculaRepository, alunos: AlunoRepository
    ) -> None:
        self._salvar = SalvarFichaMatricula(fichas=fichas, alunos=alunos)

    async def executar(
        self, *, tenant_id: UUID, aluno_id: UUID, campos: dict
    ) -> FichaMatricula:
        return await self._salvar.executar(
            tenant_id=tenant_id, aluno_id=aluno_id, campos=campos
        )
