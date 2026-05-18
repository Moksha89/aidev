# apps/api

The FastAPI backend for the AI Developer platform.

Implements the API surface that the dashboard talks to, owns the
PostgreSQL schema, talks to GitHub for branch/PR work, and dispatches
tasks to the Celery agent-runner.

## Local development

```bash
cp .env.example .env
poetry install
poetry run alembic upgrade head     # creates schema + seed data
poetry run uvicorn app.main:app --reload --port 8000
```

OpenAPI docs at `http://localhost:8000/docs`.

## Layout

```
app/
├── main.py                  # FastAPI app factory + middleware
├── config.py                # pydantic-settings config
├── db.py                    # SQLAlchemy engine + session
├── core/
│   ├── deps.py              # FastAPI dependency injectors
│   ├── security.py          # password hashing, token helpers
│   └── orchestrator.py      # in-process mock task orchestrator
├── models/                  # SQLAlchemy ORM models
├── schemas/                 # Pydantic request/response shapes
└── routes/                  # one router per resource
alembic/                     # migrations
tests/                       # integration tests (pytest + httpx)
```

## Tests

```bash
poetry run pytest -v
```

The test suite uses SQLite in-memory by default for speed. To run
against the same Postgres your dev API uses, set `DATABASE_URL` and
pass `--run-postgres`.

## Lint

```bash
poetry run ruff check .
poetry run ruff format --check .
```
