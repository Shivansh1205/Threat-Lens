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


def test_demo_auth_attempt_maps_current_account_to_login_events() -> None:
    failed = collector.parse_event(
        record(
            method="POST",
            request_uri="/demo/auth-attempt",
            status=401,
            threatlens_user="admin",
        )
    )
    succeeded = collector.parse_event(
        record(
            method="POST",
            request_uri="/demo/auth-attempt",
            status=200,
            threatlens_user="admin",
        )
    )
    assert failed["event_type"] == "LOGIN_FAILURE"
    assert succeeded["event_type"] == "LOGIN_SUCCESS"
    assert failed["user_id"] == succeeded["user_id"] == "admin"


def test_demo_port_path_maps_to_active_user_without_query_data() -> None:
    event = collector.parse_event(
        record(request_uri="/demo/port/3042", threatlens_user="admin")
    )
    assert event["event_type"] == "PORT_ACCESS"
    assert event["port"] == 3042
    assert event["endpoint"] == "/demo/port/3042"
    assert event["user_id"] == "admin"


def test_authenticated_probe_keeps_server_identity() -> None:
    event = collector.parse_event(
        record(
            request_uri="/private-probe-8",
            status=404,
            threatlens_user="alice",
        )
    )
    assert event["user_id"] == "alice"
    assert event["endpoint"] == "/private-probe-8"
