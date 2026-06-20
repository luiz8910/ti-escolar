"""Adaptadores "fake" para rodar o demo sem chaves de API.

- ``FakeLLMProvider``: gera uma resposta determinística a partir do CONTEXTO injetado no
  prompt de sistema (simula o raciocínio do RAG sobre as fontes recuperadas).
- ``FakeEmbedder``: embeddings determinísticos baseados em hashing de tokens — sem rede,
  bons o bastante para a busca por similaridade funcionar no demo.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import uuid

from app.domain.entities import (
    ChamadaFerramenta,
    FerramentaSpec,
    RespostaLLM,
    TurnoConversa,
)

# Palavras que sinalizam intenção de documento (heurística só do fake, para o demo sem chaves).
_GATILHOS_DOC = (
    "boletim", "declaraç", "documento", "comprovante", "histórico", "historico", "2ª via",
)

# Marcador do prompt de importação de alunos (ver app.application.importacao_use_cases).
_MARCADOR_IMPORTACAO = "IMPORTACAO_ALUNOS_JSON_V1"


def _csv_para_alunos_json(conteudo: str) -> str:
    """Converte texto tabular (CSV/TSV) em JSON de alunos, para o demo sem chaves.

    Não é "inteligente": detecta o delimitador, mapeia colunas por palavras-chave no
    cabeçalho (ou assume a ordem nome, série, matrícula, responsável, telefone) e
    devolve o mesmo JSON que o adaptador real produziria. A normalização "de verdade"
    (texto bagunçado, PDF) é papel do adaptador Anthropic.
    """
    linhas = [ln for ln in conteudo.splitlines() if ln.strip()]
    if not linhas:
        return json.dumps({"alunos": []}, ensure_ascii=False)

    amostra = linhas[0]
    delim = max([",", ";", "\t", "|"], key=amostra.count)
    if amostra.count(delim) == 0:
        delim = ","
    registros = [
        [c.strip() for c in r]
        for r in csv.reader(io.StringIO(conteudo), delimiter=delim)
        if any(c.strip() for c in r)
    ]
    if not registros:
        return json.dumps({"alunos": []}, ensure_ascii=False)

    cabecalho = registros[0]
    palavras = ("nome", "aluno", "serie", "série", "turma", "matr", "respons", "tel", "fone")
    tem_cabecalho = any(any(p in c.lower() for p in palavras) for c in cabecalho)

    col = {"nome": 0, "serie": 1, "matricula": 2, "resp": 3, "tel": 4}
    inicio = 0
    if tem_cabecalho:
        inicio = 1
        col = {"nome": 0, "serie": -1, "matricula": -1, "resp": -1, "tel": -1}
        for i, c in enumerate(cabecalho):
            cl = c.lower()
            if "alun" in cl or cl == "nome":
                col["nome"] = i
            elif "matr" in cl:
                col["matricula"] = i
            elif "serie" in cl or "série" in cl or "turma" in cl:
                col["serie"] = i
            elif "respons" in cl or "pai" in cl or "mãe" in cl or "mae" in cl:
                col["resp"] = i
            elif "tel" in cl or "fone" in cl or "whats" in cl or "celular" in cl:
                col["tel"] = i

    def _get(linha: list[str], i: int) -> str:
        return linha[i].strip() if 0 <= i < len(linha) else ""

    alunos = []
    for r in registros[inicio:]:
        nome = _get(r, col["nome"])
        if not nome:
            continue
        responsaveis = []
        rnome, tel = _get(r, col["resp"]), _get(r, col["tel"])
        if rnome or tel:
            responsaveis.append({"nome": rnome, "telefone": tel})
        alunos.append(
            {
                "nome": nome,
                "matricula": _get(r, col["matricula"]),
                "serie": _get(r, col["serie"]),
                "responsaveis": responsaveis,
            }
        )
    return json.dumps({"alunos": alunos}, ensure_ascii=False)


class FakeLLMProvider:
    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        pergunta = next(
            (m["content"] for m in reversed(mensagens) if m["role"] == "user"), ""
        )
        if _MARCADOR_IMPORTACAO in sistema:
            return _csv_para_alunos_json(pergunta)
        contexto = ""
        if "CONTEXTO:" in sistema:
            contexto = sistema.split("CONTEXTO:", 1)[1].strip()

        if not contexto or contexto == "(sem informações disponíveis)":
            return (
                "Olá! No momento não localizei essa informação em nossos materiais. "
                "Por gentileza, entre em contato com a secretaria da escola para te ajudarmos. "
                "Posso ajudar em algo mais?"
            )

        # Usa o primeiro bloco do contexto como base da resposta (simulação de síntese).
        primeiro = contexto.split("\n\n", 1)[0]
        primeiro = re.sub(r"^\[.*?\]\n", "", primeiro).strip()
        return (
            f"Olá! Sobre a sua dúvida \"{pergunta.strip()}\", segue a orientação da escola:\n\n"
            f"{primeiro}\n\n"
            "Permaneço à disposição caso precise de algo mais."
        )

    async def gerar_com_ferramentas(
        self,
        *,
        sistema: str,
        turnos: list[TurnoConversa],
        ferramentas: list[FerramentaSpec],
    ) -> RespostaLLM:
        """Simula o agente sem rede: um turno escolhe a ferramenta; o seguinte sintetiza.

        Não é "inteligente" — é só o suficiente para o demo funcionar sem chaves. O
        roteamento real (que entende frases ambíguas) acontece no adaptador Anthropic.
        """
        ultimo = turnos[-1] if turnos else None

        # Turno com resultados de ferramenta -> redige a resposta final (sem novas chamadas).
        if ultimo is not None and ultimo.resultados:
            partes = [r.conteudo for r in ultimo.resultados]
            corpo = "\n\n".join(partes)
            primeiro = re.sub(r"^\[.*?\]\n", "", corpo.split("\n\n", 1)[0]).strip()
            return RespostaLLM(
                texto=(
                    f"Olá! Segue o retorno da escola:\n\n{primeiro}\n\n"
                    "Permaneço à disposição caso precise de algo mais."
                )
            )

        pergunta = next(
            (t.texto for t in reversed(turnos) if t.papel == "user" and t.texto), ""
        )
        nomes = {f.nome for f in ferramentas}
        quer_doc = any(g in pergunta.lower() for g in _GATILHOS_DOC)
        alvo = "recuperar_documento" if (quer_doc and "recuperar_documento" in nomes) else (
            "buscar_conhecimento" if "buscar_conhecimento" in nomes else None
        )
        if alvo is None:
            return RespostaLLM(texto="Como posso ajudar?")
        return RespostaLLM(
            chamadas=[
                ChamadaFerramenta(
                    id=f"call_{uuid.uuid4().hex[:8]}", nome=alvo, argumentos={"consulta": pergunta}
                )
            ]
        )


class FakeEmbedder:
    def __init__(self, dimensao: int = 1536) -> None:
        self._dim = dimensao

    @property
    def dimensao(self) -> int:
        return self._dim

    async def embed(self, textos: list[str]) -> list[list[float]]:
        return [self._embed_um(t) for t in textos]

    def _embed_um(self, texto: str) -> list[float]:
        vetor = [0.0] * self._dim
        tokens = re.findall(r"\w+", texto.lower())
        for tok in tokens:
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)  # noqa: S324 — não-cripto
            idx = h % self._dim
            sinal = 1.0 if (h >> 8) & 1 else -1.0
            vetor[idx] += sinal
        norma = math.sqrt(sum(v * v for v in vetor)) or 1.0
        return [v / norma for v in vetor]
