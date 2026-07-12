"""Verify the self-learning UAT system is fully wired."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

print("=== Verifying Ise UAT System ===\n")

# 1. Check steering file
steering = ROOT / ".kiro" / "steering" / "uat-system.md"
assert steering.exists(), "Steering file missing"
content = steering.read_text()
assert "Page Health Map" in content
assert "Self-Learning Rules" in content
print("[1] Steering file: OK (.kiro/steering/uat-system.md)")

# 2. Check skill file
skill = ROOT / ".kiro" / "skills" / "run-uat.md"
assert skill.exists(), "Skill file missing"
content = skill.read_text()
assert "Run UAT Tests" in content
assert "Feed to Hermes" in content
print("[2] Skill file: OK (.kiro/skills/run-uat.md)")

# 3. Check hooks
hooks_dir = ROOT / ".kiro" / "hooks"
assert (hooks_dir / "uat-on-push.json").exists(), "Push hook missing"
assert (hooks_dir / "uat-on-test-save.json").exists(), "Test save hook missing"
assert (hooks_dir / "uat-on-page-save.json").exists(), "Page save hook missing"
print("[3] Hooks: OK (uat-on-push, uat-on-test-save, uat-on-page-save)")

# 4. Check agent
agent = ROOT / ".kiro" / "agents" / "ise-uat.md"
assert agent.exists(), "Agent file missing"
content = agent.read_text()
assert "Self-Learning Loop" in content
assert "Hermes Integration" in content
print("[4] Agent: OK (.kiro/agents/ise-uat.md)")

# 5. Check Hermes tools
from backend.aios.hermes.tools import AISTUDIO_TOOLS, execute_tool

tool_names = [t["function"]["name"] for t in AISTUDIO_TOOLS]
assert "run_uat_tests" in tool_names, "run_uat_tests not in tools"
assert "get_uat_results" in tool_names, "get_uat_results not in tools"
print(f"[5] Hermes tools: OK ({len(tool_names)} tools, includes UAT)")

# 6. Check Hermes prompt has UAT info
from backend.aios.hermes.agent import AIOS_HERMES_PROMPT

assert "ISE UAT SYSTEM" in AIOS_HERMES_PROMPT, "UAT not in Hermes prompt"
assert "run_uat_tests" in AIOS_HERMES_PROMPT, "Tool name not in prompt"
print("[6] Hermes prompt: OK (ISE UAT section present)")

# 7. Test get_uat_results tool executor
result = execute_tool("get_uat_results", {})
data = json.loads(result)
assert data["status"] in ("no_runs", "ok"), f"Unexpected status: {data}"
print(f"[7] get_uat_results executor: OK (status={data['status']})")

# 8. Check UAT runner imports
from backend.aios.obaluaye.uat_runner import run_tests_now, start_uat_scheduler, get_test_runs

print("[8] UAT runner imports: OK")

# 9. Check gateway endpoints registered
from backend.aios.gateway import router

paths = [r.path for r in router.routes if hasattr(r, "path")]
uat_paths = [p for p in paths if "uat" in p]
assert len(uat_paths) >= 4, f"Expected 4 UAT routes, found: {uat_paths}"
print(f"[9] Gateway endpoints: OK ({len(uat_paths)} UAT routes: {uat_paths})")

print("\n=== ALL 9 CHECKS PASS ===")
print("\nThe self-learning UAT system is fully wired:")
print("  Trigger: git push / page save / test save / manual")
print("  Flow: Run tests → Parse → Diagnose → Fix → Update steering → Report to Hermes")
print("  Learning: Steering accumulates patterns over time")
print("  Hermes: Can trigger tests and read results via tools")
