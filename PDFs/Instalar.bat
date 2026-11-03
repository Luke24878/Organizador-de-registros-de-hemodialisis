@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Instalador - Organizador de Hemodialisis

echo.
echo ================================================
echo   Instalador del Organizador de Hemodialisis
echo ================================================
echo.

set "PYTHON_CMD="
py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
    python --version >nul 2>&1 && set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
    echo Python no esta instalado en esta computadora.
    echo.
    where winget >nul 2>&1
    if errorlevel 1 (
        echo Instala Python 3 desde https://www.python.org/downloads/
        echo Durante la instalacion marca la opcion "Add Python to PATH".
        echo Despues vuelve a abrir este archivo.
        pause
        exit /b 1
    )

    choice /M "Deseas instalar Python ahora usando winget"
    if errorlevel 2 (
        echo Instalacion cancelada. Ejecuta este archivo despues de instalar Python.
        pause
        exit /b 1
    )

    winget install -e --id Python.Python.3.12
    if errorlevel 1 (
        echo No fue posible instalar Python automaticamente.
        echo Descargalo desde https://www.python.org/downloads/ y vuelve a intentar.
        pause
        exit /b 1
    )

    echo.
    echo Python se instalo. Cierra esta ventana y ejecuta Instalar.bat otra vez.
    pause
    exit /b 0
)

echo Creando el entorno de la aplicacion...
%PYTHON_CMD% -m venv .venv
if errorlevel 1 (
    echo No se pudo crear el entorno de la aplicacion.
    pause
    exit /b 1
)

echo Instalando componentes necesarios...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo No se pudieron instalar los componentes. Revisa la conexion a internet.
    pause
    exit /b 1
)

echo.
echo Instalacion terminada correctamente.
echo A partir de ahora abre "Abrir Organizador.bat" con doble clic.
pause
