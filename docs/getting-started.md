# Empezar

## Requisitos

- **Node ≥ 20** + **pnpm 9** (para `frontend` y este sitio de docs).
- **Python 3.12+** + **Docker** (para `backend`: Postgres/pgvector).

## Este sitio de documentación (VitePress)

```bash
pnpm install                                   # instala las deps del workspace (incl. vitepress)
pnpm --filter @syntax/docs docs:dev     # sirve la documentación en local
pnpm --filter @syntax/docs docs:build   # build estático → docs/.vitepress/dist
```

> Aún no se ha ejecutado `pnpm install` para las docs; el scaffold (config + páginas) está listo para
> arrancar.

## Backend (esqueleto → implementación)

El backend es hoy un **esqueleto doc-only**. Para construirlo y levantarlo, la referencia es la
[**Guía de implementación**](/backend/implementation) (`backend/IMPLEMENTATION-GUIDE.md`). Resumen del
arranque una vez implementado:

```bash
cd backend
cp .env.example .env        # rellena secretos (JWT_SECRET, OPENAI_API_KEY, …)
make install                # pip-tools: compila e instala requirements
docker compose up -d db     # Postgres + pgvector
make migrate                # Alembic: tablas + extensión vector + políticas RLS
make ingest                 # ingiere la KB (idempotente)
make seed                   # datos demo (tenants/roles/usuarios/tickets/KB)
make run                    # API en :8000
```

## Frontend

Ver [Frontend · visión general](/frontend/). El frontend deriva su cliente tipado y sus mocks MSW del
[contrato de API](/reference/api-contract).

## Método de trabajo

El repo sigue **Spec-Driven Design + TDD** orquestado por el plugin `task-pipeline`. La referencia del
flujo (estados, ramas, gates, DoD) es [Task lifecycle](/guides/task-lifecycle).
