# ThreatLens frontend

React 18 and Vite 5 analyst dashboard for ThreatLens. For the complete monitored
portal demonstration, use the root `compose.yaml` and [README](../README.md).

## Local setup

Run the backend on port 8002, then:

```powershell
npm install
Copy-Item .env.example .env
npm run dev
```

On macOS or Linux, use `cp .env.example .env`. The environment file contains:

```dotenv
VITE_API_URL=http://localhost:8002
VITE_WS_URL=ws://localhost:8002/ws/alerts
```

Restart Vite after changing environment variables.

## Commands

```powershell
npm run dev      # development server on http://localhost:5173
npm run build    # production build
npm run preview  # preview the production build
npm run lint     # Oxlint
npm test         # Node utility tests
```

## Application routes

- `/` - system overview and live alert dashboard
- `/threat-feed` - filterable threat analytics
- `/alerts` - alert list and resolution workflow
- `/users` - high-risk ranking and behavior profiles
- `/assistant` - alert-grounded AI assistant
- `/reports` - filtered CSV reports
- `/settings` - theme and protected detector limits

The dashboard uses REST requests for authoritative state and `/ws/alerts` for live
alert updates. If the connection indicator is disconnected, confirm the backend
URL, WebSocket URL, and CORS configuration.
