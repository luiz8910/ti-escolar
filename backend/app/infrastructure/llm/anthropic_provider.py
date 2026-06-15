"""Adaptador de LLM via Anthropic Claude (geração/raciocínio).

Reservado conforme o CLAUDE.md: usa os modelos Claude mais recentes via API. O SDK só é
importado aqui, na infraestrutura — o domínio permanece desacoplado.
"""

from __future__ import annotations

from app.domain.entities import (
    ChamadaFerramenta,
    FerramentaSpec,
    RespostaLLM,
    TurnoConversa,
)


class AnthropicLLMProvider:
    def __init__(self, *, api_key: str, model: str = "claude-opus-4-8") -> None:
        # Import tardio: o pacote só é necessário quando este adaptador é selecionado.
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def gerar(self, *, sistema: str, mensagens: list[dict[str, str]]) -> str:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=sistema,
            messages=[{"role": m["role"], "content": m["content"]} for m in mensagens],
        )
        partes = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
        return "".join(partes).strip()

    async def gerar_com_ferramentas(
        self,
        *,
        sistema: str,
        turnos: list[TurnoConversa],
        ferramentas: list[FerramentaSpec],
    ) -> RespostaLLM:
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=sistema,
            tools=[
                {"name": f.nome, "description": f.descricao, "input_schema": f.parametros}
                for f in ferramentas
            ],
            messages=[self._turno_para_mensagem(t) for t in turnos],
        )
        texto = "".join(
            b.text for b in resp.content if getattr(b, "type", None) == "text"
        ).strip()
        chamadas = [
            ChamadaFerramenta(id=b.id, nome=b.name, argumentos=dict(b.input))
            for b in resp.content
            if getattr(b, "type", None) == "tool_use"
        ]
        return RespostaLLM(texto=texto, chamadas=chamadas)

    @staticmethod
    def _turno_para_mensagem(turno: TurnoConversa) -> dict:
        if turno.papel == "assistant":
            blocos: list[dict] = []
            if turno.texto:
                blocos.append({"type": "text", "text": turno.texto})
            for ch in turno.chamadas:
                blocos.append(
                    {"type": "tool_use", "id": ch.id, "name": ch.nome, "input": ch.argumentos}
                )
            # Sem blocos estruturados, devolve texto simples.
            return {"role": "assistant", "content": blocos or turno.texto}

        if turno.resultados:
            return {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": r.id, "content": r.conteudo}
                    for r in turno.resultados
                ],
            }
        return {"role": "user", "content": turno.texto}
