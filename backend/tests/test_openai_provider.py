"""Testa a tradução do tool use para o formato da OpenAI (sem rede).

Cobre os métodos estáticos puros do ``OpenAICompatibleLLMProvider`` — a parte que mais
facilmente quebra. As chamadas HTTP em si não são exercitadas aqui.
"""

from __future__ import annotations

import json

from app.domain.entities import (
    ChamadaFerramenta,
    FerramentaSpec,
    ResultadoFerramenta,
    TurnoConversa,
)
from app.infrastructure.llm.openai_provider import OpenAICompatibleLLMProvider


def test_ferramentas_para_tools():
    spec = FerramentaSpec(
        nome="buscar_conhecimento",
        descricao="Busca na base da escola.",
        parametros={"type": "object", "properties": {"consulta": {"type": "string"}}},
    )
    tools = OpenAICompatibleLLMProvider._ferramentas_para_tools([spec])
    assert tools == [
        {
            "type": "function",
            "function": {
                "name": "buscar_conhecimento",
                "description": "Busca na base da escola.",
                "parameters": spec.parametros,
            },
        }
    ]


def test_turnos_para_mensagens_user_assistant_tool():
    turnos = [
        TurnoConversa(papel="user", texto="quero o boletim"),
        TurnoConversa(
            papel="assistant",
            texto="",
            chamadas=[
                ChamadaFerramenta(
                    id="call_1", nome="recuperar_documento", argumentos={"consulta": "boletim"}
                )
            ],
        ),
        TurnoConversa(
            papel="user",
            resultados=[
                ResultadoFerramenta(id="call_1", conteudo="Documentos enviados: Boletim.pdf.")
            ],
        ),
    ]
    msgs = OpenAICompatibleLLMProvider._turnos_para_mensagens(turnos)

    assert msgs[0] == {"role": "user", "content": "quero o boletim"}

    assistente = msgs[1]
    assert assistente["role"] == "assistant"
    assert assistente["content"] is None  # sem texto -> None (exigido pela API com tool_calls)
    assert assistente["tool_calls"][0]["id"] == "call_1"
    assert assistente["tool_calls"][0]["function"]["name"] == "recuperar_documento"
    args = assistente["tool_calls"][0]["function"]["arguments"]
    assert json.loads(args) == {"consulta": "boletim"}

    assert msgs[2] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": "Documentos enviados: Boletim.pdf.",
    }
