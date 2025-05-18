@echo off
echo Setting up environment...

if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
    if errorlevel 1 (
        echo Failed to create virtual environment
        pause
        exit /b 1
    )
)

echo Activating virtual environment...
call venv\Scripts\activate

echo Installing/Updating dependencies...
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install watchdog

echo Starting application with auto-restart...
python monitor.py

pause 