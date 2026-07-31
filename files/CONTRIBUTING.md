# Contributing

How to set up ThreatLens locally, run it, and add to it without stepping on anyone's toes. Even if you're the only person on the codebase this week, writing this down saves the future-you an hour.

---

## Prerequisites

- **Python 3.11+** (3.12 preferred).
- **Node.js 18+** and **npm** (or pnpm / yarn if you prefer).
- **PostgreSQL 14+** running locally or in Docker.
- **Ollama** — needed for the LLM explainability layer. Install from [ollama.com](https://ollama.com).
- **Git**.
- **VS Code** (recommended) with Python and ES7+ React extensions.

Check versions:

```bash
python --version
node --version
psql --version
ollama --version
```

---

## First-time setup

### 1. Clone the repo

```bash
git clone <repo-url> threatlens
cd threatlens
```

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy the env template and fill it in:

```bash
cp .env.example .env
```

Required env vars (see `.env.example` for the full list):

```
DATABASE_URL=postgresql://user:pass@localhost:5432/threatlens
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=mistral
JWT_SECRET=change-me
LOG_LEVEL=INFO
```

Initialize the database:

```bash
# create the DB
createdb threatlens

# run migrations (alembic or whatever we settle on)
alembic upgrade head
```

Optional: seed with sample data for the dashboard to have something to render:

```bash
python scripts/seed_data.py
```

### 3. Frontend

```bash
cd ../frontend
npm install
```

### 4. Ollama

```bash
ollama pull mistral
ollama serve                    # runs in background on :11434
```

Confirm it's alive:

```bash
curl http://localhost:11434/api/tags
```

---

## Running locally

Three processes, three terminals:

```bash
# Terminal 1 — backend
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev                     # opens http://localhost:5173

# Terminal 3 — Ollama (if not already running)
ollama serve
```

Then:

- Dashboard: <http://localhost:5173>
- API docs (Swagger): <http://localhost:8000/docs>
- WebSocket endpoint: `ws://localhost:8000/ws/alerts`

### Simulating log traffic

Handy for testing detection without a real log source:

```bash
python scripts/generate_logs.py --scenario brute_force --duration 60
python scripts/generate_logs.py --scenario port_scan
python scripts/generate_logs.py --scenario normal --duration 300
```

---

## Running tests

```bash
# backend
cd backend
pytest                          # all tests
pytest -k detection             # only detection tests
pytest --cov=app                # with coverage

# frontend
cd frontend
npm test
```

Before you push: run `pytest` and `npm test`. CI will re-run them, but catching failures locally is faster.

---

## Code style

- **Python**: black + ruff. Run `black . && ruff check .` before committing.
- **JavaScript / React**: Prettier + ESLint. `npm run lint` and `npm run format`.
- **Imports**: absolute imports in the backend (`from app.detection import ...`), no deep relatives.
- **Types**: type hints on all public functions in Python; TypeScript is preferred in frontend but plain JSX is fine where already used.
- **Docstrings**: every module and public function gets a one-line summary; longer for anything non-obvious.

---

## Branch and commit conventions

- **Main branch**: `main`. Never push directly.
- **Feature branches**: `feat/<short-description>`, e.g. `feat/port-scan-detector`.
- **Fix branches**: `fix/<short-description>`.
- **Docs branches**: `docs/<short-description>`.

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat(detection): add port scan detector with 3s window
fix(dashboard): correct severity color for MEDIUM
docs(architecture): clarify data flow for LLM layer
chore(deps): bump fastapi to 0.115
```

---

## Pull request checklist

Before opening a PR:

- [ ] Tests pass locally (`pytest` and `npm test`).
- [ ] Linters happy (`ruff check`, `npm run lint`).
- [ ] `CHANGELOG.md` updated under `## [Unreleased]`.
- [ ] If the change affects architecture or module boundaries, `ARCHITECTURE.md` updated.
- [ ] If a new phase milestone is complete, `PHASES.md` updated.
- [ ] Screenshot attached for any UI change.

At least one team member reviews. Squash merge into `main`.

---

## Working with the LLM layer

Some notes that would otherwise cost you a Saturday afternoon:

- **Cold-start latency**: Ollama takes a few seconds to load the model on first request. Warm it up with a dummy call at server startup if that matters for demos.
- **Prompt changes**: any change to prompt templates in `ExplainabilityEngine.build_prompt` invalidates cached explanations. Bump a `PROMPT_VERSION` constant and clear the cache.
- **Hallucinations**: the model sometimes invents mitigation steps. We defend against this by giving it a fixed vocabulary of mitigation types in the prompt and post-validating that its response only references those.
- **Timeout**: LLM calls have a 10s timeout. If exceeded, the alert is emitted without an explanation and marked for retry.

---

## Working with the detection engine

- Detectors live in `backend/app/detection/rules/`. Each is a class implementing `check(event, context) -> Optional[Alert]`.
- To add a new detector: create the class, register it in `backend/app/detection/registry.py`, add a test.
- Sliding windows and time-based checks use the shared `Deque`-backed `SlidingWindow` utility. Don't roll your own.
- Threshold constants live in `backend/app/config.py`. Don't hardcode.

---

## Working with the frontend

- Component structure: `frontend/src/components/<Feature>/<Component>.jsx`.
- Global state (alerts, connected status, user session) uses React Context. Feature-local state stays in the component.
- Real-time updates come through a single WebSocket managed by `frontend/src/hooks/useAlertStream.js`. Consume it, don't open your own connection.
- Charts use Recharts (or whatever we standardize on — check `package.json`).

---

## Getting unstuck

- **Ollama returns empty responses**: check the model is pulled (`ollama list`) and the daemon is running.
- **WebSocket disconnects immediately**: the frontend's dev proxy might not be forwarding `ws://`. Check `vite.config.js`.
- **"Address already in use"**: a previous uvicorn didn't shut down. `lsof -i :8000` and kill it.
- **DB migration errors**: `alembic downgrade base && alembic upgrade head` for a clean slate (destroys data).

If none of the above works, ask in the team chat and add the fix here once you find it.
