@echo off
REM ============================================================
REM  SELECTOR.bat - Cripo_Mine v4.6 MULTI
REM  Muestra la tabla de rutas (XMR vs Verus vs GhostRider)
REM  con precios vivos y que ruta eligio el bot para TU cpu.
REM  El daemon re-evalua solo cada SELECTOR_CADA_HORAS horas;
REM  esto es la vista rapida del mismo calculo.
REM ============================================================
setlocal
cd /d "%~dp0"
title SELECTOR MULTI - Cripo_Mine
where python >nul 2>nul
if errorlevel 1 (set PY=py -3) else (set PY=python)
%PY% selector_moneda.py --print
echo.
pause
