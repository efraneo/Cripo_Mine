@echo off
REM ============================================================
REM  DETENER_TODO.bat - BTC Miner Studio (Windows)  [v3.2]
REM  Cierra: xmrig.exe + daemon (run_miner.py) + streamlit local
REM  No borra datos ni balances: el saldo queda en cada pool.
REM  Uso: doble clic en este archivo.
REM ============================================================
setlocal
cd /d "%~dp0"
echo.
echo   ==========================================
echo    DETENER TODO - BTC Miner Studio
echo   ==========================================
echo.

REM --- [1/4] Parada amable: orden stop en data\control.json ---
echo [1/4] Pidiendo parada amable al daemon...
powershell -NoProfile -Command "$f='data\control.json'; New-Item -ItemType Directory -Force -Path data | Out-Null; if (Test-Path $f) { try { $j = Get-Content $f -Raw | ConvertFrom-Json; $j.action='stop'; $j.updated_by='detener_bat'; $j | ConvertTo-Json -Depth 5 | Set-Content $f -Encoding UTF8 } catch { @{action='stop';updated_by='detener_bat'} | ConvertTo-Json | Set-Content $f -Encoding UTF8 } } else { @{action='stop';updated_by='detener_bat'} | ConvertTo-Json | Set-Content $f -Encoding UTF8 }"
timeout /t 6 /nobreak >nul

REM --- [2/4] Mineros externos ---
echo [2/4] Cerrando xmrig / cpuminer...
taskkill /F /IM xmrig.exe >nul 2>&1
taskkill /F /FI "IMAGENAME eq cpuminer*" >nul 2>&1
taskkill /F /IM minerd.exe >nul 2>&1

REM --- [3/4] Daemon y Streamlit local (solo procesos del miner) ---
echo [3/4] Cerrando daemon (run_miner.py) y Streamlit local...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe' or Name='pythonw.exe'\" | Where-Object { $_.CommandLine -match 'run_miner\.py|streamlit' } | ForEach-Object { Write-Host ('    cerrando PID ' + $_.ProcessId); Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"

REM --- [4/4] Estado final ---
echo [4/4] Estado final:
tasklist /FI "IMAGENAME eq xmrig.exe" 2>nul | find /I "xmrig.exe" >nul
if errorlevel 1 (echo    [OK] xmrig.exe cerrado) else (echo    [!!] xmrig.exe sigue vivo: ejecuta este .bat como Administrador)
echo.
echo   Listo. El saldo pendiente NO se pierde: queda en cada pool.
echo   Consultalo con:  python recolectar_pool.py
echo.
pause
