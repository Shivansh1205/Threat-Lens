# ThreatLens Run Commands

Run these commands from the repository root:

```powershell
cd C:\Users\abhin\Desktop\Projects\Threat-Lens
```

## First-time setup

Start Docker Desktop, then create the local environment file if it does not
already exist:

```powershell
Start-Process -FilePath 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
Copy-Item .env.example .env
```

For anything other than a local demo, replace the placeholder secrets in
`.env` before starting the services.

## Start the project

Build the images and start the complete stack in the background:

```powershell
docker compose up --build -d
```

Open the project:

- Dashboard: <http://localhost:5173>
- Demo portal: <http://localhost:8080>
- Security scenarios: open the **Security Scenarios** tab in the demo portal
- API documentation: <http://localhost:8002/docs>

The portal accepts any account name. Passwords of at least six characters succeed
in its demo authentication form.

## Check status and logs

```powershell
docker compose ps
docker compose logs -f collector backend monitored-nginx
```

Press `Ctrl+C` to stop following logs. This does not stop the services.

## Generate demo attacks

```powershell
python scripts/generate_logs.py --scenario brute_force --speed 10
python scripts/generate_logs.py --scenario port_scan --speed 10
python scripts/generate_logs.py --scenario unusual_ip --speed 10
python scripts/generate_logs.py --scenario mixed --speed 10
```

## Optional Groq administrator analysis

```powershell
Set `LLM_API_KEY` in the root `.env`, then restart the stack. The assistant is
read-only, requires `ADMIN_API_KEY`, and sends targeted evidence to Groq only
when an administrator submits a chat question. The provider URL and model can
be changed through `LLM_BASE_URL` and `LLM_MODEL`.
```

## Stop or restart

Stop the services while preserving their data:

```powershell
docker compose down
```

Restart the stack:

```powershell
docker compose up -d
```

Rebuild after source-code changes:

```powershell
docker compose up --build -d
```

## Reset all project data

The following command stops the stack and permanently deletes its database,
logs, and collector checkpoint:

```powershell
docker compose down -v
```
