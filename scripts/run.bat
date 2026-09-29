@echo off
cd /d "%~dp0.."
start "Backend" cmd /k python -m uvicorn app.main:app --port 8000
start "Frontend" cmd /k "cd frontend && npm run dev"
echo Open http://localhost:3000
