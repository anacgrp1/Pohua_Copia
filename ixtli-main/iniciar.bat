@echo off
chcp 65001 >nul
title Ixtli – CGR Automation Suite

echo.
echo ╔═══════════════════════════════════════════╗
echo ║         Ixtli  ^|  CGR Automation            ║
echo ╚═══════════════════════════════════════════╝
echo.

:: ── Verificar Python ────────────────────────────────────────────────────────
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no encontrado. Instala Python 3.10+ y agrega al PATH.
    pause
    exit /b 1
)

:: ── Instalar dependencias si es necesario ───────────────────────────────────
echo Verificando dependencias...
pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo ADVERTENCIA: Hubo un problema instalando dependencias.
)

:: ── Registrar pywin32 (ruta dinámica, funciona en cualquier PC) ─────────────
python -c "import win32com.client" >nul 2>&1
if %errorlevel% neq 0 (
    echo Registrando pywin32...
    python -c "import sys, os, subprocess; scripts=os.path.join(os.path.dirname(sys.executable),'Scripts','pywin32_postinstall.py'); subprocess.call([sys.executable, scripts, '-install']) if os.path.exists(scripts) else None" >nul 2>&1
    pip install --quiet --force-reinstall pywin32
    python -c "import sys, os, subprocess; scripts=os.path.join(os.path.dirname(sys.executable),'Scripts','pywin32_postinstall.py'); subprocess.call([sys.executable, scripts, '-install']) if os.path.exists(scripts) else None" >nul 2>&1
)

echo.
echo Iniciando aplicacion...
echo.
python src\main.py

if %errorlevel% neq 0 (
    echo.
    echo ERROR: La aplicacion termino con errores.
    pause
)
