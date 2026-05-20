@echo off
echo ================================================
echo  Outbound Assistant - Starting all services...
echo ================================================

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Start ngrok tunnel in a new window
echo [1/2] Starting ngrok tunnel...
start "ngrok" cmd /k "ngrok http 8000"

:: Wait a moment for ngrok to establish
timeout /t 3 /nobreak >nul

:: Start FastAPI server in a new window
echo [2/2] Starting FastAPI server...
start "FastAPI" cmd /k "uvicorn app.api.fastapi_app:app --host 0.0.0.0 --port 8000 --reload"

echo.
echo ================================================
echo  All services started!
echo.
echo  NEXT STEPS:
echo  1. Copy your ngrok URL from the ngrok window
echo  2. Update TWILIO_STATUS_CALLBACK_URL in .env
echo  3. Update Twilio webhook at console.twilio.com
echo  4. Run: python scripts/trigger_test_call.py
echo ================================================
pause
