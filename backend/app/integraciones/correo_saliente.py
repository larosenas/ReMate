"""Correo saliente por SMTP con la biblioteca estándar (ADR 0004).

La aplicación solo envía el recordatorio de entrega al peticionario (CU-009) y el
aviso del paso 5 a los avisados del pedido SAP y su recordatorio semanal (CU-006). Los demás
correos los genera como `.eml` y los envía el ingeniero desde Outlook.

Configuración (`SMTP_*` en el `.env`): con el puerto 465 se usa SSL directo; con otro puerto y
`SMTP_SECURE=true`, STARTTLS. Usuario y contraseña son opcionales (un relé interno puede no
pedirlos).
"""

import contextlib
import smtplib
import ssl
from contextlib import contextmanager
from email.message import EmailMessage

from app.config import Config

TIEMPO_MAXIMO = 30  # segundos para conectar y para cada orden al servidor


class ErrorCorreo(RuntimeError):
    """El correo saliente no está configurado o el servidor no responde."""


def componer(remitente: str, para: str, asunto: str, cuerpo: str) -> EmailMessage:
    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["To"] = para
    # Las cabeceras no admiten saltos de línea.
    mensaje["Subject"] = " ".join(asunto.split())
    mensaje.set_content(cuerpo)
    return mensaje


@contextmanager
def conexion(config: Config):
    """Abre la conexión SMTP una sola vez para enviar varios correos."""
    if not config.smtp_host or not config.smtp_from:
        raise ErrorCorreo("El correo saliente no está configurado (SMTP_HOST y SMTP_FROM).")
    if config.smtp_user and config.smtp_port != 465 and not config.smtp_secure:
        raise ErrorCorreo(
            "Con usuario y contraseña hace falta una conexión cifrada (SMTP_SECURE=true o el "
            "puerto 465): si no, la contraseña viajaría sin cifrar."
        )
    contexto = ssl.create_default_context()
    try:
        if config.smtp_port == 465:
            servidor = smtplib.SMTP_SSL(
                config.smtp_host, config.smtp_port, timeout=TIEMPO_MAXIMO, context=contexto
            )
        else:
            servidor = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=TIEMPO_MAXIMO)
            if config.smtp_secure:
                servidor.starttls(context=contexto)
        if config.smtp_user:
            servidor.login(config.smtp_user, config.smtp_password)
    except (OSError, smtplib.SMTPException) as error:
        raise ErrorCorreo(f"No se puede conectar con el servidor de correo: {error}") from error
    try:
        yield servidor
    finally:
        with contextlib.suppress(OSError, smtplib.SMTPException):
            servidor.quit()
