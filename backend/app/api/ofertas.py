"""CU-004 — API de ofertas: subir, consultar, corregir, borrar, analizar y comparar, comparativa."""

import io
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from flask import current_app, send_file
from flask_openapi3 import APIBlueprint, FileStorage, Tag
from pydantic import BaseModel, Field

from app.api.errores import RespuestaError, respuesta_error
from app.api.listas import ComentarioEntrega
from app.api.necesidades import (
    ERRORES_ESTADO,
    SalidaNecesidad,
    _a_dict,
    _demasiado_grande,
    _iso,
    _leer_subidos,
    _no_existe,
    _proveedor,
    _raiz_archivos,
    _sesion,
)
from app.api.tipos import Id
from app.integraciones.archivos import ArchivoDemasiadoGrande
from app.integraciones.correos_entrada import CorreoNoValido
from app.modelos.necesidades import Necesidad
from app.servicios import comparativa as servicio_comparativa
from app.servicios import condiciones, historico, ofertas, peticion_datos
from app.servicios.ofertas import AdjuntoOferta, LineaEntrada, OfertaExistente

bp = APIBlueprint("ofertas", __name__, url_prefix="/api", abp_tags=[Tag(name="Ofertas (CU-004)")])


class RutaNecesidad(BaseModel):
    id: Id


class RutaOferta(BaseModel):
    id: Id
    oferta_id: Id


class FormularioOferta(BaseModel):
    # Si no se indica, se busca el proveedor por el remitente del correo.
    proveedor_id: Id | None = None
    correo: FileStorage | None = None
    adjuntos: list[FileStorage] = []
    # Uno por adjunto y en el mismo orden: pdf, excel, word, imagen u otro.
    tipos_adjunto: list[str] = []
    # Adjuntos del propio correo que se guardan: su `indice` (de `…/ofertas/correo`) y su tipo,
    # en el mismo orden.
    adjuntos_correo: list[int] = []
    tipos_adjunto_correo: list[str] = []
    # Si el proveedor ya tiene una oferta, la nueva solo la sustituye con esta confirmación.
    confirmar_sustitucion: bool = False
    # «Añadir datos del proveedor»: en lugar de sustituir su oferta, la completa.
    anadir_datos: bool = False


class FormularioCorreo(BaseModel):
    correo: FileStorage | None = None


class EntradaLinea(BaseModel):
    descripcion: str
    cantidad: Decimal = Field(max_digits=14, decimal_places=3)
    precio_unitario: Decimal = Field(max_digits=14, decimal_places=4)
    fecha_entrega: date | None = None
    # Plazo de la línea tal como lo da el proveedor («5 Sem.»; CU-004).
    plazo_entrega_texto: str | None = Field(default=None, max_length=200)


# Los estados de `app/servicios/condiciones.py` (lo comprueba test_condiciones.py).
EstadoCondicion = Literal["especificado", "incluido", "no_incluido", "no_aplica", "no_especificado"]


class EntradaCondicion(BaseModel):
    estado: EstadoCondicion
    texto: str | None = Field(default=None, max_length=500)


class CambioOferta(BaseModel):
    moneda: str | None = Field(default=None, max_length=3)
    numero_oferta: str | None = Field(default=None, max_length=100)
    importe_sin_iva: Decimal | None = Field(default=None, max_digits=14, decimal_places=2)
    plazo_entrega_texto: str | None = Field(default=None, max_length=200)
    fecha_entrega_estimada: date | None = None
    condiciones_pago: str | None = None
    otros: str | None = None
    # Solo las condiciones que cambian, por su clave (embalaje, incoterm…).
    condiciones: dict[str, EntradaCondicion] | None = None
    lineas: list[EntradaLinea] | None = None
    revisada: bool | None = None


class EntradaEvaluacion(BaseModel):
    # Quién pasa a evaluación: obligatorio en «En cotización».
    peticionario_id: Id | None = None


class SalidaEvaluacion(BaseModel):
    necesidad: SalidaNecesidad
    # Avisos de la lectura de cada oferta, con el nombre de su proveedor delante.
    avisos: list[str]


class SalidaLinea(BaseModel):
    descripcion: str
    cantidad: str
    precio_unitario: str
    fecha_entrega: date | None
    plazo_entrega_texto: str | None
    # La fecha sale del plazo contado desde el correo: al adjudicar se cuenta desde el pedido.
    fecha_calculada: bool


class SalidaArchivo(BaseModel):
    id: int
    tipo: str
    formato: str | None
    nombre_archivo: str
    tamano: int


class ProveedorOferta(BaseModel):
    id: int
    nombre: str
    email: str


class AdjuntoDelCorreo(BaseModel):
    indice: int
    nombre: str
    tamano: int


class SalidaCorreo(BaseModel):
    remitente: str | None
    # Proveedor reconocido por el remitente o su dominio; si no, el motivo en `aviso_proveedor`.
    proveedor: ProveedorOferta | None
    aviso_proveedor: str | None
    adjuntos: list[AdjuntoDelCorreo]


class SalidaCondicion(BaseModel):
    clave: str
    nombre: str
    estado: str
    texto: str | None


class SalidaOferta(BaseModel):
    id: int
    proveedor: ProveedorOferta
    fecha_correo: datetime | None
    remitente: str | None
    asunto: str | None
    registrada_en: datetime
    numero_oferta: str | None
    moneda: str | None
    importe_sin_iva: str | None
    plazo_entrega_texto: str | None
    fecha_entrega_estimada: date | None
    # La fecha no la dio el proveedor: es su plazo contado desde su correo (solo para comparar).
    fecha_calculada: bool
    # La oferta solo dio un mes: la fecha es su último viernes.
    fecha_de_mes: bool
    condiciones_pago: str | None
    # Información adicional que no encaja en las condiciones.
    otros: str | None
    # Las nueve condiciones, en el orden de la tabla.
    condiciones: list[SalidaCondicion]
    # Lo que se le puede pedir al proveedor; vacío si la IA aún no la ha leído.
    datos_que_faltan: list[str]
    revisada: bool
    # Ni la ha leído la IA ni tiene datos a mano: la leerá «Analizar y comparar».
    sin_analizar: bool
    estado_oferta: str
    lineas: list[SalidaLinea]
    archivos: list[SalidaArchivo]
    avisos: list[str]


class HistorialProveedor(BaseModel):
    pedidos: int
    con_retraso: int
    dias_retraso: int
    retraso_medio: float | None
    # Del más reciente al más antiguo.
    comentarios: list[ComentarioEntrega]


class DestacadosOferta(BaseModel):
    importe: Literal["mejor", "peor"] | None
    entrega: Literal["mejor", "peor"] | None
    retrasos: Literal["mejor", "peor"] | None


class SalidaOfertaComparativa(SalidaOferta):
    """Cada elemento de la comparativa (la respuesta es una lista)."""

    historial_proveedor: HistorialProveedor
    destacados: DestacadosOferta


def _decimal(valor: Decimal | None, minimo: int = 0) -> str | None:
    """Texto decimal exacto sin ceros sobrantes y con al menos `minimo` decimales.

    Ejemplos: «2.5», «12.50».
    """
    if valor is None:
        return None
    texto = f"{valor:f}"
    if "." in texto:
        entero, decimales = texto.split(".")
        decimales = decimales.rstrip("0").ljust(minimo, "0")
        return f"{entero}.{decimales}" if decimales else entero
    return f"{texto}.{'0' * minimo}" if minimo else texto


def _oferta(o, avisos_extra=()) -> dict:
    return {
        "id": o.id,
        "proveedor": _proveedor(o.proveedor),
        "fecha_correo": _iso(o.fecha_correo),
        "remitente": o.remitente,
        "asunto": o.asunto,
        "registrada_en": _iso(o.registrada_en),
        "numero_oferta": o.numero_oferta,
        "moneda": o.moneda,
        "importe_sin_iva": _decimal(o.importe_sin_iva, 2),
        "plazo_entrega_texto": o.plazo_entrega_texto,
        "fecha_entrega_estimada": _iso(o.fecha_entrega_estimada),
        "fecha_calculada": ofertas.fecha_calculada(o),
        "fecha_de_mes": ofertas.fecha_de_mes(o),
        "condiciones_pago": o.condiciones_pago,
        "otros": o.otros,
        "condiciones": condiciones.en_orden(o.condiciones),
        "datos_que_faltan": peticion_datos.que_falta(o),
        "revisada": o.revisada,
        "sin_analizar": ofertas.pendiente_de_ia(o),
        "estado_oferta": o.estado_oferta,
        "lineas": [
            {
                "descripcion": linea.descripcion,
                "cantidad": _decimal(linea.cantidad),
                "precio_unitario": _decimal(linea.precio_unitario, 2),
                "fecha_entrega": _iso(linea.fecha_entrega),
                "plazo_entrega_texto": linea.plazo_entrega_texto,
                "fecha_calculada": ofertas.linea_calculada(linea, o),
            }
            for linea in o.lineas
        ],
        "archivos": [
            {
                "id": a.id,
                "tipo": a.tipo,
                "formato": a.formato,
                "nombre_archivo": a.nombre_archivo,
                "tamano": a.tamano,
                "caducado": a.caducado_en is not None,
            }
            for a in o.archivos
        ],
        "avisos": [*avisos_extra, *ofertas.avisos(o)],
    }


def _oferta_no_existe():
    return respuesta_error(404, "no_encontrado", "La oferta no existe.")


ERRORES_SUBIDA = {**ERRORES_ESTADO, 422: RespuestaError}


@bp.get("/necesidades/<int:id>/ofertas", responses={200: SalidaOferta, 404: RespuestaError})
def listar_ofertas(path: RutaNecesidad):
    """Ofertas vigentes de la necesidad, de la última subida a la primera."""
    with _sesion() as sesion:
        if not sesion.get(Necesidad, path.id):
            return _no_existe()
        return [_oferta(o) for o in reversed(ofertas.vigentes(sesion, path.id))]


@bp.post("/necesidades/<int:id>/ofertas/correo", responses={200: SalidaCorreo, **ERRORES_SUBIDA})
def leer_correo_oferta(path: RutaNecesidad, form: FormularioCorreo):
    """Paso previo a subir una oferta: lee el correo (.eml o .msg) sin guardar nada y devuelve sus
    adjuntos (sin las imágenes del cuerpo) y el proveedor que reconoce por el remitente o por
    su dominio. Al subir la oferta se indican los adjuntos que se guardan (`adjuntos_correo`)."""
    correos, error = _leer_subidos([form.correo] if form.correo else [])
    if error:
        return error
    if not correos:
        return respuesta_error(
            400,
            "datos_no_validos",
            "Sube el correo de la oferta (.eml o .msg).",
            {"campo": "correo"},
        )
    with _sesion() as sesion:
        try:
            leido = ofertas.leer_correo(sesion, path.id, correos[0])
        except CorreoNoValido as e:
            return respuesta_error(422, "archivo_no_aceptado", str(e), {"campo": "correo"})
        if leido is None:
            return _no_existe()
        proveedor = leido["proveedor"]
        return {
            **leido,
            "proveedor": _proveedor(proveedor) if proveedor else None,
        }


@bp.post(
    "/necesidades/<int:id>/ofertas",
    responses={200: SalidaOferta, 201: SalidaOferta, **ERRORES_SUBIDA},
)
def subir_oferta(path: RutaNecesidad, form: FormularioOferta):
    """Sube el correo de una oferta (.eml o .msg) y sus adjuntos con su formato. Solo se
    guarda: la IA la lee después, con las demás, en «Analizar y comparar» (`…/evaluacion`); `201`.
    Con `anadir_datos`, el correo es la respuesta del proveedor a la petición de datos:
    se guarda en su oferta, que se completa y se actualiza con lo que diga (la IA lee la
    respuesta al momento); `200` con la oferta y los avisos, o `400` si el proveedor no tiene
    oferta."""
    correos, error = _leer_subidos([form.correo] if form.correo else [])
    if error:
        return error
    adjuntos, error = _leer_subidos(form.adjuntos)
    if error:
        return error
    if len(form.tipos_adjunto) != len(adjuntos) or len(form.tipos_adjunto_correo) != len(
        form.adjuntos_correo
    ):
        return respuesta_error(
            400,
            "datos_no_validos",
            "Indica el tipo de cada adjunto.",
            {"campo": "tipos_adjunto"},
        )
    with _sesion() as sesion:
        try:
            comunes = {
                "proveedor_id": form.proveedor_id,
                "correo": correos[0] if correos else None,
                "adjuntos": [
                    AdjuntoOferta(archivo, tipo.strip().lower())
                    for archivo, tipo in zip(adjuntos, form.tipos_adjunto, strict=True)
                ],
                "adjuntos_correo": [
                    (indice, tipo.strip().lower())
                    for indice, tipo in zip(
                        form.adjuntos_correo, form.tipos_adjunto_correo, strict=True
                    )
                ],
            }
            if form.anadir_datos:
                resultado = ofertas.anadir_datos_del_proveedor(
                    sesion, current_app.config["REMATE"], _raiz_archivos(), path.id, **comunes
                )
            else:
                resultado = ofertas.subir(
                    sesion,
                    _raiz_archivos(),
                    path.id,
                    **comunes,
                    confirmar_sustitucion=form.confirmar_sustitucion,
                )
        except OfertaExistente as e:
            return respuesta_error(
                409,
                "oferta_existente",
                str(e),
                {"proveedor": {"id": e.proveedor.id, "nombre": e.proveedor.nombre}},
            )
        except CorreoNoValido as e:
            return respuesta_error(422, "archivo_no_aceptado", str(e), {"campo": "correo"})
        except ArchivoDemasiadoGrande as e:
            return _demasiado_grande(e)
        if resultado is None:
            return _no_existe()
        oferta, avisos_subida = resultado
        if form.anadir_datos:
            current_app.logger.info(
                "Datos del proveedor añadidos a la oferta %s (necesidad %s)",
                oferta.id,
                oferta.necesidad.codigo,
            )
            return _oferta(oferta, avisos_subida), 200
        current_app.logger.info(
            "Oferta %s subida en la necesidad %s", oferta.id, oferta.necesidad.codigo
        )
        return _oferta(oferta, avisos_subida), 201


@bp.post(
    "/necesidades/<int:id>/ofertas/<int:oferta_id>/analisis",
    responses={200: SalidaOferta, **ERRORES_ESTADO},
)
def reanalizar_oferta(path: RutaOferta):
    """«Reanalizar con IA»: la IA vuelve a leer el correo y los adjuntos, y sus datos sustituyen
    a los de la oferta, que queda sin revisar. Si la IA falla, los datos no cambian y se avisa."""
    with _sesion() as sesion:
        leida = ofertas.analizar(
            sesion, current_app.config["REMATE"], _raiz_archivos(), path.id, path.oferta_id
        )
        if leida is None:
            return _oferta_no_existe()
        oferta, avisos_ia = leida
        current_app.logger.info(
            "Oferta %s de la necesidad %s reanalizada con la IA", oferta.id, oferta.necesidad.codigo
        )
        return _oferta(oferta, avisos_ia)


class SalidaPeticionDatos(BaseModel):
    para: str
    asunto: str
    cuerpo: str
    faltan: list[str]
    avisos: list[str]
    con_ia: bool


class EntradaPeticionDatos(BaseModel):
    cuerpo: str


@bp.post(
    "/necesidades/<int:id>/ofertas/<int:oferta_id>/peticion-datos/borrador",
    responses={200: SalidaPeticionDatos, **ERRORES_ESTADO},
)
def borrador_peticion_datos(path: RutaOferta):
    """Correo propuesto para pedir al proveedor los datos que faltan en su oferta. Lo
    redacta la IA (si falla, la lista tal cual y un aviso). No guarda nada. `400` si no falta
    nada que pedir."""
    with _sesion() as sesion:
        datos = peticion_datos.borrador(
            sesion, current_app.config["REMATE"], path.id, path.oferta_id
        )
        if datos is None:
            return _oferta_no_existe()
        return datos


@bp.post(
    "/necesidades/<int:id>/ofertas/<int:oferta_id>/peticion-datos",
    responses={200: None, **ERRORES_ESTADO},
)
def generar_peticion_datos(path: RutaOferta, body: EntradaPeticionDatos):
    """Descarga el `.eml` con el cuerpo revisado (con `X-Unsent`, al proveedor y al
    remitente de la oferta si es de su empresa, con el asunto común). No se guarda."""
    with _sesion() as sesion:
        generado = peticion_datos.generar(sesion, path.id, path.oferta_id, body.cuerpo)
        if generado is None:
            return _oferta_no_existe()
        nombre, contenido = generado
        return send_file(
            io.BytesIO(contenido),
            mimetype="message/rfc822",
            as_attachment=True,
            download_name=nombre,
        )


@bp.patch(
    "/necesidades/<int:id>/ofertas/<int:oferta_id>",
    responses={200: SalidaOferta, **ERRORES_ESTADO},
)
def corregir_oferta(path: RutaOferta, body: CambioOferta):
    """Corrige los datos de la oferta y, si se indica, la marca como revisada."""
    cambios = {
        campo: getattr(body, campo)
        for campo in body.model_fields_set
        if campo in ofertas.CAMPOS_EDITABLES
    }
    if body.condiciones is not None:
        cambios["condiciones"] = {c: v.model_dump() for c, v in body.condiciones.items()}
    lineas = None
    if body.lineas is not None:
        lineas = [LineaEntrada(**linea.model_dump()) for linea in body.lineas]
    with _sesion() as sesion:
        oferta = ofertas.actualizar(sesion, path.id, path.oferta_id, cambios, lineas, body.revisada)
        if oferta is None:
            return _oferta_no_existe()
        return _oferta(oferta)


@bp.delete(
    "/necesidades/<int:id>/ofertas/<int:oferta_id>",
    responses={204: None, 404: RespuestaError, 409: RespuestaError},
)
def borrar_oferta(path: RutaOferta):
    """Borra una oferta: deja de contar, pero queda guardada como `borrada`."""
    with _sesion() as sesion:
        borrada = ofertas.borrar(sesion, path.id, path.oferta_id)
        if not borrada:
            return _oferta_no_existe()
        return "", 204


@bp.post(
    "/necesidades/<int:id>/evaluacion",
    responses={200: SalidaEvaluacion, **ERRORES_ESTADO},
)
def analizar_y_comparar(path: RutaNecesidad, body: EntradaEvaluacion):
    """«Analizar y comparar»: en «En cotización» pasa a «En evaluación» (necesita quién y al menos
    una oferta vigente); después, la IA lee a la vez las ofertas sin analizar. En «En evaluación»,
    lo mismo con las ofertas nuevas. Puede tardar unos minutos. La comparativa se pide aparte."""
    with _sesion() as sesion:
        resultado = servicio_comparativa.analizar_y_comparar(
            sesion, current_app.config["REMATE"], _raiz_archivos(), path.id, body.peticionario_id
        )
        if resultado is None:
            return _no_existe()
        current_app.logger.info(
            "Ofertas analizadas y comparadas en la necesidad %s", resultado["necesidad"].codigo
        )
        return {**resultado, "necesidad": _a_dict(resultado["necesidad"])}


@bp.get(
    "/necesidades/<int:id>/comparativa",
    responses={200: SalidaOfertaComparativa, 404: RespuestaError},
)
def comparativa(path: RutaNecesidad):
    """Ofertas vigentes con datos (revisadas o no), de la más barata a la más cara (sin IVA).
    Cada oferta lleva el histórico de retrasos de su proveedor (CU-010) y su mejor y peor valor
    (`destacados`: importe, entrega y retrasos, cada uno «mejor», «peor» o null; todos null si
    falta alguna oferta por revisar)."""
    with _sesion() as sesion:
        if not sesion.get(Necesidad, path.id):
            return _no_existe()
        comparadas = ofertas.comparativa(sesion, path.id)
        resumenes = historico.resumenes(sesion, list({o.proveedor_id for o in comparadas}))
        marcas = servicio_comparativa.destacados(
            comparadas, ofertas.vigentes(sesion, path.id), resumenes
        )
        return [
            {
                **_oferta(o),
                "historial_proveedor": historico.para_la_api(resumenes[o.proveedor_id]),
                "destacados": marcas[o.id],
            }
            for o in comparadas
        ]
