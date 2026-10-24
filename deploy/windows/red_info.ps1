# SOLO MUESTRA informacion y comandos de red; no cambia nada. Para la defensa con otro portatil.
. "$PSScriptRoot\_comun.ps1"
$p = $script:Puerto
$ips = @(Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notmatch 'vEthernet|WSL|Loopback' } |
    Select-Object -ExpandProperty IPAddress)
$ipWsl = ''
try { $ipWsl = (& wsl.exe -d $script:Distro -- bash -lc "hostname -I | awk '{print `$1}'").Trim() } catch {}

Write-Host "== IP(s) de esta PC en la red (la que usara el otro portatil) ==" -ForegroundColor Cyan
$ips | ForEach-Object { Write-Host "  http://${_}:$p" }
Write-Host "IP actual de WSL: $ipWsl  (cambia al reiniciar WSL)"
Write-Host ""
Write-Host "== Mismo equipo ==" -ForegroundColor Cyan
Write-Host "  http://localhost:$p  (localhost forwarding de WSL2, por defecto activo)"
Write-Host ""
Write-Host "== Otro portatil (ejecute usted en PowerShell COMO ADMINISTRADOR; no se ejecutan aqui) ==" -ForegroundColor Cyan
Write-Host "Opcion A (recomendada, Windows 11 22H2+): WSL en modo espejo. Cree/edite %UserProfile%\.wslconfig:"
Write-Host "    [wsl2]"
Write-Host "    networkingMode=mirrored"
Write-Host "  luego:  wsl --shutdown   y vuelva a arrancar el servidor."
Write-Host "Opcion B (modo NAT por defecto): reenviar el puerto de la PC hacia la IP de WSL:"
Write-Host "    netsh interface portproxy add v4tov4 listenaddress=0.0.0.0 listenport=$p connectaddress=$ipWsl connectport=$p"
Write-Host "  (repetir si la IP de WSL cambia; para quitarlo: netsh interface portproxy delete v4tov4 listenaddress=0.0.0.0 listenport=$p)"
Write-Host "En ambos casos, abra el puerto en el Firewall de Windows:"
Write-Host "    New-NetFirewallRule -DisplayName 'Inventario API $p' -Direction Inbound -Protocol TCP -LocalPort $p -Action Allow -Profile Private"
Write-Host "  (quitar luego:  Remove-NetFirewallRule -DisplayName 'Inventario API $p')"
Write-Host "Verificacion desde el otro portatil:  Invoke-RestMethod http://<IP-de-esta-PC>:$p/api/v1/health"
Write-Host "Cliente en el otro portatil:  `$env:INVENTARIO_URL='http://<IP-de-esta-PC>:$p'; .\deploy\windows\start_client.ps1"
