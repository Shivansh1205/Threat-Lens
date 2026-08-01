# ThreatLens — Frontend

React 18 + Vite 5 dashboard for the ThreatLens intrusion detection platform.

## Setup

```bash
# Install dependencies
npm install --legacy-peer-deps

# Copy environment file and set backend URL
cp .env.example .env
```

`.env` must contain:

```
VITE_API_URL=http://localhost:8002
VITE_WS_URL=ws://localhost:8002/ws/alerts
```

> Vite does NOT hot-reload `.env` changes. Restart `npm run dev` after editing it.

## Commands

```bash
# Start dev server (http://localhost:5173)
npm run dev

# Production build
npm run build

# Preview production build locally
npm run preview

# Lint
npm run lint
```

## Notes

- The dashboard connects to the backend WebSocket at `VITE_WS_URL` for live alert push.
- If the connection status shows "Disconnected", check that the backend is running on the correct port.
- The High-Risk Users panel only shows users who have triggered at least one alert (risk score > 0).
  Run `python scripts/flood_users.py` from the repo root to populate it with test data.
