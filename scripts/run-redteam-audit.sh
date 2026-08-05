#!/bin/bash
# =============================================================================
# Red Team Interactive Audit — Visual + Button Interaction Audit
#
# Modes:
#   ./scripts/run-redteam-audit.sh              — Headless (screenshots only)
#   ./scripts/run-redteam-audit.sh --headed     — Opens browser window (watch it)
#   ./scripts/run-redteam-audit.sh --slow       — Headed + 500ms delay between actions
#   ./scripts/run-redteam-audit.sh --debug      — Headed + 1000ms delay + pauses
#
# Output:
#   frontend/redteam-audit/*.png                — Full page screenshots
#   frontend/redteam-audit/interactions/*.png   — After-click screenshots
#   frontend/redteam-audit/REDUNDANCY_REPORT.md — Auto-generated findings
#
# Then: Feed screenshots + report to @redteam in Kiro for strategic review
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_DIR/frontend"
OUTPUT_DIR="$FRONTEND_DIR/redteam-audit"

# Parse arguments
MODE="headless"
SLOW_MO=0
EXTRA_ARGS=""

for arg in "$@"; do
  case $arg in
    --headed)
      MODE="headed"
      EXTRA_ARGS="--headed"
      ;;
    --slow)
      MODE="slow"
      EXTRA_ARGS="--headed"
      SLOW_MO=500
      ;;
    --debug)
      MODE="debug"
      EXTRA_ARGS="--headed"
      SLOW_MO=1000
      ;;
  esac
done

echo "╔══════════════════════════════════════════════════════╗"
echo "║     Red Team Interactive Audit — AI Studio          ║"
echo "║     Mode: $MODE                                     ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Check if frontend is running
echo "[1/3] Checking frontend (port 3000)..."
if curl -s http://localhost:3000/ > /dev/null 2>&1; then
    echo "      ✓ Frontend running"
else
    echo "      ✗ Frontend not running. Start with: cd frontend && npm run dev"
    echo "      (Or this script will use Playwright's built-in webServer config)"
fi

# Check if backend is running
echo "[2/3] Checking backend (port 8000)..."
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "      ✓ Backend running"
else
    echo "      ⚠ Backend not running — pages may show loading states only"
fi

# Run the audit
echo "[3/3] Running Playwright audit..."
echo "      Output: $OUTPUT_DIR/"
echo ""

cd "$FRONTEND_DIR"
mkdir -p "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR/interactions"

SLOW_MO=$SLOW_MO npx playwright test ../scripts/redteam-interactive-audit.ts \
  --project=desktop \
  --workers=1 \
  --reporter=list \
  $EXTRA_ARGS \
  2>&1 | grep -v "^$"

# Results
echo ""
echo "════════════════════════════════════════════════════════"
echo "  Audit Complete!"
echo ""
SCREENSHOT_COUNT=$(ls "$OUTPUT_DIR"/*.png 2>/dev/null | wc -l | tr -d ' ')
INTERACTION_COUNT=$(ls "$OUTPUT_DIR/interactions"/*.png 2>/dev/null | wc -l | tr -d ' ')
echo "  Screenshots: $SCREENSHOT_COUNT pages"
echo "  Interactions: $INTERACTION_COUNT button clicks"
echo ""
if [ -f "$OUTPUT_DIR/REDUNDANCY_REPORT.md" ]; then
    echo "  Report: $OUTPUT_DIR/REDUNDANCY_REPORT.md"
    echo ""
    echo "  Quick findings:"
    grep "^###" "$OUTPUT_DIR/REDUNDANCY_REPORT.md" 2>/dev/null | head -5
fi
echo ""
echo "  Next steps:"
echo "  1. Open screenshots in Finder: open $OUTPUT_DIR/"
echo "  2. Drag images into Kiro chat"
echo "  3. Ask: '@redteam review these for redundancies'"
echo "════════════════════════════════════════════════════════"
