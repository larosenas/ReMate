"""Prepara los adjuntos de una oferta para OpenAI Responses API (CU-004, pasos 3 y 4).

Según el formato que indica el ingeniero:
- PDF: se envía el archivo tal cual; OpenAI extrae el texto y procesa las páginas como imágenes.
- Imagen (PNG, JPEG, WebP o GIF): se envía como imagen.
- Word (`.docx`) y Excel (`.xlsx`): se extrae el texto aquí, con la biblioteca estándar, porque
  ya existe código probado para extraerlos sin enviar el archivo completo.
- Otro: solo si es texto (`.txt`, `.csv`…).
Lo que no se puede leer se salta con un aviso para el ingeniero.
"""

import base64
import io
import posixpath
import zipfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree

MAXIMO_TEXTO = 60_000  # caracteres por adjunto de texto
MAXIMO_FILAS = 1_000  # filas por hoja de Excel
# Tamaño descomprimido de cada XML de un .docx o .xlsx. ElementTree ocupa unas 20 veces el XML:
# con 50 MB, un archivo de 75 KB gastaría 800 MB. Una oferta real tiene XML
# de pocos cientos de KB.
MAXIMO_XML = 10 * 1024 * 1024
# Un .xlsx pequeño con muchas hojas sobre un XML grande y muy comprimido tendría el servidor
# decenas de segundos descomprimiendo: límite total
# de lo descomprimido en un libro y de hojas, y cada hoja se lee una sola vez.
MAXIMO_XML_TOTAL = 20 * 1024 * 1024
MAXIMO_HOJAS = 50
MAXIMO_ENVIO = 30 * 1024 * 1024  # PDF e imágenes en una petición (OpenAI admite 50 MB en base64)

IMAGENES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
TEXTO = (".txt", ".csv", ".tsv", ".md", ".html", ".htm", ".xml", ".json")

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
_REL = "{http://schemas.openxmlformats.org/package/2006/relationships}"


# Lo que puede lanzar zipfile al leer un archivo interno dañado, cifrado o con una compresión que
# no admite, además de un XML mal formado o una pieza que falta.
_ERRORES_DE_LECTURA = (
    KeyError,
    ElementTree.ParseError,
    zipfile.BadZipFile,
    zlib.error,
    NotImplementedError,
    RuntimeError,
    EOFError,
)


class ArchivoIlegible(ValueError):
    """El adjunto no se puede leer (formato antiguo, dañado…)."""


@dataclass
class Contenido:
    """Partes del mensaje para la IA y avisos de lo que no se ha podido enviar."""

    partes: list[dict] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    _bytes: int = 0

    def texto(self, titulo: str, texto: str) -> None:
        if len(texto) > MAXIMO_TEXTO:
            texto = texto[:MAXIMO_TEXTO]
            self.avisos.append(f"{titulo}: es muy largo y la IA solo ha leído el principio.")
        self.partes.append({"type": "input_text", "text": f"{titulo}:\n{texto}"})

    def archivo(self, nombre: str, datos: bytes) -> bool:
        if self._bytes + len(datos) > MAXIMO_ENVIO:
            self.avisos.append(
                f"«{nombre}» no se ha enviado a la IA: los adjuntos pesan demasiado."
            )
            return False
        self._bytes += len(datos)
        return True


def _xml(
    paquete: zipfile.ZipFile, nombre: str, leido: list[int] | None = None
) -> ElementTree.Element:
    """El XML `nombre` del paquete. `leido`: lo descomprimido hasta ahora en este archivo (se
    suma y no puede pasar de MAXIMO_XML_TOTAL). Se lee con un tope de bytes reales: el tamaño
    que declara el ZIP (`file_size`) lo puede falsear el archivo, y `read()` sin tope descomprimiría
    hasta 2 GiB antes de comprobar nada."""
    with paquete.open(nombre) as archivo:
        datos = archivo.read(MAXIMO_XML + 1)
    if len(datos) > MAXIMO_XML:
        raise ArchivoIlegible("demasiado grande")
    if leido is not None:
        leido[0] += len(datos)
        if leido[0] > MAXIMO_XML_TOTAL:
            raise ArchivoIlegible("demasiado grande")
    # S314: ElementTree no resuelve entidades externas y, con el expat de Python 3.15 (2.4.1 o
    # posterior), tampoco es vulnerable a la expansión de entidades («billion laughs»); el tamaño
    # del XML está limitado arriba (tabla de vulnerabilidades del módulo xml de Python).
    return ElementTree.fromstring(datos)  # noqa: S314


def _abrir(datos: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(datos))
    except zipfile.BadZipFile as error:
        raise ArchivoIlegible("no es un archivo de Office válido") from error


def _texto_de(elemento: ElementTree.Element, etiqueta: str) -> str:
    return "".join(t.text or "" for t in elemento.iter(etiqueta))


def texto_word(datos: bytes) -> str:
    """Párrafos y tablas (celdas separadas por « | ») de un `.docx`, en orden."""
    try:
        with _abrir(datos) as paquete:
            cuerpo = _xml(paquete, "word/document.xml").find(f"{_W}body")
    except _ERRORES_DE_LECTURA as error:
        raise ArchivoIlegible("no se encuentra el texto del documento") from error
    lineas = []
    for bloque in cuerpo if cuerpo is not None else []:
        if bloque.tag == f"{_W}p":
            lineas.append(_texto_de(bloque, f"{_W}t"))
        elif bloque.tag == f"{_W}tbl":
            for fila in bloque.iter(f"{_W}tr"):
                celdas = [_texto_de(c, f"{_W}t").strip() for c in fila.iter(f"{_W}tc")]
                lineas.append(" | ".join(celdas))
    return "\n".join(lineas).strip()


def texto_excel(datos: bytes) -> str:
    """Cada hoja de un `.xlsx` con sus filas (celdas separadas por tabuladores)."""
    try:
        with _abrir(datos) as paquete:
            leido = [0]
            compartidas = []
            if "xl/sharedStrings.xml" in paquete.namelist():
                raiz = _xml(paquete, "xl/sharedStrings.xml", leido)
                compartidas = [_texto_de(si, f"{_S}t") for si in raiz.iter(f"{_S}si")]
            libro = _xml(paquete, "xl/workbook.xml", leido)
            relaciones = {
                r.get("Id"): r.get("Target", "")
                for r in _xml(paquete, "xl/_rels/workbook.xml.rels", leido).iter(
                    f"{_REL}Relationship"
                )
            }
            hojas, rutas_leidas = [], set()
            for hoja in libro.iter(f"{_S}sheet"):
                destino = relaciones.get(hoja.get(f"{_R}id"), "")
                ruta = posixpath.normpath(
                    destino.lstrip("/") if destino.startswith("/") else f"xl/{destino}"
                )
                if ruta in rutas_leidas:
                    continue
                if len(rutas_leidas) == MAXIMO_HOJAS:
                    hojas.append(f"(…el libro tiene más de {MAXIMO_HOJAS} hojas; no se leen)")
                    break
                rutas_leidas.add(ruta)
                filas = []
                for fila in _xml(paquete, ruta, leido).iter(f"{_S}row"):
                    if len(filas) == MAXIMO_FILAS:
                        filas.append("(…más filas)")
                        break
                    valores = [_valor_celda(c, compartidas) for c in fila.iter(f"{_S}c")]
                    if any(valores):
                        filas.append("\t".join(valores))
                hojas.append(f"Hoja «{hoja.get('name')}»:\n" + "\n".join(filas))
    except _ERRORES_DE_LECTURA as error:
        raise ArchivoIlegible("no se encuentran las hojas del libro") from error
    return "\n\n".join(hojas).strip()


def _valor_celda(celda: ElementTree.Element, compartidas: list[str]) -> str:
    tipo = celda.get("t")
    if tipo == "inlineStr":
        return _texto_de(celda, f"{_S}t").strip()
    valor = celda.findtext(f"{_S}v") or ""
    if tipo == "s":
        try:
            return compartidas[int(valor)].strip()
        except ValueError, IndexError:
            return ""
    return valor.strip()


def preparar(contenido: Contenido, nombre: str, formato: str | None, datos: bytes) -> None:
    """Añade un adjunto al contenido para la IA o, si no se puede leer, un aviso."""
    extension = Path(nombre).suffix.lower()
    titulo = f"Adjunto «{nombre}»"
    try:
        if formato == "pdf":
            if contenido.archivo(nombre, datos):
                codificado = base64.b64encode(datos).decode("ascii")
                contenido.partes.append(
                    {
                        "type": "input_file",
                        "filename": nombre,
                        "file_data": f"data:application/pdf;base64,{codificado}",
                        # El texto se extrae igual; reduce los tokens de las imágenes de página.
                        "detail": "low",
                    }
                )
        elif formato == "imagen" and extension in IMAGENES:
            if contenido.archivo(nombre, datos):
                codificado = base64.b64encode(datos).decode("ascii")
                url = f"data:{IMAGENES[extension]};base64,{codificado}"
                contenido.partes.append({"type": "input_text", "text": f"{titulo} (imagen):"})
                contenido.partes.append({"type": "input_image", "image_url": url, "detail": "auto"})
        elif formato == "word" and extension in (".docx", ".docm"):
            contenido.texto(f"{titulo} (Word)", texto_word(datos))
        elif formato == "excel" and extension in (".xlsx", ".xlsm"):
            contenido.texto(f"{titulo} (Excel)", texto_excel(datos))
        elif formato == "otro" and extension in TEXTO:
            contenido.texto(titulo, datos.decode("utf-8", errors="replace"))
        else:
            contenido.avisos.append(_aviso_formato(nombre, formato, extension))
    except ArchivoIlegible as error:
        contenido.avisos.append(f"«{nombre}» no se ha podido leer ({error}). Revisa sus datos.")


def _aviso_formato(nombre: str, formato: str | None, extension: str) -> str:
    if formato == "imagen":
        consejo = "guárdala como PNG o JPEG"
    elif formato in ("word", "excel") and extension in (".doc", ".xls"):
        consejo = "guárdalo como PDF o en el formato nuevo (.docx o .xlsx)"
    else:
        consejo = "guárdalo como PDF"
    return f"La IA no puede leer «{nombre}»: {consejo} o copia sus datos a mano."
