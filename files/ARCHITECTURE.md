# Architecture

ThreatLens is a single-backend security-monitoring prototype. This document
describes the current implementation; the root [README](../README.md) contains the
setup and operations guide.

## Runtime topology

```text
client
  |
  v
monitored-nginx ---> demo-site
  |
  +-- JSON access log --> collector -- authenticated batches --+
                                                               |
structured integrations -------- POST /api/v1/log -------------+
                                                               v
                                                         FastAPI backend
                                                        /       |       \
                                               PostgreSQL   WebSocket   Ollama
                                                   |           |       optional
                                                   +-----------+
                                                               v
                                                        React dashboard
```

The Compose file runs PostgreSQL, backend, dashboard, demo portal, Nginx, and
collector services. Ollama is opt-in through the `ai` profile. Published ports are
bound to loopback.

## Components

### Monitored portal and Nginx

`demo_site/` is a generic Flask portal with deterministic, bounded Attack Lab
actions. `nginx/nginx.conf` proxies the portal and emits structured JSON access
logs. The Attack Lab produces real HTTP activity; it has no path to the alerts
table or detection engine.

### Collector

`collector/collector.py` tails the Nginx log and maps HTTP records to the common
event schema. It batches events, authenticates with `X-ThreatLens-Key`, checkpoints
only accepted records, retries temporary failures, handles log rotation, removes
query strings, derives HMAC-based anonymous IDs, and sends source heartbeats.

### Backend API

`backend/app/main.py` creates the FastAPI app, registers REST routers under
`/api/v1`, registers `/ws/alerts` and `/health`, initializes detector settings,
captures the serving event loop for broadcasts, and manages risk decay.

| Module | Responsibility |
|---|---|
| `api/logs.py` | Single-event ingestion and processing pipeline |
| `api/collector.py` | Authenticated batch ingestion and heartbeats |
| `api/alerts.py` | Alert queries and resolution state |
| `api/users.py` | Risk ranking and behavior profiles |
| `api/metrics.py` | Summary, activity, and threat analytics |
| `api/reports.py` | Filtered CSV export |
| `api/sources.py` | Monitoring-source health |
| `api/admin.py` | Protected settings and manual risk decay |
| `api/chat.py` | Alert-grounded assistant |
| `api/websocket.py` | Live alert connections |

### Detection, profiling, and scoring

`detection/registry.py` owns brute-force, port-scan, unusual-IP, request-flood,
path-probe, and server-error-spike rules. Detectors return candidates rather than
writing database rows. Count rules use event-time sliding windows protected by
locks because synchronous handlers can execute concurrently.

`profiling/profiler.py` maintains persistent per-user baselines with exponential
moving averages and known IP addresses. No trained ML model is active.

`scoring/risk_scorer.py` preserves each raw assessment, adjusts its final score
with behavioral deviation, and updates rolling user risk. `scoring/decay_job.py`
applies elapsed-time decay independently of new alerts.

### AI and dashboard

`ai/explainability.py` validates model mitigations against a fixed vocabulary.
Background tasks call Ollama after ingestion commits, so model failure cannot roll
back alerts. `ai/chatbot.py` retrieves recent alerts and keeps bounded,
process-local conversation history.

`frontend/src/App.jsx` defines Dashboard, Threat Feed, Alerts, User Analytics,
Assistant, Reports, and Settings routes. REST queries load authoritative state and
the alert WebSocket supplies live updates.

## Event transaction

Single-event and collector ingestion converge on the same processing function:

1. Validate the event and timestamp.
2. Upsert the user and persist the event.
3. Load or create the behavior profile.
4. Compute deviation using the pre-event baseline.
5. Snapshot thresholds and run all rules.
6. Score candidates, create alerts, and update user risk.
7. Mutate the behavior profile with the event.
8. Commit the event, profile, and alerts together.
9. Schedule WebSocket delivery and optional explanations.

The ordering prevents a novel IP from joining the baseline before the unusual-IP
rule evaluates it. Collector batches use source and external-event identifiers for
idempotent redelivery.

## Persistence and state

PostgreSQL stores users, log events, alerts, behavior profiles, monitoring sources,
and the active detection-settings override. Alembic migrations define schema
evolution.

Detector windows, WebSocket connections, assistant history, and the scheduler are
process-local. This is appropriate for the one-backend Compose deployment;
horizontal scaling would require shared state and an external scheduler or queue.

## Security boundaries

- Collector endpoints require `INGEST_API_KEY` in `X-ThreatLens-Key`.
- Administrative endpoints require `ADMIN_API_KEY` in
  `X-ThreatLens-Admin-Key`.
- Anonymous web identities use `IP_HASH_SECRET`; query strings are discarded.
- CSV export neutralizes formula-like spreadsheet cells.
- CORS origins and detection defaults are environment-configurable.
- Compose defaults and demo credentials are not production credentials.

## Known limitations

- It monitors application and access-log events, not raw network packets.
- Access logs cannot inspect request bodies or failures returned as HTTP 2xx.
- In-memory detector state is lost on backend restart.
- Failed AI explanations have no durable retry queue.
- Assistant history is ephemeral and is not an audit record.
- Automated response and multi-tenant authorization are outside the current scope.
