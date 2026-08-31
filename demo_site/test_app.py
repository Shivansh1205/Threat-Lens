import os
from copy import deepcopy
from pathlib import Path

os.environ["DEMO_MODE"] = "true"

import pytest
from app import USERS, app
from fastapi.testclient import TestClient

BASE_USERS = deepcopy(USERS)


@pytest.fixture
def client():
    USERS.clear()
    USERS.update(deepcopy(BASE_USERS))
    with TestClient(app) as test_client:
        yield test_client


def test_login_and_role_protection(client: TestClient) -> None:
    failed = client.post("/login", content="username=alice&password=wrong")
    assert failed.status_code == 401
    assert failed.headers["x-threatlens-user"] == "alice"

    success = client.post(
        "/login", content="username=alice&password=demo123", follow_redirects=False
    )
    assert success.status_code == 303
    denied = client.get("/admin")
    assert denied.status_code == 403


def test_demo_user_switcher_changes_session_and_avoids_forbidden_page(
    client: TestClient,
) -> None:
    client.post("/login", content="username=admin&password=admin123")
    switched = client.post(
        "/switch-user",
        content="username=alice&next=%2Fadmin",
        follow_redirects=False,
    )
    assert switched.status_code == 303
    assert switched.headers["location"] == "/profile"
    assert switched.headers["x-threatlens-user"] == "alice"

    profile = client.get("/profile")
    assert "<h2>alice</h2>" in profile.text
    assert profile.headers["x-threatlens-user"] == "alice"
    assert client.get("/admin").status_code == 403


def test_admin_can_add_demo_user(client: TestClient) -> None:
    client.post("/login", content="username=admin&password=admin123")
    added = client.post(
        "/admin/users",
        content="username=bob&password=bob123",
    )
    assert added.status_code == 200
    assert "bob" in added.text
    login = client.post(
        "/login", content="username=bob&password=bob123", follow_redirects=False
    )
    assert login.status_code == 303


def test_non_admin_cannot_add_demo_user(client: TestClient) -> None:
    client.post("/login", content="username=alice&password=demo123")
    denied = client.post("/admin/users", content="username=mallory&password=mallory123")
    assert denied.status_code == 403


def test_attack_lab_requires_login_and_returns_to_requested_page(
    client: TestClient,
) -> None:
    anonymous = client.get("/demo-controls", follow_redirects=False)
    assert anonymous.status_code == 303
    assert anonymous.headers["location"] == "/login?next=%2Fdemo-controls"

    login = client.post(
        "/login",
        content="username=admin&password=admin123&next=%2Fdemo-controls",
        follow_redirects=False,
    )
    assert login.headers["location"] == "/demo-controls"
    controls = client.get("/demo-controls")
    assert "Active account: admin" in controls.text


def test_safe_next_rejects_external_redirects(client: TestClient) -> None:
    login = client.post(
        "/login",
        content="username=alice&password=demo123&next=https%3A%2F%2Fexample.com",
        follow_redirects=False,
    )
    assert login.headers["location"] == "/profile"


def test_active_identity_is_attached_to_all_attack_responses(
    client: TestClient,
) -> None:
    client.post("/login", content="username=admin&password=admin123")

    for path, expected_status in (
        ("/private-probe-1", 404),
        ("/demo/port/3001", 404),
        ("/demo/error", 500),
        ("/api/data", 200),
    ):
        response = client.get(path)
        assert response.status_code == expected_status
        assert response.headers["x-threatlens-user"] == "admin"


def test_demo_auth_attempt_uses_active_account_without_switching_it(
    client: TestClient,
) -> None:
    client.post("/login", content="username=admin&password=admin123")

    failed = client.post("/demo/auth-attempt", content="outcome=failure")
    succeeded = client.post("/demo/auth-attempt", content="outcome=success")
    assert failed.status_code == 401
    assert succeeded.status_code == 200
    assert failed.headers["x-threatlens-user"] == "admin"
    assert succeeded.headers["x-threatlens-user"] == "admin"
    assert "<h2>admin</h2>" in client.get("/profile").text


def test_controlled_error_route(client: TestClient) -> None:
    assert client.get("/demo/error").status_code == 500


def test_portal_pages_stay_in_one_application(client: TestClient) -> None:
    admin_login = client.post(
        "/login", content="username=admin&password=admin123", follow_redirects=False
    )
    assert admin_login.status_code == 303
    admin_page = client.get("/admin")
    assert admin_page.status_code == 200
    assert "ADMIN CONTROL PLANE" in admin_page.text
    assert "localhost" not in admin_page.url.path


def test_synthetic_api_never_places_an_order(client: TestClient) -> None:
    catalog = client.get("/api/catalog")
    assert catalog.status_code == 200
    preview = client.post("/api/checkout-preview", json={"items": ["workspace"]})
    assert preview.json() == {"status": "preview", "items": 1, "charged": False}


def test_api_overview_links_are_hidden_but_api_remains_available(
    client: TestClient,
) -> None:
    home = client.get("/")
    assert 'href="/api/data"' not in home.text
    assert ">API activity<" not in home.text
    assert client.get("/api/data").status_code == 200


def test_attack_lab_script_never_logs_in_as_a_hardcoded_user() -> None:
    script = (Path(__file__).parent / "static" / "attack-lab.js").read_text(
        encoding="utf-8"
    )
    assert "/demo/auth-attempt" in script
    assert "username=alice" not in script
