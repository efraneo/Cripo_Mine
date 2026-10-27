# ============================================================
#  DESVELO.ps1 - Cripo_Mine v4.3.1
#  Haz que tu portatil NUNCA se duerma mientras mina.
#  (Cerraste la tapa, se durmio, el daemon se congelo y
#   el hashrate se fue a 0 - esto lo impide para siempre.)
#
#  *** SI POWERSHELL TE DA ERROR AL EJECUTAR ESTE SCRIPT ***
#  Error tipico: "no se puede cargar el archivo ... porque la
#  ejecucion de scripts esta deshabilitada en este sistema".
#  Windows bloquea los .ps1 por defecto (ExecutionPolicy).
#
#  SOLUCION FACIL (recomendada): doble clic en DESVELO.bat
#  - es el mismo arreglo y no puede ser bloqueado.
#
#  SOLUCION CON ESTE PS1: abre PowerShell en la carpeta y
#  ejecuta exactamente:
#    powershell -ExecutionPolicy Bypass -File .\DESVELO.ps1
#
#  Efecto: PERMANENTE en el plan de energia actual (con cargador).
#  NOTA: minar con la tapa cerrada necesita CARGADOR puesto.
# ============================================================
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) { Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""; exit }

Write-Host ""
Write-Host "  DESVELO - configurando energia para minar 24/7..." -ForegroundColor Cyan
Write-Host ""

# 1) Nunca dormirse ni hibernar con cargador (0 = nunca)
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
Write-Host "  [OK] Sueno/hibernacion con cargador: NUNCA" -ForegroundColor Green

# 2) Cerrar la tapa (con cargador) = NO HACER NADA (sigue minando)
#    LIDACTION: 0=Nada  1= suspender
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
Write-Host "  [OK] Cerrar la tapa con cargador = SIGUE MINANDO" -ForegroundColor Green

# 3) La pantalla si se apaga (15 min) - eso no detiene nada
powercfg /change monitor-timeout-ac 15
Write-Host "  [OK] Pantalla se apaga a los 15 min (no afecta el minado)" -ForegroundColor Green

Write-Host ""
Write-Host "  LISTO. A partir de ahora:" -ForegroundColor Cyan
Write-Host "   - Cierra la tapa (con cargador) -> el bot sigue minando"
Write-Host "   - La pantalla se apaga -> normal, sigue minando"
Write-Host "   - OJO: sin cargador Windows se duerme igual (bateria)"
Write-Host "   - OJO: con la tapa cerrada el portatil calienta mas;"
Write-Host "     dejale ventilacion. Si baja el hashrate, abrela."
Write-Host ""
Write-Host "  Para deshacer: Panel de control > Opciones de energia." -ForegroundColor Yellow
Write-Host ""
pause
