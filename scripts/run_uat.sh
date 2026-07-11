#!/bin/bash
# =============================================================================
# AI Studio — Full UAT Test Runner
# =============================================================================
# Installs Playwright, runs E2E tests, captures screenshots + traces
#
# Usage:
#   chmod +x scripts/run_uat.sh
#   ./scripts/run_uat.sh
#
# Prerequisites:
#   - Frontend running on localhost:3000 (npm run dev in frontend/)
#   - Backend running on localhost:8000 (uv run uvicorn backend.main:app)
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════════╗"
echo "║   AI Studio — UAT Test Suite         ║"
echo -e "╚══════════════════════════════════════╝${NC}"
echo ""

cd "$(dirname "$0")/../frontend"

# Step 1: Verify services
echo -e "${YELLOW}[1/4] Verifying services...${NC}"
if curl -s http://localhost:3000/ > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Frontend (localhost:3000)"
else
    echo -e "  ${RED}✗${NC} Frontend not running. Start: cd frontend && npm run dev"
    exit 1
fi

if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo -e "  ${GREEN}✓${NC} Backend (localhost:8000)"
else
    echo -e "  ${RED}✗${NC} Backend not running. Start: uv run uvicorn backend.main:app --reload"
    exit 1
fi

# Step 2: Install Playwright browsers (if needed)
echo -e "${YELLOW}[2/4] Checking Playwright browsers...${NC}"
if [ ! -d "$HOME/Library/Caches/ms-playwright/chromium-1228" ] && [ ! -d "$HOME/.cache/ms-playwright/chromium-1228" ]; then
    echo "  Installing Chromium..."
    npx playwright install chromium
else
    echo -e "  ${GREEN}✓${NC} Chromium already installed"
fi

# Step 3: Run tests
echo -e "${YELLOW}[3/4] Running E2E tests...${NC}"
echo ""

npx playwright test --reporter=list 2>&1 | tee /tmp/uat_results.txt

# Step 4: Generate report
echo ""
echo -e "${YELLOW}[4/4] Generating HTML report...${NC}"
npx playwright show-report --host 0.0.0.0 --port 9323 &
REPORT_PID=$!

echo ""
echo -e "${GREEN}╔══════════════════════════════════════╗"
echo "║   UAT Complete!                      ║"
echo -e "╚══════════════════════════════════════╝${NC}"
echo ""
echo "  Results: /tmp/uat_results.txt"
echo "  Report:  http://localhost:9323 (press Ctrl+C to stop)"
echo "  Traces:  frontend/test-results/"
echo ""

# Wait for user
wait $REPORT_PID 2>/dev/null
