@echo off
echo Creating virtual environment...
python -m venv .venv

echo.
echo Installing requirements...
.venv\Scripts\pip install -r requirements.txt

echo.
echo Installation completed!
echo Run start.bat to launch Chrome Profiles Manager.
pause
