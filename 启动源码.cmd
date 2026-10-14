@echo off
setlocal
cd /d "%~dp0"
set "APP_PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%APP_PYTHON%" (
  echo Project Python environment is missing.
  echo Create .venv and install requirements.txt first.
  pause
  exit /b 1
)
"%APP_PYTHON%" -c "import pyaudiowpatch; import tkinter"
if errorlevel 1 (
  echo Required packages are missing from the PROJECT environment.
  echo Run this command in the project folder:
  echo .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)
if /I "%~1"=="--check" exit /b 0
"%APP_PYTHON%" "%~dp0app.py"
if errorlevel 1 pause
