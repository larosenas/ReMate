"""Comprobación de que la API y la base de datos responden."""

from flask import current_app
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

bp = APIBlueprint("salud", __name__, url_prefix="/api", abp_tags=[Tag(name="Salud")])


class RespuestaSalud(BaseModel):
    estado: str
    base_de_datos: str


@bp.get("/salud", responses={200: RespuestaSalud, 503: RespuestaSalud})
def salud():
    """Estado de la API y de la conexión con PostgreSQL."""
    try:
        with current_app.extensions["remate.sesiones"]() as sesion:
            sesion.execute(text("SELECT 1"))
    except SQLAlchemyError:
        current_app.logger.exception("La base de datos no responde")
        return RespuestaSalud(estado="error", base_de_datos="sin conexión").model_dump(), 503
    return RespuestaSalud(estado="ok", base_de_datos="ok").model_dump()
