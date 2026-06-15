# TI-Escolar

Plataforma de comunicação escolar com chatbot via WhatsApp. Veja [CLAUDE.md](./CLAUDE.md)
para a visão de arquitetura completa.

- **Back-end:** Python 3.12 + FastAPI, arquitetura hexagonal, PostgreSQL + pgvector.
- **Front-end demo:** Next.js que simula a interface do WhatsApp.
- **LLM:** abstração multi-provider (geração + embeddings); adaptador `fake` roda sem chaves.
- **Outbound:** disparo de avisos a pais via Meta WhatsApp Cloud API (com templates e limites por tier).

## Como rodar (Docker)

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000 (docs em `/docs`)
- Demo WhatsApp: http://localhost:3000

O backend, ao subir, aplica as migrations (Alembic) e executa o **seed** com uma escola de
demonstração, FAQs e avisos indexados (RAG). Com `LLM_PROVIDER=fake` tudo funciona sem chaves de API.

## Estrutura

```
backend/   # FastAPI — domain / application / infrastructure / interfaces
web/        # Next.js — demo estilo WhatsApp
docker-compose.yml
```

## Testes (back-end)

```bash
cd backend
pip install -e ".[dev]"
pytest
```
