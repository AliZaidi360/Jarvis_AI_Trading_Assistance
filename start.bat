@echo off
echo Starting JARVIS Paper Trading System...
echo ----------------------------------------

:: Start Backend API & UI
start "JARVIS Backend" cmd /k "python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000"

:: Wait a moment
timeout /t 3

:: Start Trading Bot
start "JARVIS Bot" cmd /k "python main.py"

echo.
echo System Launched.
echo Open http://127.0.0.1:8000/ui in your browser to view the Dashboard.
echo.
pause
