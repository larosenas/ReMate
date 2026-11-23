"""Lector de correos de oferta, `.eml` y `.msg`, con la biblioteca estándar (CU-004).

Lee la fecha de envío, el remitente, el asunto, el cuerpo y los adjuntos, igual para
los dos formatos. El `.eml` con el paquete `email`; el `.msg` de Outlook, con el lector propio
de `correos_msg` (ADR 0013, sin dependencias). Las imágenes incrustadas en el cuerpo (logos de
la firma) no cuentan como adjuntos.
"""

import html
import re
from dataclasses import dataclass, field
from datetime import datetime
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default
from email.utils import parseaddr

from app.integraciones import correos_msg
from app.integraciones.archivos import nombre_limpio

MENSAJE_DEMASIADO_ANIDADO = (
    "El correo tiene demasiadas partes unas dentro de otras: no parece un correo normal."
)


class CorreoNoValido(ValueError):
    """El archivo no es un `.eml` ni un `.msg` que se pueda leer."""


@dataclass(frozen=True)
class AdjuntoCorreo:
    nombre: str
    tipo_mime: str
    datos: bytes


@dataclass(frozen=True)
class CorreoLeido:
    fecha: datetime | None
    remitente: str | None
    asunto: str | None
    cuerpo: str
    adjuntos: tuple[AdjuntoCorreo, ...] = field(default=())


MENSAJE_MSG_NO_VALIDO = (
    "No se ha podido leer el .msg. En Outlook, abre el correo y usa «Archivo > Guardar como» "
    "con el tipo «.eml»; después súbelo aquí."
)


def _extension(nombre: str) -> str:
    extension = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    if extension not in ("eml", "msg"):
        raise CorreoNoValido("El correo de la oferta tiene que ser un archivo .eml o .msg.")
    return extension


def _texto_de_html(contenido: str) -> str:
    sin_estilos = re.sub(r"(?is)<(script|style).*?</\1>", " ", contenido)
    con_saltos = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>", "\n", sin_estilos)
    texto = html.unescape(re.sub(r"<[^>]+>", " ", con_saltos))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", texto)).strip()


# Partes dentro de partes que se admiten. Un correo normal tiene 3 o 4; uno fabricado con miles
# daría RecursionError (error 500) en `get_body` y `_hojas`.
MAXIMO_ANIDADO = 30


def _demasiado_anidado(mensaje: EmailMessage) -> bool:
    """Profundidad de las partes, sin recursión."""
    pendientes = [(mensaje, 0)]
    while pendientes:
        parte, nivel = pendientes.pop()
        if nivel > MAXIMO_ANIDADO:
            return True
        # También los correos reenviados (message/rfc822), cuyo contenido es otro correo: con
        # 300 uno dentro de otro daría RecursionError al copiarlos.
        contenido = parte.get_payload()
        if parte.get_content_maintype() in ("multipart", "message") and isinstance(contenido, list):
            pendientes.extend((hija, nivel + 1) for hija in contenido)
    return False


def _hojas(parte: EmailMessage):
    """Las partes finales del correo, sin entrar en un correo adjunto (es un adjunto entero)."""
    if parte.get_content_maintype() == "multipart":
        for hija in parte.iter_parts():
            yield from _hojas(hija)
    else:
        yield parte


def _contenido(parte: EmailMessage) -> str:
    try:
        return parte.get_content()
    except LookupError, UnicodeDecodeError:
        return (parte.get_payload(decode=True) or b"").decode("latin-1", errors="replace")


def _es_adjunto(parte: EmailMessage, html_cuerpo: str) -> bool:
    if parte.get_content_type() == "message/rfc822":
        return True
    # Una imagen que usa el cuerpo en HTML (`cid:`) es parte del cuerpo (los logos de la
    # firma), no un adjunto, aunque venga marcada como adjunto (pasa según el programa).
    cid = str(parte["Content-ID"] or "").strip().strip("<>").lower()
    if parte.get_content_maintype() == "image" and cid and f"cid:{cid}" in html_cuerpo:
        return False
    return parte.get_content_disposition() == "attachment" or bool(parte.get_filename())


def _adjunto(parte: EmailMessage) -> AdjuntoCorreo:
    if parte.get_content_type() == "message/rfc822":
        reenviado = parte.get_payload(0)
        asunto = str(reenviado["Subject"] or "") or "correo adjunto"
        nombre = parte.get_filename() or f"{asunto}.eml"
        return AdjuntoCorreo(nombre_limpio(nombre), "message/rfc822", reenviado.as_bytes())
    nombre = nombre_limpio(parte.get_filename() or "adjunto")
    return AdjuntoCorreo(nombre, parte.get_content_type(), parte.get_payload(decode=True) or b"")


def _leer_msg(datos: bytes) -> CorreoLeido:
    try:
        mensaje = correos_msg.leer(datos)
    except correos_msg.MsgNoValido as e:
        raise CorreoNoValido(MENSAJE_MSG_NO_VALIDO) from e
    cuerpo = mensaje.texto.strip() or _texto_de_html(mensaje.html)
    html_cuerpo = mensaje.html.lower()

    def del_cuerpo(adjunto: correos_msg.AdjuntoMsg) -> bool:
        # La misma regla que en el .eml; Outlook además marca ocultas las imágenes del cuerpo.
        if not adjunto.tipo_mime.startswith("image/"):
            return False
        usada = adjunto.content_id and f"cid:{adjunto.content_id}" in html_cuerpo
        return bool(usada or adjunto.oculto)

    adjuntos = tuple(
        AdjuntoCorreo(nombre_limpio(a.nombre), a.tipo_mime, a.datos)
        for a in mensaje.adjuntos
        if not del_cuerpo(a)
    )
    return CorreoLeido(
        fecha=mensaje.fecha,
        remitente=mensaje.remitente,
        asunto=mensaje.asunto,
        cuerpo=cuerpo.strip(),
        adjuntos=adjuntos,
    )


# Antes de analizar un .eml: la cabecera del correo y el número de partes. El paquete `email` se
# vuelve muy lento con una cabecera de 1 MB plegada en muchas líneas (26 s) o con 100 000 partes
# (30 s); un correo normal tiene unos pocos KB de cabecera y unas decenas de partes.
MAXIMO_CABECERA = 256 * 1024
MAXIMO_PARTES = 1000
_CONTENT_TYPE = re.compile(rb"(?im)^content-type[ \t]*:")


def _demasiado_grande(datos: bytes) -> bool:
    finales = [i for i in (datos.find(b"\r\n\r\n"), datos.find(b"\n\n")) if i >= 0]
    cabecera = min(finales) if finales else len(datos)
    if cabecera > MAXIMO_CABECERA:
        return True
    return sum(1 for _ in _CONTENT_TYPE.finditer(datos)) > MAXIMO_PARTES


def leer(nombre: str, datos: bytes) -> CorreoLeido:
    if _extension(nombre) == "msg":
        return _leer_msg(datos)
    if _demasiado_grande(datos):
        raise CorreoNoValido(
            "El correo tiene una cabecera o un número de partes fuera de lo normal: no se puede "
            "leer."
        )
    try:
        return _leer_eml(datos)
    except RecursionError:
        raise CorreoNoValido(MENSAJE_DEMASIADO_ANIDADO) from None


def _leer_eml(datos: bytes) -> CorreoLeido:
    try:
        mensaje = message_from_bytes(datos, policy=default)
    except RecursionError:
        raise CorreoNoValido(MENSAJE_DEMASIADO_ANIDADO) from None
    if _demasiado_anidado(mensaje):
        raise CorreoNoValido(MENSAJE_DEMASIADO_ANIDADO)
    # Un .eml de verdad trae al menos alguna de estas cabeceras.
    if not any(mensaje[c] for c in ("From", "Date", "Subject")):
        raise CorreoNoValido("El archivo no parece un correo .eml válido.")
    try:
        fecha = mensaje["Date"].datetime if mensaje["Date"] else None
    except AttributeError, TypeError, ValueError:
        fecha = None
    remitente = parseaddr(str(mensaje["From"] or ""))[1].lower() or None
    asunto = str(mensaje["Subject"]) if mensaje["Subject"] else None
    cuerpo = ""
    parte = mensaje.get_body(preferencelist=("plain", "html"))
    if parte is not None:
        contenido = _contenido(parte)
        cuerpo = _texto_de_html(contenido) if parte.get_content_subtype() == "html" else contenido
    html = mensaje.get_body(preferencelist=("html",))
    html_cuerpo = _contenido(html).lower() if html is not None else ""
    adjuntos = tuple(
        _adjunto(p)
        for p in _hojas(mensaje)
        if p is not parte and p is not html and _es_adjunto(p, html_cuerpo)
    )
    return CorreoLeido(
        fecha=fecha, remitente=remitente, asunto=asunto, cuerpo=cuerpo.strip(), adjuntos=adjuntos
    )
