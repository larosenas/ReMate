"""Copia de seguridad (ADR 0014): volcado por día, archivos en una copia espejo y retención de 7
diarias y 4 semanales, que solo elimina copias propias completas, en un destino temporal."""

import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/windows/copia-de-seguridad.ps1"
POWERSHELL = shutil.which("powershell.exe")
AHORA = datetime(2026, 11, 2, 12, tzinfo=UTC)
pytestmark = pytest.mark.skipif(POWERSHELL is None, reason="Requiere PowerShell de Windows")


def _ejecutar(
    tmp_path,
    diarias=7,
    codigo_dump=0,
    codigo_archivos=1,
    archivos=None,
    destino=None,
    ahora=AHORA,
    forzar=False,
):
    wrapper = tmp_path / "ejecutar.ps1"
    wrapper.write_text(
        """param($Script, $Destino, $Archivos, [int]$Diarias, [int]$CodigoDump,
      [int]$CodigoArchivos, [string]$Ahora, [string]$Forzar)
$ErrorActionPreference = 'Stop'
function Get-Date {
    param([string]$Format)
    $ahora = [datetime]$Ahora
    if ($Format) { return $ahora.ToString($Format) }
    return $ahora
}
function Invoke-PgDumpPrueba {
    $f = [Array]::IndexOf($args, '-f')
    [IO.File]::WriteAllText($args[$f + 1], 'dump ficticio')
    $global:LASTEXITCODE = $CodigoDump
}
function robocopy {
    New-Item -ItemType Directory -Path $args[1] -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $args[0] 'adjunto.txt') -Destination $args[1]
    $global:LASTEXITCODE = $CodigoArchivos
}
# Todas las carpetas parecen antiguas: si la retención volviera a fijarse en la fecha de
# creación en vez de en el nombre y el marcador, borraría las ajenas y la prueba fallaría.
if (Test-Path -LiteralPath $Destino) {
    Get-ChildItem -LiteralPath $Destino -Directory | ForEach-Object {
        $_.CreationTime = (Get-Date).AddDays(-60)
    }
}
& $Script -Destino $Destino -Archivos $Archivos -PgDump Invoke-PgDumpPrueba -Diarias $Diarias `
    -ForzarEspejo:($Forzar -eq 'si')
exit $LASTEXITCODE
""",
        encoding="utf-8-sig",
    )
    return subprocess.run(  # noqa: S603 (script local y rutas temporales, sin servicios reales)
        [
            POWERSHELL,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-Script",
            str(SCRIPT),
            "-Destino",
            str(destino or tmp_path / "copias"),
            "-Archivos",
            str(archivos or tmp_path / "archivos"),
            "-Diarias",
            str(diarias),
            "-CodigoDump",
            str(codigo_dump),
            "-CodigoArchivos",
            str(codigo_archivos),
            "-Ahora",
            ahora.strftime("%Y-%m-%dT%H:%M:%S"),
            "-Forzar",
            "si" if forzar else "no",
        ],
        capture_output=True,
        # Windows PowerShell escribe en la página de códigos de la consola, no en UTF-8.
        encoding="oem",
        errors="replace",
        check=False,
    )


def _archivos(tmp_path):
    archivos = tmp_path / "archivos"
    archivos.mkdir()
    (archivos / "adjunto.txt").write_text("ficticio", encoding="utf-8")
    return archivos


def _copia(destino, dias_antes, completa=True):
    carpeta = destino / f"remate-{(AHORA - timedelta(days=dias_antes)):%Y%m%d-%H%M%S}"
    carpeta.mkdir(parents=True)
    (carpeta / "dato.txt").write_text("copia", encoding="utf-8")
    if completa:
        (carpeta / ".remate-copia-completa").write_text("ReMate", encoding="utf-8")
    return carpeta


def test_retencion_7_diarias_y_4_semanales(tmp_path):
    """El 2026-11-02 es lunes. Con una copia por día hasta 40 días antes, se quedan la de hoy y
    las de los 6 días anteriores, y la más reciente de cada una de las 4 semanas anteriores (los
    domingos 25/10, 18/10, 11/10 y 04/10)."""
    destino = tmp_path / "copias"
    _archivos(tmp_path)
    copias = {dias: _copia(destino, dias) for dias in range(1, 41)}
    resultado = _ejecutar(tmp_path)
    assert resultado.returncode == 0, resultado.stderr
    quedan = {dias for dias, carpeta in copias.items() if carpeta.exists()}
    assert quedan == {1, 2, 3, 4, 5, 6, 8, 15, 22, 29}
    # La de hoy también se queda, con el volcado; los archivos van al espejo.
    hoy = destino / f"remate-{AHORA:%Y%m%d-%H%M%S}"
    assert (hoy / ".remate-copia-completa").is_file()
    assert (destino / "archivos-espejo/adjunto.txt").read_text(encoding="utf-8") == "ficticio"
    assert not (hoy / "archivos").exists()


def test_retencion_conserva_carpetas_ajenas_e_incompletas(tmp_path):
    destino = tmp_path / "copias"
    _archivos(tmp_path)
    for dias in range(1, 20):
        _copia(destino, dias)
    conservar = [
        destino / "otra-aplicacion",
        destino / "20200101-0000",
        destino / "remate-20201340-250000",
        _copia(destino, 365, completa=False),
    ]
    for carpeta in conservar[:3]:
        carpeta.mkdir()
        (carpeta / ".remate-copia-completa").write_text("ReMate", encoding="utf-8")
    resultado = _ejecutar(tmp_path)
    assert resultado.returncode == 0, resultado.stderr
    assert all(c.is_dir() for c in conservar)


def test_sin_la_carpeta_de_archivos_no_se_toca_el_espejo(tmp_path):
    """Con /MIR, un origen equivocado vaciaría el espejo."""
    espejo = tmp_path / "copias/archivos-espejo"
    espejo.mkdir(parents=True)
    (espejo / "adjunto.txt").write_text("ficticio", encoding="utf-8")
    resultado = _ejecutar(tmp_path, archivos=tmp_path / "no-existe")
    assert resultado.returncode != 0
    assert "No existe la carpeta de archivos" in resultado.stderr
    assert (espejo / "adjunto.txt").is_file()


@pytest.mark.parametrize("diarias", [0, -1])
def test_retencion_rechaza_diarias_no_positivas(tmp_path, diarias):
    _archivos(tmp_path)
    resultado = _ejecutar(tmp_path, diarias)
    assert resultado.returncode != 0
    assert "Diarias" in resultado.stderr
    assert not (tmp_path / "copias").exists()


@pytest.mark.parametrize(
    ("codigo_dump", "codigo_archivos", "mensaje"),
    [(1, 1, "pg_dump ha fallado"), (0, 8, "robocopy ha fallado")],
)
def test_copia_fallida_no_se_marca_ni_borra_copias_anteriores(
    tmp_path, codigo_dump, codigo_archivos, mensaje
):
    destino = tmp_path / "copias"
    anteriores = [_copia(destino, dias) for dias in range(1, 12)]
    _archivos(tmp_path)
    resultado = _ejecutar(tmp_path, codigo_dump=codigo_dump, codigo_archivos=codigo_archivos)
    assert resultado.returncode != 0
    assert mensaje in resultado.stderr
    assert all(a.is_dir() for a in anteriores)
    nuevas = [c for c in destino.glob("remate-*") if c not in anteriores]
    assert len(nuevas) == 1
    assert not (nuevas[0] / ".remate-copia-completa").exists()


def _esperadas(dias, diarias=7, semanales=4, ahora=AHORA):
    """La retención calculada en Python con la semana ISO (`isocalendar`), para comparar."""
    vistas, guardadas, quedan = set(), 0, set()
    for n, d in enumerate(sorted([0, *dias]), start=1):
        semana = (ahora - timedelta(days=d)).isocalendar()[:2]
        if n <= diarias:
            vistas.add(semana)
            quedan.add(d)
        elif semana not in vistas and guardadas < semanales:
            vistas.add(semana)
            guardadas += 1
            quedan.add(d)
    return quedan - {0}


@pytest.mark.parametrize(
    "ahora", [datetime(2027, 1, 14, 12, tzinfo=UTC), datetime(2025, 1, 9, 12, tzinfo=UTC)]
)
def test_retencion_en_el_cambio_de_anio_usa_la_semana_iso(tmp_path, ahora):
    """Con la semana ISO, el 01/01/2027 y el 31/12/2026 son la misma (2026-W53); con la de .NET
    serían distintas y se perdería la copia más antigua."""
    destino = tmp_path / "copias"
    _archivos(tmp_path)
    copias = {}
    for dias in range(1, 41):
        carpeta = destino / f"remate-{(ahora - timedelta(days=dias)):%Y%m%d-%H%M%S}"
        carpeta.mkdir(parents=True)
        (carpeta / ".remate-copia-completa").write_text("ReMate", encoding="utf-8")
        copias[dias] = carpeta
    resultado = _ejecutar(tmp_path, ahora=ahora)
    assert resultado.returncode == 0, resultado.stderr
    quedan = {dias for dias, carpeta in copias.items() if carpeta.exists()}
    assert quedan == _esperadas(range(1, 41), ahora=ahora)


def test_origen_vacio_no_vacia_el_espejo(tmp_path):
    """Una carpeta de archivos que existe pero está vacía (recreada, u otra) no vacía el único
    espejo: el script falla y pide -ForzarEspejo."""
    (tmp_path / "archivos").mkdir()
    espejo = tmp_path / "copias/archivos-espejo"
    espejo.mkdir(parents=True)
    for i in range(3):
        (espejo / f"adjunto{i}.txt").write_text("ficticio", encoding="utf-8")
    resultado = _ejecutar(tmp_path)
    assert resultado.returncode != 0
    assert "ForzarEspejo" in resultado.stderr
    assert len(list(espejo.iterdir())) == 3


def test_origen_con_muchos_menos_archivos_no_se_espeja(tmp_path):
    _archivos(tmp_path)
    espejo = tmp_path / "copias/archivos-espejo"
    espejo.mkdir(parents=True)
    for i in range(10):
        (espejo / f"otro{i}.txt").write_text("ficticio", encoding="utf-8")
    resultado = _ejecutar(tmp_path)
    assert resultado.returncode != 0
    assert "ForzarEspejo" in resultado.stderr
    assert len(list(espejo.iterdir())) == 10
    # Si se ha comprobado que el origen es el bueno, con -ForzarEspejo sí se espeja.
    assert _ejecutar(tmp_path, forzar=True).returncode == 0


def test_destino_dentro_de_los_archivos_no(tmp_path):
    """No se copia a sí mismo sin fin."""
    archivos = _archivos(tmp_path)
    resultado = _ejecutar(tmp_path, destino=archivos / "copias")
    assert resultado.returncode != 0
    assert "dentro" in resultado.stderr
    assert not (archivos / "copias").exists()
