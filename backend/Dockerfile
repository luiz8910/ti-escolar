FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instala dependências primeiro (cache de camada).
COPY pyproject.toml ./
# Inclui o extra "llm" (pacote anthropic) para suportar LLM_PROVIDER=anthropic em produção.
# O extra "s3" traz o boto3, para ARQUIVO_STORAGE=s3.
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir ".[dev,llm,s3]"

COPY . .

# Commit publicado, ecoado por /health (ver app/main.py). Fica DEPOIS do pip install para
# não invalidar a camada de dependências a cada commit. A Fly recebe via
# `fly deploy --build-arg GIT_SHA=...`; o Render injeta RENDER_GIT_COMMIT sozinho, em
# tempo de execução, e por isso não precisa deste argumento.
ARG GIT_SHA=""
ENV GIT_COMMIT=$GIT_SHA

EXPOSE 8000
# Render injeta a porta via $PORT; localmente cai em 8000.
# Aplica migrations e provisiona o super admin (idempotente, seguro em produção) antes
# de subir a API. O seed de DEMONSTRAÇÃO não roda aqui: ele cria escola fictícia e logins
# com senha de exemplo, e é chamado explicitamente pelo docker-compose (dev) ou por um
# job manual de homologação, sempre com SEED_DEMO=true. Ver `app/bootstrap.py`.
CMD ["sh", "-c", "alembic upgrade head && python -m app.bootstrap && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
