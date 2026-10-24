# Lanza el servidor dentro de WSL (en segundo plano, persiste al cerrar la terminal) y comprueba
# el health DESDE WINDOWS. Requiere haber ejecutado antes deploy/wsl/setup.sh (ver docs/DESPLIEGUE.md).
# Variables: INVENTARIO_WSL_DISTRO (Ubuntu), INVENTARIO_PORT (8000).
. "$PSScriptRoot\_comun.ps1"

Test-WslDisponible
Write-Host "Arrancando servidor en WSL ($($script:Distro))..."
$rc = Invoke-WslScript 'start_server.sh'
if ($rc -ne 0) { Write-Host "start_server.sh fallo (codigo $rc). Vea la salida anterior." -ForegroundColor Red; exit $rc }

# Comprobacion desde Windows: depende del "localhost forwarding" de WSL2 (activo por defecto).
$h = $null
foreach ($i in 1..10) { $h = Get-Health $script:UrlLocal; if ($h) { break }; Start-Sleep -Milliseconds 500 }
if ($h) {
    Write-Host "OK desde Windows: $($script:UrlLocal)/api/v1/health -> estado=$($h.estado) version=$($h.version) so=$($h.so)" -ForegroundColor Green
    exit 0
}
$ip = (& wsl.exe -d $script:Distro -- bash -lc "hostname -I | awk '{print `$1}'").Trim()
Write-Host "El servidor responde dentro de WSL pero NO en $($script:UrlLocal) desde Windows." -ForegroundColor Yellow
Write-Host "Causas habituales: localhostForwarding=false en %UserProfile%\.wslconfig, o el puerto lo usa un proceso de Windows."
Write-Host "Alternativa: use la IP de WSL: `$env:INVENTARIO_URL='http://${ip}:$($script:Puerto)'  (cambia en cada reinicio de WSL)."
$h2 = Get-Health "http://${ip}:$($script:Puerto)"
if ($h2) { Write-Host "Por IP de WSL (http://${ip}:$($script:Puerto)) SI responde." -ForegroundColor Green; exit 0 }
exit 3
