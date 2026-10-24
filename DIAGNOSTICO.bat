@echo off
REM ============================================================
REM  DIAGNOSTICO.bat - Cripo_Mine  [v3.8 DESBLOQUEO]
REM  Doble clic = examen COMPLETO del bot en 1 minuto:
REM    - ¿Por qué no hay hashrate? (daemon, pools ZOMBIS, xmrig,
REM      Defender, secrets, pausas pegadas...)
REM    - REPARA solo lo reparable y ARRANCA el daemon si está caído
REM    - Todo en español claro, sin tecnicismos
REM  Si Windows pregunta por permisos de ADMINISTRADOR, acéptalos:
REM  son necesarios para blindar Defender y aplicar el MSR.
REM ============================================================
setlocal
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo   Solicitando permisos de ADMINISTRADOR ^(necesarios para
    echo   reparar Defender y el mod MSR^)... acepta la ventanita.
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
cd /d "%~dp0"
title DIAGNOSTICO - Cripo_Mine
echo.
where python >nul 2>nul
if errorlevel 1 (set PY=py -3) else (set PY=python)
%PY% diagnostico.py
echo.
echo   ==============================================
echo    Diagnostico terminado. Si el daemon fue
echo    arrancado, espera 1-2 min y abre el dashboard
echo    (CORRER_BOT.bat) para ver el hashrate.
echo   ==============================================
pause
