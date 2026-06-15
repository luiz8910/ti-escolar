"""Adaptadores para APIs compatíveis com a OpenAI (Chat Completions + Embeddings).

Cobre tanto a OpenAI quanto endpoints compatíveis (vLLM, Together, Groq, etc.) via
``base_url``. Usa ``httpx`` (já no core) — nenhum SDK específico é necessário, e o domínio
permanece desacoplado. A tradução do tool use (formato ``tools``/``tool_calls`` da OpenAI)
acontece só aqui, na infraestrutura.
"""

from __future__ import annotations

import json

from app.domain.entities import (
    ChamadaFerramenta,
    FerramentaSpec,
    RespostaLLM,
    TurnoConversa,
)

_TIMEOUT_SEGUNDOS = 60.0


class OpenAICompatibleLLMProvider:
    def __init__(
        self, *, api_key: str, model: str, base_url: str = "https://api.openai.com/v1"
    ) -> None:
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}

    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        corpo = {
            "model": self._model,
            "max_tokens": 1024,
            "messages": [{"role": "system", "content": sistema}, *mensagens],
        }
        dados = await self._post("/chat/completions", corpo)
        return (dados["choices"][0]["message"].get("content") or "").strip()

    async def gerar_com_ferramentas(
        self,
        *,
        sistema: str,
        turnos: list[TurnoConversa],
        ferramentas: list[FerramentaSpec],
    ) -> RespostaLLM:
        corpo = {
            "model": self._model,
            "max_tokens": 1024,
            "messages": [
                {"role": "system", "content": sistema},
                *self._turnos_para_mensagens(turnos),
            ],
            "tools": self._ferramentas_para_tools(ferramentas),
            "tool_choice": "auto",
        }
        dados = await self._post("/chat/completions", corpo)
        msg = dados["choices"][0]["message"]
        texto = (msg.get("content") or "").strip()
        chamadas = [
            ChamadaFerramenta(
                id=tc["id"],
                nome=tc["function"]["name"],
                argumentos=json.loads(tc["function"].get("arguments") or "{}"),
            )
            for tc in (msg.get("tool_calls") or [])
        ]
        return RespostaLLM(texto=texto, chamadas=chamadas)

    async def _post(self, caminho: str, corpo: dict) -> dict:
        import httpx  # import tardio: httpx é core, mas mantém o módulo leve para teste

        async with httpx.AsyncClient(timeout=_TIMEOUT_SEGUNDOS) as client:
            resp = await client.post(
                f"{self._base_url}{caminho}", json=corpo, headers=self._headers
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def _ferramentas_para_tools(ferramentas: list[FerramentaSpec]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": f.nome,
                    "description": f.descricao,
                    "parameters": f.parametros,
                },
            }
            for f in ferramentas
        ]

    @staticmethod
    def _turnos_para_mensagens(turnos: list[TurnoConversa]) -> list[dict]:
        mensagens: list[dict] = []
        for turno in turnos:
            if turno.papel == "assistant":
                msg: dict = {"role": "assistant", "content": turno.texto or None}
                if turno.chamadas:
                    msg["tool_calls"] = [
                        {
                            "id": ch.id,
                            "type": "function",
                            "function": {
                                "name": ch.nome,
                                "arguments": json.dumps(ch.argumentos, ensure_ascii=False),
                            },
                        }
                        for ch in turno.chamadas
                    ]
                mensagens.append(msg)
            elif turno.resultados:
                # Resultados de ferramenta viram mensagens role="tool" (uma por resultado).
                mensagens.extend(
                    {"role": "tool", "tool_call_id": r.id, "content": r.conteudo}
                    for r in turno.resultados
                )
            else:
                mensagens.append({"role": "user", "content": turno.texto})
        return mensagens


class OpenAICompatibleEmbedder:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensao: int = 1536,
        base_url: str = "https://api.openai.com/v1",
    ) -> None:
        self._model = model
        self._dim = dimensao
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}"}

    @property
    def dimensao(self) -> int:
        return self._dim

    async def embed(self, textos: list[str]) -> list[list[float]]:
        if not textos:
            return []
        import httpx  # import tardio (ver OpenAICompatibleLLMProvider._post)

        async with httpx.AsyncClient(timeout=_TIMEOUT_SEGUNDOS) as client:
            resp = await client.post(
                f"{self._base_url}/embeddings",
                json={"model": self._model, "input": textos},
                headers=self._headers,
            )
            resp.raise_for_status()
            dados = resp.json()["data"]
        # A API garante ordem por "index"; ordena por segurança.
        dados.sort(key=lambda d: d["index"])
        return [d["embedding"] for d in dados]
