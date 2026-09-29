#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null && command -v python &> /dev/null; then
    PYTHON_CMD="python"
fi

echo "=== Launching Standards Navigator ==="

# Trap cleanup to stop backend when frontend exits or script is interrupted
cleanup() {
    echo ""
    echo "Stopping backend process..."
    if [ -n "$BACKEND_PID" ]; then
        kill "$BACKEND_PID" 2>/dev/null || true
    fi
    exit 0
}
trap cleanup EXIT INT TERM

# Start backend in background
echo "Starting FastAPI backend on port 8000..."
$PYTHON_CMD -m uvicorn app.main:app --port 8000 &
BACKEND_PID=$!

echo "Starting Next.js frontend on port 3000..."
echo ""
echo "Standards Navigator is starting!"
echo "  Frontend: http://localhost:3000"
echo "  Backend API: http://localhost:8000"
echo "  API Docs (Swagger): http://localhost:8000/docs"
echo ""

# Start frontend in foreground
cd "$ROOT_DIR/frontend"
npm run dev
