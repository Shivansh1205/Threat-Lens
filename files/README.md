# ThreatLens

**Explainable and Context-Aware Log-Based Intrusion Detection and Response System**

A real-time cybersecurity monitoring platform that ingests structured logs, detects anomalies using rule-based and behavioral techniques, scores threats dynamically, and explains alerts in analyst-friendly language via an AI assistant.

---

## Why ThreatLens?

Traditional IDS tools depend on static signatures and produce raw, unfiltered alerts — leaving analysts overwhelmed with fatigue and blind to zero-day threats. ThreatLens addresses this with:

- **Real-time detection** on continuously ingested logs (login events, IP activity, port scans, API calls).
- **Behavioral profiling** that builds per-user baselines and flags deviations.
- **Dynamic risk scoring** (0–100) that ranks alerts by severity, so analysts focus on what matters.
- **Explainable AI layer** — every alert comes with a natural-language explanation and suggested mitigation, powered by a local LLM (Ollama + Mistral).
- **Live dashboard** with WebSocket-driven updates, threat trends, high-risk user rankings, and an integrated chatbot.

---

## Architecture at a glance

```
External Sources ──▶ Log Ingestion (FastAPI + Pydantic)
                         │
                         ▼
                  Detection & Behavior Profiling
                  (rules + sliding windows + baselines)
                         │
                         ▼
                  Dynamic Risk Scoring (0–100)
                         │
                         ▼
                  AI & Explainability Layer (Ollama/Mistral)
                         │
                         ▼
             ┌───────────┴───────────┐
             ▼                       ▼
      WebSocket Push          Alert Storage (Postgres)
             │
             ▼
      React + Vite Dashboard  ──▶  Analyst / Admin
```

See `ARCHITECTURE.md` for the full breakdown of layers and modules.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3, FastAPI |
| Database | PostgreSQL 16 (Docker) |
| Frontend | React 18 + Vite 5 |
| Real-time | WebSocket |
| LLM explainability | Ollama running Mistral |
| Validation | Pydantic v2 |
| Migrations | Alembic |
| Testing | pytest + pytest-asyncio |

---

## Prerequisites

- Python 3.11+ (tested on 3.14 on Windows)
- Node.js 18+
- Docker Desktop (for the Postgres container)
- Ollama (optional — only needed for AI explanations and the chatbot)

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/Shivansh1205/Threat-Lens.git ThreatLens
cd ThreatLens
```

### 2. Start the database

```bash
# Pull and run Postgres 16 on port 5433
# (5433 avoids conflicts with any native Postgres installation on 5432)
docker run -d \
  --name threatlens-db \
  -e POSTGRES_PASSWORD=devpass \
  -e POSTGRES_DB=threatlens \
  -p 5433:5432 \
  postgres:16

# Verify it's accepting connections
docker exec threatlens-db pg_isready -U postgres
```

> **Windows note:** use `127.0.0.1` not `localhost` in the DATABASE_URL.
> Windows resolves `localhost` to `::1` (IPv6) which Docker doesn't bind.

If the container already exists but is stopped:

```bash
docker start threatlens-db
```

### 3. Backend setup

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment
cp .env.example .env
```

The `.env` file should contain:

```
DATABASE_URL=postgresql://postgres:devpass@127.0.0.1:5433/threatlens
```

Run database migrations:

```bash
python -m alembic upgrade head
```

### 4. Frontend setup

```bash
cd frontend

# Install dependencies (--legacy-peer-deps required for recharts compatibility)
npm install --legacy-peer-deps

# Copy environment file
cp .env.example .env
```

The `frontend/.env` file should contain:

```
VITE_API_URL=http://localhost:8002
VITE_WS_URL=ws://localhost:8002/ws/alerts
```

### 5. Ollama (optional — AI explanations + chatbot)

```bash
ollama pull mistral
ollama serve
```

---

## Running the app

### Start the backend

```bash
cd backend
python -m uvicorn app.main:app --reload --port 8002
```

> Ports 8000 and 8001 are commonly occupied on Windows. Use `--port 8002`.

API docs available at: `http://localhost:8002/docs`

### Start the frontend

```bash
cd frontend
npm run dev
```

Dashboard available at: `http://localhost:5173`

---

## Running tests

All tests are in `backend/tests/`. Run from the `backend/` directory with the virtual environment active.

```bash
cd backend
```

Run the full test suite:

```bash
python -m pytest
```

Run with verbose output:

```bash
python -m pytest -v
```

Run a specific test file:

```bash
python -m pytest tests/test_detection/test_registry.py -v
python -m pytest tests/test_alerts.py -v
python -m pytest tests/test_alerts_resolve.py -v
python -m pytest tests/test_users_profile.py -v
```

Run a specific test by name:

```bash
python -m pytest -k "test_port_scan_60_events_no_crash_two_alerts" -v
```

Run tests for a specific module group:

```bash
python -m pytest tests/test_detection/ -v
python -m pytest tests/test_scoring/ -v
python -m pytest tests/test_realtime/ -v
```

Run with coverage (if pytest-cov is installed):

```bash
python -m pytest --cov=app --cov-report=term-missing
```

> Tests use SQLite in-memory — no running Postgres or Docker required.

---

## Generating test traffic

Scripts live in `scripts/` and are run from the **repo root**.

### Scenario-based log generator

Sends scripted attack/normal traffic to the backend:

```bash
# Brute force attack (25 failures + 1 success -> 4 alerts)
python scripts/generate_logs.py --scenario brute_force --speed 10 --target-url http://localhost:8002

# Port scan (60 distinct ports -> HIGH + CRITICAL alerts)
python scripts/generate_logs.py --scenario port_scan --speed 10 --target-url http://localhost:8002

# Unusual IP (bootstrap 3 logins, then new IP -> LOW alert)
python scripts/generate_logs.py --scenario unusual_ip --speed 10 --target-url http://localhost:8002

# Normal baseline traffic (no alerts expected)
python scripts/generate_logs.py --scenario normal --speed 10 --target-url http://localhost:8002

# All scenarios combined across distinct users
python scripts/generate_logs.py --scenario mixed --speed 10 --target-url http://localhost:8002
```

`--speed` is a multiplier: `1` = real-time, `10` = 10x faster, `100` = near-instant.

### Flood 10 users (populate the High-Risk Users panel)

Sends 6 login failures + 1 success per user, triggering alerts for all 10:

```bash
python scripts/flood_users.py
```

---

## Useful API endpoints

All endpoints are prefixed with `/api/v1`. Full interactive docs at `/docs`.

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/log` | Ingest a log event |
| `GET` | `/api/v1/alerts` | List alerts (supports `?severity=`, `?resolved=`, `?limit=`) |
| `PATCH` | `/api/v1/alerts/{id}/resolve` | Mark an alert resolved |
| `PATCH` | `/api/v1/alerts/{id}/unresolve` | Unmark resolved |
| `GET` | `/api/v1/users/high-risk` | Users ranked by risk score |
| `GET` | `/api/v1/users/{user_id}/profile` | Full behavioral profile for one user |
| `POST` | `/api/v1/chat` | Send a message to the AI assistant |
| `POST` | `/api/v1/admin/decay` | Manually trigger a risk-score decay pass |
| `GET` | `/health` | Liveness check |
| `WS` | `/ws/alerts` | WebSocket — live alert push |

---

## Project layout

```
ThreatLens/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers (logs, alerts, users, chat, admin, websocket)
│   │   ├── detection/      # Rule-based detectors + registry
│   │   ├── scoring/        # Risk scorer + decay job
│   │   ├── profiling/      # Behavior profiler
│   │   ├── ai/             # Ollama client + explainability
│   │   ├── realtime/       # WebSocket manager
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic schemas
│   │   └── main.py         # App entrypoint + lifespan
│   ├── alembic/            # DB migrations
│   ├── tests/              # pytest test suite
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/     # UI components
│   │   ├── hooks/          # Data-fetching hooks
│   │   ├── pages/          # Dashboard, Alerts, UserAnalytics, Assistant
│   │   ├── context/        # ChatContext
│   │   └── utils/
│   ├── .env.example
│   └── package.json
├── scripts/
│   ├── generate_logs.py    # Scenario-based traffic generator
│   └── flood_users.py      # Multi-user flood for dashboard testing
└── files/
    ├── README.md           # You are here
    ├── ARCHITECTURE.md
    ├── PHASES.md
    └── CHANGELOG.md
```

---

## Team

Final-year major project, Department of CSE, Bangalore Institute of Technology (2025–26).

- **Abhinav Kumar Singh** — 1BI23CS011
- **Anurag Patil** — 1BI23CS034
- **Harshitha M P** — 1BI23CS091
- **Shivansh Bhageria** — 1BI23CS194

**Guide:** Dr. Hemavathi P, Professor, Department of CSE.

---

## License

Academic / educational use only.
