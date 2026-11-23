"""Formato común de errores de la API."""

from flask import jsonify
from pydantic import BaseModel, ValidationError
from werkzeug.exceptions import RequestEntityTooLarge


class RespuestaError(BaseModel):
    error: str
    mensaje: str
    detalles: dict = {}


def respuesta_error(estado: int, error: str, mensaje: str, detalles: dict | None = None):
    return jsonify(error=error, mensaje=mensaje, detalles=detalles or {}), estado


def error_de_validacion(e: ValidationError):
    """Sustituye la respuesta por defecto de flask-openapi3 (422) por el formato común (400)."""
    campos = [".".join(str(p) for p in err["loc"]) for err in e.errors()]
    respuesta, estado = respuesta_error(
        400,
        "datos_no_validos",
        "Faltan datos o no tienen el formato correcto.",
        {"campos": campos},
    )
    respuesta.status_code = estado
    return respuesta


def registrar_manejadores(app) -> None:
    """Los errores de datos y de estado de los servicios dan la misma respuesta en toda la API:
    las rutas no los capturan una a una."""
    from app.servicios.listas import DatosNoValidos
    from app.servicios.necesidades import TransicionNoPermitida

    @app.errorhandler(DatosNoValidos)
    def datos_no_validos(e: DatosNoValidos):
        return respuesta_error(400, "datos_no_validos", str(e), {"campo": e.campo})

    @app.errorhandler(TransicionNoPermitida)
    def transicion_no_permitida(e: TransicionNoPermitida):
        return respuesta_error(409, "transicion_no_permitida", str(e))

    @app.errorhandler(RequestEntityTooLarge)
    def subida_demasiado_grande(e: RequestEntityTooLarge):
        return respuesta_error(
            413,
            "subida_demasiado_grande",
            "Entre todos los archivos superan los 100 MB. Súbelos en varias veces.",
        )


# Descargas de archivos: 404 si no existe; 410 si se borró por antigüedad (ADR 0014).
ERRORES_DESCARGA = {404: RespuestaError, 410: RespuestaError}
