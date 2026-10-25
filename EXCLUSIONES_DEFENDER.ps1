# EXCLUSIONES_DEFENDER.ps1
# Ejecuta este script UNA VEZ como Administrador.
# Doble clic -> "Ejecutar con PowerShell" -> acepta UAC.
# Resultado: Defender nunca mas borra ni mata xmrig.exe

$ErrorActionPreference = "Continue"

# Auto-elevacion
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Write-Host "`n===== EXCLUSIONES DEFENDER para xmrig =====" -ForegroundColor Cyan

$bin     = "C:\software_phyton\Cripo_Mine\bin"
$binMo   = "C:\software_phyton\Cripo_Mine\bin\xmrig-mo"
$xmrigEx = "C:\software_phyton\Cripo_Mine\bin\xmrig-mo\xmrig.exe"

# Cargar modulo explicitamente
Import-Module ConfigDefender -ErrorAction SilentlyContinue

foreach ($ruta in @($bin, $binMo, $xmrigEx)) {
    if (Test-Path $ruta) {
        try {
            Add-MpPreference -ExclusionPath $ruta -ErrorAction Stop
            Write-Host "OK ruta excluida: $ruta" -ForegroundColor Green
        } catch {
            Write-Host "WARN $ruta : $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

try {
    Add-MpPreference -ExclusionProcess "xmrig.exe" -ErrorAction Stop
    Write-Host "OK proceso excluido: xmrig.exe" -ForegroundColor Green
} catch {
    Write-Host "WARN proceso: $($_.Exception.Message)" -ForegroundColor Yellow
}

# Restaurar de cuarentena (recupera WinRing0x64.sys)
$mp = "$env:ProgramFiles\Windows Defender\MpCmdRun.exe"
if (!(Test-Path $mp)) { $mp = "${env:ProgramFiles(x86)}\Windows Defender\MpCmdRun.exe" }
if (Test-Path $mp) {
    Write-Host "`nRestaurando archivos de cuarentena..." -ForegroundColor Cyan
    & $mp -Restore -All 2>&1
    Write-Host "OK restauracion ejecutada" -ForegroundColor Green
}

# Desbloquear archivos (quita marca de descarga de internet)
Get-ChildItem $bin -Recurse -File -ErrorAction SilentlyContinue |
    ForEach-Object { try { Unblock-File $_.FullName } catch {} }
Write-Host "OK archivos desbloqueados" -ForegroundColor Green

Write-Host "`nLISTO. Ahora cierra el bot (DETENER_TODO.bat) y vuelve a" -ForegroundColor Cyan
Write-Host "abrirlo con CORRER_BOT.bat aceptando el UAC de admin." -ForegroundColor Cyan
Write-Host "El hashrate deberia subir a 1500-3000 H/s con MSR activo.`n" -ForegroundColor Yellow
pause
