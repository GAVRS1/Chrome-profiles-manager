@echo off
:: Проверка на запуск от администратора
net session >nul 2>&1
if %errorlevel% NEQ 0 (
    echo Запуск с правами администратора...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: Переход в директорию скрипта
cd /d "%~dp0"

echo Checking virtual environment...

if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
    call venv\Scripts\activate.bat
    echo Installing requirements...
    pip install -r requirements.txt
)

echo.
echo Activating virtual environment...
call venv\Scripts\activate.bat

echo.
echo Starting Chrome Profiles Manager...
python "%~dp0src\main.py"

pause
