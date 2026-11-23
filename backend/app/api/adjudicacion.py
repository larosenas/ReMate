"""CU-005 — API de la adjudicación: borrador, confirmación, información para SAP y .eml."""

from datetime import date

from flask import current_app
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel

from app.api.errores import ERRORES_DESCARGA, RespuestaError, respuesta_error
from app.api.necesidades import (
    ERRORES_ESTADO,
    SalidaNecesidad,
    _a_dict,
    _enviar_archivo,
    _iso,
    _no_existe,
    _raiz_archivos,
    _sesion,
)
from app.api.tipos import Id
from app.modelos.necesidades import Necesidad
from app.servicios import adjudicacion

bp = APIBlueprint(
    "adjudicacion", __name__, url_prefix="/api", abp_tags=[Tag(name="Adjudicación y SAP (CU-005)")]
)


class RutaNecesidad(BaseModel):
    id: Id


class EntradaBorrador(BaseModel):
    oferta_id: Id


class EntradaAdjudicacion(BaseModel):
    peticionario_id: Id
    oferta_id: Id
    descripcion_inversion: str
    cuerpo_correo: str


class FilaSap(BaseModel):
    short_text: str
    quantity_requested: str
    valuation_price: str
    delivery_date: str
    requisitioner: str


class CorreoAdjudicacion(BaseModel):
    para: str
    asunto: str
    cuerpo: str


class SalidaBorrador(BaseModel):
    moneda: str | None
    texto_sap_fijo: str
    descripcion_inversion: str
    tabla_sap: list[FilaSap]
    correo: CorreoAdjudicacion
    bloqueos: list[str]
    avisos: list[str]


class SalidaSap(BaseModel):
    moneda: str | None
    proveedor: str
    texto_sap: str
    tabla_sap: list[FilaSap]
    fecha_entrega_inicial: date | None


@bp.post(
    "/necesidades/<int:id>/adjudicacion/borrador",
    responses={200: SalidaBorrador, **ERRORES_ESTADO},
)
def borrador_adjudicacion(path: RutaNecesidad, body: EntradaBorrador):
    """Prepara el texto y la tabla para SAP y el correo al adjudicatario (no guarda nada)."""
    with _sesion() as sesion:
        datos = adjudicacion.borrador(sesion, current_app.config["REMATE"], path.id, body.oferta_id)
        if datos is None:
            return _no_existe()
        return datos


@bp.post(
    "/necesidades/<int:id>/adjudicacion",
    responses={200: SalidaNecesidad, **ERRORES_ESTADO},
)
def adjudicar(path: RutaNecesidad, body: EntradaAdjudicacion):
    """Confirma la adjudicación: genera el .eml y pasa a «Pendiente solicitud SAP»."""
    with _sesion() as sesion:
        necesidad = adjudicacion.adjudicar(
            sesion,
            _raiz_archivos(),
            path.id,
            peticionario_id=body.peticionario_id,
            oferta_id=body.oferta_id,
            descripcion_inversion=body.descripcion_inversion,
            cuerpo_correo=body.cuerpo_correo,
        )
        if necesidad is None:
            return _no_existe()
        current_app.logger.info("Necesidad %s adjudicada", necesidad.codigo)
        return _a_dict(necesidad)


@bp.get("/necesidades/<int:id>/sap", responses={200: SalidaSap, 404: RespuestaError})
def informacion_sap(path: RutaNecesidad):
    """Texto y tabla para copiar en SAP, con sus formatos exactos."""
    with _sesion() as sesion:
        necesidad = sesion.get(Necesidad, path.id)
        if necesidad is None:
            return _no_existe()
        datos = adjudicacion.informacion_sap(necesidad)
        if datos is None:
            return respuesta_error(404, "no_encontrado", "La necesidad aún no está adjudicada.")
        return {**datos, "fecha_entrega_inicial": _iso(datos["fecha_entrega_inicial"])}


@bp.get("/necesidades/<int:id>/adjudicacion.eml", responses=ERRORES_DESCARGA)
def descargar_adjudicacion(path: RutaNecesidad):
    """Descarga (o vuelve a descargar) el .eml al proveedor adjudicatario."""
    with _sesion() as sesion:
        necesidad = sesion.get(Necesidad, path.id)
        correo = necesidad.ultimo_adjunto("adjudicacion") if necesidad else None
        if correo is None:
            return respuesta_error(404, "no_encontrado", "No hay correo de adjudicación.")
        return _enviar_archivo(correo)
