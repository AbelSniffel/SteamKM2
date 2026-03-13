@echo off
echo Starting SteamKM2...
python main.py
if errorlevel 1 (
    echo.
    echo Error: Failed to start SteamKM2
    echo Please ensure Python and PySide6 are installed
    echo.
    echo To install dependencies:
    echo pip install -r requirements.txt
    echo.
    pause
)
