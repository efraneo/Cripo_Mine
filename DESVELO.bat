@echo off
REM ============================================================
REM  DESVELO.bat - Cripo_Mine v4.3.1
REM  Portatil NUNCA se duerme mientras mina (tapa cerrada OK).
REM  Doble clic = acepta la ventanita UAC = listo (permanente).
REM  (Version .bat de DESVELO.ps1: NO usa politicas de
REM   PowerShell, no puede ser bloqueado al ejecutarlo.)
REM ============================================================
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo   Solicitando permisos de ADMINISTRADOR...
    echo   ^(acepta la ventanita UAC^)
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)
title DESVELO - Cripo_Mine
echo.
echo   DESVELO: configurando energia para minar 24/7...
echo.

REM 1) Nunca dormirse ni hibernar con cargador (0 = nunca)
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
echo   [OK] Sueno/hibernacion con cargador: NUNCA

REM 2) Cerrar la tapa con cargador = NO HACER NADA (sigue minando)
REM    LIDACTION: 0=Nada  1= suspender
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
echo   [OK] Cerrar la tapa con cargador = SIGUE MINANDO

REM 3) La pantalla si se apaga (15 min) - eso no detiene nada
powercfg /change monitor-timeout-ac 15
echo   [OK] Pantalla se apaga a los 15 min (no afecta el minado)

echo.
echo   LISTO. A partir de ahora:
echo    - Cierra la tapa (con cargador) -^> el bot sigue minando
echo    - La pantalla se apaga -^> normal, sigue minando
echo    - OJO: sin cargador Windows se duerme igual (bateria)
echo    - OJO: con la tapa cerrada el portatil calienta mas;
echo      dejale ventilacion. Si baja el hashrate, abrela.
echo.
echo   Para deshacer: Panel de control ^> Opciones de energia.
echo.
pause
