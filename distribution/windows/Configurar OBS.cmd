@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Execute Preparar.cmd antes de configurar o OBS.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" "tools\obs_setup.py"
