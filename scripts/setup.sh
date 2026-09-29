#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

echo "=== Standards Navigator: Evaluator Setup ==="

# 1. Dependency checks
MISSING=0

if ! command -v docker &> /dev/null; then
    echo "[ERROR] Docker is not installed or not in PATH."
    echo "        Please install Docker: https://docs.docker.com/get-docker/"
    MISSING=1
fi

PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "[ERROR] Python 3 is not installed or not in PATH."
    echo "        Please install Python 3.10+: https://www.python.org/downloads/"
    MISSING=1
fi

if ! command -v node &> /dev/null; then
    echo "[ERROR] Node.js is not installed or not in PATH."
    echo "        Please install Node.js 18+ LTS: https://nodejs.org/"
    MISSING=1
fi

if ! command -v npm &> /dev/null; then
    echo "[ERROR] npm is not installed or not in PATH."
    echo "        Please install npm (included with Node.js)."
    MISSING=1
fi

if [ $MISSING -ne 0 ]; then
    exit 1
fi

# Verify Docker daemon is running
if ! docker info &> /dev/null; then
    echo "[ERROR] Docker daemon is not running."
    echo "        Please start Docker Desktop or the dockerd service and retry."
    exit 1
fi

# 2. Setup .env file
if [ ! -f "$ROOT_DIR/.env" ]; then
    echo "Creating .env from .env.example..."
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
else
    echo ".env already exists, keeping existing configuration."
fi

# 3. Start database and wait until healthy
echo "Starting database via docker compose..."
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

$DOCKER_COMPOSE up -d

echo "Waiting for database container to be healthy (timeout: 90s)..."
TIMEOUT=90
ELAPSED=0
HEALTHY=0

while [ $ELAPSED -lt $TIMEOUT ]; do
    sleep 2
    ELAPSED=$((ELAPSED + 2))
    STATUS=$($DOCKER_COMPOSE ps 2>&1)
    if echo "$STATUS" | grep -q "(healthy)"; then
        HEALTHY=1
        break
    fi
done

if [ $HEALTHY -eq 0 ]; then
    echo "[ERROR] Database container failed to become healthy within 90s."
    $DOCKER_COMPOSE ps
    $DOCKER_COMPOSE logs --tail 20
    exit 1
fi
echo "Database is healthy."

# 4. Install Python dependencies
echo "Installing Python dependencies from requirements.txt..."
$PYTHON_CMD -m pip install -r requirements.txt

# 5. Database initialization, seed import, and embeddings
echo "Initializing database schema (idempotent)..."
$PYTHON_CMD scripts/init_db.py

echo "Importing seed data (idempotent)..."
$PYTHON_CMD scripts/import_seed.py

echo "Generating / verifying embeddings..."
$PYTHON_CMD scripts/reembed.py

# 6. Install frontend dependencies
echo "Installing frontend dependencies..."
(cd "$ROOT_DIR/frontend" && npm install)

# 7. Complete
echo ""
echo "Setup done. Start the app with scripts/run.sh"
