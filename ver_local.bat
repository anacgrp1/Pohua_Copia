@echo off
REM ===========================================================================
REM  CGR Cotizador - Vista local
REM
REM  Doble clic en este archivo para ver el cotizador en tu computadora, sin
REM  subir nada a git ni tocar el sitio de Render.
REM
REM  Toda la logica esta en scripts\ver_local.py; esto solo busca Python y lo
REM  llama, para que un problema aqui se vea claro en vez de fallar en silencio.
REM ===========================================================================

setlocal
cd /d "%~dp0"

REM Pagina de codigos UTF-8: sin esto los acentos de los mensajes salen como
REM simbolos raros en cmd.exe. El >nul traga el "Active code page: 65001".
chcp 65001 >nul 2>&1

echo.
echo   Buscando Python...

REM El lanzador "py" es el que instala Python en Windows por defecto.
REM Si no esta, se prueba con "python" del PATH.
set PYEXE=
py -3 --version >nul 2>&1 && set PYEXE=py -3
if not defined PYEXE (
    python --version >nul 2>&1 && set PYEXE=python
)

if not defined PYEXE (
    echo.
    echo   [ERROR] No encontre Python en esta computadora.
    echo.
    echo   Instalalo desde https://www.python.org/downloads/
    echo   IMPORTANTE: en la primera pantalla del instalador, marca la casilla
    echo   "Add Python to PATH" antes de darle a instalar.
    echo.
    pause
    exit /b 1
)

%PYEXE% scripts\ver_local.py
set CODIGO=%ERRORLEVEL%

if not "%CODIGO%"=="0" (
    echo.
    echo   El servidor termino con codigo %CODIGO%.
    echo   Si arriba dice que faltan dependencias, corre esto una vez:
    echo.
    echo       pip install -r requirements.txt
    echo.
)

echo.
pause
endlocal
