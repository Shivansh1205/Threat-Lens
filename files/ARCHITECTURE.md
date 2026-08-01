# Architecture

This document explains **how ThreatLens is put together and why** — the layers, the data flow, and the key trade-offs. If you're new to the codebase, read this before diving into modules.

---

## Design goals

1. **Real-time by default** — logs stream in, alerts stream out. No batch delay.
2. **Explainable** — every alert answers *why was this flagged?* in plain language.
3. **Modular** — each concern (ingestion, detection, scoring, explanation, presentation) is a separate layer so we can iterate independently.
4. **Analyst-first** — the dashboard, risk ranking, and chatbot exist to reduce alert fatigue, not add to it.

---

## Layered view

```
┌──────────────────────────────────────────────────────────┐
│  1. External Sources                                     │
│     • Web app (frontend + backend)                       │
│     • User activity: logins, API calls, network events   │
│     • External datasets (for training / evaluation)      │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  2. Log Ingestion Layer                                  │
│     • FastAPI `/log` endpoint                            │
│     • Pydantic JSON schema validation                    │
│     • Log parser → structured LogEvent                   │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  3. Detection & Behavioral Profiling                     │
│     • Rule-based detectors (brute force, port scan,      │
│       unusual IP, failed logins)                         │
│     • Behavior profiler (per-user baselines)             │
│     • Isolation Forest for anomaly detection             │
│     • Sliding window + threshold rules                   │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  4. Dynamic Risk Scoring                                 │
│     • Weighted score 0–100                               │
│     • Severity buckets: LOW / MEDIUM / HIGH / CRITICAL   │
│     • Max-heap top-N ranking for the alert feed          │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  5. AI & Explainability Layer                            │
│     • Ollama (Mistral) generates alert explanations      │
│     • Mitigation recommendation engine                   │
│     • Chatbot module (RAG-style, grounded on real alerts)│
└──────────────────────────────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
┌────────────────────────┐   ┌────────────────────────────┐
│  6a. Real-time Push    │   │  6b. Persistence           │
│  • WebSocket manager   │   │  • PostgreSQL              │
│  • Connection tracking │   │  • Logs / Users / Alerts   │
│  • Broadcast to clients│   │  • Profiles                │
└────────────────────────┘   └────────────────────────────┘
              │
              ▼
┌──────────────────────────────────────────────────────────┐
│  7. Presentation Layer (React + Vite)                    │
│     • Live alert feed        • Threat distribution       │
│     • High-risk users        • Chatbot widget            │
│     • Severity breakdown     • Activity trend            │
└──────────────────────────────────────────────────────────┘
```

---

## Data flow: a single log event

A concrete walk-through. A user logs in from an unusual IP:

1. **Ingestion** — the log arrives at `POST /log` as JSON. Pydantic validates the shape (`user_id`, `ip`, `timestamp`, `status`, …). Malformed events are rejected here, never reaching the detection engine.

2. **Enrichment & storage** — the parser extracts the structured `LogEvent`, adds contextual data (geo, session), and persists to PostgreSQL. The event is pushed into a queue for downstream processing.

3. **Behavior profiler updates** — `BehaviorProfiler.get_or_create(user_id)` returns the user's baseline. `update(event)` adjusts login-time patterns and known-IP set. If the IP is not in the user's known set, an unknown-IP flag is raised.

4. **Detection engine runs** — a fan-out of checks executes in the sliding window:
   - `check_brute_force` — 5+ failed logins in 60s?
   - `check_unusual_ip` — IP unseen for this user?
   - `check_port_scan` — 15+ distinct ports in 3s from same source?
   - Each check returns an `Alert` or nothing.

5. **Risk scoring** — the RiskScorer takes the alert + user profile and computes a weighted score in [0, 100]. Score maps to severity: LOW (0–25) / MEDIUM (26–50) / HIGH (51–75) / CRITICAL (76–100).

6. **Explainability** — the ExplainabilityEngine builds a prompt combining the alert, the user's baseline, and recent history. It calls the local Mistral model via Ollama to produce a natural-language explanation and a mitigation checklist.

7. **Distribution** —
   - **AlertManager** writes the enriched alert to Postgres.
   - **WebSocketManager** broadcasts it to every connected dashboard client.
   - The dashboard's alert feed updates without polling.

8. **Analyst interaction** — the analyst can click the alert for details, or ask the chatbot follow-ups ("what's this user's login history?", "how do I mitigate this?"). The chatbot pulls recent alerts as context and calls the LLM.

Total path, ideally: **sub-second** from log arrival to dashboard update.

---

## Component responsibilities

### Ingestion layer

| Component | Responsibility |
|---|---|
| `LogIngestor` | Parse, validate, enrich, and forward raw logs |
| Pydantic models | Enforce schema on every incoming event |
| DB session | Persist structured events for audit and replay |

### Detection & profiling

| Component | Responsibility |
|---|---|
| `DetectionEngine` | Run rule-based + anomaly checks on the event stream |
| `BehaviorProfiler` | Maintain per-user baselines, compute deviation scores |
| Sliding window | Track events within configurable time windows |

### Scoring

| Component | Responsibility |
|---|---|
| `RiskScorer` | Compute weighted 0–100 score per alert |
| Severity labels | Bucket scores into LOW/MEDIUM/HIGH/CRITICAL |
| Top-N heap | Efficiently surface highest-risk alerts and users |

### AI layer

| Component | Responsibility |
|---|---|
| `ExplainabilityEngine` | Build prompts, call LLM, parse responses, cache explanations |
| Mitigation engine | Map detected threat types to recommended actions |
| `ChatbotModule` | Conversational analyst interface, grounded on real alerts |

### Delivery

| Component | Responsibility |
|---|---|
| `AlertManager` | CRUD on alerts, resolution status, notifications |
| `WebSocketManager` | Track connected clients, broadcast in real time |
| Frontend | Render alerts, charts, high-risk users, chatbot |

---

## Data model (high level)

**Logs** — raw ingested events. `user_id`, `ip`, `timestamp`, `status`, `port`, `endpoint`, `country`, session metadata.

**Users** — monitored identities with associated baselines (typical login hours, known IPs, avg session duration).

**Alerts** — detection outputs. Type (brute_force, port_scan, etc.), score, severity, timestamp, linked user/IP, LLM explanation, mitigation steps, resolution status.

**Profiles** — per-user behavioral baselines maintained by `BehaviorProfiler`. Updated with each event via EMA-style decay.

---

## Key data structures (and why they're chosen)

| Structure | Where | Why |
|---|---|---|
| Dictionary / hash map | WebSocketManager, BehaviorProfiler, ChatbotModule | O(1) lookup by client_id / user_id / session_id |
| Sliding window (deque) | DetectionEngine | Fixed-time-window checks; auto-expire old events |
| Set | BehaviorProfiler (known IPs) | O(1) membership check for new-IP detection |
| Max-heap / priority queue | RiskScorer, dashboard top-N | Extract highest-risk alerts without sorting the full list |
| Circular buffer | Live alert feed | Fixed memory for last-N alerts on the dashboard |
| Graph (adjacency map) | Threat correlation layer | Model shared IPs / users to detect coordinated intrusions |

---

## Trade-offs and why we made them

- **Local LLM (Ollama + Mistral) over a hosted API** — keeps the deployment self-contained, avoids sending log data to third parties, and is realistic for on-prem SOC deployments. Cost: slower cold-start, higher local compute needs.
- **Rule-based + ML hybrid** — pure ML would miss known-attack patterns and demand large labeled datasets; pure rules miss zero-days. The hybrid detects both, with ML backing up rules.
- **Sliding windows over batch analysis** — real-time detection needs streaming; batch would be simpler but defeats the purpose.
- **WebSocket over polling** — polling adds latency and load. WebSocket keeps the dashboard live.
- **PostgreSQL over a time-series DB** — for the scale of a project deployment, Postgres is sufficient and simplifies operations. TSDB is a future consideration if we go to real production volumes.
- **APScheduler (in-process) over a real task queue for time-based risk decay** — `BehaviorProfile.user_risk_score` decays two ways: per-alert-event (`RiskScorer.update_user_risk`, immediate, applied whenever a user triggers a new alert) and, now, purely on elapsed wall-clock time (`app/scoring/decay_job.py`'s `run_decay_pass`, exponential — `score * DAILY_DECAY_RATE ** days_elapsed` — so a user flagged once and then quiet for months actually sees their score fall, not just plateau). The two are additive, not double-counting: since the job anchors on `updated_at` and that column resets on every write (including the per-event decay's own commits), a profile touched by a fresh alert sees negligible decay from the scheduled job that same day. A real task queue (Celery, arq) would be overkill for a single-process student-project deployment; APScheduler's `AsyncIOScheduler` is a lightweight, in-process library that hooks directly into the same FastAPI `lifespan` handler already used to capture the event loop for WebSocket broadcasting (Phase 7a), runs the decay pass once on startup plus every `DECAY_JOB_INTERVAL_HOURS` (default 24), and is also exposed on demand via `POST /api/v1/admin/decay-now` for testing and live demonstration.

---

## What this architecture does *not* address (yet)

- **Automated response** (e.g., auto-blocking IPs) — currently the system detects and alerts; the analyst decides the action. Future work.
- **Federated / distributed deployment** — single-node right now. Scaling to multi-node ingestion is a Phase 6+ concern.
- **Model retraining pipeline** — the Isolation Forest and behavior baselines update online, but a formal offline retraining loop with feedback is not in scope for v1.
- **Adversarial robustness** — no explicit defenses against attackers trying to poison the behavior baselines.

---

## References to other docs

- `PHASES.md` — the milestone plan and current status.
- `CONTRIBUTING.md` — how to run, test, and contribute to the modules.
- `CHANGELOG.md` — what's changed release over release.
