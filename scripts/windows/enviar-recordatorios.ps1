# Recordatorio diario de entrega (CU-009) en Windows Server: lo ejecuta la tarea programada
# «ReMate - recordatorio» cada día a las 9:00 (documentacion/guia-de-instalacion.md).
# La salida va al log; el código de salida es 1 si algún correo no se ha podido enviar.
#
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File C:\ReMate\app\scripts\windows\enviar-recordatorios.ps1

$ErrorActionPreference = 'Stop'
$app = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)   # C:\ReMate\app (raíz del código)
$logs = Join-Path (Split-Path -Parent $app) 'logs'             # C:\ReMate\logs
New-Item -ItemType Directory -Force -Path $logs | Out-Null

Set-Location (Join-Path $app 'backend')
$log = Join-Path $logs 'recordatorios.log'
Add-Content -Path $log -Value "--- $(Get-Date -Format 'yyyy-MM-dd HH:mm') ---"
# El resumen y los errores van también a la tabla logs (ADR 0008). La salida la escribe
# Python (app/a_archivo.py, en UTF-8), no la redirección de PowerShell 5.1, que escribe en UTF-16
# y, con 'Stop', puede pararse en la primera línea de la salida de errores.
& (Join-Path $app 'backend\.venv\Scripts\python.exe') -m app.a_archivo $log flask --app app enviar-recordatorios
exit $LASTEXITCODE
