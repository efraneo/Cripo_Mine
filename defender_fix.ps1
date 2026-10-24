# ============================================================
#  defender_fix.ps1 - Cripo_Mine v3.7 - ESCUDO manual
#  Doble uso: clic derecho > "Ejecutar con PowerShell" (o lo
#  llama el daemon automaticamente via hidra_minera.py).
#
#  Que hace (en orden):
#   1) Agrega exclusiones CORRECTAS en Windows Defender:
#      - carpeta bin\ completa
#      - ruta EXACTA del xmrig.exe encontrado
#      - proceso "xmrig.exe"  <- la carpeta sola NO basta:
#        Defender puede cuarentenar el .exe al ejecutarlo
#   2) Restaura de la cuarentena lo que Defender borro
#      (MpCmdRun.exe -Restore -All)
#   3) Muestra amenazas recientes contra xmrig/coinminer
#
#  Requiere permisos de ADMINISTRADOR (los pide solo).
# ============================================================
$ErrorActionPreference = "Continue"

# --- auto-elevacion a administrador ---
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "Pidiendo permisos de ADMINISTRADOR..." -ForegroundColor Yellow
    Start-Process -FilePath "powershell" -Verb RunAs -ArgumentList `
        "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Write-Host ""
Write-Host "===== ESCUDO Cripo_Mine: reparar bloqueo de xmrig =====" -ForegroundColor Cyan
$raiz = Split-Path -Parent $PSCommandPath
$binDir = Join-Path $raiz "bin"

# --- 1) exclusiones: carpeta + .exe exacto + proceso ---
$rutas = @($binDir, (Join-Path $binDir "xmrig-mo"),
           (Join-Path $binDir "xmrig-oficial"))
if (Test-Path (Join-Path $binDir "xmrig_binary_path.json")) {
    try {
        $j = Get-Content (Join-Path $binDir "xmrig_binary_path.json") -Raw `
             | ConvertFrom-Json
        if ($j.path) { $rutas += $j.path }
    } catch {}
}
if (Get-ChildItem -Path $binDir -Recurse -Filter "xmrig.exe" `
        -ErrorAction SilentlyContinue) {
    $rutas += (Get-ChildItem -Path $binDir -Recurse -Filter "xmrig.exe" `
        -ErrorAction SilentlyContinue).FullName
}

Write-Host "`n[1/3] Agregando exclusiones en Windows Defender..." -ForegroundColor Green
foreach ($r in ($rutas | Where-Object { $_ -and (Test-Path $_) } | Select-Object -Unique)) {
    try {
        Add-MpPreference -ExclusionPath $r -ErrorAction Stop
        Write-Host "  excluida ruta: $r"
    } catch { Write-Host "  NO se pudo excluir $r : $($_.Exception.Message)" -ForegroundColor Red }
}
try {
    Add-MpPreference -ExclusionProcess "xmrig.exe" -ErrorAction Stop
    Write-Host "  excluido proceso: xmrig.exe"
} catch { Write-Host "  NO se pudo excluir el proceso: $($_.Exception.Message)" -ForegroundColor Red }

# --- 2) restaurar de cuarentena ---
Write-Host "`n[2/3] Restaurando archivos de la cuarentena..." -ForegroundColor Green
$mp = Join-Path $env:ProgramFiles "Windows Defender\MpCmdRun.exe"
if (-not (Test-Path $mp)) {
    $mp = Join-Path ${env:ProgramFiles(x86)} "Windows Defender\MpCmdRun.exe"
}
if (Test-Path $mp) {
    & $mp -Restore -All
} else {
    Write-Host "  MpCmdRun.exe no encontrado (Defender ausente u otro AV)." -ForegroundColor Yellow
}

# --- 3) amenazas recientes contra xmrig ---
Write-Host "`n[3/3] Amenazas recientes contra xmrig/coinminer:" -ForegroundColor Green
try {
    $t = Get-MpThreatDetection -ErrorAction Stop | Where-Object {
        $_.Resources -match "xmrig|coinminer" } | Select-Object -First 5
    if ($t) { $t | Format-List ThreatID, InitialDetectionTime, Resources }
    else { Write-Host "  ninguna registrada" }
} catch { Write-Host "  (sin acceso al historial: $($_.Exception.Message))" }

Write-Host "`nLISTO. Cierra y vuelve a abrir con CORRER_BOT.bat." -ForegroundColor Cyan
Write-Host "(si tu antivirus NO es Defender: Avast/Avira/McAfee/... agrega la" -ForegroundColor Yellow
Write-Host " exclusion de la carpeta bin en el panel de ESE antivirus)" -ForegroundColor Yellow
pause
