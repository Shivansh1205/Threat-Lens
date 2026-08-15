"""A safe, deliberately observable portal for the ThreatLens demo."""

import hashlib
import hmac
import os
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


def render(
    name: str, request: Request, status_code: int = 200, **context
) -> HTMLResponse:
    user = request.session.get("user")
    body = env.get_template(name).render(
        request=request, user=user, demo_mode=DEMO_MODE, **context
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
    return render("login.html", request)


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
            "login.html", request, status_code=401, error="Invalid username or password"
        )
        if username:
            response.headers["X-ThreatLens-User"] = username
        return response
    request.session["user"] = username
    response = RedirectResponse("/profile", status_code=303)
    response.headers["X-ThreatLens-User"] = username
    return response


@app.post("/logout")
def logout(request: Request):
    username = request.session.pop("user", None)
    response = RedirectResponse("/", status_code=303)
    if username:
        response.headers["X-ThreatLens-User"] = username
    return response


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
    return render(
        "message.html",
        request,
        title="Admin console",
        message="This is a safe demonstration page.",
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
    return render("controls.html", request)


@app.get("/health")
def health():
    return {"status": "ok", "demo_mode": DEMO_MODE}
