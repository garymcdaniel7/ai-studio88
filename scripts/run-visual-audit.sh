#!/bin/bash
# =============================================================================
# AI Studio — Visual Audit (End-to-End)
#
# This script:
# 1. Checks if frontend dev server is running, starts it if not
# 2. Checks if backend is running, starts it if not
# 3. Runs Playwright to screenshot every page
# 4. Reports results
#
# Usage:
#   ./scripts/run-visual-audit.sh
#
# Output: frontend/visual-audit/*.png (one screenshot per page)
# =============================================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_DIR/frontend"
OUTPUT_DIR="$FRONTEND_DIR/visual-audit"

echo "╔══════════════════════════════════════════════╗"
echo "║       AI Studio — Visual Audit              ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# =============================================================================
# 1. Check/Start Backend
# =============================================================================
echo "[1/4] Checking backend (port 8000)..."
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "      ✓ Backend already running"
    BACKEND_STARTED=false
else
    echo "      Starting backend..."
    cd "$PROJECT_DIR"
    /Users/garymcdaniel/.local/bin/uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
    BACKEND_PID=$!
    BACKEND_STARTED=true
    # Wait for it to be ready
    for i in $(seq 1 15); do
        if curl -s http://localhost:8000/ > /dev/null 2>&1; then
            echo "      ✓ Backend started (PID: $BACKEND_PID)"
            break
        fi
        sleep 1
    done
fi

# =============================================================================
# 2. Check/Start Frontend
# =============================================================================
echo "[2/4] Checking frontend (port 3000)..."
if curl -s http://localhost:3000/ > /dev/null 2>&1; then
    echo "      ✓ Frontend already running"
    FRONTEND_STARTED=false
else
    echo "      Starting frontend..."
    cd "$FRONTEND_DIR"
    npm run dev &
    FRONTEND_PID=$!
    FRONTEND_STARTED=true
    # Wait for it to be ready
    for i in $(seq 1 30); do
        if curl -s http://localhost:3000/ > /dev/null 2>&1; then
            echo "      ✓ Frontend started (PID: $FRONTEND_PID)"
            break
        fi
        sleep 1
    done
fi

# =============================================================================
# 3. Run Visual Audit
# =============================================================================
echo "[3/4] Capturing screenshots..."
cd "$FRONTEND_DIR"
mkdir -p "$OUTPUT_DIR"

npx playwright test e2e/visual-audit.spec.ts --project=desktop --reporter=list 2>&1 | grep -E "✓|✗|passed|failed"

# =============================================================================
# 4. Report Results
# =============================================================================
echo ""
echo "[4/4] Results:"
SCREENSHOT_COUNT=$(ls "$OUTPUT_DIR"/*.png 2>/dev/null | wc -l)
echo "      $SCREENSHOT_COUNT screenshots captured in: $OUTPUT_DIR/"
echo ""
ls -la "$OUTPUT_DIR"/*.png 2>/dev/null | awk '{print "      " $NF " (" $5 " bytes)"}'
echo ""
echo "════════════════════════════════════════════════"
echo "  Next: Feed screenshots to @redteam for review"
echo "  Drag images into Kiro chat and ask:"
echo "  '@redteam review these for visual issues'"
echo "════════════════════════════════════════════════"

# Cleanup: stop services we started
if [ "$BACKEND_STARTED" = true ] && [ -n "$BACKEND_PID" ]; then
    echo ""
    echo "Note: Backend running as PID $BACKEND_PID (kill manually when done)"
fi
if [ "$FRONTEND_STARTED" = true ] && [ -n "$FRONTEND_PID" ]; then
    echo "Note: Frontend running as PID $FRONTEND_PID (kill manually when done)"
fi
