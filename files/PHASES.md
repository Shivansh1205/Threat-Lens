# Phases

ThreatLens is being built as a sequence of milestones — each one has to exist before the next makes sense. This doc is capability-oriented (what has to work) rather than date-oriented; the Gantt in the report is the calendar view.

For each phase: **goal**, **exit criteria** (how we know it's done), **out of scope**, **open questions**.

---

## Phase 1 — Foundation & requirements

**Goal:** decide what we're building and why.

**Exit criteria**
- Problem statement locked.
- Literature survey (12 papers) documented with contributions and limitations.
- SRS complete: functional + non-functional + domain requirements.
- Team roles agreed.

**Out of scope**
- Any code. This phase is pure specification.

**Status:** Done (Jan–Mar).

---

## Phase 2 — Skeleton pipeline end-to-end

**Goal:** get a single log event to flow through *every* layer, even if each layer is a stub. Prove the shape of the system before optimizing any part.

**Exit criteria**
- FastAPI backend up with `POST /log` and `GET /alerts`.
- Postgres schema created for logs, users, alerts.
- One trivial detector (e.g., "any failed login is an alert") wired in.
- Alert written to DB and returned via GET.
- React dashboard renders the alerts list (no styling required).

**Out of scope**
- Real detection logic — just enough to prove data flows.
- Behavior profiling, risk scoring, LLM, WebSockets.

**Open questions**
- Do we need a message queue between ingest and detection, or is direct call fine for our volumes? *(Answer for now: direct call. Revisit if latency becomes an issue.)*

---

## Phase 3 — Real detection engine

**Goal:** replace the stub detector with the actual rule set + behavioral profiling.

**Exit criteria**
- Brute-force detection (5 failed logins / 60s) works on synthetic data.
- Port scan detection (15+ ports / 3s) works on synthetic data.
- Unusual-IP detection triggers when a user logs in from an IP not in their known set.
- `BehaviorProfiler` maintains per-user baselines: login-time distribution, known IPs, session duration.
- Sliding window and set membership operations verified.

**Out of scope**
- Risk scoring math (Phase 4).
- LLM explanations (Phase 5).
- Real datasets — synthetic log generators are enough here.

**Open questions**
- How do we bootstrap a user baseline for their *first* login? *(Cold-start problem — currently defaulting to "trust and observe" for the first N events.)*
- What's the right sliding window size for port scan? Current 3s is a guess.

---

## Phase 4 — Dynamic risk scoring

**Goal:** every alert gets a defensible 0–100 score, and the dashboard can rank them.

**Exit criteria**
- Weighted scoring algorithm implemented — combines detection severity, behavioral deviation, historical context.
- Severity buckets: LOW (0–25) / MEDIUM (26–50) / HIGH (51–75) / CRITICAL (76–100).
- Top-N alerts extractable via max-heap.
- Manual test cases: brute force from unknown IP scores CRITICAL; single failed login scores LOW.

**Out of scope**
- Feedback loop for weight adjustment — the algorithm is static in v1.
- ML-learned scoring — the "ML-based scoring" is currently a weighted heuristic; a trained model can come later.

**Open questions**
- Should the weights be configurable per organization, or fixed? *(Leaning: fixed for v1, configurable later.)*

**Implementation note:** elapsed-time decay is complete. An in-process APScheduler
runs `app/scoring/decay_job.py` on startup and at the configured interval, and
administrators can trigger a pass through `POST /api/v1/admin/decay-now`.
Per-alert `USER_RISK_DECAY_FACTOR` and elapsed-time `DAILY_DECAY_RATE` remain
complementary mechanisms.

---

## Phase 5 — AI-assisted explainability

**Goal:** every alert comes with a natural-language explanation and a mitigation checklist. Analysts can query a chatbot for follow-ups.

**Exit criteria**
- Ollama running locally with Mistral.
- `ExplainabilityEngine.build_prompt` takes an alert + user profile and produces a well-formed prompt.
- LLM response parsed into structured `{explanation, mitigation_steps}`.
- Explanations cached per `alert_id` to avoid re-calling the model.
- Chatbot answers questions grounded on recent alerts (retrieval-augmented context).

**Out of scope**
- Fine-tuning Mistral on security data — using it zero-shot for v1.
- Multi-turn memory beyond the current session.

**Open questions**
- Latency budget for LLM calls — target under 3s per alert. Currently unmeasured against a real Ollama instance — all automated tests mock the LLM boundary, by design (see below), so this needs a manual pass with Ollama actually running.
- Fallback behavior when Ollama is down? *(Resolved: explanation/mitigation_steps stay NULL — no "pending" placeholder state was added. The alert is fully usable without an explanation; GET /api/v1/alerts just shows null fields until/unless a later Ollama call succeeds. No retry loop exists yet — see follow-up below.)*

**Implementation notes (this diverges slightly from "cached per alert_id to avoid re-calling the model" above — worth flagging):** explanations are not "cached" in the sense of a cache with eviction/invalidation; they're generated exactly once, opportunistically, via a `BackgroundTasks` job scheduled at ingestion time (`POST /api/v1/log` schedules `generate_explanation_task`, never calls the LLM inline — see `app/api/logs.py` and `app/ai/explainability.py`). If that one attempt fails (Ollama down, timeout, unparseable response), the alert simply stays unexplained forever — there is no retry, scheduled or otherwise. A TODO in `explainability.py` flags retry-with-backoff as a future improvement; a real task queue (Celery/arq) would be the natural place to add it, rather than bolting retry logic onto `BackgroundTasks`.

**Follow-up (flagged, not built):** no retry logic for failed/timed-out explanation generation. A transient Ollama hiccup at the moment an alert is created means that alert never gets an explanation unless something re-triggers generation manually. Named as a Phase 6.5+/task-queue follow-up.

---

## Phase 6 — Live dashboard & WebSocket delivery

**Goal:** the analyst-facing UI is real, live, and useful. No manual refresh.

**Exit criteria**
- WebSocket connection from browser to backend; disconnects handled cleanly.
- Alert feed updates in real time.
- Threat activity trend chart (time series).
- Severity breakdown (pie / donut chart).
- High-risk users ranked list.
- Chatbot widget integrated.
- Search bar for threats / users / IPs.
- All matches the mockups (see Figure 4.11 in the report).

**Out of scope**
- User authentication & authorization (Phase 7).
- Configurable dashboards / saved views.

**Open questions**
- How many concurrent dashboard clients do we design for? A handful is realistic for a demo; enterprise scale isn't v1.

---

## Phase 7 — Auth, hardening, and admin controls

**Goal:** the platform is safe to demo and usable by more than one persona.

**Exit criteria**
- Admin login with hashed credentials.
- Role separation (admin vs. analyst) if we go that route.
- Detection threshold configuration surface (per the SRS "configure thresholds" use case).
- Alert resolution workflow (mark resolved, add notes).
- Basic rate limiting on `/log` and `/chat` endpoints.

**Out of scope**
- SSO, MFA — nice-to-haves for a real deployment, not for the project scope.

**Open questions**
- Do we ship with a hardcoded admin user for the demo, or a proper user table? *(Leaning: seeded admin for demo; user table stub for extensibility.)*

---

## Phase 8 — Evaluation & documentation

**Goal:** prove the system works and hand it in.

**Exit criteria**
- Test dataset assembled: mix of synthetic normal + attack traffic.
- Metrics recorded: detection rate, false positive rate, alert-to-explanation latency, dashboard update latency.
- Comparison table against baseline (e.g., rules-only) showing the value of the behavioral + AI layers.
- Screenshots and diagrams for the final report.
- Video demo of an end-to-end scenario.
- All code documented; README + this doc + architecture doc are up to date.

**Out of scope**
- Publishing to open source, packaging as a product.

---

## Beyond v1 (post-submission ideas)

Not part of the project, but worth capturing so we don't lose them:

- **Automated response** — auto-block IPs after CRITICAL alerts, with a manual override.
- **Predictive threat analysis** — model future attack likelihood from current trends.
- **Multi-tenant / SaaS** — one deployment, many organizations.
- **Federated deployment** — collectors at edges, central detection.
- **Feedback loop for scoring weights** — analyst thumbs-up / thumbs-down updates the model.
- **Additional data sources** — SIEM integrations (Splunk, Elastic), cloud audit logs (AWS CloudTrail, GCP Audit).

---

## Current position

The end-to-end demonstration now covers the roadmap's core implementation and
dashboard goals: structured and Nginx-log ingestion, persistent behavior profiles,
rule-based detection, contextual scoring, scheduled risk decay, background AI
explanations, WebSocket delivery, alert resolution, user analytics, reports, and
runtime detector administration.

The repository also includes a monitored Flask portal, Nginx reverse proxy,
durable checkpointing collector, source-health telemetry, web-specific detectors,
and a Docker Compose topology for a reproducible local demonstration.

Remaining Phase 7/8 work is primarily production hardening and formal evaluation.
Known engineering follow-ups include durable retry for failed explanations, shared
detector/chat state for multiple backend replicas, broader authentication and role
authorization, CI packaging, and measured accuracy/latency evaluation on documented
datasets. Automated response remains outside the current implementation.
