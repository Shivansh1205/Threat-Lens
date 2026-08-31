from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app as fastapi_app
from app.security import require_admin_key


def test_chat_requires_admin_key(client: TestClient) -> None:
    fastapi_app.dependency_overrides.pop(require_admin_key, None)
    response = client.post(
        "/api/v1/chat",
        json={"session_id": "auth-test", "message": "show recent alerts"},
    )
    assert response.status_code == 401
    fastapi_app.dependency_overrides[require_admin_key] = lambda: None


def test_chat_accepts_admin_key(client: TestClient) -> None:
    fastapi_app.dependency_overrides.pop(require_admin_key, None)
    with patch("app.ai.ollama_client.generate_grounded", new=AsyncMock(return_value="analysis")):
        response = client.post(
            "/api/v1/chat",
            headers={"X-ThreatLens-Admin-Key": get_settings().ADMIN_API_KEY},
            json={"session_id": "auth-test-valid", "message": "show detector settings"},
        )
    assert response.status_code == 200
    assert response.json()["response"].startswith("analysis")
    fastapi_app.dependency_overrides[require_admin_key] = lambda: None
