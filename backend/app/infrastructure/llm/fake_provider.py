"""Adaptadores "fake" para rodar o demo sem chaves de API.

- ``FakeLLMProvider``: gera uma resposta determinística a partir do CONTEXTO injetado no
  prompt de sistema (simula o raciocínio do RAG sobre as fontes recuperadas).
- ``FakeEmbedder``: embeddings determinísticos baseados em hashing de tokens — sem rede,
  bons o bastante para a busca por similaridade funcionar no demo.
"""

from __future__ import annotations

import hashlib
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


class FakeLLMProvider:
    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        pergunta = next(
            (m["content"] for m in reversed(mensagens) if m["role"] == "user"), ""
        )
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
