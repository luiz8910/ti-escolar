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

from app.application.validacao import (
    data_nao_futura,
    normalizar_cpf,
    normalizar_data,
    normalizar_email,
)
from app.domain.entities import (
    CAMPOS_FICHA_MATRICULA,
    FichaMatricula,
    PreviaFichaMatricula,
    TipoFiliacao,
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


# Campos que a ficha física marca com asterisco (apontamento de 10/08). São exigidos ao
# **salvar a ficha**, e não ao cadastrar o aluno: a importação em massa (§6c-quater) e o
# cadastro do dia a dia criam o aluno só com nome e série, e exigir CPF ali travaria o
# caminho que a escola mais usa. A ficha é o momento em que a secretaria tem a papelada
# na mão — a lista de "ficha pendente" no painel é o que cobra o resto.
_OBRIGATORIOS_FICHA: tuple[tuple[str, str], ...] = (
    ("cor_raca", "cor/raça"),
    ("cpf", "CPF"),
    ("ra_rm", "RA/RM"),
    ("data_nascimento", "data de nascimento"),
    ("endereco", "endereço"),
    ("sexo", "sexo"),
)

_LAUDO_STATUS_VALIDOS = ("", "nao", "sim", "em_investigacao")


def _normalizar_campos_ficha(campos: dict) -> dict:
    """Canoniza os formatos antes de gravar e recusa o que é erro de digitação.

    A ficha é fonte de declaração e de histórico escolar: CPF ora com pontuação ora sem
    inviabiliza cruzar o aluno com o cadastro do responsável e com o censo.
    """
    normalizados = dict(campos)
    normalizados["cpf"] = normalizar_cpf(str(campos.get("cpf", "") or ""))
    normalizados["data_nascimento"] = data_nao_futura(
        normalizar_data(
            str(campos.get("data_nascimento", "") or ""), campo="Data de nascimento"
        ),
        campo="Data de nascimento",
    )
    if campos.get("email"):
        normalizados["email"] = normalizar_email(str(campos["email"]))

    status = str(campos.get("laudo_status", "") or "").strip()
    if status not in _LAUDO_STATUS_VALIDOS:
        raise ValueError(
            "Situação do laudo inválida. Use: nao, sim ou em_investigacao."
        )
    # "Sem laudo" e "em investigação" não carregam CID — deixar o texto antigo pendurado
    # faria a ficha afirmar um diagnóstico que a escola acabou de negar.
    if status in ("", "nao", "em_investigacao"):
        normalizados["laudo_cid"] = ""
    normalizados["laudo_status"] = status
    return normalizados


def _preencher_filiacao(ficha: FichaMatricula, aluno) -> None:
    """Copia os responsáveis **vinculados ao aluno** para os campos de filiação da ficha.

    A ficha nasceu com ``filiacao1_*``/``filiacao2_*``/``responsavel_legal`` como texto
    solto — uma segunda cópia dos mesmos dados que moram em ``Contato``, digitada à mão e
    livre para divergir. Agora eles são **derivados**: a secretaria mantém o responsável
    num lugar só, e a ficha impressa continua saindo completa.

    Mãe e pai ocupam as duas primeiras linhas quando declarados; o responsável legal
    (termo de guarda) vai para a linha própria da ficha física.
    """
    responsaveis = list(getattr(aluno, "responsaveis", []) or [])
    legal = next((c for c in responsaveis if c.eh_responsavel_legal), None)
    filiacao = [c for c in responsaveis if c is not legal]
    # Mãe e pai primeiro, na ordem da ficha; o resto entra depois, se sobrar linha.
    ordem = {TipoFiliacao.MAE: 0, TipoFiliacao.PAI: 1}
    filiacao.sort(key=lambda c: ordem.get(c.tipo_filiacao, 2))

    for indice, prefixo in enumerate(("filiacao1", "filiacao2")):
        contato = filiacao[indice] if indice < len(filiacao) else None
        setattr(ficha, f"{prefixo}_nome", contato.nome if contato else "")
        setattr(ficha, f"{prefixo}_cpf", contato.cpf if contato else "")
        setattr(ficha, f"{prefixo}_telefone", contato.telefone if contato else "")

    ficha.responsavel_legal = legal.nome if legal else ""
    # O booleano continua existindo para a ficha impressa, mas deixou de ser a fonte da
    # verdade: quem responde pelo aluno é o `Contato` (§6a).
    ficha.termo_guarda = legal is not None


class SalvarFichaMatricula:
    """Cria ou atualiza (upsert) a ficha de matrícula de um aluno do tenant.

    Valida que o aluno pertence ao tenant e que os campos obrigatórios da ficha física
    foram informados. Os campos de **filiação são derivados** dos responsáveis vinculados
    ao aluno — ver ``_preencher_filiacao``.
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

        faltando = [
            rotulo
            for campo, rotulo in _OBRIGATORIOS_FICHA
            if not str(campos.get(campo, "") or "").strip()
        ]
        if faltando:
            raise ValueError(
                "A ficha de matrícula exige: " + ", ".join(faltando) + "."
            )

        ficha = _ficha_de_campos(
            tenant_id=tenant_id,
            aluno_id=aluno_id,
            campos=_normalizar_campos_ficha(campos),
            aluno_nome=aluno.nome,
        )
        _preencher_filiacao(ficha, aluno)
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
