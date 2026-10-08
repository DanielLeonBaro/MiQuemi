@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "MIQUEMI_PYTHON="
py -3 -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 set "MIQUEMI_PYTHON=py -3"
if not defined MIQUEMI_PYTHON (
    python -c "import sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
    if not errorlevel 1 set "MIQUEMI_PYTHON=python"
)
if not defined MIQUEMI_PYTHON (
    echo Necesitas Python 3.10 o posterior. Instala Python desde https://www.python.org/downloads/
    echo Al instalarlo, activa Add Python to PATH y vuelve a abrir este archivo.
    pause
    exit /b 1
)
pushd "%~dp0"
if errorlevel 1 (
    echo No se pudo abrir la carpeta de MiQuemi.
    pause
    exit /b 1
)
set "HOST=127.0.0.1"
set "PORT=8000"
echo Iniciando MiQuemi. Conserva esta ventana abierta mientras usas la pagina.
%MIQUEMI_PYTHON% -u server.py --open-browser
set "MIQUEMI_EXIT=%ERRORLEVEL%"
popd
echo.
echo El servidor se detuvo. Si hubo un error, aparece arriba.
pause
exit /b %MIQUEMI_EXIT%
