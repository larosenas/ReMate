# Copia de seguridad diaria de ReMate en Windows Server: base de datos (pg_dump) y ARCHIVOS_DIR.
# La ejecuta la tarea programada «ReMate - copia de seguridad» (documentacion/guia-de-instalacion.md).
#
# Para ocupar lo mínimo (ADR 0014):
# - Base de datos: un volcado por día en su carpeta remate-AAAAMMDD-HHMMSS. Se guardan los 7
#   últimos y, de los anteriores, el más reciente de cada una de las 4 semanas siguientes.
# - Archivos: una sola copia espejo, archivos-espejo (robocopy /MIR). Los archivos de ReMate no se
#   modifican y los que caducan se borran también del espejo. Sin recordatorios-prueba.
#
# Uso: powershell -NoProfile -ExecutionPolicy Bypass -File C:\ReMate\app\scripts\windows\copia-de-seguridad.ps1
#
# La contraseña de la base de datos NO va en este script: pg_dump la toma del archivo de contraseñas
# de PostgreSQL de la cuenta que ejecuta la tarea (%APPDATA%\postgresql\pgpass.conf).

param(
    [string]$Destino = 'C:\ReMate\copias',          # carpeta o unidad de red de las copias
    [string]$Archivos = 'C:\ReMate\archivos',       # el mismo valor que ARCHIVOS_DIR en el .env
    [string]$PgDump = 'C:\Program Files\PostgreSQL\18\bin\pg_dump.exe',
    [string]$Servidor = 'localhost',
    [int]$Puerto = 5432,
    [string]$Usuario = 'remate',
    [string]$BaseDeDatos = 'remate',
    [ValidateRange(1, 366)]
    [int]$Diarias = 7,                              # volcados diarios que se guardan
    [ValidateRange(0, 520)]
    [int]$Semanales = 4,                            # semanas anteriores con un volcado cada una
    # Obsoleto (antes se guardaban N copias enteras). Se acepta para no romper una tarea que lo
    # pase, pero no se usa.
    [int]$DiasQueSeGuardan = 0,
    # Espejar aunque la carpeta de archivos esté vacía o tenga muchos menos archivos que el espejo
    # (solo si se ha comprobado que es la buena: con /MIR, lo que no esté se borra del espejo).
    [switch]$ForzarEspejo
)

$ErrorActionPreference = 'Stop'
if ($PSBoundParameters.ContainsKey('DiasQueSeGuardan')) {
    Write-Warning 'DiasQueSeGuardan ya no se usa (ADR 0014): se guardan -Diarias y -Semanales.'
}
$Destino = [IO.Path]::GetFullPath($Destino).TrimEnd('\', '/')
if ($Destino -eq [IO.Path]::GetPathRoot($Destino).TrimEnd('\', '/')) {
    throw 'El destino debe ser una carpeta exclusiva de copias de ReMate, no la raiz de una unidad.'
}
# Con /MIR, un origen equivocado vaciaría el espejo: si no existe la carpeta, no se sigue.
if (-not (Test-Path -LiteralPath $Archivos -PathType Container)) {
    throw "No existe la carpeta de archivos $Archivos (debe ser ARCHIVOS_DIR)."
}
# Sin la barra final: con espacios, robocopy entendería '\"' como unas comillas.
$Archivos = [IO.Path]::GetFullPath($Archivos).TrimEnd('\', '/')
# Una dentro de la otra, la copia se copiaría a sí misma sin fin.
$conBarra = { param($ruta) $ruta.TrimEnd('\') + '\' }
if ((& $conBarra $Destino).StartsWith((& $conBarra $Archivos), [StringComparison]::OrdinalIgnoreCase) -or
    (& $conBarra $Archivos).StartsWith((& $conBarra $Destino), [StringComparison]::OrdinalIgnoreCase)) {
    throw 'El destino de las copias no puede estar dentro de la carpeta de archivos ni al reves.'
}
# Una carpeta que existe pero está vacía (recreada, u otra carpeta) vaciaría el único espejo: si
# tiene menos de la mitad de archivos que el espejo, no se sigue sin -ForzarEspejo.
$espejo = Join-Path $Destino 'archivos-espejo'
if (-not $ForzarEspejo -and (Test-Path -LiteralPath $espejo -PathType Container)) {
    $enEspejo = @(Get-ChildItem -LiteralPath $espejo -Recurse -File -Force).Count
    $enOrigen = @(Get-ChildItem -LiteralPath $Archivos -Recurse -File -Force |
        Where-Object { $_.FullName -notlike '*\recordatorios-prueba\*' }).Count
    if ($enEspejo -gt 0 -and $enOrigen * 2 -lt $enEspejo) {
        throw ("La carpeta de archivos $Archivos tiene $enOrigen archivo(s) y el espejo $enEspejo. " +
            'Comprueba que es ARCHIVOS_DIR; si lo es, vuelve a lanzar la copia con -ForzarEspejo.')
    }
}
$fecha = Get-Date -Format 'yyyyMMdd-HHmmss'
$carpeta = Join-Path $Destino "remate-$fecha"
$marcador = '.remate-copia-completa'
# Sin -Force: nunca mezclar dos ejecuciones en una misma carpeta.
New-Item -ItemType Directory -Path $carpeta | Out-Null

# 1. Base de datos, en formato propio de PostgreSQL (se restaura con pg_restore).
& $PgDump -Fc -h $Servidor -p $Puerto -U $Usuario -w -f (Join-Path $carpeta "remate-$fecha.dump") $BaseDeDatos
if ($LASTEXITCODE -ne 0) { throw "pg_dump ha fallado (código $LASTEXITCODE)." }

# 2. Archivos (adjuntos, correos y pedidos SAP), en una sola copia espejo. Robocopy devuelve 0-7
# cuando todo va bien.
# /XJ: sin seguir uniones de directorios, que copiarían o vaciarían carpetas de fuera.
robocopy $Archivos $espejo /MIR /XJ /XD recordatorios-prueba /R:2 /W:5 /NP /NFL /NDL | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy ha fallado (código $LASTEXITCODE)." }

# Solo las copias terminadas pueden participar en la retencion.
Set-Content -LiteralPath (Join-Path $carpeta $marcador) -Value 'ReMate'

# 3. Retención: los $Diarias más recientes y, de los anteriores, el más reciente de cada semana
# hasta $Semanales semanas. Solo se borran carpetas propias y completas; las antiguas sin
# marcador se conservan para su revision manual.
$completas = foreach ($candidata in Get-ChildItem -LiteralPath $Destino -Directory) {
    if ($candidata.Name -notmatch '^remate-(\d{8}-\d{6})$') { continue }
    $fechaCopia = [datetime]::MinValue
    if (-not [datetime]::TryParseExact($Matches[1], 'yyyyMMdd-HHmmss',
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::None, [ref]$fechaCopia)) { continue }
    $ruta = [IO.Path]::GetFullPath($candidata.FullName)
    if (-not [string]::Equals([IO.Path]::GetDirectoryName($ruta), $Destino,
        [StringComparison]::OrdinalIgnoreCase)) { throw 'Copia fuera del destino previsto.' }
    if (-not (Test-Path -LiteralPath (Join-Path $ruta $marcador) -PathType Leaf)) { continue }
    [pscustomobject]@{ Carpeta = $candidata; Ruta = $ruta; Fecha = $fechaCopia }
}
$semanasVistas = @{}
$semanalesGuardadas = 0
$n = 0
foreach ($copia in @($completas | Sort-Object Fecha -Descending)) {
    $n++
    # Semana ISO: la del jueves de esa semana (PowerShell 5.1 no tiene [Globalization.ISOWeek];
    # GetWeekOfYear de .NET separa en dos la semana del cambio de año).
    $jueves = $copia.Fecha.Date.AddDays(3 - (([int]$copia.Fecha.DayOfWeek + 6) % 7))
    $semana = '{0}-{1}' -f $jueves.Year, ([math]::Floor(($jueves.DayOfYear - 1) / 7) + 1)
    if ($n -le $Diarias) { $semanasVistas[$semana] = $true; continue }
    # La más reciente de cada semana que no tenga ya una copia guardada.
    if (-not $semanasVistas.ContainsKey($semana) -and $semanalesGuardadas -lt $Semanales) {
        $semanasVistas[$semana] = $true
        $semanalesGuardadas++
        continue
    }
    # No atravesar enlaces ni uniones de directorios al borrar recursivamente.
    if ($copia.Carpeta.Attributes -band [IO.FileAttributes]::ReparsePoint) { continue }
    $enlaces = Get-ChildItem -LiteralPath $copia.Ruta -Recurse -Force |
        Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
    if ($enlaces) { continue }
    Remove-Item -LiteralPath $copia.Ruta -Recurse -Force
}

Write-Output "Copia de seguridad hecha en $carpeta (archivos en $espejo)"
exit 0
