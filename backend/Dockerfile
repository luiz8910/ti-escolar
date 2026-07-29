FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instala dependências primeiro (cache de camada).
COPY pyproject.toml ./
# Inclui o extra "llm" (pacote anthropic) para suportar LLM_PROVIDER=anthropic em produção.
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir ".[dev,llm]"

COPY . .

EXPOSE 8000
# Render injeta a porta via $PORT; localmente cai em 8000.
# Aplica migrations e provisiona o super admin (idempotente, seguro em produção) antes
# de subir a API. O seed de DEMONSTRAÇÃO não roda aqui: ele cria escola fictícia e logins
# com senha de exemplo, e é chamado explicitamente pelo docker-compose (dev) ou por um
# job manual de homologação, sempre com SEED_DEMO=true. Ver `app/bootstrap.py`.
CMD ["sh", "-c", "alembic upgrade head && python -m app.bootstrap && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
