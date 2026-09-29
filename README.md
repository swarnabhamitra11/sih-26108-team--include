# Standards Navigator

Precision search, citation verification, and compliance navigator for Indian Standards (BIS).

## Prerequisites
- Docker Desktop (must be running; PostgreSQL pgvector runs on host port `5433`)
- Python 3.10+ (with dependencies in `requirements.txt`)
- Node.js 18+ and npm (for the Next.js frontend)

## Run Locally (Windows PowerShell)

Ensure Docker Desktop is running before executing commands. Note that the PostgreSQL database is mapped to localhost port **5433**.

### 1. Start the Database
```powershell
docker compose up -d
```

### 2. Run the Backend API (FastAPI)
```powershell
python -m uvicorn app.main:app --reload --port 8000
```
Backend will be live at:
- API Root: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/api/health`
- Stats: `http://localhost:8000/api/stats`

### 3. Run the Frontend (Next.js)
```powershell
cd frontend
npm install
npm run dev
```
Frontend will be live at `http://localhost:3000`.

## Testing & Smoke Tests
Run unit tests (no live DB required):
```powershell
pytest
```

Run retrieval smoke tests against the live database:
```powershell
python scripts/smoke_test.py
```
Results are advisory and require human engineer review before use in production.

## Quick start for evaluators (Windows PowerShell)
Prerequisites: Docker Desktop (running), Python 3.10+, Node 18+, internet on first run (embedding model download).

    scripts\setup.bat
    scripts\run.bat

Then open http://localhost:3000. The database runs on port 5433.

Try these queries: "ordinary portland cement", "XLPE cable 33 kV", "TMT bars for building construction", and "asdfgh qwerty zxcv" (should abstain).
Try these citations: IS 269:2013, IS 1489, ISO 9001:2015.

No Docker or Node? Run the logic tests only: python -m pytest

Troubleshooting: "Backend not reachable" means the backend window is not running; port 5433 busy means stop the other Postgres or change POSTGRES_PORT in .env.

## Quick start for evaluators (Windows PowerShell)
Prerequisites: Docker Desktop (running), Python 3.10+, Node 18+, internet on first run (embedding model download).

    scripts\setup.bat
    scripts\run.bat

Then open http://localhost:3000. The database runs on port 5433.

Try these queries: "ordinary portland cement", "XLPE cable 33 kV", "TMT bars for building construction", and "asdfgh qwerty zxcv" (should abstain).
Try these citations: IS 269:2013, IS 1489, ISO 9001:2015.

No Docker or Node? Run the logic tests only: python -m pytest

Troubleshooting: "Backend not reachable" means the backend window is not running; port 5433 busy means stop the other Postgres or change POSTGRES_PORT in .env.

## Quick start for evaluators (Windows PowerShell)
Prerequisites: Docker Desktop (running), Python 3.10+, Node 18+, internet on first run (embedding model download).

    scripts\setup.bat
    scripts\run.bat

Then open http://localhost:3000. The database runs on port 5433.

Try these queries: "ordinary portland cement", "XLPE cable 33 kV", "TMT bars for building construction", and "asdfgh qwerty zxcv" (should abstain).
Try these citations: IS 269:2013, IS 1489, ISO 9001:2015.

No Docker or Node? Run the logic tests only: python -m pytest

Troubleshooting: "Backend not reachable" means the backend window is not running; port 5433 busy means stop the other Postgres or change POSTGRES_PORT in .env.

