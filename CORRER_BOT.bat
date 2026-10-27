@echo off
REM ============================================================
REM  CORRER_BOT.bat - Cripo_Mine (Windows)  [v4.2 PUENTE-DASHBOARD]
REM  Doble clic = bot minando + pruebas + dashboard:
REM    0) PIDE ADMINISTRADOR SOLO (necesario para el mod MSR:
REM       sin el MSR el hashrate cae a menos de la mitad)
REM    1) sincroniza con GitHub (opcional; si falla sigue)
REM    2) verifica dependencias (pip install)
REM    3) arranca el DAEMON minero 24/7 (ventana propia)
REM       + 7 POOLS (v3.9): unMineable + ZergPool pagan en BTC
REM         directo a Binance; MoneroOcean/Kryptex/SupportXMR de
REM         respaldo. Solo mina en pools VIVOS (sondeo stratum real)
REM         + HIDRA (5 cabezas)
REM    4) abre el DASHBOARD en tu navegador (ventana propia)
REM  ¿Hashrate 0 o "no hace nada"? -> doble clic DIAGNOSTICO.bat
REM  (examina todo, repara lo reparable y arranca el daemon)
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
echo    CORRER EL BOT  -  Cripo_Mine v4.3 DESVELO
echo    Carpeta: %CD%
echo   ==============================================
echo.
where python >nul 2>nul
if errorlevel 1 (set PY=py -3) else (set PY=python)

echo   [0/4] DESVELO: el portatil NO se va a dormir...
powercfg /change standby-timeout-ac 0 >nul 2>&1
powercfg /change hibernate-timeout-ac 0 >nul 2>&1
powercfg /change monitor-timeout-ac 15 >nul 2>&1
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0 >nul 2>&1
powercfg /setactive SCHEME_CURRENT >nul 2>&1
echo         OK: con el cargador puesto, puedes cerrar la tapa
echo         y el bot SIGUE minando (pantalla se apaga a los 15 min,
echo         eso no detiene nada).
echo.

echo   [1/4] Sincronizando con GitHub (si es la primera vez,
echo         te pedira autorizar en el navegador)...
%PY% sincronizar.py auto
echo.

echo   [2/4] Verificando dependencias...
%PY% -m pip install -q -r requirements.txt
echo         OK
echo.

echo   [3/4] Arrancando el DAEMON minero (ventana nueva)...
REM v4.3: a prueba de dobles - si xmrig ya vive, NO arranca otro
REM (dos mineros pelean la CPU y el hashrate se va a la mitad).
tasklist /FI "IMAGENAME eq xmrig.exe" 2>nul | find /I "xmrig.exe" >nul
if %errorlevel%==0 (
    echo   El DAEMON YA esta corriendo: no se arranca otro.
    echo   Solo se abre el panel. Para reiniciar de cero:
    echo   DETENER_TODO.bat y vuelve a correr este bat.
) else (
    start "CripoMine DAEMON" cmd /k %PY% run_miner.py
    timeout /t 4 /nobreak >nul
)

echo   [4/4] Abriendo el DASHBOARD (ventana nueva)...
start "CripoMine DASHBOARD" cmd /k %PY% -m streamlit run app.py

echo.
echo   ==============================================
echo    LISTO. El bot esta corriendo:
echo     - Ventana "CripoMine DAEMON"    = minero 24/7
echo     - Ventana "CripoMine DASHBOARD" = panel visual
echo.
echo    *** NO PULSES "INICIAR" DENTRO DEL PANEL ***
echo    El daemon YA esta minando. Ese boton es solo para
echo    minar sin el bat: si lo pulsas ahora abre un SEGUNDO
echo    minero que pelea la CPU y el hashrate se va a la mitad.
echo    (En v4.2.1 el boton se desactiva solo si ve al daemon.)
echo     - Tu Telegram                   = PRUEBA DE GANANCIAS
echo       (y /ganancias /hidra /estado /apagar cuando quieras)
echo.
echo    LA HIDRA esta despierta: config optima + escudo Defender
echo    + medico de xmrig.exe + vigia anti-hashrate-0.
echo    v3.9: 7 pools; ZergPool paga en BTC directo si unMineable
echo    falla. Payout estimado NO fiable si el hashrate esta en 0.
echo    ¿Hashrate 0? -> doble clic en DIAGNOSTICO.bat
echo.
echo    Para DETENER TODO: doble clic en DETENER_TODO.bat
echo   ==============================================
timeout /t 10 >nul
