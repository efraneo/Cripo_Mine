@echo off
setlocal
title Cripo_Mine v4.5 - AFINADOR (maximo hashrate para tu i5)
cd /d "%~dp0"

rem ============================================================
rem  AFINADOR v4.5 - saca el maximo de tu HP Pavilion (i5+Iris)
rem  Prueba combinaciones de hilos + sonda GPU Iris (OpenCL)
rem  y deja el ganador en data/afinado.json para el daemon.
rem  Duracion: 25-45 min. NO uses la laptop durante la medicion.
rem ============================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
  echo [!] AFINAR funciona mejor como ADMINISTRADOR: medira el efecto
  echo     real de MSR y huge pages en tu i5. Acepta la ventana UAC.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

echo ============================================================
echo  AFINADOR CRIPRO_MINE v4.5
echo  1) Cierra el bot si esta corriendo (DETENER_TODO.bat)
echo  2) Conecta el cargador y no cierres la tapa (DESVELO.bat)
echo  3) No uses la laptop hasta que termine
echo ============================================================
echo.
where python >nul 2>&1
if errorlevel 1 (
  echo [X] Python no encontrado en PATH. Reinstalalo con "Add to PATH".
  pause
  exit /b 1
)
python afinador.py
echo.
echo Listo. Si aplico un ganador: doble clic CORRER_BOT.bat para minar
echo con la configuracion medida. Si no pudo medir, prueba otra vez con
echo la laptop enchufada (el admin activa MSR y huge pages reales).
pause
