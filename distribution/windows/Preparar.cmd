@echo off
setlocal
cd /d "%~dp0"

py -3.11 -c "import struct,sys; assert struct.calcsize('P') == 8 and sys.platform == 'win32'" >nul 2>&1
if errorlevel 1 (
    echo Instale o Python 3.11 x64 com o launcher py e abra este arquivo novamente.
    goto failed
)
py -3.11 -c "from pathlib import Path; from shutil import which; assert which('openssl') or Path('C:/Program Files/Git/usr/bin/openssl.exe').is_file()" >nul 2>&1
if errorlevel 1 (
    echo Instale o Git for Windows em sua pasta padrao, ou deixe o OpenSSL disponivel no PATH.
    goto failed
)
if not exist ".venv\Scripts\python.exe" (
    py -3.11 -m venv .venv
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -c "import struct,sys,tkinter; assert sys.version_info[:2] == (3,11) and struct.calcsize('P') == 8"
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip --isolated --disable-pip-version-check install --index-url https://pypi.org/simple --require-hashes --only-binary=:all: -r requirements-windows-beta.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -c "from ucs.sdl_preview import native_path; native_path()" >nul 2>&1
if errorlevel 1 (
    ".venv\Scripts\python.exe" tools\install_sdl.py
    if errorlevel 1 goto failed
)
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto failed
echo.
echo Pronto. Abra "Abrir SMB Camera.cmd".
if not defined SMB_CAMERA_NONINTERACTIVE pause
exit /b 0

:failed
echo.
echo A preparacao falhou. Confira a mensagem acima.
if not defined SMB_CAMERA_NONINTERACTIVE pause
exit /b 1
