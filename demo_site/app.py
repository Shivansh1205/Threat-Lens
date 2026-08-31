"""A safe, deliberately observable portal for the ThreatLens demo."""

import hashlib
import hmac
import os
import re
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.middleware.sessions import SessionMiddleware

BASE = Path(__file__).parent
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"
SESSION_SECRET = os.getenv("PORTAL_SESSION_SECRET", "local-demo-change-me")
env = Environment(
    loader=FileSystemLoader(BASE / "templates"), autoescape=select_autoescape()
)


def password_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode(), salt.encode(), 120_000
    ).hex()


USERS = {
    "alice": {
        "salt": "alice-demo",
        "hash": password_hash("demo123", "alice-demo"),
        "role": "user",
    },
    "admin": {
        "salt": "admin-demo",
        "hash": password_hash("admin123", "admin-demo"),
        "role": "admin",
    },
}

app = FastAPI(title="ThreatLens Demo Portal", docs_url=None, redoc_url=None)
app.add_middleware(
    SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=False
)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")


def safe_next_path(value: str | None, default: str = "/profile") -> str:
    """Allow redirects only to a local absolute path."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return default
    return value


@app.middleware("http")
async def attach_monitored_identity(request: Request, call_next):
    """Expose the authenticated identity to Nginx for every response status."""
    response = await call_next(request)
    user = request.scope.get("session", {}).get("user")
    if user and "X-ThreatLens-User" not in response.headers:
        response.headers["X-ThreatLens-User"] = user
    return response


def render(
    name: str, request: Request, status_code: int = 200, **context
) -> HTMLResponse:
    user = request.session.get("user")
    body = env.get_template(name).render(
        request=request,
        user=user,
        demo_mode=DEMO_MODE,
        demo_users=sorted(USERS),
        **context,
    )
    response = HTMLResponse(body, status_code=status_code)
    if user:
        response.headers["X-ThreatLens-User"] = user
    return response


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return render("home.html", request)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return render(
        "login.html",
        request,
        next_path=safe_next_path(request.query_params.get("next")),
    )


@app.post("/login")
async def login(request: Request):
    values = parse_qs((await request.body()).decode("utf-8", errors="replace"))
    username = values.get("username", [""])[0][:100]
    password = values.get("password", [""])[0]
    record = USERS.get(username)
    valid = record is not None and hmac.compare_digest(
        record["hash"], password_hash(password, record["salt"])
    )
    if not valid:
        response = render(
            "login.html",
            request,
            status_code=401,
            error="Invalid username or password",
            next_path=safe_next_path(values.get("next", [None])[0]),
        )
        if username:
            response.headers["X-ThreatLens-User"] = username
        return response
    request.session["user"] = username
    next_path = safe_next_path(values.get("next", [None])[0])
    response = RedirectResponse(next_path, status_code=303)
    response.headers["X-ThreatLens-User"] = username
    return response


@app.post("/logout")
def logout(request: Request):
    username = request.session.pop("user", None)
    response = RedirectResponse("/", status_code=303)
    if username:
        response.headers["X-ThreatLens-User"] = username
    return response


@app.post("/switch-user")
async def switch_user(request: Request):
    """Switch identities in the local demo without exposing real credentials."""
    if not DEMO_MODE:
        return HTMLResponse("Not found", status_code=404)

    values = parse_qs((await request.body()).decode("utf-8", errors="replace"))
    username = values.get("username", [""])[0][:100]
    if username not in USERS:
        return render(
            "message.html",
            request,
            status_code=400,
            title="Unknown demo user",
            message="Choose one of the available demo identities.",
        )

    request.session["user"] = username
    next_path = safe_next_path(values.get("next", [None])[0])
    if next_path.startswith("/admin") and USERS[username]["role"] != "admin":
        next_path = "/profile"
    response = RedirectResponse(next_path, status_code=303)
    response.headers["X-ThreatLens-User"] = username
    return response


@app.post("/demo/auth-attempt")
async def demo_auth_attempt(request: Request):
    """Emit a bounded login outcome for the active demo identity."""
    if not DEMO_MODE:
        return HTMLResponse("Not found", status_code=404)
    if not request.session.get("user"):
        return JSONResponse({"error": "Sign in first"}, status_code=401)

    values = parse_qs((await request.body()).decode("utf-8", errors="replace"))
    outcome = values.get("outcome", [""])[0]
    if outcome == "failure":
        return JSONResponse({"status": "failure"}, status_code=401)
    if outcome == "success":
        return JSONResponse({"status": "success"}, status_code=200)
    return JSONResponse({"error": "Invalid outcome"}, status_code=400)


@app.get("/profile", response_class=HTMLResponse)
def profile(request: Request):
    if not request.session.get("user"):
        return RedirectResponse("/login", status_code=303)
    return render("profile.html", request)


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=303)
    if USERS[username]["role"] != "admin":
        return render(
            "message.html",
            request,
            status_code=403,
            title="Access denied",
            message="Administrator access is required.",
        )
    return render("admin.html", request, users=sorted(USERS))


@app.post("/admin/users", response_class=HTMLResponse)
async def add_demo_user(request: Request):
    """Create a local demo user from the admin control plane."""
    username = request.session.get("user")
    if not username:
        return RedirectResponse("/login", status_code=303)
    if USERS[username]["role"] != "admin":
        return HTMLResponse("Administrator access is required.", status_code=403)

    values = parse_qs((await request.body()).decode("utf-8", errors="replace"))
    new_username = values.get("username", [""])[0].strip().lower()[:32]
    password = values.get("password", [""])[0][:128]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,31}", new_username):
        return render(
            "admin.html", request, status_code=400, users=sorted(USERS),
            user_error="Use 3–32 lowercase letters, numbers, hyphens, or underscores.",
        )
    if len(password) < 6:
        return render(
            "admin.html", request, status_code=400, users=sorted(USERS),
            user_error="Password must contain at least 6 characters.",
        )
    if new_username in USERS:
        return render(
            "admin.html", request, status_code=409, users=sorted(USERS),
            user_error="That username already exists.",
        )

    salt = f"{new_username}-demo"
    USERS[new_username] = {
        "salt": salt,
        "hash": password_hash(password, salt),
        "role": "user",
    }
    return render(
        "admin.html", request, users=sorted(USERS),
        user_notice=f"User {new_username} was added and is ready to use.",
    )


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = ""):
    return render(
        "message.html", request, title="Search", message=f"No results for {q[:80]!r}."
    )


@app.get("/api/data")
def api_data(request: Request):
    response = JSONResponse(
        {"status": "ok", "items": ["profile", "preferences", "activity"]}
    )
    if request.session.get("user"):
        response.headers["X-ThreatLens-User"] = request.session["user"]
    return response


@app.get("/api/catalog")
def api_catalog():
    """Synthetic catalog data used to make the portal feel like a real app."""
    return {
        "items": [
            {"id": "workspace", "name": "Workspace protection", "status": "active"},
            {"id": "identity", "name": "Identity controls", "status": "active"},
            {"id": "monitoring", "name": "Threat monitoring", "status": "active"},
        ]
    }


@app.post("/api/checkout-preview")
async def checkout_preview(request: Request):
    """Accept a fake checkout request but never place an order or charge anything."""
    values = await request.json()
    return {
        "status": "preview",
        "items": min(len(values.get("items", [])), 10),
        "charged": False,
    }


@app.get("/demo/error", response_class=HTMLResponse)
def controlled_error(request: Request):
    if not DEMO_MODE:
        return HTMLResponse("Not found", status_code=404)
    return render(
        "message.html",
        request,
        status_code=500,
        title="Controlled error",
        message="Intentional demo-only 500 response.",
    )


@app.get("/demo-controls", response_class=HTMLResponse)
def demo_controls(request: Request):
    if not DEMO_MODE:
        return HTMLResponse("Not found", status_code=404)
    if not request.session.get("user"):
        return RedirectResponse("/login?next=%2Fdemo-controls", status_code=303)
    return render("controls.html", request)


@app.get("/health")
def health():
    return {"status": "ok", "demo_mode": DEMO_MODE}
