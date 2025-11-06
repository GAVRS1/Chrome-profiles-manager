@echo off
cd /d "G:\work\Chrome-profiles-manager"

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
python src\main.py
pause
