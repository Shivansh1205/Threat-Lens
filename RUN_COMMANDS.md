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
- Attack Lab: <http://localhost:8080/demo-controls>
- API documentation: <http://localhost:8002/docs>

Demo accounts:

- Member: `alice` / `demo123`
- Administrator: `admin` / `admin123`

## Check status and logs

```powershell
docker compose ps
docker compose logs -f collector backend monitored-nginx
```

Press `Ctrl+C` to stop following logs. This does not stop the services.

## Generate demo attacks

```powershell
python scripts/demo_attacks.py brute
python scripts/demo_attacks.py flood
python scripts/demo_attacks.py probe
python scripts/demo_attacks.py errors
python scripts/demo_attacks.py combined
```

## Optional local AI model

```powershell
docker compose --profile ai up -d ollama
docker compose exec ollama ollama pull mistral
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
logs, collector checkpoint, and optional Ollama model volume:

```powershell
docker compose down -v
```
