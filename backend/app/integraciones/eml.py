"""Generador de `.eml` con la biblioteca estándar (CU-002, y más adelante CU-005 y CU-007).

La aplicación no envía correos: genera el `.eml`, el ingeniero lo abre con su cliente de correo
y lo envía él. La cabecera `X-Unsent: 1` hace que Outlook lo abra como un correo nuevo listo
para enviar, en lugar de como un correo recibido.
"""

from dataclasses import dataclass
from email.message import EmailMessage
from email.policy import SMTP


@dataclass(frozen=True)
class ArchivoAdjunto:
    nombre: str
    tipo_mime: str
    datos: bytes


def componer(
    asunto: str,
    cuerpo: str,
    *,
    para: list[str] = (),
    cco: list[str] = (),
    adjuntos: list[ArchivoAdjunto] = (),
) -> bytes:
    mensaje = EmailMessage(policy=SMTP)
    # Las cabeceras no admiten saltos de línea (segunda barrera; el título ya se guarda sin ellos).
    mensaje["Subject"] = " ".join(asunto.split())
    if para:
        mensaje["To"] = ", ".join(para)
    if cco:
        mensaje["Bcc"] = ", ".join(cco)
    mensaje["X-Unsent"] = "1"
    mensaje.set_content(cuerpo)
    for adjunto in adjuntos:
        principal, _, secundario = (adjunto.tipo_mime or "").partition("/")
        if not principal or not secundario:
            principal, secundario = "application", "octet-stream"
        mensaje.add_attachment(
            adjunto.datos, maintype=principal, subtype=secundario, filename=adjunto.nombre
        )
    return mensaje.as_bytes()
