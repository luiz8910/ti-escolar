FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instala dependências primeiro (cache de camada).
COPY pyproject.toml ./
# Caminho OpenAI usa httpx (core); o extra "llm" (pacote anthropic) só é necessário
# se LLM_PROVIDER=anthropic.
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir ".[dev]"

COPY . .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
