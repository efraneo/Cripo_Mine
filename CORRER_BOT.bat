@echo off
REM ============================================================
REM  CORRER_BOT.bat - Cripo_Mine (Windows)  [v3.7 - LA HIDRA]
REM  Doble clic = bot minando + pruebas + dashboard:
REM    0) PIDE ADMINISTRADOR SOLO (necesario para el mod MSR:
REM       sin el MSR el hashrate cae a menos de la mitad)
REM    1) sincroniza con GitHub (opcional; si falla sigue)
REM    2) verifica dependencias (pip install)
REM    3) arranca el DAEMON minero 24/7 (ventana propia)
REM       + DESPIERTA LA HIDRA (5 cabezas): configura xmrig a
REM         maximo, blinda Defender (carpeta + .exe + proceso),
REM         resucita xmrig.exe si el antivirus lo borra y
REM         vigila el hashrate contra tu record 24/7
REM    4) abre el DASHBOARD en tu navegador (ventana propia)
REM  Ademas, al arrancar, el bot envia a tu Telegram la
REM  PRUEBA DE GANANCIAS (saldo del pool + BTC/dia proyectado).
REM  Comandos Telegram: /estado /ganancias /hidra /apagar
REM  Para DETENER todo: doble clic en DETENER_TODO.bat
REM ============================================================
setlocal
REM ---- [0] Auto-elevacion a ADMINISTRADOR (acepta la ventanita UAC) ----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo   Solicitando permisos de ADMINISTRADOR...
    echo   ^(necesarios para el mod MSR: mas del doble de hashrate en Ryzen^)
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
cd /d "%~dp0"
title CORRER BOT - Cripo_Mine
echo.
echo   ==============================================
echo    CORRER EL BOT  -  Cripo_Mine v3.7 LA HIDRA
echo    Carpeta: %CD%
echo   ==============================================
echo.
where python >nul 2>nul
if errorlevel 1 (set PY=py -3) else (set PY=python)

echo   [1/4] Sincronizando con GitHub (si es la primera vez,
echo         te pedira autorizar en el navegador)...
%PY% sincronizar.py auto
echo.

echo   [2/4] Verificando dependencias...
%PY% -m pip install -q -r requirements.txt
echo         OK
echo.

echo   [3/4] Arrancando el DAEMON minero (ventana nueva)...
start "CripoMine DAEMON" cmd /k %PY% run_miner.py
timeout /t 4 /nobreak >nul

echo   [4/4] Abriendo el DASHBOARD (ventana nueva)...
start "CripoMine DASHBOARD" cmd /k %PY% -m streamlit run app.py

echo.
echo   ==============================================
echo    LISTO. El bot esta corriendo:
echo     - Ventana "CripoMine DAEMON"    = minero 24/7
echo     - Ventana "CripoMine DASHBOARD" = panel visual
echo     - Tu Telegram                   = PRUEBA DE GANANCIAS
echo       (y /ganancias /hidra /estado /apagar cuando quieras)
echo.
echo    LA HIDRA esta despierta: config optima + escudo Defender
echo    + medico de xmrig.exe + vigia de hashrate (5 cabezas).
echo    Si xmrig.exe aparece bloqueado: defender_fix.ps1
echo    (clic derecho > Ejecutar con PowerShell).
echo.
echo    Para DETENER TODO: doble clic en DETENER_TODO.bat
echo   ==============================================
timeout /t 10 >nul
