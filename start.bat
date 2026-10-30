@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found in PATH. Install Python or activate a virtual environment.
    pause
    exit /b 1
)

python bot.py
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" (
    echo.
    echo Bot exited with code %EXIT_CODE%.
    pause
)
exit /b %EXIT_CODE%
