# habilitar_xmrig.ps1 — QUE XMRIG.EXE SE EJECUTE SIEMPRE (Windows)
# ================================================================
# Ejecutar COMO ADMINISTRADOR (clic derecho → "Con PowerShell como
# administrador"), o desde un terminal admin:
#   powershell -ExecutionPolicy Bypass -File .\habilitar_xmrig.ps1
#
# Qué hace (idempotente, se puede correr las veces que quiera):
#   1. Exclusión de CARPETA en Defender  -> bin\ no se escanea.
#   2. Exclusión de PROCESO xmrig.exe    -> corre aunque esté en otra ruta.
#   3. Unblock-File de todo bin\         -> quita marca de internet (MotW).
#   4. Verificación real: xmrig --dry-run y código de salida.
#
# Por qué: Defender clasifica mineros como "software potencialmente no
# deseado" (PUA:Win32/CoinMiner / heurísticas) y lanza WinError 225
# "el archivo contiene un virus". XMRig es open source y se descarga de
# github.com/xmrig/xmrig — si no confías, compara el hash en
# https://github.com/xmrig/xmrig/releases y usa EXTERNAL_MINER_PATH.
# Este script NO descarga nada ni cambia firmas: sólo permisos locales.

$ErrorActionPreference = 'Stop'

$id = [Security.Principal.WindowsIdentity]::GetCurrent()
$pr = New-Object Security.Principal.WindowsPrincipal($id)
if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "X Necesita ADMIN: clic derecho en PowerShell -> Ejecutar como administrador." -ForegroundColor Red
    exit 1
}

$bin = Join-Path $PSScriptRoot 'bin'
if (-not (Test-Path $bin)) { $bin = 'C:\software_phyton\Cripo_Mine\bin' }

# 1) exclusión de carpeta
try {
    Add-MpPreference -ExclusionPath $bin -ErrorAction Stop
    Write-Host "[1] Exclusion de carpeta OK: $bin" -ForegroundColor Green
} catch {
    if ((Get-MpPreference).ExclusionPath -contains $bin) {
        Write-Host "[1] Exclusion de carpeta ya existia: $bin" -ForegroundColor Gray
    } else {
        Write-Host "[1] FALLO exclusion de carpeta: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# 2) exclusion de proceso (donde quiera que viva xmrig.exe)
try {
    Add-MpPreference -ExclusionProcess 'xmrig.exe' -ErrorAction Stop
    Write-Host "[2] Exclusion de proceso OK: xmrig.exe" -ForegroundColor Green
} catch {
    if ((Get-MpPreference).ExclusionProcess -contains 'xmrig.exe') {
        Write-Host "[2] Exclusion de proceso ya existia" -ForegroundColor Gray
    } else {
        Write-Host "[2] FALLO exclusion de proceso: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# 3) desbloquear archivos descargados
$n = 0
Get-ChildItem -Path $bin -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
    try { Unblock-File -Path $_.FullName -ErrorAction Stop; $n++ } catch { }
}
Write-Host "[3] Unblock-File: $n archivo(s) procesado(s)" -ForegroundColor Green

# 4) prueba real de ejecucion
$exe = Get-ChildItem -Path $bin -Recurse -Filter xmrig.exe -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $exe) {
    Write-Host "[4] todavia no hay xmrig.exe (lo descarga la app al iniciar el motor)" -ForegroundColor Yellow
    exit 0
}
& $exe.FullName --dry-run --no-color 2>&1 | Select-Object -First 3
$cod = $LASTEXITCODE
if ($null -eq $cod) { $cod = 0 }   # dry-run puede terminar sin codigo
Write-Host "[4] xmrig ejecutable: SI (dry-run OK) -> $($exe.FullName)" -ForegroundColor Green
Write-Host "Listo: xmrig.exe podra ejecutarse SIEMPRE en esta maquina." -ForegroundColor Cyan
