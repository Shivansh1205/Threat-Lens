#!/usr/bin/env python3
"""Run the same bounded scenarios exposed by the demo portal Attack Lab."""

import argparse
import concurrent.futures
import urllib.error
import urllib.parse
import urllib.request


def request(url: str, data: dict | None = None) -> int:
    encoded = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=encoded, method="POST" if data else "GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def brute(base: str) -> None:
    for _ in range(6):
        request(base + "/login", {"username": "alice", "password": "incorrect"})
    request(base + "/login", {"username": "alice", "password": "demo123"})


def flood(base: str) -> None:
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        list(pool.map(lambda i: request(f"{base}/api/data?demo={i}"), range(80)))


def probe(base: str) -> None:
    for i in range(22):
        request(f"{base}/private-probe-{i}")


def errors(base: str) -> None:
    for i in range(16):
        request(f"{base}/demo/error?attempt={i}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "scenario", choices=["brute", "flood", "probe", "errors", "combined"]
    )
    parser.add_argument("--url", default="http://localhost:8080")
    args = parser.parse_args()
    scenarios = {"brute": brute, "flood": flood, "probe": probe, "errors": errors}
    selected = (
        scenarios.values()
        if args.scenario == "combined"
        else [scenarios[args.scenario]]
    )
    for scenario in selected:
        scenario(args.url.rstrip("/"))
    print(f"Completed {args.scenario}. Check http://localhost:5173 for alerts.")


if __name__ == "__main__":
    main()
