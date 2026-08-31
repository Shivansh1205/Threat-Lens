# ShopSphere demo portal

ShopSphere is the React/Vite demo application for ThreatLens. It simulates
e-commerce, authentication, background traffic, and bounded security scenarios,
then sends structured events to the ThreatLens ingestion API.

## Local development

```powershell
Copy-Item .env.example .env
npm install
npm run dev
```

Open <http://localhost:5174>. The default backend URL is
<http://localhost:8002>; override it with `VITE_THREATLENS_URL` when needed.

Validate changes with:

```powershell
npm run lint
npm run build
```

The production image serves the SPA and `/health` on port `8080`.
