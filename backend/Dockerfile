FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Instala dependências primeiro (cache de camada).
COPY pyproject.toml ./
# Inclui o extra "llm" (pacote anthropic) para suportar LLM_PROVIDER=anthropic em produção.
# O extra "s3" traz o boto3, para ARQUIVO_STORAGE=s3.
# **Sem o extra "dev":** pytest e ruff não têm o que fazer numa imagem de produção, e cada
# pacote a mais é superfície que alguém precisa acompanhar por CVE.
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir ".[llm,s3]"

COPY . .

EXPOSE 8000
# Render/Fly injetam a porta via $PORT; localmente cai em 8000.
#
# **As migrations continuam aqui, mas o Fly não usa este caminho.** No Render o `CMD` é o
# único gancho disponível, então `alembic upgrade head` roda a cada restart — e é por isso
# que um `downgrade` se desfaz sozinho durante um rollback (§15 item 9). No Fly, o
# `release_command` do `fly.toml` faz isso uma vez por deploy e este trecho não executa,
# porque o comando de lá substitui a etapa. Ao mexer num, confira o outro.
#
# O seed de DEMONSTRAÇÃO não roda em lugar nenhum daqui: ele cria escola fictícia e logins
# com senha de exemplo, e é chamado explicitamente pelo docker-compose (dev) ou por um job
# manual de homologação, sempre com SEED_DEMO=true. Ver `app/bootstrap.py`.
CMD ["sh", "-c", "alembic upgrade head && python -m app.bootstrap && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
