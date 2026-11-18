@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Execute Preparar.cmd antes de abrir o SMB Camera.
    pause
    exit /b 1
)
set "SMB_CAMERA_OUTPUT=--alpha-output"
if /i "%~1"=="gpu" set "SMB_CAMERA_OUTPUT=--gpu-output"
set "SMB_CAMERA_DECODER=d3d11va"
if /i "%~2"=="cpu" set "SMB_CAMERA_DECODER=cpu"
".venv\Scripts\python.exe" -m ucs.desktop --decoder %SMB_CAMERA_DECODER% --renderer gl --matting-backend nvidia %SMB_CAMERA_OUTPUT%
if errorlevel 1 (
    echo O SMB Camera encontrou um erro. Confira a mensagem acima.
    pause
    exit /b 1
)
