#!/usr/bin/env python3
"""Send alert-triggering log events for 10 users so they all appear on the dashboard."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

TARGET = "http://localhost:8002/api/v1/log"

# 10 users, each with a distinct attacker IP
USERS = [
    {"user_id": "alice",   "ip": "203.0.113.7"},
    {"user_id": "bob",     "ip": "203.0.113.8"},
    {"user_id": "carol",   "ip": "203.0.113.9"},
    {"user_id": "dave",    "ip": "203.0.113.10"},
    {"user_id": "eve",     "ip": "203.0.113.11"},
    {"user_id": "frank",   "ip": "203.0.113.12"},
    {"user_id": "grace",   "ip": "203.0.113.13"},
    {"user_id": "heidi",   "ip": "203.0.113.14"},
    {"user_id": "ivan",    "ip": "203.0.113.15"},
    {"user_id": "judy",    "ip": "203.0.113.16"},
]


def send(payload: dict) -> str:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        TARGET, data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            body = json.loads(resp.read())
            alerts = body.get("alert_ids", [])
            return f"{resp.status} alerts={len(alerts)}"
    except urllib.error.HTTPError as exc:
        return f"ERR {exc.code} {exc.read(120)}"
    except OSError as exc:
        return f"ERR {exc}"


def flood_user(user_id: str, ip: str) -> None:
    """Send 6 LOGIN_FAILUREs (crosses MEDIUM at 5) then a LOGIN_SUCCESS."""
    base_ts = datetime.now(timezone.utc)
    for i in range(6):
        ts = (base_ts + timedelta(seconds=i * 2)).isoformat().replace("+00:00", "Z")
        result = send({"user_id": user_id, "ip": ip, "timestamp": ts,
                       "event_type": "LOGIN_FAILURE", "status": "bad_password"})
        print(f"  [{result}] {user_id:8s}  LOGIN_FAILURE #{i+1}")
    # success after failures -> brute_force_success alert
    ts = (base_ts + timedelta(seconds=14)).isoformat().replace("+00:00", "Z")
    result = send({"user_id": user_id, "ip": ip, "timestamp": ts,
                   "event_type": "LOGIN_SUCCESS", "status": "ok"})
    print(f"  [{result}] {user_id:8s}  LOGIN_SUCCESS")


def main() -> None:
    total_users = len(USERS)
    print(f"Flooding {total_users} users — 6 failures + 1 success each...\n")
    for u in USERS:
        flood_user(u["user_id"], u["ip"])
        print()
        time.sleep(0.2)  # small pause between users
    print(f"Done. {total_users} users flooded. Check /api/v1/users/high-risk.")


if __name__ == "__main__":
    main()
