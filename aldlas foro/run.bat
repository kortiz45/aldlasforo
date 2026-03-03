@echo off
setlocal

cd /d "%~dp0"

if "%PORT%"=="" set "PORT=8000"

if not exist "venv\Scripts\python.exe" (
    echo [run] Creating virtual environment...
    where py >nul 2>&1
    if %errorlevel%==0 (
        py -m venv venv
    ) else (
        python -m venv venv
    )
    if errorlevel 1 goto :error
)

echo [run] Installing dependencies from requirements.txt...
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo [run] Starting API at http://127.0.0.1:%PORT%
venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port %PORT% --reload %*
goto :eof

:error
echo [run] Failed to start.
exit /b 1
