# Arranca el cliente PyQt6 con el .venv del proyecto.
# Uso: .\start_client.ps1 [-Url http://localhost:8000] [-SalirEn 3]
# Prioridad de URL: -Url > variable INVENTARIO_URL ya definida > http://localhost:8000
param(
    [string]$Url,
    [double]$SalirEn = 0   # solo pruebas de humo (cierra la app tras N segundos)
)
$raiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$py = Join-Path $raiz '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host "No existe $py. Cree el entorno: py -m venv .venv ; .\.venv\Scripts\python.exe -m pip install -r requirements-client.txt" -ForegroundColor Red
    exit 1
}
if ($Url) { $env:INVENTARIO_URL = $Url }
elseif (-not $env:INVENTARIO_URL) { $env:INVENTARIO_URL = 'http://localhost:8000' }
# Equivale a activar el venv (sin depender de la politica de ejecucion de Activate.ps1)
$env:VIRTUAL_ENV = Join-Path $raiz '.venv'
$env:PATH = (Join-Path $raiz '.venv\Scripts') + ';' + $env:PATH
Write-Host "Cliente -> INVENTARIO_URL=$($env:INVENTARIO_URL)"
Set-Location $raiz
$args2 = @('-m', 'client.main')
if ($SalirEn -gt 0) { $args2 += @('--salir-en', "$SalirEn") }
& $py @args2
exit $LASTEXITCODE
