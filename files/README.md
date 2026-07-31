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
                  (rules + Isolation Forest + baselines)
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
| Database | PostgreSQL |
| Frontend | React + Vite |
| Real-time | WebSocket |
| ML / anomaly detection | scikit-learn (Isolation Forest, K-Means baselines) |
| LLM explainability | Ollama running Mistral |
| Validation | Pydantic (JSON schemas) |

---

## Getting started

> Detailed setup lives in `CONTRIBUTING.md`. Quick version below.

```bash
# 1. Clone
git clone <repo-url> threatlens && cd threatlens

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # fill in DB URL, Ollama host, etc.
uvicorn app.main:app --reload

# 3. Frontend
cd ../frontend
npm install
npm run dev

# 4. Ollama (for the explainability engine)
ollama pull mistral
ollama serve
```

Then open `http://localhost:5173` for the dashboard and `http://localhost:8000/docs` for the API.

---

## Project layout

```
threatlens/
├── backend/              # FastAPI app, detection engine, risk scoring, LLM layer
├── frontend/             # React + Vite dashboard
├── docs/                 # Design docs, diagrams
├── scripts/              # Log generators, seed data, dev utilities
├── ARCHITECTURE.md       # System design and data flow
├── PHASES.md             # Milestone-based build plan
├── CONTRIBUTING.md       # Dev setup and conventions
├── CHANGELOG.md          # Versioned change log
└── README.md             # You are here
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

To be added. Default assumption: academic / educational use only until a formal license is chosen.
