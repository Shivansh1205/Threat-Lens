# Contributing

Start with the root [README](../README.md) for the product overview and complete
Compose demonstration. This guide covers source development and validation.

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm
- Docker Desktop and Docker Compose
- Git
- Ollama only when developing optional AI features

Never commit `.env` files or real API keys. Root, backend, and frontend templates
are provided as `.env.example` files.

## Integrated setup

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

Use the integrated stack for cross-service verification. Rebuild images after
source changes with `docker compose up --build -d`.

## Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python -m ruff check .
python -m black --check .
```

On macOS or Linux, activate with `source .venv/bin/activate`. Tests use SQLite, so
PostgreSQL and Ollama are not required.

To run the backend directly, copy `backend/.env.example` to `backend/.env`, provide
the PostgreSQL database in `DATABASE_URL`, apply migrations, and start Uvicorn:

```powershell
Copy-Item .env.example .env
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8002
```

Stop the Compose backend first because it also publishes port 8002.

## Frontend

```powershell
cd frontend
npm install
Copy-Item .env.example .env
npm run dev
```

Restart Vite after changing environment variables. Validate with:

```powershell
npm test
npm run lint
npm run build
```

Oxlint is the configured linter and Node's test runner executes utility tests.
There is no configured Prettier or ESLint command.

## Collector and Sentinel portal

Validate the demo portal and collector from the repository root:

```powershell
cd demo_site
python -m pytest -q
cd ..
python -m pytest collector/test_collector.py
```

Use Compose for end-to-end collector testing because it supplies the shared log
and checkpoint volumes. Generate bounded direct traffic with:

```powershell
python scripts/generate_logs.py --scenario mixed --speed 10
```

## Changing detectors

Detectors live in `backend/app/detection/rules/`, return `AlertCandidate` values,
and must not commit database rows themselves.

When changing a rule:

1. Register it in `detection/registry.py`.
2. Put configuration in `config.py`, `detection/settings.py`, and the env template.
3. Update Settings UI metadata for administrator-editable values.
4. Add threshold, escalation, reset, and concurrency tests as applicable.
5. Update user-facing docs and the changelog.

Do not update a behavior profile before rules inspect the current event; unusual-IP
detection depends on the pre-event baseline.

## Changing AI or frontend code

Mock `backend/app/ai/ollama_client.py` in AI tests. Ingestion must stay independent
of model latency, and explanation failures must leave stored alerts intact.

Frontend pages live in `frontend/src/pages/` and reusable features in
`frontend/src/components/`. Reuse the alert stream and chat/theme contexts, test
non-trivial utilities, and verify visual changes in both themes.

## Commits and reviews

Use focused branches and Conventional Commit messages, for example:

```text
feat(detection): add path-probe escalation
fix(reports): escape spreadsheet formula cells
docs(architecture): document collector idempotency
```

Before review, run relevant tests, linters, and the frontend production build; add
a changelog entry for user-visible behavior; update architecture/setup docs for
interface changes; and include screenshots for UI changes.

For the disposable Compose demo, `docker compose down -v` is the explicit full
reset and permanently deletes all project volumes.
