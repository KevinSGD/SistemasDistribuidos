# Detiene el servidor de WSL (solo el proceso registrado en su PID file).
. "$PSScriptRoot\_comun.ps1"
Test-WslDisponible
$rc = Invoke-WslScript 'stop_server.sh' $args
exit $rc
