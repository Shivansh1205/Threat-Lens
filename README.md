# ThreatLens

ThreatLens is an explainable, context-aware intrusion detection and response
prototype. It collects structured application and Nginx access logs, detects
suspicious behavior in real time, scores alerts using user context, and presents
the results in a live analyst dashboard.

The repository includes a complete local demonstration: a monitored web portal,
Nginx reverse proxy, durable log collector, FastAPI detection backend, PostgreSQL,
React dashboard, and an optional Ollama/Mistral explanation layer.

## What it detects

- Brute-force login attempts and a successful login after repeated failures
- Port scans in directly ingested network events
- Logins from unusual IP addresses after a user baseline is established
- Excessive HTTP request rates
- Probing of many distinct missing paths
- Repeated HTTP 5xx responses

Detector windows and thresholds can be changed at runtime from the Settings page.
Overrides are validated, persisted in PostgreSQL, and applied without restarting
the stack.

## Quick start

### Prerequisites

- Docker Desktop with Docker Compose
- Python 3.11+ only if you want to run the traffic scripts or backend tests
- Node.js 18+ only for standalone frontend development

Copy the environment template and start the stack:

```powershell
Copy-Item .env.example .env
docker compose up --build -d
```

On macOS or Linux, use `cp .env.example .env` instead of `Copy-Item`.

Open:

| Service | URL |
|---|---|
| ThreatLens dashboard | <http://localhost:5173> |
| Monitored demo portal | <http://localhost:8080> |
| Attack Lab | <http://localhost:8080/demo-controls> |
| API documentation | <http://localhost:8002/docs> |

Demo portal accounts:

| Role | Username | Password |
|---|---|---|
| Member | `alice` | `demo123` |
| Administrator | `admin` | `admin123` |

All published ports bind to `127.0.0.1`. The default credentials and secrets are
for a local demonstration only. Replace every value in `.env` before using the
stack on a shared machine.

Check service health and follow logs with:

```powershell
docker compose ps
docker compose logs -f collector backend monitored-nginx
```

See [RUN_COMMANDS.md](RUN_COMMANDS.md) for the short operations reference.

## Generate monitored traffic

The Attack Lab buttons and `scripts/demo_attacks.py` send bounded HTTP scenarios
through Nginx. They do not insert events or alerts directly.

```powershell
python scripts/demo_attacks.py brute
python scripts/demo_attacks.py flood
python scripts/demo_attacks.py probe
python scripts/demo_attacks.py errors
python scripts/demo_attacks.py combined
```

The older structured-event generator is still useful for exercising login,
port-scan, and unusual-IP detectors directly through the backend API:

```powershell
python scripts/generate_logs.py --scenario mixed --speed 10 --target-url http://localhost:8002
```

Only run the supplied scenarios against systems you own or are authorized to
test. Their default targets are local services.

## Optional AI explanations

Detection, scoring, reporting, and the dashboard work without a language model.
To enable alert explanations and the assistant with the Compose-managed Ollama
service:

```powershell
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull mistral
```

Recent alerts can temporarily show no explanation while the background request is
running. If Ollama is unavailable or times out, ingestion continues and the
assistant returns an availability message.

## Detection settings

Open <http://localhost:5173/settings>, enter the `ADMIN_API_KEY` from the root
`.env`, and unlock **Detection Limits**. The key is held in browser session
storage, so it must be entered again in a new browser session.

Saving settings clears active in-memory detector windows to avoid interpreting old
events under new limits. **Restore defaults** removes the database override and
reloads the environment defaults from `backend/.env.example`.

## Architecture

```text
Browser -> monitored Nginx -> demo portal
              |
              v
        JSON access log -> collector -> authenticated batch API
                                           |
Direct structured events ------------------+
                                           v
                              validate and persist event
                                           |
                              profile -> detect -> score
                                           |
                              PostgreSQL alerts and metrics
                                  |                  |
                           WebSocket updates    background AI
                                  |
                                  v
                             React dashboard
```

The collector checkpoints only records accepted by the backend, retries temporary
failures, handles log rotation, removes query strings, and replaces anonymous
visitor IPs with keyed hashes. Nginx access logs cannot reveal request bodies,
application failures hidden behind HTTP 200 responses, or network traffic that
never reaches the proxy.

Detector windows and chat history are process-local. The current Compose topology
runs one backend instance; scaling it horizontally would require shared state such
as Redis.

For component responsibilities and the event lifecycle, see
[Architecture](files/ARCHITECTURE.md). A more detailed implementation narrative is
available in [description.md](description.md).

## Dashboard

The React application includes:

- Overview metrics, severity breakdowns, activity charts, source health, and live alerts
- Filterable Threat Feed and Alerts pages
- Per-user behavioral analytics and risk rankings
- CSV report generation with time, severity, type, and resolution filters
- Runtime detection settings protected by the admin API key
- A shared AI assistant conversation and light/dark themes

## API overview

REST endpoints are under `/api/v1`; the WebSocket and health routes are not.
Interactive request and response schemas are available at `/docs`.

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/log` | Ingest one structured event |
| `POST` | `/api/v1/events/batch` | Idempotent collector ingestion (`X-ThreatLens-Key`) |
| `POST` | `/api/v1/sources/{source_id}/heartbeat` | Update collector health and counters |
| `GET` | `/api/v1/sources` | List monitoring-source status |
| `GET` | `/api/v1/alerts` | Filter and list alerts |
| `PATCH` | `/api/v1/alerts/{id}/resolve` | Resolve an alert |
| `PATCH` | `/api/v1/alerts/{id}/unresolve` | Reopen an alert |
| `GET` | `/api/v1/users/high-risk` | Rank users by rolling risk |
| `GET` | `/api/v1/users/{user_id}/profile` | Read a behavioral profile |
| `GET` | `/api/v1/metrics/summary` | Read dashboard totals |
| `GET` | `/api/v1/metrics/activity` | Read alert activity buckets |
| `GET` | `/api/v1/metrics/threats` | Read filtered threat analytics |
| `GET` | `/api/v1/reports/alerts.csv` | Download a filtered alert report |
| `POST` | `/api/v1/chat` | Ask the alert-grounded assistant |
| `GET/PUT/DELETE` | `/api/v1/admin/detection-settings` | Manage detector limits (`X-ThreatLens-Admin-Key`) |
| `POST` | `/api/v1/admin/decay-now` | Run risk decay (`X-ThreatLens-Admin-Key`) |
| `GET` | `/health` | Backend liveness |
| `WS` | `/ws/alerts` | Live alert stream |

## Development and tests

The fastest validation path does not require a running PostgreSQL instance because
backend tests use SQLite databases created by the test fixtures.

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pytest
python -m ruff check .
```

On macOS or Linux, activate with `source .venv/bin/activate`.

Frontend validation:

```powershell
cd frontend
npm install
npm test
npm run lint
npm run build
```

Collector and demo-site tests:

```powershell
python -m pytest collector/test_collector.py demo_site/test_app.py
```

For local development workflows and contribution conventions, see
[Contributing](files/CONTRIBUTING.md).

## Project layout

```text
backend/       FastAPI API, detectors, profiling, scoring, AI, and migrations
collector/     Durable Nginx JSON-log tailer and authenticated batch client
demo_site/     Safe Flask portal and browser-based Attack Lab
frontend/      React 18 and Vite dashboard
nginx/         Reverse-proxy and structured access-log configuration
scripts/       Monitored HTTP and direct structured-event generators
files/         Architecture, roadmap, changelog, and contribution docs
compose.yaml   Complete local demonstration topology
```

## Data reset

```powershell
docker compose down
```

This stops services and preserves data. The following command also permanently
deletes the PostgreSQL, Nginx log, collector checkpoint, and Ollama volumes:

```powershell
docker compose down -v
```

## Team and license

Final-year major project, Department of CSE, Bangalore Institute of Technology
(2025-26).

- Abhinav Kumar Singh - 1BI23CS011
- Anurag Patil - 1BI23CS034
- Harshitha M P - 1BI23CS091
- Shivansh Bhageria - 1BI23CS194

Guide: Dr. Hemavathi P, Professor, Department of CSE.

Academic and educational use only. No separate open-source license is currently
included in the repository.
