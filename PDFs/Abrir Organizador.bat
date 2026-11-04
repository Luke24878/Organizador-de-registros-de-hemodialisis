@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo La aplicacion aun no esta instalada.
    echo Ejecuta primero "Instalar.bat" con doble clic.
    pause
    exit /b 1
)

start "" ".venv\Scripts\pythonw.exe" "Aplicacion.py"
