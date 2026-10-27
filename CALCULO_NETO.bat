@echo off
REM ============================================================
REM  CALCULO_NETO.bat - Cripo_Mine v4.4
REM  La REGLA DEL NETO del plan costo/beneficio:
REM    bruto XMR del dia - luz del dia = NETO
REM  Te dice con TU hashrate, TU luz y TU tarifa:
REM    MINAR 24/7  /  SOLO HORAS OCIOSAS  /  APAGAR ESTA MAQUINA
REM  Lee el hashrate real del daemon si ya esta minando.
REM  Plan completo: doble clic VER_PLAN.bat
REM ============================================================
setlocal
cd /d "%~dp0"
title CALCULO DEL NETO - Cripo_Mine
where python >nul 2>nul
if errorlevel 1 (set PY=py -3) else (set PY=python)
%PY% calculadora_neta.py
echo.
pause
