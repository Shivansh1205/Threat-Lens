"""Durable, dependency-free Nginx JSON access-log collector."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

LOG_PATH = Path(os.getenv("COLLECTOR_LOG_PATH", "/var/log/nginx/threatlens.json.log"))
STATE_PATH = Path(os.getenv("COLLECTOR_STATE_PATH", "/state/checkpoint.json"))
API_URL = os.getenv("THREATLENS_API_URL", "http://backend:8002").rstrip("/")
API_KEY = os.getenv("INGEST_API_KEY", "change-me-ingest")
IP_HASH_SECRET = os.getenv("IP_HASH_SECRET", "change-me-ip-hash").encode()
SOURCE_ID = os.getenv("SOURCE_ID", "demo-portal")
SOURCE_NAME = os.getenv("SOURCE_NAME", "Sentinel demo portal")
LOGIN_PATHS = {
    item.strip()
    for item in os.getenv("LOGIN_PATHS", "/login").split(",")
    if item.strip()
}
BATCH_SIZE = int(os.getenv("COLLECTOR_BATCH_SIZE", "50"))
FLUSH_SECONDS = float(os.getenv("COLLECTOR_FLUSH_SECONDS", "1"))
HEARTBEAT_SECONDS = float(os.getenv("COLLECTOR_HEARTBEAT_SECONDS", "10"))
START_AT = os.getenv("COLLECTOR_START_AT", "end").lower()


def post(path: str, payload: dict, timeout: float = 10) -> dict:
    request = urllib.request.Request(
        API_URL + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-ThreatLens-Key": API_KEY},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"{}")


def load_state() -> dict:
    try:
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        return {
            "inode": int(state.get("inode", 0)),
            "offset": int(state.get("offset", 0)),
        }
    except (OSError, ValueError, TypeError):
        return {"inode": 0, "offset": 0}


def save_state(inode: int, offset: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"inode": inode, "offset": offset}), encoding="utf-8"
    )
    temporary.replace(STATE_PATH)


def visitor_id(ip: str) -> str:
    digest = hmac.new(IP_HASH_SECRET, ip.encode(), hashlib.sha256).hexdigest()[:20]
    return f"visitor_{digest}"


def clean_uri(raw: str) -> str:
    """Drop query strings so tokens and user input are never stored."""
    try:
        return urlsplit(raw).path[:2048] or "/"
    except ValueError:
        return "/invalid-uri"


def parse_event(line: str) -> dict:
    item = json.loads(line)
    ip = str(item["remote_addr"])
    endpoint = clean_uri(str(item.get("request_uri", "/")))
    status_code = int(item["status"])
    username = str(item.get("threatlens_user") or "").strip()
    if username in {"-", "null"}:
        username = ""
    event_type = "API_CALL"
    if endpoint in LOGIN_PATHS and str(item.get("method", "")).upper() == "POST":
        event_type = (
            "LOGIN_FAILURE" if status_code in {400, 401, 403} else "LOGIN_SUCCESS"
        )
    elif endpoint == "/logout":
        event_type = "LOGOUT"
    timestamp = datetime.fromisoformat(str(item["time_iso8601"]).replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return {
        "external_event_id": str(item["request_id"]),
        "user_id": username[:200] if username else visitor_id(ip),
        "ip": ip,
        "timestamp": timestamp.astimezone(timezone.utc).isoformat(),
        "event_type": event_type,
        "status": str(status_code),
        "endpoint": endpoint,
        "user_agent": str(item.get("user_agent") or "")[:1024] or None,
        "http_method": str(item.get("method") or "GET").upper()[:16],
        "http_status": status_code,
        "response_time_ms": max(0, float(item.get("request_time") or 0) * 1000),
        "bytes_sent": max(0, int(item.get("bytes_sent") or 0)),
        "host": str(item.get("host") or "")[:255] or None,
        "referrer": (
            clean_uri(str(item.get("referrer")))
            if item.get("referrer") not in {None, "", "-"}
            else None
        ),
        "event_metadata": {"collector": "nginx-json-v1"},
    }


def heartbeat(malformed: int, failures: int) -> None:
    post(
        f"/api/v1/sources/{SOURCE_ID}/heartbeat",
        {
            "name": SOURCE_NAME,
            "source_type": "nginx",
            "malformed_lines": malformed,
            "delivery_failures": failures,
        },
    )


def main() -> None:
    state = load_state()
    pending: list[dict] = []
    pending_offset = state["offset"]
    malformed = 0
    failures = 0
    last_flush = time.monotonic()
    last_heartbeat = 0.0
    retry_delay = 1.0
    print(f"[collector] source={SOURCE_ID} log={LOG_PATH} api={API_URL}", flush=True)

    while True:
        now = time.monotonic()
        try:
            stat = LOG_PATH.stat()
        except OSError:
            if now - last_heartbeat >= HEARTBEAT_SECONDS:
                try:
                    heartbeat(malformed, failures)
                    last_heartbeat = now
                except OSError:
                    failures += 1
            time.sleep(1)
            continue

        inode = int(stat.st_ino)
        if state["inode"] != inode or state["offset"] > stat.st_size:
            state = {
                "inode": inode,
                "offset": (
                    stat.st_size if state["inode"] == 0 and START_AT == "end" else 0
                ),
            }
            save_state(inode, state["offset"])

        with LOG_PATH.open("r", encoding="utf-8", errors="replace") as handle:
            handle.seek(state["offset"])
            while len(pending) < BATCH_SIZE:
                line = handle.readline()
                if not line or not line.endswith("\n"):
                    break
                pending_offset = handle.tell()
                try:
                    pending.append(parse_event(line))
                except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    malformed += 1
                    print(f"[collector] rejected malformed line: {exc}", flush=True)
                    if not pending:
                        state["offset"] = pending_offset
                        save_state(inode, pending_offset)

        should_flush = pending and (
            len(pending) >= BATCH_SIZE or now - last_flush >= FLUSH_SECONDS
        )
        if should_flush:
            try:
                result = post(
                    "/api/v1/events/batch",
                    {
                        "source_id": SOURCE_ID,
                        "source_name": SOURCE_NAME,
                        "events": pending,
                    },
                )
                alert_count = len(result.get("alert_ids", []))
                print(
                    f"[collector] accepted={result.get('accepted')} "
                    f"duplicates={result.get('duplicates')} alerts={alert_count}",
                    flush=True,
                )
                state["offset"] = pending_offset
                save_state(inode, pending_offset)
                pending.clear()
                retry_delay = 1.0
                last_flush = now
            except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
                failures += 1
                print(
                    f"[collector] delivery failed; retrying in "
                    f"{retry_delay:.0f}s: {exc}",
                    flush=True,
                )
                time.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, 30)

        if now - last_heartbeat >= HEARTBEAT_SECONDS:
            try:
                heartbeat(malformed, failures)
                last_heartbeat = now
            except (OSError, urllib.error.HTTPError):
                failures += 1
        time.sleep(0.2)


if __name__ == "__main__":
    main()
