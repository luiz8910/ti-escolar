"""Leitura de documentos por IA — adaptadores da porta ``LeitorDocumento`` (§4.3).

O apontamento de 10/08 pede "LLM especialista em OCR para identificar tipo de documento e
pré preencher os campos". O que existia era `sugerir_categoria`, uma heurística de palavra
sobre a **legenda** — decisão correta para texto, e cega para o conteúdo da foto.

**Porta separada de ``LLMProvider``**: aquele contrato é de texto puro, e nem todo provedor
sabe olhar uma imagem. Aqui o adaptador manda o arquivo como bloco `image`/`document` para
a API da Anthropic.

**Custo:** roda **sob demanda** (a secretaria clica em "Ler documento"), nunca em todo
upload. Em época de matrícula o volume é alto e a maioria dos documentos a secretaria
classifica de olho — pagar inferência por todos seria caro e lento sem ganho.

``LeitorDocumentoFake`` mantém o fluxo demonstrável sem chave, como o resto da infra.
"""

from __future__ import annotations

import base64
import json
import logging
import re

from app.domain.entities import CategoriaDocumento, DocumentoLido

logger = logging.getLogger("leitor_documento")

# Marcador no prompt, como nos outros fluxos de IA do projeto (importação em massa, ficha).
# É o que permite ao provedor fake reconhecer a intenção sem chave nenhuma.
MARCADOR_LEITURA = "LEITURA_DOCUMENTO_JSON_V1"

_SISTEMA = (
    f"{MARCADOR_LEITURA}\n"
    "Você lê documentos enviados por responsáveis a uma escola brasileira pelo WhatsApp "
    "(foto ou PDF). Responda ESTRITAMENTE com um JSON válido, sem texto fora dele:\n"
    '{"categoria": "matricula|atestado|comprovante|outro", "aluno_nome": "...", '
    '"resumo": "uma frase", "campos_ficha": {}}\n'
    "Regras:\n"
    "- `categoria` é o tipo do documento. Use 'outro' quando não for claro — não adivinhe.\n"
    "- `aluno_nome` só quando o nome do aluno aparecer no documento; senão, string vazia.\n"
    "- `resumo` descreve o documento em uma frase, sem transcrever dados de saúde.\n"
    "- `campos_ficha` só para FICHA DE MATRÍCULA, com as chaves que conseguir ler "
    "(cpf, ra_rm, data_nascimento, endereco, sexo, cor_raca, cartao_sus, cidade_natal).\n"
    "- Não invente nada: campo que você não leu com clareza fica de fora."
)

# Formatos que a API aceita como imagem. PDF vai como bloco `document`.
_MIMES_IMAGEM = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def _extrair_json(texto: str) -> dict:
    t = (texto or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z]*\n?", "", t)
        t = re.sub(r"\n?```$", "", t).strip()
    inicio, fim = t.find("{"), t.rfind("}")
    if inicio == -1 or fim == -1 or fim < inicio:
        raise ValueError("resposta sem JSON")
    return json.loads(t[inicio : fim + 1])


def montar_documento_lido(bruto: dict) -> DocumentoLido:
    """Valida **em código** o que o modelo devolveu. A LLM não é fonte de verdade.

    Categoria desconhecida vira ``None`` em vez de estourar: o palpite errado do modelo
    não pode impedir a secretaria de ver o resto do que ele leu.
    """
    categoria = None
    bruta = str(bruto.get("categoria", "") or "").strip().lower()
    if bruta:
        try:
            categoria = CategoriaDocumento(bruta)
        except ValueError:
            logger.info("Categoria desconhecida devolvida pela leitura: %s", bruta)

    campos = bruto.get("campos_ficha")
    return DocumentoLido(
        categoria=categoria,
        aluno_nome=str(bruto.get("aluno_nome", "") or "").strip(),
        resumo=str(bruto.get("resumo", "") or "").strip(),
        campos_ficha={
            k: str(v).strip()
            for k, v in (campos or {}).items()
            if isinstance(k, str) and v not in (None, "")
        }
        if isinstance(campos, dict)
        else {},
    )


class AnthropicLeitorDocumento:
    """Leitura via API da Anthropic, mandando o arquivo como bloco de conteúdo."""

    def __init__(self, *, api_key: str, model: str = "claude-opus-4-8") -> None:
        from anthropic import AsyncAnthropic  # import tardio, como no provider de texto

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    async def ler(self, *, conteudo: bytes, mime: str) -> DocumentoLido:
        if mime in _MIMES_IMAGEM:
            bloco = {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": base64.b64encode(conteudo).decode(),
                },
            }
        elif mime == "application/pdf":
            bloco = {
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": mime,
                    "data": base64.b64encode(conteudo).decode(),
                },
            }
        else:
            # DOC/DOCX estão na allowlist de upload mas não são legíveis assim. Dizer isso
            # é melhor que devolver um resultado vazio que parece falha do modelo.
            return DocumentoLido(erro=f"A leitura por IA não suporta {mime}.")

        try:
            resp = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=_SISTEMA,
                messages=[
                    {
                        "role": "user",
                        "content": [bloco, {"type": "text", "text": "Leia este documento."}],
                    }
                ],
            )
            texto = "".join(
                b.text for b in resp.content if getattr(b, "type", None) == "text"
            )
            return montar_documento_lido(_extrair_json(texto))
        except Exception:  # noqa: BLE001 — leitura é auxiliar; não pode derrubar a tela
            logger.warning("Falha ao ler o documento por IA", exc_info=True)
            return DocumentoLido(erro="Não foi possível ler o documento agora.")


class LeitorDocumentoFake:
    """Leitura simulada — demonstra o fluxo sem chave nenhuma.

    Devolve um palpite estável a partir do MIME, para a tela de revisão ser exercitável em
    desenvolvimento e nos testes.
    """

    async def ler(self, *, conteudo: bytes, mime: str) -> DocumentoLido:
        if not conteudo:
            return DocumentoLido(erro="Arquivo vazio.")
        if mime == "application/pdf":
            return DocumentoLido(
                categoria=CategoriaDocumento.MATRICULA,
                resumo="Documento em PDF enviado pelo responsável (leitura simulada).",
            )
        return DocumentoLido(
            categoria=CategoriaDocumento.ATESTADO,
            resumo="Imagem enviada pelo responsável (leitura simulada).",
        )
