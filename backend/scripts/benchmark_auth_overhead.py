"""Measure auth-boundary overhead using a fixed representative request mix.

The benchmark is a standalone tool and is never imported by the application.
Run it before and after a rollout change with the same environment, iteration
count, URL, and token. Results are JSON so they can be attached to a gate record.

Example:
    uv run python backend/scripts/benchmark_auth_overhead.py --label after \
      --base-url http://127.0.0.1:8000 --iterations 25
"""
from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx


@dataclass(frozen=True)
class Probe:
    """One request in the fixed auth benchmark mix."""

    name: str
    method: str
    path: str
    headers: dict[str, str]



def probes(valid_token: str) -> tuple[Probe, ...]:
    """Return the stable probe/auth/injection/preflight request mix."""
    return (
        Probe("public_probe", "GET", "/health", {}),
        Probe("valid_auth", "GET", "/api/v1/capabilities", {"Authorization": f"Bearer {valid_token}"}),
        Probe("missing_auth", "GET", "/api/v1/capabilities", {}),
        Probe("invalid_auth", "GET", "/api/v1/capabilities", {"Authorization": "Bearer benchmark-invalid"}),
        Probe("injection", "GET", "/api/v1/capabilities?" + urlencode({"org_id": "foreign"}), {}),
        Probe(
            "preflight",
            "OPTIONS",
            "/api/v1/capabilities",
            {
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        ),
    )


def run(base_url: str, iterations: int, valid_token: str, timeout: float) -> dict[str, object]:
    """Run every probe the same number of times and return aggregate timings."""
    results: dict[str, list[float]] = {probe.name: [] for probe in probes(valid_token)}
    statuses: dict[str, list[int]] = {probe.name: [] for probe in probes(valid_token)}
    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        for _ in range(iterations):
            for probe in probes(valid_token):
                started = time.perf_counter()
                response = client.request(probe.method, probe.path, headers=probe.headers)
                results[probe.name].append((time.perf_counter() - started) * 1000)
                statuses[probe.name].append(response.status_code)
    summary = {
        name: {
            "requests": len(values),
            "median_ms": round(statistics.median(values), 3),
            "p95_ms": round(sorted(values)[max(0, int(len(values) * 0.95) - 1)], 3),
            "statuses": sorted(set(statuses[name])),
        }
        for name, values in results.items()
    }
    return {"base_url": base_url, "iterations": iterations, "probes": summary}


def main() -> int:
    """Parse benchmark options and print a JSON evidence record."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--iterations", type=int, default=25)
    parser.add_argument("--valid-token", default="benchmark-valid-token")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    evidence = run(args.base_url, args.iterations, args.valid_token, args.timeout)
    evidence.update(
        {
            "label": args.label,
            "utc_started": datetime.now(UTC).isoformat(),
            "request_mix": "probe,valid-auth,missing-auth,invalid-auth,injection,preflight",
            "comparison_contract": "Run before and after with identical options and environment.",
        }
    )
    print(json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
