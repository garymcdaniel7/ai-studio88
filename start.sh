#!/bin/bash
# =============================================================================
# AI Studio — Start All Services
# =============================================================================
# Usage: ./start.sh
#
# Starts:
#   1. Ollama (local LLM for Brain)
#   2. FastAPI backend (port 8000)
#   3. Next.js frontend (port 3000)
# =============================================================================

set -e

echo "=============================================="
echo "  AI Studio — Starting All Services"
echo "=============================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Check if Ollama is installed
if command -v ollama &> /dev/null; then
    echo -e "${GREEN}[1/3]${NC} Starting Ollama..."
    # Start Ollama if not already running
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        ollama serve > /dev/null 2>&1 &
        sleep 2
        echo "       Ollama started on port 11434"
    else
        echo "       Ollama already running"
    fi
    # Ensure model is available
    if ! ollama list 2>/dev/null | grep -q "llama3.1:8b"; then
        echo -e "${YELLOW}       Pulling llama3.1:8b (first time only)...${NC}"
        ollama pull llama3.1:8b &
    fi
else
    echo -e "${YELLOW}[1/3]${NC} Ollama not installed. Brain will be offline."
    echo "       Install: brew install ollama"
fi

# Start FastAPI backend
echo -e "${GREEN}[2/3]${NC} Starting FastAPI backend (port 8000)..."
cd "$(dirname "$0")"
uv run uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload > /dev/null 2>&1 &
BACKEND_PID=$!
sleep 3

# Verify backend
if curl -s http://localhost:8000/ > /dev/null 2>&1; then
    echo "       Backend running on http://localhost:8000"
else
    echo -e "${YELLOW}       Backend may still be starting...${NC}"
fi

# Start Next.js frontend
echo -e "${GREEN}[3/3]${NC} Starting Next.js frontend (port 3000)..."
cd frontend
npm run dev -- --port 3000 > /dev/null 2>&1 &
FRONTEND_PID=$!
sleep 3
echo "       Frontend running on http://localhost:3000"

echo ""
echo "=============================================="
echo "  AI Studio is running!"
echo ""
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo "  Ollama:    http://localhost:11434"
echo "=============================================="
echo ""
echo "Press Ctrl+C to stop all services."

# Wait for interrupt
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo 'Stopped.'" EXIT
wait
