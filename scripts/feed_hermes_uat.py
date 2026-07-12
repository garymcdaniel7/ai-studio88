"""Feed Playwright UAT results to Hermes/Ollama for analysis and enhancement suggestions."""

import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/generate"

message = """You are the AI Studio Production Advisor. Ise (our QA agent) just completed a full Playwright E2E test run across all 19 frontend pages.

GRAND TOTAL: 102/104 tests passing (98% pass rate)

Phase 1 Navigation (28/28 PASS): All 16 routes load, sidebar links navigate, brain popup works, page refresh stability verified.
Phase 2 Brain (7/7 PASS): Chat input, send button, brain modes, message sending, conversation history, health indicator.
Phase 3 Create/Editor/Workflows (14/14 PASS): Prompt input, model selector, generate button, resolution options, workflow cards, editor tools.
Phase 4 Talent/Assets/Models (17/19, 2 FAIL): Models page upload form + LoRA fields tests expect input[type=file] that page no longer exposes.
Phase 5 Production/Publish/Analytics (14/14 PASS): Worker status, launch button, job queue, social platforms, time range selector, GPU cost.
Phase 6 Admin/Training/Settings (22/22 PASS): Service cards, toggles, health indicators, training form, settings profile.
Phase 7 Fleet/Full-flow/Responsive (65/65 PASS): Fleet UI+API (22), full user flows (8), mobile responsive all pages (35).

ISSUES:
1. Models page: no standard input[type=file] - upload mechanism changed
2. Admin page: h1 slow on cold load (10s+) - heavy data fetching on mount
3. Some pages intermittently slow - API polling starts before DOM ready

Answer concisely:
1. What UI/UX improvements do you recommend?
2. What additional test coverage should we add?
3. Which patterns feel brittle?
4. How to fix cold-load performance?
5. How should Models upload be redesigned?"""

payload = json.dumps({
    "model": "llama3.1:8b",
    "prompt": message,
    "stream": False,
    "options": {"num_predict": 1000, "temperature": 0.7}
}).encode()

req = urllib.request.Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"})

try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
        print("=== HERMES (via Ollama llama3.1:8b) ANALYSIS ===\n")
        print(data.get("response", "No response"))
except urllib.error.HTTPError as e:
    print(f"HTTP {e.code}: {e.read().decode()}")
except Exception as e:
    print(f"Error: {e}")
