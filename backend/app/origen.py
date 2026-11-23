"""Protección frente a otras webs abiertas en el navegador del ingeniero y frente a DNS
rebinding: solo se atiende a la dirección de ReMate.

Sin login, una web externa podría enviar un formulario a ReMate desde el navegador de
alguien de la red interna, saltándose el cortafuegos, o mostrar ReMate dentro de un marco para
engañar con los clics. Los cambios solo se aceptan desde la propia dirección de ReMate; los
clientes sin navegador (curl, pruebas) no envían Origin y siguen funcionando.
"""

from urllib.parse import urlsplit

from flask import Flask, current_app, request

from app.api.errores import respuesta_error

_SIN_CAMBIOS = ("GET", "HEAD", "OPTIONS")


def _desde_otra_web() -> bool:
    origen = request.headers.get("Origin")
    if origen is not None:
        # «null»: documentos locales o marcos aislados; tampoco son ReMate.
        return urlsplit(origen).netloc.lower() != request.host.lower()
    return request.headers.get("Sec-Fetch-Site") == "cross-site"


LOCALES = ("localhost", "127.0.0.1", "::1")


def _nombre(host: str) -> str:
    """El nombre o la IP de una cabecera Host o de una URL, sin el puerto."""
    return (urlsplit(f"//{host}").hostname or "").lower()


def hosts_permitidos() -> set[str] | None:
    """Nombres con los que se puede llegar a ReMate: el de APP_URL, localhost y HOSTS_PERMITIDOS.
    None si no hay APP_URL ni HOSTS_PERMITIDOS (desarrollo): no se comprueba."""
    config = current_app.config["REMATE"]
    propios = set(config.hosts_permitidos)
    if config.app_url:
        propios.add(_nombre(urlsplit(config.app_url).netloc))
    return propios | set(LOCALES) if propios else None


def registrar(app: Flask) -> None:
    @app.before_request
    def solo_su_propia_direccion():
        """DNS rebinding: una web externa cuyo
        nombre pasa a apuntar a la IP de ReMate hace que `Origin` y `Host` coincidan y se salta
        la comprobación de abajo; además podría leer datos. Se rechaza cualquier petición cuyo
        Host no sea la dirección de ReMate."""
        permitidos = hosts_permitidos()
        if permitidos is not None and _nombre(request.host) not in permitidos:
            return respuesta_error(
                400,
                "host_no_permitido",
                "Entra a ReMate con su dirección (la de APP_URL o una de HOSTS_PERMITIDOS).",
            )
        return None

    @app.before_request
    def solo_desde_remate():
        if request.method not in _SIN_CAMBIOS and _desde_otra_web():
            return respuesta_error(
                403, "origen_no_permitido", "Solo se admiten cambios desde la propia ReMate."
            )
        return None

    @app.after_request
    def cabeceras(respuesta):
        respuesta.headers["X-Frame-Options"] = "DENY"
        respuesta.headers["Content-Security-Policy"] = "frame-ancestors 'none'"
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        return respuesta
