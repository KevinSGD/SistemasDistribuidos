# Funciones compartidas por los scripts de deploy/windows (se cargan con dot-sourcing). Solo ASCII.
$ErrorActionPreference = 'Stop'

$script:RepoRaiz = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$script:Distro = if ($env:INVENTARIO_WSL_DISTRO) { $env:INVENTARIO_WSL_DISTRO } else { 'Ubuntu' }
$script:Puerto = if ($env:INVENTARIO_PORT) { $env:INVENTARIO_PORT } else { '8000' }
$script:UrlLocal = "http://localhost:$($script:Puerto)"

# C:\a\b -> /mnt/c/a/b
function ConvertTo-WslPath([string]$ruta) {
    $r = $ruta -replace '\\', '/'
    if ($r -match '^([A-Za-z]):(.*)$') { return '/mnt/' + $Matches[1].ToLower() + $Matches[2] }
    return $r
}

function Test-WslDisponible {
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        throw "wsl.exe no existe. Instale WSL (comando en docs/DESPLIEGUE.md); este script no lo instala."
    }
    $null = & wsl.exe -d $script:Distro -- true 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo ejecutar la distro '$($script:Distro)'. Revise 'wsl -l -v' o defina INVENTARIO_WSL_DISTRO."
    }
}

# Ejecuta un script de deploy/wsl dentro de WSL. Devuelve el codigo de salida (la salida se muestra).
function Invoke-WslScript([string]$nombre, [string[]]$extra = @()) {
    $ruta = (ConvertTo-WslPath $script:RepoRaiz) + "/deploy/wsl/$nombre"
    $cmd = "INVENTARIO_PORT=$($script:Puerto) bash '$ruta' " + ($extra -join ' ')
    & wsl.exe -d $script:Distro -- bash -lc $cmd | Out-Host   # Out-Host: la salida no contamina el valor devuelto
    return [int]$LASTEXITCODE
}

# Health desde Windows. Devuelve el objeto o $null.
function Get-Health([string]$baseUrl) {
    try { return Invoke-RestMethod -Uri ($baseUrl.TrimEnd('/') + '/api/v1/health') -TimeoutSec 3 }
    catch { return $null }
}
