"""Almacén de archivos: guarda los adjuntos en ARCHIVOS_DIR; la base de datos solo guarda la ruta.

Cada archivo se guarda como `<carpeta>/<uuid><extensión>`: el nombre original (que puede
tener tildes, espacios o repetirse) se conserva en la base de datos para mostrarlo.
"""

import re
import unicodedata
import uuid
from pathlib import Path, PurePosixPath, PureWindowsPath

TAMANO_MAXIMO = 25 * 1024 * 1024  # 25 MB por archivo (CU-001, límite habitual de Outlook)
# Entre todos los archivos de una misma subida: sin él, una petición
# podría llegar a 1 GB, el máximo por defecto de Waitress.
MAXIMO_POR_PETICION = 100 * 1024 * 1024


class ArchivoDemasiadoGrande(ValueError):
    def __init__(self, nombre: str):
        super().__init__(f"El archivo «{nombre}» supera el máximo de 25 MB.")
        self.nombre = nombre


def comprobar_tamano(nombre: str, tamano: int) -> None:
    if tamano > TAMANO_MAXIMO:
        raise ArchivoDemasiadoGrande(nombre)


def nombre_limpio(nombre: str) -> str:
    """Nombre de un archivo subido o sacado de un correo, sin carpetas ni caracteres de control
    (saltos de línea, NUL…): romperían el .eml, la descarga y el guardado en PostgreSQL."""
    sin_control = "".join(c for c in nombre if not unicodedata.category(c).startswith("C"))
    # PureWindowsPath separa tanto «/» como «\\».
    return PureWindowsPath(sin_control).name.strip() or "archivo"


def guardar(raiz: Path, carpeta: str, nombre_original: str, datos: bytes) -> str:
    """Escribe el archivo y devuelve su ruta relativa a `raiz` (con barras «/»)."""
    comprobar_tamano(nombre_original, len(datos))
    # Solo letras y números: evita, por ejemplo, flujos alternativos de NTFS («x.eml:flujo»).
    extension = re.sub(r"[^a-z0-9]", "", Path(nombre_original).suffix.lower())[:10]
    extension = f".{extension}" if extension else ""
    relativa = PurePosixPath(carpeta) / f"{uuid.uuid4().hex}{extension}"
    destino = raiz / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(datos)
    return str(relativa)


def ruta_absoluta(raiz: Path, relativa: str) -> Path:
    destino = (raiz / relativa).resolve()
    if not destino.is_relative_to(raiz.resolve()):
        raise ValueError("La ruta del archivo está fuera de ARCHIVOS_DIR.")
    return destino


def borrar(raiz: Path, relativa: str) -> None:
    ruta_absoluta(raiz, relativa).unlink(missing_ok=True)
