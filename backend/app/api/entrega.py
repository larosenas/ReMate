"""CU-008 — API de la entrega: registrar retrasos y confirmar la entrega."""

from datetime import date

from flask import current_app
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel

from app.api.necesidades import (
    ERRORES_ESTADO,
    SalidaNecesidad,
    _a_dict,
    _no_existe,
    _sesion,
)
from app.api.tipos import Id
from app.servicios import entrega

bp = APIBlueprint(
    "entrega", __name__, url_prefix="/api", abp_tags=[Tag(name="Retrasos y entrega (CU-008)")]
)


class RutaNecesidad(BaseModel):
    id: Id


class EntradaRetraso(BaseModel):
    peticionario_id: Id | None = None
    fecha_nueva: date | None = None
    motivo: str | None = None


class EntradaEntrega(BaseModel):
    peticionario_id: Id | None = None
    # Si no se indica, hoy.
    fecha_entrega_real: date | None = None
    # Obligatorio si la fecha real es posterior a la prevista: se registra como retraso.
    motivo_retraso: str | None = None
    # Comentario opcional de la entrega (por ejemplo, «llegó el paquete destrozado»).
    # El máximo y los caracteres no válidos los comprueba el servicio, sin los espacios de los
    # extremos.
    comentario: str | None = None


@bp.post("/necesidades/<int:id>/retrasos", responses={200: SalidaNecesidad, **ERRORES_ESTADO})
def registrar_retraso(path: RutaNecesidad, body: EntradaRetraso):
    """Registra un retraso con su motivo; la nueva fecha pasa a ser la prevista."""
    with _sesion() as sesion:
        necesidad = entrega.registrar_retraso(
            sesion,
            path.id,
            peticionario_id=body.peticionario_id,
            fecha_nueva=body.fecha_nueva,
            motivo=body.motivo,
        )
        if necesidad is None:
            return _no_existe()
        current_app.logger.info("Retraso registrado: %s", necesidad.codigo)
        return _a_dict(necesidad)


@bp.post("/necesidades/<int:id>/entrega", responses={200: SalidaNecesidad, **ERRORES_ESTADO})
def confirmar_entrega(path: RutaNecesidad, body: EntradaEntrega):
    """Confirma la entrega y pasa a «Entregado», con un comentario opcional que sale
    en la comparativa de las ofertas futuras del proveedor y se pasa a la IA al adjudicar."""
    with _sesion() as sesion:
        necesidad = entrega.confirmar_entrega(
            sesion,
            path.id,
            peticionario_id=body.peticionario_id,
            fecha_entrega_real=body.fecha_entrega_real,
            motivo_retraso=body.motivo_retraso,
            comentario=body.comentario,
        )
        if necesidad is None:
            return _no_existe()
        current_app.logger.info("Entrega confirmada: %s", necesidad.codigo)
        return _a_dict(necesidad)
