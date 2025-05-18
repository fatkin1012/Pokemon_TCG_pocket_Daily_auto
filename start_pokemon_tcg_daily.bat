@echo off
setlocal EnableDelayedExpansion

echo Pokemon TCG Daily Assistant - Full Environment Launcher
echo ==================================================

:: Set Python path
set PYTHON_PATH=python

:: Check for virtual environment
if not exist "venv\Scripts\activate.bat" (
    echo Virtual environment not found. Creating...
    "%PYTHON_PATH%" -m venv venv
    if errorlevel 1 (
        echo Failed to create virtual environment. Please make sure Python is installed.
        pause
        exit /b 1
    )
)

:: Activate virtual environment
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo Failed to activate virtual environment.
    pause
    exit /b 1
)

:: Install/update dependencies
echo Checking dependencies...
pip install -r requirements.txt --quiet

:: Add watchdog for monitoring
pip install watchdog --quiet

:: Check command line arguments
set MODE=%1

if "%MODE%"=="" (
    goto :menu
) else if /i "%MODE%"=="normal" (
    goto :normal
) else if /i "%MODE%"=="monitor" (
    goto :monitor
) else (
    goto :menu
)

:menu
cls
echo Choose launch mode:
echo 1. Normal Mode - Run Pokemon TCG Daily Assistant directly
echo 2. Monitor Mode - Run with automatic restart on code changes
echo.
set /p CHOICE="Enter choice (1 or 2): "

if "!CHOICE!"=="1" goto :normal
if "!CHOICE!"=="2" goto :monitor
goto :menu

:normal
echo Starting Pokemon TCG Daily Assistant in normal mode...
python main.py
goto :end

:monitor
echo Starting Pokemon TCG Daily Assistant in monitor mode...
python monitor.py main.py
goto :end

:end
:: Deactivate virtual environment
call deactivate
echo Pokemon TCG Daily Assistant closed.
pause 