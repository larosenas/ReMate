"""CU-007 — Número de pedido en el PDF del pedido oficial de SAP, sin IA ni dependencias.

En el pedido, el número va debajo del logo, detrás de «Purchase Order». Comprobado con pedidos
reales (fuera del repositorio): los genera SAP NetWeaver 750, el texto va en los contenidos de la
página como cadenas en hexadecimal (`<…> Tj`) y el número sale como «PURCHASE ORDER NO.
4500012345». No se envía a la IA: se lee aquí con la biblioteca estándar.

Solo se buscan los textos que dibuja la página (operadores `Tj`, `TJ`, `'` y `"`) en los
contenidos sin comprimir o con FlateDecode. Si el PDF es de otro tipo o no lo dice, no hay número
y se escribe a mano.
"""

import re
import zlib

# El número de pedido de SAP: de 6 a 12 cifras (habitualmente, 10: 45…).
_NUMERO = re.compile(r"PURCHASE\s+ORDER\s+(?:NO|NUMBER|NR|N[º°])\.?\s*[:#]?\s*(\d{6,12})\b", re.I)
_FLUJO = re.compile(rb"stream\r?\n(.*?)\r?\n?endstream", re.S)
# Una cadena del PDF: (literal) o <hexadecimal>.
_CADENA = rb"\((?:\\.|[^\\)])*\)|<[0-9A-Fa-f\s]*>"
_TEXTO = re.compile(rb"(" + _CADENA + rb")\s*(?:Tj|'|\")|\[((?:" + _CADENA + rb"|[^\]])*)\]\s*TJ")
_EN_ARRAY = re.compile(_CADENA)
# Un pedido ocupa unos cientos de KB: con esto un PDF malicioso no llena la memoria.
_MAXIMO_DESCOMPRIMIDO = 20 * 1024 * 1024
_ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def _cadena(bruta: bytes) -> str:
    if bruta.startswith(b"<"):
        hexa = re.sub(rb"\s", b"", bruta[1:-1])
        if len(hexa) % 2:
            hexa += b"0"
        datos = bytes.fromhex(hexa.decode())
        # Dos bytes por letra (fuentes con identidad): si empieza por un cero, es UTF-16.
        if len(datos) > 1 and datos[0] == 0:
            return datos.decode("utf-16-be", "replace")
        return datos.decode("cp1252", "replace")
    interior = bruta[1:-1]
    interior = re.sub(rb"\\([nrtbf])", lambda m: _ESCAPES[m.group(1)], interior)
    interior = re.sub(rb"\\([0-7]{1,3})", lambda m: bytes([int(m.group(1), 8) & 0xFF]), interior)
    interior = re.sub(rb"\\(.)", rb"\1", interior)
    return interior.decode("cp1252", "replace")


def _contenidos(pdf: bytes):
    restante = _MAXIMO_DESCOMPRIMIDO
    for flujo in _FLUJO.finditer(pdf):
        datos = flujo.group(1)
        try:
            descompresor = zlib.decompressobj()
            datos = descompresor.decompress(datos, restante)
        except zlib.error:
            pass  # Sin comprimir (así van los textos en los pedidos de ejemplo).
        restante -= len(datos)
        if restante <= 0:
            return
        yield datos


def textos(pdf: bytes) -> list[str]:
    """Los textos que dibujan las páginas, en orden."""
    encontrados = []
    for contenido in _contenidos(pdf):
        for simple, array in _TEXTO.findall(contenido):
            if simple:
                encontrados.append(_cadena(simple))
            else:
                encontrados.append("".join(_cadena(c) for c in _EN_ARRAY.findall(array)))
    return encontrados


def numero_de_pedido(pdf: bytes) -> str | None:
    """El número de «PURCHASE ORDER NO. …», o None si no está (o no es un PDF que se entienda)."""
    if not pdf.startswith(b"%PDF"):
        return None
    try:
        encontrado = _NUMERO.search(" ".join(textos(pdf)))
    except ValueError:
        return None
    return encontrado.group(1) if encontrado else None
