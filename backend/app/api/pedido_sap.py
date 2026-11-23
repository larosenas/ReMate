"""CU-007 — API del pedido SAP: propuesta, borrador del correo, envío y descarga del .eml."""

from datetime import date

from flask import current_app
from flask_openapi3 import APIBlueprint, FileStorage, Tag
from pydantic import BaseModel, Field, field_validator

from app.api.errores import ERRORES_DESCARGA, RespuestaError, respuesta_error
from app.api.necesidades import (
    ERRORES_ESTADO,
    SalidaNecesidad,
    _a_dict,
    _demasiado_grande,
    _enviar_archivo,
    _iso,
    _leer_subidos,
    _no_existe,
    _raiz_archivos,
    _sesion,
)
from app.api.tipos import Id
from app.integraciones.archivos import ArchivoDemasiadoGrande
from app.modelos.necesidades import Necesidad
from app.servicios import pedido_sap

bp = APIBlueprint(
    "pedido_sap", __name__, url_prefix="/api", abp_tags=[Tag(name="Pedido SAP (CU-007)")]
)


class RutaNecesidad(BaseModel):
    id: Id


class SalidaPropuesta(BaseModel):
    proveedor: str
    para: str
    numero_oferta: str | None
    # «oferta» (la revisada), «archivo» (el nombre del adjunto de la oferta) o null.
    origen_numero_oferta: str | None
    fecha_entrega_prevista: date | None


class EntradaBorrador(BaseModel):
    numero_oferta: str | None = None
    numero_pedido: str | None = None


class SalidaBorrador(BaseModel):
    para: str
    asunto: str
    cuerpo: str


class FormularioPedido(BaseModel):
    peticionario_id: Id | None = None
    pedido: FileStorage | None = None
    numero_oferta: str | None = Field(default=None, max_length=200)
    numero_pedido: str | None = Field(default=None, max_length=200)
    cuerpo_correo: str | None = None

    @field_validator("numero_oferta", "numero_pedido", "cuerpo_correo", mode="before")
    @classmethod
    def _como_texto(cls, valor):
        # Del formulario, «4500012345» llega como número: los números de pedido son texto.
        return None if valor is None else str(valor)


@bp.get(
    "/necesidades/<int:id>/pedido-sap/propuesta",
    responses={200: SalidaPropuesta, 404: RespuestaError, 409: RespuestaError},
)
def propuesta_pedido(path: RutaNecesidad):
    """Proveedor adjudicatario y número de oferta propuesto para el correo del pedido."""
    with _sesion() as sesion:
        datos = pedido_sap.propuesta(sesion, path.id)
        if datos is None:
            return _no_existe()
        return {**datos, "fecha_entrega_prevista": _iso(datos["fecha_entrega_prevista"])}


@bp.post(
    "/necesidades/<int:id>/pedido-sap/borrador",
    responses={200: SalidaBorrador, **ERRORES_ESTADO},
)
def borrador_pedido(path: RutaNecesidad, body: EntradaBorrador):
    """Correo al proveedor con el pedido (plantilla fija, sin IA; no guarda nada)."""
    with _sesion() as sesion:
        datos = pedido_sap.borrador(
            sesion,
            path.id,
            body.numero_oferta,
            body.numero_pedido,
            current_app.config["REMATE"].empresa_nombre,
        )
        if datos is None:
            return _no_existe()
        return datos


class FormularioPdf(BaseModel):
    pedido: FileStorage | None = None


class SalidaNumero(BaseModel):
    # Null si el PDF no dice «PURCHASE ORDER NO. …»: entonces se escribe a mano.
    numero_pedido: str | None


@bp.post(
    "/necesidades/<int:id>/pedido-sap/numero",
    responses={200: SalidaNumero, **ERRORES_ESTADO},
)
def numero_del_pedido(path: RutaNecesidad, form: FormularioPdf):
    """Lee el número de pedido del PDF de SAP («PURCHASE ORDER NO. …») para proponerlo. Sin IA
    y sin guardar nada."""
    subidos, error = _leer_subidos([form.pedido] if form.pedido else [])
    if error:
        return error
    if not subidos:
        return respuesta_error(
            400, "datos_no_validos", "Sube el pedido oficial de SAP.", {"campo": "pedido"}
        )
    with _sesion() as sesion:
        datos = pedido_sap.numero_del_pdf(sesion, path.id, subidos[0])
        if datos is None:
            return _no_existe()
        return datos


@bp.post("/necesidades/<int:id>/pedido-sap", responses={200: SalidaNecesidad, **ERRORES_ESTADO})
def enviar_pedido(path: RutaNecesidad, form: FormularioPedido):
    """Guarda el pedido SAP, genera el .eml al proveedor y pasa a «Pendiente entrega»."""
    subidos, error = _leer_subidos([form.pedido] if form.pedido else [])
    if error:
        return error
    with _sesion() as sesion:
        try:
            necesidad = pedido_sap.enviar(
                sesion,
                _raiz_archivos(),
                path.id,
                peticionario_id=form.peticionario_id,
                pedido=subidos[0] if subidos else None,
                numero_oferta=form.numero_oferta,
                numero_pedido=form.numero_pedido,
                cuerpo_correo=form.cuerpo_correo,
            )
        except ArchivoDemasiadoGrande as e:
            return _demasiado_grande(e)
        if necesidad is None:
            return _no_existe()
        current_app.logger.info("Pedido SAP generado: %s", necesidad.codigo)
        return _a_dict(necesidad)


@bp.get("/necesidades/<int:id>/pedido-sap.eml", responses=ERRORES_DESCARGA)
def descargar_pedido(path: RutaNecesidad):
    """Descarga (o vuelve a descargar) el .eml al proveedor con el pedido SAP."""
    with _sesion() as sesion:
        necesidad = sesion.get(Necesidad, path.id)
        correo = necesidad.ultimo_adjunto("envio_pedido") if necesidad else None
        if correo is None:
            return respuesta_error(404, "no_encontrado", "No hay correo del pedido SAP.")
        return _enviar_archivo(correo)
