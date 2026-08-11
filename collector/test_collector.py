import json

import collector


def record(**updates) -> str:
    data = {
        "request_id": "abc123",
        "time_iso8601": "2026-08-11T12:00:00+00:00",
        "remote_addr": "203.0.113.10",
        "host": "localhost",
        "method": "GET",
        "request_uri": "/api/data?token=secret",
        "status": 200,
        "bytes_sent": 120,
        "request_time": 0.012,
        "referrer": "-",
        "user_agent": "pytest",
        "threatlens_user": "-",
    }
    data.update(updates)
    return json.dumps(data)


def test_parse_redacts_query_and_hashes_anonymous_ip() -> None:
    event = collector.parse_event(record())
    assert event["endpoint"] == "/api/data"
    assert "secret" not in str(event)
    assert event["user_id"].startswith("visitor_")


def test_login_mapping_uses_server_identity() -> None:
    event = collector.parse_event(
        record(method="POST", request_uri="/login", status=401, threatlens_user="alice")
    )
    assert event["event_type"] == "LOGIN_FAILURE"
    assert event["user_id"] == "alice"
