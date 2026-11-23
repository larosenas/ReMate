"""Lector propio de correos `.msg` de Outlook, solo con la biblioteca estándar (ADR 0013).

Un `.msg` es un archivo compuesto de Office (formato público MS-CFB: un pequeño sistema de
archivos con «carpetas» y «archivos» dentro) que guarda las propiedades del correo según
MS-OXMSG: cada propiedad va en un archivo `__substg1.0_PPPPTTTT` (PPPP, la propiedad; TTTT, su
tipo) o, si es de tamaño fijo (fechas, números), en `__properties_version1.0`. Cada adjunto es
una carpeta `__attach_version1.0_#NNNNNNNN`; un correo adjunto es otra carpeta
`__substg1.0_3701000D`
con el mismo formato, que se devuelve convertido en `.eml`.

Solo se lee lo que necesita ReMate: asunto, remitente, fecha, cuerpo (texto o HTML) y adjuntos.
El cuerpo que solo viene en RTF comprimido no se lee (se queda vacío): Outlook guarda casi
siempre también el texto. Todo error de formato acaba en `MsgNoValido`; los bucles y los
tamaños están limitados porque el archivo viene de fuera.
"""

import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email import message_from_string
from email.message import EmailMessage
from email.policy import default
from email.utils import format_datetime, parseaddr

FIRMA = bytes.fromhex("d0cf11e0a1b11ae1")
_FIN_CADENA = 0xFFFFFFFE
_LIBRE = 0xFFFFFFFF
_SIN_ENTRADA = 0xFFFFFFFF
# Carpeta y archivo en el directorio del contenedor (la raíz también es una carpeta).
_CARPETA, _ARCHIVO, _RAIZ = 1, 2, 5
# Un .msg de más de 25 MB ya lo rechaza la subida; esto solo evita cadenas sin fin.
_MAX_SECTORES = 1_000_000
# Lo que se puede leer de un .msg en total: unas pocas veces su tamaño. Un .msg normal lee cada
# flujo una vez; uno fabricado con muchos adjuntos (o correos adjuntos) que apuntan al mismo
# contenido lo leería y copiaría miles de veces.
_VECES_EL_TAMANO = 3
_LECTURA_MINIMA = 1024 * 1024
_MAX_ANIDADOS = 5

# Tipos de propiedad (MS-OXCDATA) y propiedades que se leen (MS-OXPROPS).
_UNICODE, _STRING8, _BINARIO, _OBJETO = "001F", "001E", "0102", "000D"
_PT_LONG, _PT_BOOLEAN, _PT_SYSTIME = 0x0003, 0x000B, 0x0040
P_ASUNTO = "0037"
P_CABECERAS = "007D"
P_CUERPO = "1000"
P_HTML = "1013"
P_REMITENTES = ("5D01", "5D02", "0C1F", "0065")  # SMTP del remitente, «en nombre de», otros
P_ENVIO, P_ENTREGA = 0x0039, 0x0E06
P_CODIGO_INTERNET = 0x3FDE
P_ADJ_DATOS = "3701"
P_ADJ_NOMBRES = ("3707", "3704", "3001")  # nombre largo, nombre corto, nombre que se ve
P_ADJ_MIME = "370E"
P_ADJ_CONTENT_ID = "3712"
P_ADJ_OCULTO = 0x7FFE


class MsgNoValido(ValueError):
    """El archivo no es un `.msg` que se pueda leer."""


@dataclass(frozen=True)
class AdjuntoMsg:
    nombre: str
    tipo_mime: str
    datos: bytes
    content_id: str = ""
    oculto: bool = False


@dataclass(frozen=True)
class MensajeMsg:
    fecha: datetime | None
    remitente: str | None
    asunto: str | None
    texto: str
    html: str
    adjuntos: tuple[AdjuntoMsg, ...] = field(default=())


# --- Contenedor (MS-CFB) ---------------------------------------------------------------------


@dataclass
class _Entrada:
    nombre: str
    tipo: int
    izquierda: int
    derecha: int
    hija: int
    inicio: int
    tamano: int


class _Contenedor:
    def __init__(self, datos: bytes):
        if len(datos) < 512 or datos[:8] != FIRMA:
            raise MsgNoValido("No es un archivo .msg de Outlook.")
        self.datos = datos
        self.leido = 0
        self.maximo_lectura = max(_VECES_EL_TAMANO * len(datos), _LECTURA_MINIMA)
        self.sector = 1 << struct.unpack_from("<H", datos, 0x1E)[0]
        self.mini_sector = 1 << struct.unpack_from("<H", datos, 0x20)[0]
        if self.sector not in (512, 4096) or self.mini_sector != 64:
            raise MsgNoValido("El .msg tiene un formato que no se reconoce.")
        (inicio_dir,) = struct.unpack_from("<I", datos, 0x30)
        (self.corte_mini,) = struct.unpack_from("<I", datos, 0x38)
        inicio_minifat, num_minifat = struct.unpack_from("<II", datos, 0x3C)
        inicio_difat, num_difat = struct.unpack_from("<II", datos, 0x44)
        difat = list(struct.unpack_from("<109I", datos, 0x4C))
        self.fat = self._fat(difat, inicio_difat, num_difat)
        directorio = self._cadena(inicio_dir)
        self.entradas = [self._entrada(directorio, i) for i in range(len(directorio) // 128)]
        if not self.entradas or self.entradas[0].tipo != _RAIZ:
            raise MsgNoValido("El .msg no tiene carpeta raíz.")
        raiz = self.entradas[0]
        self.minifat = (
            list(struct.unpack(f"<{len(m) // 4}I", m))
            if num_minifat and (m := self._cadena(inicio_minifat))
            else []
        )
        self.mini_datos = self._cadena(raiz.inicio)[: raiz.tamano] if raiz.tamano else b""

    def _leer_sector(self, numero: int) -> bytes:
        desde = (numero + 1) * self.sector
        if numero >= _FIN_CADENA - 5 or desde + self.sector > len(self.datos):
            raise MsgNoValido("El .msg está dañado o incompleto.")
        return self.datos[desde : desde + self.sector]

    def _fat(self, difat: list[int], siguiente: int, cuantos: int) -> list[int]:
        """La FAT, a partir de la DIFAT. Ninguna cadena puede tener más sectores de los que caben
        en el archivo ni pasar dos veces por el mismo: un .msg manipulado con la DIFAT en ciclo
        llenaría la memoria aunque ocupara 1 KB."""
        por_sector = self.sector // 4
        en_el_archivo = len(self.datos) // self.sector
        vistos: set[int] = set()
        for _ in range(min(cuantos, en_el_archivo, _MAX_SECTORES)):
            if siguiente in (_FIN_CADENA, _LIBRE):
                break
            if siguiente in vistos:
                raise MsgNoValido("El .msg está dañado o incompleto.")
            vistos.add(siguiente)
            valores = struct.unpack(f"<{por_sector}I", self._leer_sector(siguiente))
            difat.extend(valores[:-1])
            siguiente = valores[-1]
        sectores_fat = [n for n in difat if n != _LIBRE]
        if len(sectores_fat) > en_el_archivo:
            raise MsgNoValido("El .msg está dañado o incompleto.")
        fat = []
        for numero in sectores_fat:
            fat.extend(struct.unpack(f"<{por_sector}I", self._leer_sector(numero)))
        return fat

    def _cadena(self, inicio: int) -> bytes:
        """Una cadena de sectores. No puede pasar dos veces por el mismo sector: un directorio en
        ciclo recorrería hasta un millón de sectores antes de fallar."""
        partes, numero, vistos = [], inicio, set()
        while numero != _FIN_CADENA:
            if numero >= len(self.fat) or numero in vistos or len(vistos) >= _MAX_SECTORES:
                raise MsgNoValido("El .msg está dañado o incompleto.")
            vistos.add(numero)
            partes.append(self._leer_sector(numero))
            numero = self.fat[numero]
        return b"".join(partes)

    def _mini_cadena(self, inicio: int, tamano: int) -> bytes:
        """Una cadena de minisectores, con el total que se lleva (sumarlo en cada vuelta sería
        cuadrático) y sin pasar dos veces por el mismo."""
        partes, numero, vistos, total = [], inicio, set(), 0
        while numero != _FIN_CADENA and total < tamano:
            desde = numero * self.mini_sector
            if numero >= len(self.minifat) or numero in vistos:
                raise MsgNoValido("El .msg está dañado o incompleto.")
            if desde + self.mini_sector > len(self.mini_datos):
                raise MsgNoValido("El .msg está dañado o incompleto.")
            vistos.add(numero)
            partes.append(self.mini_datos[desde : desde + self.mini_sector])
            total += self.mini_sector
            numero = self.minifat[numero]
        return b"".join(partes)[:tamano]

    @staticmethod
    def _entrada(directorio: bytes, i: int) -> _Entrada:
        base = i * 128
        largo = min(struct.unpack_from("<H", directorio, base + 0x40)[0], 64)
        nombre = directorio[base : base + max(largo - 2, 0)].decode("utf-16-le", "replace")
        izquierda, derecha, hija = struct.unpack_from("<III", directorio, base + 0x44)
        inicio, tamano = struct.unpack_from("<IQ", directorio, base + 0x74)
        tipo = directorio[base + 0x42]
        return _Entrada(nombre, tipo, izquierda, derecha, hija, inicio, tamano)

    def hijos(self, indice: int) -> dict[str, int]:
        """Lo que hay dentro de una carpeta: {nombre en mayúsculas: índice de la entrada}."""
        encontrados, pendientes, vistos = {}, [self.entradas[indice].hija], set()
        while pendientes:
            i = pendientes.pop()
            if i == _SIN_ENTRADA or i in vistos:
                continue
            if i >= len(self.entradas):
                raise MsgNoValido("El .msg está dañado o incompleto.")
            vistos.add(i)
            entrada = self.entradas[i]
            encontrados[entrada.nombre.upper()] = i
            pendientes.extend((entrada.izquierda, entrada.derecha))
        return encontrados

    def leer(self, indice: int) -> bytes:
        entrada = self.entradas[indice]
        if entrada.tipo != _ARCHIVO:
            raise MsgNoValido("El .msg está dañado o incompleto.")
        if entrada.tamano < self.corte_mini:
            datos = self._mini_cadena(entrada.inicio, entrada.tamano)
        else:
            datos = self._cadena(entrada.inicio)[: entrada.tamano]
        self.leido += len(datos)
        if self.leido > self.maximo_lectura:
            raise MsgNoValido("El .msg está dañado o incompleto.")
        return datos


# --- Propiedades del correo (MS-OXMSG) -------------------------------------------------------


class _Carpeta:
    """Las propiedades de una carpeta del `.msg`: el correo, un adjunto o un correo adjunto."""

    def __init__(self, contenedor: _Contenedor, indice: int, cabecera: int):
        self.c = contenedor
        self.hijos = contenedor.hijos(indice)
        self.fijas: dict[int, tuple[int, bytes]] = {}
        propiedades = self.hijos.get("__PROPERTIES_VERSION1.0")
        if propiedades is not None:
            datos = contenedor.leer(propiedades)
            for desde in range(cabecera, len(datos) - 15, 16):
                tipo, numero = struct.unpack_from("<HH", datos, desde)
                self.fijas[numero] = (tipo, datos[desde + 8 : desde + 16])

    def _bruto(self, propiedad: str, tipo: str) -> bytes | None:
        indice = self.hijos.get(f"__SUBSTG1.0_{propiedad}{tipo}")
        return None if indice is None else self.c.leer(indice)

    def texto(self, propiedad: str) -> str | None:
        unicode = self._bruto(propiedad, _UNICODE)
        if unicode is not None:
            return unicode.decode("utf-16-le", "replace").rstrip("\x00")
        ocho = self._bruto(propiedad, _STRING8)
        if ocho is not None:
            return _decodificar(ocho.rstrip(b"\x00"), self.numero(P_CODIGO_INTERNET))
        return None

    def binario(self, propiedad: str) -> bytes | None:
        return self._bruto(propiedad, _BINARIO)

    def numero(self, propiedad: int) -> int | None:
        tipo, valor = self.fijas.get(propiedad, (None, b""))
        if tipo in (_PT_LONG, _PT_BOOLEAN):
            return struct.unpack_from("<i", valor)[0]
        return None

    def fecha(self, propiedad: int) -> datetime | None:
        tipo, valor = self.fijas.get(propiedad, (None, b""))
        if tipo != _PT_SYSTIME:
            return None
        (centenas_ns,) = struct.unpack_from("<Q", valor)
        try:
            return datetime(1601, 1, 1, tzinfo=UTC) + timedelta(microseconds=centenas_ns // 10)
        except OverflowError:
            return None


def _decodificar(datos: bytes, codigo: int | None) -> str:
    # El código de página de Windows (65001 = UTF-8, 1252 = Europa occidental…).
    for codificacion in (f"cp{codigo}" if codigo else None, "utf-8", "cp1252"):
        if codificacion:
            try:
                return datos.decode("utf-8" if codificacion == "cp65001" else codificacion)
            except LookupError, UnicodeDecodeError:
                continue
    return datos.decode("latin-1")


def _mensaje(contenedor: _Contenedor, indice: int, cabecera: int, nivel: int) -> MensajeMsg:
    carpeta = _Carpeta(contenedor, indice, cabecera)
    cabeceras = message_from_string(carpeta.texto(P_CABECERAS) or "", policy=default)
    remitente = next(
        (t for p in P_REMITENTES if (t := (carpeta.texto(p) or "").strip()) and "@" in t), None
    ) or (parseaddr(str(cabeceras["From"] or ""))[1] or None)
    fecha = carpeta.fecha(P_ENVIO) or carpeta.fecha(P_ENTREGA)
    if fecha is None and cabeceras["Date"]:
        try:
            fecha = cabeceras["Date"].datetime
        except AttributeError, TypeError, ValueError:
            fecha = None
    html = carpeta.texto(P_HTML)
    if html is None and (bruto := carpeta.binario(P_HTML)) is not None:
        html = _decodificar(bruto, carpeta.numero(P_CODIGO_INTERNET))
    adjuntos = tuple(
        _adjunto(contenedor, i, nivel)
        for nombre, i in sorted(carpeta.hijos.items())
        if nombre.startswith("__ATTACH_VERSION1.0_#")
    )
    return MensajeMsg(
        fecha=fecha,
        remitente=remitente.lower() if remitente else None,
        asunto=carpeta.texto(P_ASUNTO),
        texto=carpeta.texto(P_CUERPO) or "",
        html=html or "",
        adjuntos=adjuntos,
    )


def _adjunto(contenedor: _Contenedor, indice: int, nivel: int) -> AdjuntoMsg:
    carpeta = _Carpeta(contenedor, indice, 8)
    nombre = next((t for p in P_ADJ_NOMBRES if (t := carpeta.texto(p))), "adjunto")
    oculto = bool(carpeta.numero(P_ADJ_OCULTO))
    content_id = (carpeta.texto(P_ADJ_CONTENT_ID) or "").strip().strip("<>")
    incrustado = carpeta.hijos.get(f"__SUBSTG1.0_{P_ADJ_DATOS}{_OBJETO}")
    if incrustado is not None:
        if nivel >= _MAX_ANIDADOS:
            raise MsgNoValido("El .msg tiene demasiados correos adjuntos uno dentro de otro.")
        reenviado = _mensaje(contenedor, incrustado, 24, nivel + 1)
        asunto = reenviado.asunto or "correo adjunto"
        return AdjuntoMsg(f"{asunto}.eml", "message/rfc822", a_eml(reenviado), oculto=oculto)
    datos = carpeta.binario(P_ADJ_DATOS) or b""
    tipo_mime = (carpeta.texto(P_ADJ_MIME) or "application/octet-stream").strip().lower()
    return AdjuntoMsg(nombre, tipo_mime, datos, content_id.lower(), oculto)


def a_eml(mensaje: MensajeMsg) -> bytes:
    """Un correo adjunto dentro del `.msg`, como `.eml` (lo que ya saben leer ReMate y la IA)."""
    eml = EmailMessage()
    if mensaje.remitente:
        eml["From"] = mensaje.remitente
    if mensaje.asunto:
        eml["Subject"] = " ".join(mensaje.asunto.split())
    if mensaje.fecha:
        eml["Date"] = format_datetime(mensaje.fecha)
    eml.set_content(mensaje.texto or "")
    if mensaje.html:
        eml.add_alternative(mensaje.html, subtype="html")
    for adjunto in mensaje.adjuntos:
        principal, _, secundario = adjunto.tipo_mime.partition("/")
        if principal == "message":
            principal, secundario = "application", "octet-stream"
        eml.add_attachment(
            adjunto.datos,
            principal or "application",
            secundario or "octet-stream",
            filename=adjunto.nombre,
        )
    return eml.as_bytes()


def leer(datos: bytes) -> MensajeMsg:
    try:
        contenedor = _Contenedor(datos)
        return _mensaje(contenedor, 0, 32, 0)
    except MsgNoValido:
        raise
    except (struct.error, IndexError, ValueError, KeyError) as e:
        raise MsgNoValido("El .msg está dañado o incompleto.") from e
