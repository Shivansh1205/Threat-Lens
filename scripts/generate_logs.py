#!/usr/bin/env python3
"""Synthetic log traffic generator for ThreatLens.

Sends scripted `POST /api/v1/log` traffic at a chosen speed so the human
running it can watch alerts land on the dashboard.

Usage
-----

    python scripts/generate_logs.py --scenario brute_force
    python scripts/generate_logs.py --scenario port_scan --speed 50
    python scripts/generate_logs.py --scenario mixed --target-url http://localhost:8000

Flags
-----
    --scenario   One of: normal, brute_force, port_scan, unusual_ip, mixed.
    --target-url Backend base URL. Default http://localhost:8000.
    --speed      Speed multiplier. 1 = real-time. 100 = 100x faster. Default 1.

Each scenario prints ``Sent N events over Ds. Expected M alerts.`` at the end.
This is a *sender* — it does not GET alerts back or verify anything. Eyeball
the dashboard for the outcomes.
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import httpx

# --------------------------------------------------------------------- events


@dataclass
class ScriptedEvent:
    """A single event to send at ``offset_seconds`` after the scenario starts."""

    offset_seconds: float
    user_id: str
    ip: str
    event_type: str
    status: str = "ok"
    port: int | None = None
    endpoint: str | None = None


@dataclass
class Scenario:
    name: str
    events: list[ScriptedEvent]
    expected_alerts: int
    description: str = ""


# ---------------------------------------------------------------- scenarios --


def _normal(base_user: str = "bob", ip: str = "10.0.0.5") -> list[ScriptedEvent]:
    """1 login, 20 API calls one/minute, 1 logout — quiet baseline."""
    out: list[ScriptedEvent] = [
        ScriptedEvent(0, base_user, ip, "LOGIN_SUCCESS"),
    ]
    for i in range(20):
        out.append(
            ScriptedEvent(60 + i * 60, base_user, ip, "API_CALL", endpoint="/api/v1/health")
        )
    out.append(ScriptedEvent(1260, base_user, ip, "LOGOUT"))
    return out


def _brute_force() -> list[ScriptedEvent]:
    """25 rapid failures then a successful login — should fire MEDIUM, HIGH,
    CRITICAL and a brute_force_success (4 alerts total)."""
    user = "alice"
    attacker_ip = "203.0.113.7"
    events = [
        ScriptedEvent(
            offset_seconds=i * 1.5,
            user_id=user,
            ip=attacker_ip,
            event_type="LOGIN_FAILURE",
            status="bad_password",
        )
        for i in range(25)
    ]
    events.append(ScriptedEvent(38.0, user, attacker_ip, "LOGIN_SUCCESS"))
    return events


def _port_scan() -> list[ScriptedEvent]:
    """60 PORT_ACCESS events, 60 distinct ports in ~2s from one IP.
    Crosses the HIGH (15) and CRITICAL (50) distinct-port thresholds → 2 alerts."""
    ip = "198.51.100.42"
    return [
        ScriptedEvent(
            offset_seconds=i * 0.03,
            user_id="scanner",
            ip=ip,
            event_type="PORT_ACCESS",
            port=i + 1,
        )
        for i in range(60)
    ]


def _unusual_ip() -> list[ScriptedEvent]:
    """Bootstrap on IP A, then a single login from IP B → 1 LOW alert."""
    user = "carol"
    return [
        ScriptedEvent(0, user, "10.0.0.10", "LOGIN_SUCCESS"),
        ScriptedEvent(60, user, "10.0.0.10", "LOGIN_SUCCESS"),
        ScriptedEvent(120, user, "10.0.0.10", "LOGIN_SUCCESS"),
        ScriptedEvent(180, user, "10.0.0.99", "LOGIN_SUCCESS"),
    ]


def _mixed() -> list[ScriptedEvent]:
    """Interleave the attack scenarios across distinct users/IPs plus quiet
    background traffic. Verifies detectors don't cross-contaminate.

    Expected alerts:
        - brute_force block  (alice / 203.0.113.7): 4
        - port_scan block    (scanner / 198.51.100.42): 2
        - unusual_ip block   (carol): 1
        - three normal users (dave, eve, frank): 0
        Total: 7
    """
    events: list[ScriptedEvent] = []
    events += _brute_force()
    events += _port_scan()
    events += _unusual_ip()
    for user in ("dave", "eve", "frank"):
        events += _normal(base_user=user, ip=f"10.0.1.{hash(user) % 200 + 1}")
    events.sort(key=lambda e: e.offset_seconds)
    return events


SCENARIOS: dict[str, Scenario] = {
    "normal": Scenario(
        name="normal",
        events=_normal(),
        expected_alerts=0,
        description="Baseline: one user, quiet traffic, no alerts.",
    ),
    "brute_force": Scenario(
        name="brute_force",
        events=_brute_force(),
        expected_alerts=4,
        description="25 failures escalating MEDIUM→HIGH→CRITICAL, then a "
        "successful login (brute_force_success).",
    ),
    "port_scan": Scenario(
        name="port_scan",
        events=_port_scan(),
        expected_alerts=2,
        description="60 distinct ports probed → HIGH then CRITICAL.",
    ),
    "unusual_ip": Scenario(
        name="unusual_ip",
        events=_unusual_ip(),
        expected_alerts=1,
        description="Bootstrap on one IP, single login from a new one → LOW.",
    ),
    "mixed": Scenario(
        name="mixed",
        events=_mixed(),
        expected_alerts=7,
        description="All three attack scenarios plus 3 quiet users — must not "
        "cross-contaminate.",
    ),
}


# ------------------------------------------------------------------- sending


def _payload(ev: ScriptedEvent, ts: datetime) -> dict:
    body: dict = {
        "user_id": ev.user_id,
        "ip": ev.ip,
        "timestamp": ts.isoformat().replace("+00:00", "Z"),
        "event_type": ev.event_type,
        "status": ev.status,
    }
    if ev.port is not None:
        body["port"] = ev.port
    if ev.endpoint is not None:
        body["endpoint"] = ev.endpoint
    return body


async def _send_one(
    client: httpx.AsyncClient, url: str, ev: ScriptedEvent, ts: datetime
) -> None:
    try:
        resp = await client.post(url, json=_payload(ev, ts))
        if resp.status_code >= 300:
            print(f"  ! {resp.status_code} {resp.text[:120]}")
    except httpx.HTTPError as exc:  # noqa: PERF203
        print(f"  ! request failed: {exc}")


async def run_scenario(scenario: Scenario, target_url: str, speed: float) -> None:
    if speed <= 0:
        raise ValueError("--speed must be positive")

    url = target_url.rstrip("/") + "/api/v1/log"
    start_wall = asyncio.get_event_loop().time()
    start_ts = datetime.now(timezone.utc)

    print(
        f"[generate_logs] scenario={scenario.name} events={len(scenario.events)} "
        f"speed={speed}x -> {url}"
    )
    print(f"[generate_logs] {scenario.description}")

    async with httpx.AsyncClient(timeout=5.0) as client:
        tasks: list[asyncio.Task] = []
        for ev in scenario.events:
            wait = (ev.offset_seconds / speed) - (asyncio.get_event_loop().time() - start_wall)
            if wait > 0:
                await asyncio.sleep(wait)
            event_ts = start_ts + timedelta(seconds=ev.offset_seconds)
            tasks.append(asyncio.create_task(_send_one(client, url, ev, event_ts)))
        await asyncio.gather(*tasks)

    elapsed = asyncio.get_event_loop().time() - start_wall
    print(
        f"[generate_logs] Sent {len(scenario.events)} events over "
        f"{elapsed:.1f}s. Expected {scenario.expected_alerts} alerts."
    )


# ---------------------------------------------------------------------- main


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send synthetic ThreatLens traffic.")
    parser.add_argument(
        "--scenario",
        choices=list(SCENARIOS.keys()),
        required=True,
        help="Traffic pattern to simulate.",
    )
    parser.add_argument(
        "--target-url",
        default="http://localhost:8000",
        help="Backend base URL (default: http://localhost:8000).",
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Speed multiplier. 1 = real time, 100 = 0.01s between events (default: 1).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    scenario = SCENARIOS[args.scenario]
    asyncio.run(run_scenario(scenario, args.target_url, args.speed))


if __name__ == "__main__":
    main()
