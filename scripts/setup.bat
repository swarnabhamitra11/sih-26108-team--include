@echo off
cd /d "%~dp0.."
for %%T in (docker python node) do (
  where %%T >nul 2>nul || (echo Missing %%T. Install Docker Desktop, Python 3.10+, Node 18+. & exit /b 1)
)
if not exist .env copy .env.example .env
docker compose up -d
set /a tries=0
:wait
docker compose exec -T db pg_isready -U user >nul 2>nul && goto ready
set /a tries+=1
if %tries% GEQ 30 (echo Database not ready. Is Docker Desktop running? & exit /b 1)
timeout /t 3 >nul
goto wait
:ready
python -m pip install -r requirements.txt
python scripts\init_db.py
python scripts\import_seed.py
if exist scripts\reembed.py python scripts\reembed.py
cd frontend
call npm install
cd ..
echo Setup done. Now run scripts\run.bat
