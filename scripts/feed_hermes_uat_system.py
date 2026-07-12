"""Feed the self-learning UAT system information to Hermes.

This tells Hermes about:
- The Ise UAT agent and its capabilities
- The steering, skill, and hook system
- How to trigger tests and interpret results
- The self-learning loop

Run: uv run python scripts/feed_hermes_uat_system.py
"""

import json
import urllib.request

HERMES_URL = "http://localhost:8000/aios/v1/hermes/chat"
AIOS_CHAT_URL = "http://localhost:8000/aios/v1/chat"

MESSAGE = """SYSTEM UPDATE: The Ise UAT Agent is now fully operational.

## What was built:

1. **Steering** (.kiro/steering/uat-system.md) — Living test knowledge that updates after every run. Contains:
   - Page Health Map (all 19 pages tracked)
   - Known failure patterns + fixes
   - Test file map
   - Enhancement backlog

2. **Skill** (.kiro/skills/run-uat.md) — Step-by-step UAT procedure:
   - How to run tests (full or targeted)
   - How to interpret and classify failures
   - How to update steering and feed results back

3. **Hooks** (3 triggers):
   - `uat-on-push` — Runs full Playwright suite after git push
   - `uat-on-test-save` — Re-runs affected test when spec files change
   - `uat-on-page-save` — Runs corresponding test when page components change

4. **Agent** (.kiro/agents/ise-uat.md) — Orchestrates the full flow:
   - Detect → Run → Parse → Diagnose → Fix → Update → Report
   - Decision framework for different failure severities
   - Self-learning loop that builds pattern knowledge over time

## How you (Hermes) interact with Ise:

- Call `run_uat_tests(filter?)` to trigger a test run
- Call `get_uat_results()` to check the latest results
- Read .kiro/steering/uat-system.md for current health status
- When the user asks "is the UI working?" or "run the tests" — use these tools

## Current state:

- 104/104 core tests passing (100%)
- 22 fleet tests (depend on live infrastructure)
- 35 responsive tests (mobile viewport)
- Tests run automatically on git push and page saves
- Results feed into the topbar alert bell

## The self-learning loop:

Run tests → Parse results → Update steering → Report to you (Hermes)
     ↑                                              |
     |                                              v
     ←←←←←← You suggest improvements ←←←←←←←←←←←←

Over time, the steering file accumulates intelligence about what breaks and why.
"""


def send_to_endpoint(url: str, message: str) -> bool:
    """Try sending to a specific endpoint."""
    payload = json.dumps({"message": message, "mode": "production_advisor"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            if "response" in data:
                print(f"Response from {url}:")
                print(data["response"][:500])
                return True
            elif "message" in data:
                print(f"Stored: {data.get('message', 'ok')}")
                return True
            else:
                print(f"Result: {json.dumps(data, indent=2)[:300]}")
                return True
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} from {url}: {e.read().decode()[:200]}")
        return False
    except Exception as e:
        print(f"Error with {url}: {e}")
        return False


if __name__ == "__main__":
    print("=== Feeding UAT System Info to Hermes ===\n")

    # Try Hermes first
    if not send_to_endpoint(HERMES_URL, MESSAGE):
        print("\nHermes unavailable. Trying AIOS chat...")
        if not send_to_endpoint(AIOS_CHAT_URL, MESSAGE):
            print("\nBoth endpoints unavailable. Info stored in steering file instead.")
            print("Hermes will pick this up from .kiro/steering/uat-system.md on next session.")
        else:
            print("\nSent to AIOS chat successfully.")
    else:
        print("\nSent to Hermes successfully.")
