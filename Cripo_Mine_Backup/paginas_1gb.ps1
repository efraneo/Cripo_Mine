# ============================================================
#  paginas_1gb.ps1 - Cripo_Mine v4.1.1
#  Concede el privilegio de Windows "Lock pages in memory"
#  (SeLockMemoryPrivilege) a los Administradores — requisito
#  para las 1GB huge pages de xmrig (dataset RandomX completo
#  en 3 paginas de 1GB, ~+1-3% hashrate sobre 2MB pages).
#
#  USO: clic derecho -> "Ejecutar con PowerShell" (pide admin)
#  Tras concederlo hay que REINICIAR el PC una sola vez.
#
#  Sin riesgo: si algo falla, xmrig simplemente sigue usando
#  las 2MB huge pages (la config ya activa 1gb-pages con
#  fallback automatico).
# ============================================================

# --- Auto-elevacion (pide UAC si no eres admin) ---
$id = [System.Security.Principal.WindowsIdentity]::GetCurrent()
$esAdmin = (New-Object System.Security.Principal.WindowsPrincipal($id)).IsInRole([System.Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $esAdmin) {
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    exit
}

Write-Host "== Cripo_Mine: conceder 'Lock pages in memory' ==" -ForegroundColor Cyan
$export = Join-Path $env:TEMP "secpol_cripo_export.cfg"
$nuevo  = Join-Path $env:TEMP "secpol_cripo_nuevo.cfg"
$BANDE  = "SeLockMemoryPrivilege"
$ADMIN  = "*S-1-5-32-544"   # grupo Administradores (SID conocido)

$rc = Start-Process secedit -ArgumentList "/export /cfg `"$export`"" `
       -Wait -PassThru -NoNewWindow
if ($rc.ExitCode -ne 0 -or -not (Test-Path $export)) {
    Write-Host "FALLO: no pude exportar la politica local (secedit)." `
        -ForegroundColor Red
    Read-Host "Enter para salir"; exit 1
}

$contenido = Get-Content $export -Raw
$lineaNueva = "$BANDE = $ADMIN"

if ($contenido -match "(?m)^\s*$BANDE\s*=\s*(.*?)\s*$") {
    $lineaActual = $Matches[0].Trim()
    if ($lineaActual -match [regex]::Escape($ADMIN)) {
        Write-Host "El privilegio YA estaba concedido. Nada que hacer." `
            -ForegroundColor Green
        Write-Host "Si xmrig aun dice '1GB pages failed', REINICIA el PC."
        Read-Host "Enter para salir"; exit 0
    }
    $derechos = ($Matches[1].Trim() + "," + $ADMIN).Trim(",")
    $lineaNueva = "$BANDE = $derechos"
    $contenido = $contenido.Replace($lineaActual, $lineaNueva)
} else {
    # La linea no existe: anadir la seccion al final del INF
    if ($contenido -notmatch "\[Privilege Rights\]") {
        $contenido += "`r`n[Privilege Rights]`r`n"
    }
    $contenido += "`r`n$lineaNueva`r`n"
}

Set-Content -Path $nuevo -Value $contenido -Encoding Unicode

$rc2 = Start-Process secedit `
       -ArgumentList "/configure /db secpol_cripo.sdb /cfg `"$nuevo`"" `
       -Wait -PassThru -NoNewWindow

if ($rc2.ExitCode -eq 0) {
    Write-Host "" 
    Write-Host "LISTO: 'Lock pages in memory' concedido a Administradores." `
        -ForegroundColor Green
    Write-Host ">>> REINICIA EL PC una vez para que Windows lo aplique." `
        -ForegroundColor Yellow
    Write-Host "Luego abre CORRER_BOT.bat: xmrig mostrara '1GB pages: 3/3'"
} else {
    Write-Host "FALLO al importar la politica (codigo $($rc2.ExitCode))." `
        -ForegroundColor Red
    Write-Host "Plan B manual: secpol.msc -> Asignacion de derechos de" 
    Write-Host "usuario -> 'Bloquear paginas en la memoria' -> Administradores"
}
Remove-Item $export, $nuevo -ErrorAction SilentlyContinue
Read-Host "Enter para salir"
