# Demo completa en una sola maquina: servidor en WSL -> health -> credenciales -> dos clientes.
# Uso: .\demo.ps1 [-SinClientes]
param([switch]$SinClientes)
. "$PSScriptRoot\_comun.ps1"

& "$PSScriptRoot\start_server_wsl.ps1"
if ($LASTEXITCODE -ne 0) { Write-Host "No se pudo levantar el servidor; demo cancelada." -ForegroundColor Red; exit 1 }

Write-Host ""
Write-Host "== Credenciales de demo (leidas de WSL: ~/.inventario/credenciales.env) ==" -ForegroundColor Cyan
$cred = & wsl.exe -d $script:Distro -- bash -lc 'cat ~/.inventario/credenciales.env 2>/dev/null'
$map = @{}
foreach ($l in $cred) { if ($l -match '^(\w+)=(.*)$') { $map[$Matches[1]] = $Matches[2].Trim() } }
if ($map.Count -eq 0) { Write-Host "No hay credenciales (ejecute deploy/wsl/setup.sh)." -ForegroundColor Yellow }
else {
    Write-Host "  admin     : $($map['INVENTARIO_ADMIN_PASSWORD'])"
    Write-Host "  comprador : $($map['INVENTARIO_COMPRADOR_PASSWORD'])"
}
Write-Host ""
Write-Host "Servidor: $($script:UrlLocal)   (para otro portatil: .\deploy\windows\red_info.ps1)"

if (-not $SinClientes) {
    $cliente = Join-Path $PSScriptRoot 'start_client.ps1'
    foreach ($rol in 'admin', 'comprador') {
        Write-Host "Abriendo cliente para: $rol"
        Start-Process powershell.exe -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $cliente, '-Url', $script:UrlLocal)
        Start-Sleep -Seconds 2
    }
    Write-Host "Inicie sesion en la 1a ventana como admin y en la 2a como comprador."
}
Write-Host "Para detener: .\deploy\windows\stop_server_wsl.ps1"
