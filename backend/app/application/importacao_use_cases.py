"""Casos de uso de importação de alunos em massa (planilha/PDF).

Duas etapas, para um fluxo seguro de "revisar antes de gravar":

1. **Prévia** (``PrevisualizarImportacaoAlunos``): o texto bruto da planilha/PDF é
   enviado à ``LLMProvider``, que **normaliza e estrutura** os alunos. O resultado é
   validado **em código** (a LLM não é fonte de verdade) e devolvido para revisão —
   nada é persistido.
2. **Confirmação** (``ConfirmarImportacaoAlunos``): recebe as linhas já revisadas e
   persiste, de forma **determinística e sem LLM**: resolve/cria séries (``Sala``),
   reaproveita/cria responsáveis (``Contato`` por telefone) e cadastra os ``Aluno``s.

Tudo escopado por ``tenant_id``. A camada de aplicação só orquestra as portas
(``LLMProvider``, ``SalaRepository``, ``ContatoRepository``, ``AlunoRepository``).
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from uuid import UUID

from app.domain.entities import (
    Aluno,
    Contato,
    LinhaImportacaoAluno,
    PreviaImportacaoAlunos,
    ResponsavelImportado,
    ResultadoImportacaoAlunos,
    Sala,
)
from app.domain.ports import (
    AlunoRepository,
    ContatoRepository,
    LLMProvider,
    SalaRepository,
)

# Marcador no prompt de sistema: permite ao adaptador "fake" (demo sem chaves)
# reconhecer a tarefa de importação e devolver JSON determinístico.
MARCADOR_IMPORTACAO = "IMPORTACAO_ALUNOS_JSON_V1"


# --------------------------------------------------------------------------- #
# Helpers de normalização/parsing
# --------------------------------------------------------------------------- #
def _chave_serie(nome: str) -> str:
    """Chave canônica para comparar nomes de série (case/espaços-insensível)."""
    return " ".join(nome.casefold().split())


def normalizar_telefone(bruto: str) -> tuple[str, str]:
    """Normaliza um telefone brasileiro para E.164. Retorna ``(e164, aviso)``.

    ``e164`` vazio quando não há telefone ou o formato não é reconhecível (com o
    motivo em ``aviso``). Aceita números com ou sem DDI (55) e com 10/11 dígitos
    (DDD + número).
    """
    digitos = re.sub(r"\D", "", bruto or "")
    if not digitos:
        return "", ""
    if digitos.startswith("55") and len(digitos) in (12, 13):
        return "+" + digitos, ""
    if len(digitos) in (10, 11):
        return "+55" + digitos, ""
    return "", f"Telefone em formato não reconhecido: {bruto.strip()}"


def _extrair_json_objeto(texto: str) -> dict:
    """Extrai o objeto JSON da resposta da LLM, tolerando cercas de código e ruído."""
    t = (texto or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    inicio, fim = t.find("{"), t.rfind("}")
    if inicio == -1 or fim == -1 or fim < inicio:
        raise ValueError("A resposta da LLM não contém um JSON de alunos.")
    return json.loads(t[inicio : fim + 1])


def montar_prompt_importacao(series_existentes: Sequence[str]) -> str:
    series_txt = ", ".join(series_existentes) if series_existentes else "(nenhuma cadastrada)"
    return (
        f"{MARCADOR_IMPORTACAO}\n"
        "Você normaliza listas de alunos de uma escola brasileira para importação. "
        "A entrada é o texto de uma planilha ou PDF, possivelmente desorganizado ou "
        "com colunas fora de ordem. Extraia os alunos e responda ESTRITAMENTE com um "
        "JSON válido, sem nenhum texto fora do JSON, no formato:\n"
        '{"alunos": [{"nome": "...", "matricula": "...", "serie": "...", '
        '"responsaveis": [{"nome": "...", "telefone": "..."}]}]}\n'
        "Regras:\n"
        "- Padronize nomes próprios com a capitalização adequada "
        "(ex.: 'maria silva' -> 'Maria Silva').\n"
        "- Telefones no padrão brasileiro com DDD (apenas dígitos ou E.164).\n"
        "- 'serie' é a turma/série do aluno (ex.: '5º A', '4ª série B').\n"
        f"- Séries já cadastradas na escola: {series_txt}. "
        "Reaproveite exatamente esses nomes quando houver correspondência.\n"
        '- "matricula" é opcional; use "" quando não houver.\n'
        "- Ignore linhas que não sejam de aluno (cabeçalhos, totais, linhas vazias).\n"
        "- Não invente dados que não estejam na entrada."
    )


def _normalizar_linha(item: dict) -> LinhaImportacaoAluno:
    nome = str(item.get("nome", "") or "").strip()
    serie = str(item.get("serie", "") or "").strip()
    matricula = str(item.get("matricula", "") or "").strip()

    responsaveis: list[ResponsavelImportado] = []
    for r in item.get("responsaveis") or []:
        if not isinstance(r, dict):
            continue
        rnome = str(r.get("nome", "") or "").strip()
        telefone, aviso = normalizar_telefone(str(r.get("telefone", "") or ""))
        if not rnome and not telefone:
            continue
        responsaveis.append(
            ResponsavelImportado(nome=rnome or "Responsável", telefone=telefone, aviso=aviso)
        )

    linha = LinhaImportacaoAluno(
        nome=nome, serie=serie, matricula=matricula, responsaveis=responsaveis
    )
    if not nome:
        linha.erros.append("Nome do aluno ausente.")
    if not serie:
        linha.erros.append("Série/turma ausente.")
    for r in responsaveis:
        if r.aviso:
            linha.avisos.append(r.aviso)
        elif not r.telefone:
            linha.avisos.append(f"Responsável {r.nome} sem telefone.")
    if not responsaveis:
        linha.avisos.append("Aluno sem responsável informado.")
    return linha


# --------------------------------------------------------------------------- #
# Etapa 1: prévia (LLM normaliza, validamos em código)
# --------------------------------------------------------------------------- #
class PrevisualizarImportacaoAlunos:
    def __init__(self, *, llm: LLMProvider, salas: SalaRepository) -> None:
        self._llm = llm
        self._salas = salas

    async def executar(self, *, tenant_id: UUID, conteudo: str) -> PreviaImportacaoAlunos:
        conteudo = (conteudo or "").strip()
        if not conteudo:
            raise ValueError("Envie o conteúdo da planilha/PDF para importar.")

        salas = await self._salas.listar(tenant_id=tenant_id)
        nomes_existentes = [s.nome for s in salas]
        chaves_existentes = {_chave_serie(s.nome) for s in salas}

        sistema = montar_prompt_importacao(nomes_existentes)
        bruto = await self._llm.gerar(
            sistema=sistema, mensagens=[{"role": "user", "content": conteudo}]
        )
        try:
            dados = _extrair_json_objeto(bruto)
        except (ValueError, json.JSONDecodeError) as e:
            raise ValueError(
                "Não foi possível interpretar o conteúdo enviado. "
                "Revise o formato da planilha/PDF ou a configuração da LLM."
            ) from e

        linhas = [_normalizar_linha(i) for i in dados.get("alunos", []) if isinstance(i, dict)]

        # Marca séries novas (citadas, mas ainda inexistentes no tenant).
        novas: dict[str, str] = {}
        for linha in linhas:
            if linha.serie and _chave_serie(linha.serie) not in chaves_existentes:
                linha.serie_nova = True
                novas.setdefault(_chave_serie(linha.serie), linha.serie)

        return PreviaImportacaoAlunos(
            linhas=linhas,
            series_existentes=nomes_existentes,
            series_novas=list(novas.values()),
        )


# --------------------------------------------------------------------------- #
# Etapa 2: confirmação (persistência determinística, sem LLM)
# --------------------------------------------------------------------------- #
class ConfirmarImportacaoAlunos:
    def __init__(
        self,
        *,
        alunos: AlunoRepository,
        salas: SalaRepository,
        contatos: ContatoRepository,
    ) -> None:
        self._alunos = alunos
        self._salas = salas
        self._contatos = contatos

    async def executar(
        self,
        *,
        tenant_id: UUID,
        linhas: Sequence[LinhaImportacaoAluno],
        criar_series_ausentes: bool = False,
    ) -> ResultadoImportacaoAlunos:
        salas = await self._salas.listar(tenant_id=tenant_id)
        mapa_series = {_chave_serie(s.nome): s for s in salas}
        resultado = ResultadoImportacaoAlunos()

        for linha in linhas:
            if not linha.valido:
                resultado.ignorados += 1
                continue

            chave = _chave_serie(linha.serie)
            sala = mapa_series.get(chave)
            if sala is None:
                if not criar_series_ausentes:
                    resultado.ignorados += 1
                    resultado.erros.append(
                        f"Série '{linha.serie}' não existe (aluno {linha.nome})."
                    )
                    continue
                sala = await self._salas.criar(Sala(tenant_id=tenant_id, nome=linha.serie))
                mapa_series[chave] = sala
                resultado.series_criadas.append(sala.nome)

            responsavel_ids = await self._resolver_responsaveis(tenant_id, linha.responsaveis)

            aluno = await self._alunos.criar(
                Aluno(
                    tenant_id=tenant_id,
                    nome=linha.nome,
                    sala_id=sala.id,
                    matricula=linha.matricula,
                )
            )
            for contato_id in responsavel_ids:
                await self._alunos.vincular_responsavel(
                    tenant_id=tenant_id, aluno_id=aluno.id, contato_id=contato_id
                )
            resultado.criados += 1

        return resultado

    async def _resolver_responsaveis(
        self, tenant_id: UUID, responsaveis: Sequence[ResponsavelImportado]
    ) -> list[UUID]:
        """Reaproveita o ``Contato`` existente (por telefone) ou cria um novo.

        Responsáveis sem telefone são ignorados (o ``Contato`` exige telefone único
        por tenant); o aluno é cadastrado mesmo assim, e fica visível no alerta de
        cobertura de contatos da turma.
        """
        ids: list[UUID] = []
        for r in responsaveis:
            if not r.telefone:
                continue
            contato = await self._contatos.por_telefone(
                tenant_id=tenant_id, telefone=r.telefone
            )
            if contato is None:
                contato = await self._contatos.criar(
                    Contato(tenant_id=tenant_id, nome=r.nome, telefone=r.telefone)
                )
            if contato.id not in ids:
                ids.append(contato.id)
        return ids
