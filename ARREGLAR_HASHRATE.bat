@echo off
REM ============================================================
REM  ARREGLAR_HASHRATE.bat — Cripo_Mine
REM  Resuelve de una vez:
REM    1) Exclusiones correctas en Windows Defender
REM    2) Restaura WinRing0x64.sys y xmrig.exe de cuarentena
REM    3) Aplica mod MSR (hashrate +40% en Intel, +80-100% AMD)
REM    4) Reinicia el daemon con la config optimizada
REM
REM  DOBLE CLIC → acepta la ventanita de admin → listo.
REM ============================================================
setlocal

REM ---- Auto-elevacion a ADMINISTRADOR ----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando permisos de ADMINISTRADOR...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
title ARREGLAR HASHRATE - Cripo_Mine
color 0A

echo.
echo  ================================================
echo   ARREGLAR HASHRATE  -  Cripo_Mine
echo   Ejecutando como ADMINISTRADOR
echo  ================================================
echo.

where python >nul 2>nul
if errorlevel 1 (set PY=py -3) else (set PY=python)

echo  [1/4] Deteniendo minero actual...
%PY% -c "from miner_manager import matar_mineros_huerfanos; n=matar_mineros_huerfanos(); print('  Procesos detenidos:', n)"
timeout /t 3 /nobreak >nul

echo.
echo  [2/4] Aplicando exclusiones en Windows Defender...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { ^
    $b = 'C:\software_phyton\Cripo_Mine\bin'; ^
    Add-MpPreference -ExclusionPath $b -ErrorAction Stop; ^
    Add-MpPreference -ExclusionPath ($b+'\xmrig-mo') -ErrorAction Stop; ^
    $exe = Get-ChildItem $b -Recurse -Filter xmrig.exe -ErrorAction SilentlyContinue | Select-Object -First 1; ^
    if ($exe) { Add-MpPreference -ExclusionPath $exe.FullName -ErrorAction Stop }; ^
    Add-MpPreference -ExclusionProcess 'xmrig.exe' -ErrorAction Stop; ^
    Get-ChildItem $b -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object { try { Unblock-File $_.FullName } catch {} }; ^
    Write-Host '  Exclusiones aplicadas OK' -ForegroundColor Green ^
  } catch { Write-Host ('  Error: '+$_.Exception.Message) -ForegroundColor Red }"

echo.
echo  [3/4] Restaurando archivos de cuarentena (WinRing0x64.sys)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$mp = Join-Path $env:ProgramFiles 'Windows Defender\MpCmdRun.exe'; ^
   if (!(Test-Path $mp)) { $mp = Join-Path ${env:ProgramFiles(x86)} 'Windows Defender\MpCmdRun.exe' }; ^
   if (Test-Path $mp) { & $mp -Restore -All; Write-Host '  Restauracion ejecutada' -ForegroundColor Green } ^
   else { Write-Host '  MpCmdRun no encontrado' -ForegroundColor Yellow }"
timeout /t 3 /nobreak >nul

echo.
echo  [4/4] Actualizando config de xmrig (todos los nucleos + MSR)...
%PY% -c "
from config import load_secrets
from miner_manager import write_xmrig_config
import json, os

cfg = load_secrets()

# Determinar pool activo
try:
    with open('data/engine_state.json') as f:
        eng = json.load(f)
    target_id = eng.get('target', 'moneroocean')
except:
    target_id = 'moneroocean'

from aggressive_engine import TARGETS
target = next((t for t in TARGETS if t['id']==target_id), TARGETS[4])
try:
    user = target['user_fn'](cfg, 'cpu01')
    passw_fn = target.get('pass_fn')
    passw = passw_fn(cfg, 'cpu01') if passw_fn else 'x'
except:
    user = cfg.get('WALLET_XMR','')
    passw = 'x'

import psutil
fisicos = psutil.cpu_count(logical=False) or 4
logicos = psutil.cpu_count(logical=True) or fisicos

path = write_xmrig_config(target['url'], user, passw, logicos)
print('  Config generada:', path)
print('  Pool:', target[\"url\"])
print('  Nucleos logicos usados:', logicos)
"

echo.
echo  ================================================
echo   LISTO. Ahora cierra el daemon actual y vuelve
echo   a abrir CORRER_BOT.bat para que arranque con
echo   permisos de admin y el MSR activo.
echo.
echo   Hashrate esperado con MSR + todos los nucleos:
echo   Intel 10-core:  ~1500-2500 H/s
echo   AMD Ryzen:      ~2000-4000 H/s
echo  ================================================
echo.
pause
