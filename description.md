# ThreatLens project description

ThreatLens is a real-time security-monitoring prototype focused on explainable,
context-aware detection. It demonstrates the complete path from activity on a
monitored website to an actionable alert: collection, validation, behavioral
profiling, rule evaluation, risk scoring, storage, live delivery, reporting, and
optional natural-language explanation.

## System scope

The default demonstration runs seven Compose services:

1. `monitored-nginx` exposes a generic portal on `127.0.0.1:8080` and writes one
   structured JSON access-log record per request.
2. `demo-site` serves the React ShopSphere portal and its bounded security scenarios.
3. `collector` tails the Nginx log, transforms records into ThreatLens events,
   batches them, and sends them to the backend using an ingestion API key.
4. `backend` provides the FastAPI ingestion, detection, analytics, reporting,
   administration, WebSocket, and chat APIs on `127.0.0.1:8002`.
5. `postgres` stores events, alerts, users, behavior profiles, monitoring-source
   state, and persisted detection-setting overrides.
6. `dashboard` serves the React analyst interface on `127.0.0.1:5173`.
7. `ollama` is an optional profile service that runs Mistral for explanations and
   chat responses.

Page and asset requests pass through Nginx and the collector. The portal's
storefront, authentication, background-traffic, and security-scenario actions send
structured events directly to the backend's single-event ingestion endpoint.

## Event lifecycle

For each accepted event, the backend:

1. Validates the Pydantic input schema and timestamp bounds.
2. Upserts the associated user and persists the event.
3. Loads or creates the user's behavioral profile.
4. Computes deviation against the profile before mutating it with the new event.
5. Runs the detector registry with one immutable snapshot of active thresholds.
6. Adjusts detector scores using behavioral deviation and updates rolling user risk.
7. Updates the profile, commits the transaction, and broadcasts new alerts.
8. Schedules optional explanation generation in a background task.

Running detection before folding the event into the baseline is important. If a
new IP were stored first, the unusual-IP detector would incorrectly see it as
already known.

## Inputs

ThreatLens supports two ingestion paths:

- `POST /api/v1/log` accepts individual structured events for direct integrations
  and the scenario generator.
- `POST /api/v1/events/batch` accepts authenticated, idempotent batches from the
  collector. Source heartbeats expose delivery status and counters in the dashboard.

The collector deliberately minimizes stored web data. It removes query strings,
maps known authenticated usernames when Nginx supplies them, and derives stable
anonymous visitor identifiers with an HMAC secret rather than storing raw visitor
addresses as user IDs. Its checkpoint advances only after successful delivery.

## Detection and profiling

The active detector registry implements:

- Brute force: escalating thresholds for failures by user within a sliding window,
  plus a critical alert when a success follows an active failure sequence.
- Port scan: distinct destination ports by source IP within a short window.
- Unusual IP: a new login address after the user's bootstrap baseline.
- Request flood: request count by web identity within a window.
- Path probe: distinct HTTP 404 paths by web identity within a window.
- Server-error spike: repeated HTTP 5xx responses within a window.

Sliding-window state is held in memory and protected for concurrent requests.
Behavior profiles and unusual-IP baselines are stored in PostgreSQL and survive
backend restarts. There is no trained machine-learning or Isolation Forest model in
the current implementation; behavioral anomaly context comes from explicit,
auditable profile features and exponential moving averages.

Administrators can manage every window and threshold from the dashboard. The
backend validates threshold ordering, stores overrides in the database, swaps the
active settings atomically, and clears detector windows after a change. Environment
settings remain the source of defaults.

## Risk scoring

Each alert preserves two views:

- `raw_score` and `raw_severity` record the detector's original assessment.
- `score` and `severity` contain the context-adjusted result.

Behavioral deviation increases a score within its remaining headroom up to 100.
Alerts also contribute to a rolling `user_risk_score`, which drives the high-risk
user ranking. An APScheduler job applies elapsed-time decay on startup and at the
configured interval; administrators can trigger the same decay pass through the
protected API.

## Explainability and assistant

When Ollama is enabled, the explanation engine prompts Mistral with the alert,
triggering event, raw and adjusted risk, and user context. It accepts only
mitigations drawn from a fixed vocabulary. Generation runs after ingestion so a
slow or unavailable model cannot prevent event storage or alert delivery.

The assistant retrieves recent alerts as context and keeps a bounded conversation
history in backend memory. It returns an explicit availability fallback if Ollama
cannot answer. Explanations that fail are left empty; the current implementation
does not provide a durable retry queue.

## Analyst experience

The dashboard offers overview metrics, live connection state, source health,
severity and activity visualizations, a threat feed, alert resolution, user
profiles, high-risk rankings, filtered CSV reports, detector configuration, theme
selection, and an alert-grounded assistant. Alerts arrive through `/ws/alerts`,
while REST queries remain the authoritative source for page loads and filtered data.

## Security and deployment boundaries

ThreatLens is an academic prototype, not a production SIEM or network IDS.

- Compose ports are loopback-only and default secrets are strictly for local use.
- Collector and admin routes use separate API keys; the demo portal credentials are
  intentionally public.
- The single-backend topology is required for consistent detector windows and chat
  history. Multiple replicas would need a shared state service.
- Nginx access logs cannot inspect request bodies, encrypted traffic before
  termination, or packets that never reach Nginx.
- Automated blocking or remediation is not implemented; analyst actions remain
  advisory and manual.

## Technology

- Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy, Alembic, and APScheduler
- PostgreSQL 16 in the demonstration stack; SQLite-backed backend tests
- React 18, React Router, Vite 5, Tailwind CSS, Recharts, and Lucide
- Nginx JSON access logs and a dependency-free Python collector
- Optional Ollama with Mistral
- pytest, Ruff, Black, Node's test runner, and Oxlint

Use [README.md](README.md) for setup and operation, and
[files/ARCHITECTURE.md](files/ARCHITECTURE.md) for module boundaries and design
trade-offs.
