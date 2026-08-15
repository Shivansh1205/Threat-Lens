import os

os.environ["DEMO_MODE"] = "true"

from app import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_login_and_role_protection() -> None:
    failed = client.post("/login", content="username=alice&password=wrong")
    assert failed.status_code == 401
    assert failed.headers["x-threatlens-user"] == "alice"

    success = client.post(
        "/login", content="username=alice&password=demo123", follow_redirects=False
    )
    assert success.status_code == 303
    denied = client.get("/admin")
    assert denied.status_code == 403


def test_controlled_demo_routes() -> None:
    assert client.get("/demo-controls").status_code == 200
    assert client.get("/demo/error").status_code == 500
