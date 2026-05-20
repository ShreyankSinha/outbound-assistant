@echo off
echo ================================================
echo  Outbound Assistant - Starting all services...
echo ================================================

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Start ngrok tunnel in a new window (static domain)
echo [1/2] Starting ngrok tunnel...
start "ngrok" cmd /k "ngrok http 8000 --domain=unlit-stratus-unsubtly.ngrok-free.app"

:: Wait a moment for ngrok to establish
timeout /t 3 /nobreak >nul

:: Start FastAPI server in a new window
echo [2/2] Starting FastAPI server...
start "FastAPI" cmd /k "uvicorn app.api.fastapi_app:app --host 0.0.0.0 --port 8000 --reload"

echo.
echo ================================================
echo  All services started!
echo  - ngrok:   https://unlit-stratus-unsubtly.ngrok-free.app
echo  - FastAPI: http://localhost:8000
echo.
echo  To trigger a call, run in another terminal:
echo    python scripts/trigger_test_call.py
echo ================================================
pause
