"""CU-001 y CU-002 — API de necesidades: crear, consultar, adjuntos y solicitud de ofertas."""

from datetime import date, datetime

from flask import current_app, request, send_file
from flask_openapi3 import APIBlueprint, FileStorage, Tag
from pydantic import BaseModel, field_validator

from app import fechas
from app.api.errores import ERRORES_DESCARGA, RespuestaError, respuesta_error
from app.api.tipos import Id
from app.integraciones import archivos
from app.integraciones.archivos import ArchivoDemasiadoGrande
from app.modelos.necesidades import ESTADOS
from app.servicios import adjudicacion, avisos_pedido_sap, historico, necesidades, solicitudes
from app.servicios.listas import clave_orden
from app.servicios.necesidades import (
    ArchivoSubido,
    DemasiadasNecesidades,
)

bp = APIBlueprint("necesidades", __name__, url_prefix="/api", abp_tags=[Tag(name="Necesidades")])


class FormularioNecesidad(BaseModel):
    titulo: str
    proyecto: str
    peticionario_id: Id
    descripcion: str
    adjuntos: list[FileStorage] = []

    # flask-openapi3 intenta leer cada campo del formulario como JSON («2026» → número);
    # aquí se acepta cualquier valor y la vista usa el texto tal cual llega.
    @field_validator("titulo", "proyecto", "descripcion", mode="before")
    @classmethod
    def _como_texto(cls, valor):
        return valor if valor is None else str(valor)


class EntradaDatos(BaseModel):
    titulo: str
    proyecto: str
    peticionario_id: Id
    descripcion: str


class EntradaCancelacion(BaseModel):
    peticionario_id: Id
    motivo: str


class EntradaPedidoEnSap(BaseModel):
    peticionario_id: Id
    fecha_entrega_prevista: date | None = None


class FormularioAdjuntos(BaseModel):
    adjuntos: list[FileStorage] = []


class RutaNecesidad(BaseModel):
    id: Id


class RutaAdjunto(BaseModel):
    id: Id
    adjunto_id: Id


class EntradaBorrador(BaseModel):
    adjunto_ids: list[Id] = []


class EntradaSolicitud(BaseModel):
    peticionario_id: Id
    proveedor_ids: list[Id]
    adjunto_ids: list[Id] = []
    cuerpo: str
    # Obligatorio con menos de 3 proveedores; va al texto para SAP.
    motivo_pocos_proveedores: str | None = None


class PeticionarioResumen(BaseModel):
    id: int
    nombre_completo: str


class ProveedorResumen(BaseModel):
    id: int
    nombre: str
    email: str


class SalidaAdjunto(BaseModel):
    id: int
    nombre_archivo: str
    tipo_mime: str
    tamano: int
    # ADR 0014: el archivo se borró por antigüedad; la descarga responde 410.
    caducado: bool = False


class SalidaCambioEstado(BaseModel):
    estado_anterior: str | None
    estado_nuevo: str
    peticionario: PeticionarioResumen
    cambiado_en: datetime


class SalidaCambioPeticionario(BaseModel):
    peticionario_anterior: PeticionarioResumen
    peticionario_nuevo: PeticionarioResumen
    cambiado_en: datetime


class ResumenNecesidad(BaseModel):
    id: int
    codigo: str
    titulo: str
    proyecto: str
    estado: str
    estado_texto: str
    peticionario: PeticionarioResumen
    creada_en: datetime
    fecha_entrega_prevista: date | None
    # CU-010: proveedor de la oferta adjudicada (para filtrar el panel por proveedor).
    proveedor_adjudicado: ProveedorResumen | None
    # Cuándo pasó al estado actual (último cambio de estado).
    estado_desde: datetime | None


class SalidaRetraso(BaseModel):
    fecha_anterior: date
    fecha_nueva: date
    motivo: str
    peticionario: PeticionarioResumen
    registrado_en: datetime
    # Llegó el día previsto o antes: el retraso avisado no se cumplió (CU-010).
    sin_efecto: bool


class SalidaNecesidad(ResumenNecesidad):
    descripcion: str
    motivo_cancelacion: str | None
    # Por qué se pidieron ofertas a menos de 3 proveedores.
    motivo_pocos_proveedores: str | None
    adjuntos: list[SalidaAdjunto]
    historial: list[SalidaCambioEstado]
    # CU-003: pasó a otro peticionario al dar de baja al anterior.
    cambios_peticionario: list[SalidaCambioPeticionario]
    proveedores_solicitados: list[ProveedorResumen]
    solicitud_eml: SalidaAdjunto | None
    oferta_adjudicada_id: int | None
    fecha_entrega_inicial: date | None
    fecha_entrega_prevista: date | None
    # La oferta adjudicada dio un plazo («3 semanas») y no una fecha; la fecha que se propone al
    # meter el pedido en SAP se cuenta desde hoy (CU-006).
    plazo_entrega_relativo: str | None
    fecha_entrega_propuesta: date | None
    adjudicacion_eml: SalidaAdjunto | None
    # CU-007: número de pedido (opcional), el pedido oficial y el .eml al proveedor.
    numero_pedido_sap: str | None
    pedido_sap: SalidaAdjunto | None
    pedido_sap_eml: SalidaAdjunto | None
    # CU-008: retrasos (del más antiguo al más reciente) y fecha en que llegó el pedido.
    retrasos: list[SalidaRetraso]
    fecha_entrega_real: date | None
    # Comentario opcional de la entrega (por ejemplo, «llegó el paquete destrozado»).
    comentario_entrega: str | None
    # CU-009: cuándo se envió el recordatorio de la fecha prevista actual.
    recordatorio_enviado_en: datetime | None
    # Último aviso a los avisados del pedido SAP (vacío = sin enviar todavía).
    aviso_pedido_sap_en: datetime | None
    # Solo al confirmar el paso 5, si no se ha podido enviar el aviso.
    avisos: list[str] = []


class SalidaBorrador(BaseModel):
    asunto: str
    cuerpo: str
    avisos: list[str]
    con_ia: bool


def _sesion():
    return current_app.extensions["remate.sesiones"]()


def _raiz_archivos():
    return current_app.config["REMATE"].archivos_dir


def _iso(valor):
    """Fecha o fecha y hora en formato ISO; None si no hay."""
    return valor.isoformat() if valor else None


def _peticionario(p) -> dict:
    return {"id": p.id, "nombre_completo": p.nombre_completo}


def _proveedor(p) -> dict:
    return {"id": p.id, "nombre": p.nombre, "email": p.email}


def _adjunto(a) -> dict:
    return {
        "id": a.id,
        "nombre_archivo": a.nombre_archivo,
        "tipo_mime": a.tipo_mime,
        "tamano": a.tamano,
        "caducado": a.caducado_en is not None,
    }


def _resumen(n, estado_desde: datetime | None) -> dict:
    return {
        "id": n.id,
        "codigo": n.codigo,
        "titulo": n.titulo,
        "proyecto": n.proyecto,
        "estado": n.estado,
        "estado_texto": ESTADOS[n.estado],
        "peticionario": _peticionario(n.peticionario),
        "creada_en": n.creada_en.isoformat(),
        "fecha_entrega_prevista": _iso(n.fecha_entrega_prevista),
        "estado_desde": _iso(estado_desde),
        "proveedor_adjudicado": (
            _proveedor(n.oferta_adjudicada.proveedor) if n.oferta_adjudicada else None
        ),
    }


def _a_dict(n) -> dict:
    eml = n.ultimo_adjunto("solicitud")
    correo_adjudicacion = n.ultimo_adjunto("adjudicacion")
    pedido = n.ultimo_adjunto("pedido_sap")
    correo_pedido = n.ultimo_adjunto("envio_pedido")
    return {
        **_resumen(n, n.historial[-1].cambiado_en if n.historial else None),
        "descripcion": n.descripcion,
        "motivo_cancelacion": n.motivo_cancelacion,
        "motivo_pocos_proveedores": n.motivo_pocos_proveedores,
        # Solo los adjuntos de la necesidad; el .eml generado va aparte.
        "adjuntos": [_adjunto(a) for a in n.adjuntos if a.tipo == "necesidad"],
        "historial": [
            {
                "estado_anterior": c.estado_anterior,
                "estado_nuevo": c.estado_nuevo,
                "peticionario": _peticionario(c.peticionario),
                "cambiado_en": c.cambiado_en.isoformat(),
            }
            for c in n.historial
        ],
        "cambios_peticionario": [
            {
                "peticionario_anterior": _peticionario(c.peticionario_anterior),
                "peticionario_nuevo": _peticionario(c.peticionario_nuevo),
                "cambiado_en": c.cambiado_en.isoformat(),
            }
            for c in n.cambios_peticionario
        ],
        "proveedores_solicitados": [
            _proveedor(s.proveedor)
            for s in sorted(n.solicitados, key=lambda s: clave_orden(s.proveedor.nombre))
        ],
        "solicitud_eml": _adjunto(eml) if eml else None,
        "oferta_adjudicada_id": n.oferta_adjudicada_id,
        "fecha_entrega_inicial": _iso(n.fecha_entrega_inicial),
        "plazo_entrega_relativo": adjudicacion.plazo_relativo(n),
        "fecha_entrega_propuesta": _iso(adjudicacion.fecha_propuesta(n)),
        "adjudicacion_eml": _adjunto(correo_adjudicacion) if correo_adjudicacion else None,
        "numero_pedido_sap": n.numero_pedido_sap,
        "pedido_sap": _adjunto(pedido) if pedido else None,
        "pedido_sap_eml": _adjunto(correo_pedido) if correo_pedido else None,
        "retrasos": [
            {
                "fecha_anterior": r.fecha_anterior.isoformat(),
                "fecha_nueva": r.fecha_nueva.isoformat(),
                "motivo": r.motivo,
                "peticionario": _peticionario(r.peticionario),
                "registrado_en": r.registrado_en.isoformat(),
                "sin_efecto": historico.sin_efecto(n),
            }
            for r in n.retrasos
        ],
        "fecha_entrega_real": _iso(n.fecha_entrega_real),
        "comentario_entrega": n.comentario_entrega,
        "recordatorio_enviado_en": _iso(n.recordatorio_enviado_en),
        "aviso_pedido_sap_en": _iso(n.aviso_pedido_sap_en),
    }


def _leer_subidos(lista):
    """Lee los archivos subidos. Devuelve (archivos, None) o (None, respuesta 413)."""
    subidos = []
    for f in lista:
        if not f.filename:
            continue
        # El tamaño se mira antes de leer el archivo para no cargar en memoria uno enorme.
        f.stream.seek(0, 2)
        tamano = f.stream.tell()
        f.stream.seek(0)
        try:
            archivos.comprobar_tamano(f.filename, tamano)
        except ArchivoDemasiadoGrande as e:
            return None, _demasiado_grande(e)
        subidos.append(
            ArchivoSubido(
                nombre=archivos.nombre_limpio(f.filename), tipo_mime=f.mimetype, datos=f.read()
            )
        )
    return subidos, None


def _demasiado_grande(e: ArchivoDemasiadoGrande):
    return respuesta_error(413, "archivo_demasiado_grande", str(e), {"archivo": e.nombre})


def _no_existe():
    return respuesta_error(404, "no_encontrado", "La necesidad no existe.")


def _enviar_archivo(adjunto):
    if adjunto.caducado_en is not None:
        return respuesta_error(
            410,
            "archivo_caducado",
            "El archivo se eliminó por antigüedad (ADR 0014): búscalo en Outlook o en SAP.",
        )
    ruta = archivos.ruta_absoluta(_raiz_archivos(), adjunto.ruta)
    if not ruta.is_file():
        current_app.logger.error("Falta en disco el adjunto %s (%s)", adjunto.id, adjunto.ruta)
        return respuesta_error(404, "no_encontrado", "El archivo no está en el servidor.")
    return send_file(
        ruta,
        mimetype=adjunto.tipo_mime,
        as_attachment=True,
        download_name=adjunto.nombre_archivo,
    )


ERRORES = {400: RespuestaError, 404: RespuestaError, 413: RespuestaError}
ERRORES_ESTADO = {**ERRORES, 409: RespuestaError}


@bp.get("/necesidades", responses={200: ResumenNecesidad})
def listar_necesidades():
    """Panel provisional: todas las necesidades, de la más reciente a la más antigua."""
    with _sesion() as sesion:
        return [_resumen(n, fecha) for n, fecha in necesidades.listar(sesion)]


@bp.post("/necesidades", responses={201: SalidaNecesidad, 409: RespuestaError, **ERRORES})
def crear_necesidad(form: FormularioNecesidad):
    """Crea una necesidad en «Necesidad creada» y le asigna el código AAAAMMDDNN."""
    adjuntos, error = _leer_subidos(form.adjuntos)
    if error:
        return error
    with _sesion() as sesion:
        try:
            necesidad = necesidades.crear(
                sesion,
                _raiz_archivos(),
                titulo=request.form.get("titulo"),
                proyecto=request.form.get("proyecto"),
                descripcion=request.form.get("descripcion"),
                peticionario_id=form.peticionario_id,
                adjuntos=adjuntos,
            )
        except ArchivoDemasiadoGrande as e:
            return _demasiado_grande(e)
        except DemasiadasNecesidades as e:
            return respuesta_error(409, "codigo_agotado", str(e))
        current_app.logger.info("Necesidad creada: %s", necesidad.codigo)
        return _a_dict(necesidad), 201


@bp.get("/necesidades/<int:id>", responses={200: SalidaNecesidad, 404: RespuestaError})
def obtener_necesidad(path: RutaNecesidad):
    """Detalle de una necesidad con sus adjuntos, el historial y la solicitud de ofertas."""
    with _sesion() as sesion:
        necesidad = necesidades.obtener(sesion, path.id)
        if necesidad is None:
            return _no_existe()
        return _a_dict(necesidad)


@bp.put("/necesidades/<int:id>", responses={200: SalidaNecesidad, **ERRORES_ESTADO})
def actualizar_necesidad(path: RutaNecesidad, body: EntradaDatos):
    """Corrige título, proyecto, peticionario y descripción (solo en «Necesidad creada»)."""
    with _sesion() as sesion:
        necesidad = necesidades.actualizar(
            sesion,
            path.id,
            titulo=body.titulo,
            proyecto=body.proyecto,
            descripcion=body.descripcion,
            peticionario_id=body.peticionario_id,
        )
        if necesidad is None:
            return _no_existe()
        return _a_dict(necesidad)


@bp.post("/necesidades/<int:id>/cancelar", responses={200: SalidaNecesidad, **ERRORES_ESTADO})
def cancelar_necesidad(path: RutaNecesidad, body: EntradaCancelacion):
    """Cancela la necesidad con un motivo (no se puede si está «Entregado» o ya cancelada)."""
    with _sesion() as sesion:
        necesidad = necesidades.cancelar(
            sesion, path.id, peticionario_id=body.peticionario_id, motivo=body.motivo
        )
        if necesidad is None:
            return _no_existe()
        current_app.logger.info("Necesidad cancelada: %s", necesidad.codigo)
        return _a_dict(necesidad)


@bp.post("/necesidades/<int:id>/pedido-en-sap", responses={200: SalidaNecesidad, **ERRORES_ESTADO})
def confirmar_pedido_en_sap(path: RutaNecesidad, body: EntradaPedidoEnSap):
    """CU-006 — Confirma que el pedido está en SAP y fija la fecha de entrega prevista.
    Avisa en el momento a los avisados del pedido SAP; si no se puede, lo dice en `avisos` y
    la tarea diaria lo reintenta."""
    with _sesion() as sesion:
        necesidad = necesidades.confirmar_pedido_en_sap(
            sesion,
            path.id,
            peticionario_id=body.peticionario_id,
            fecha_entrega_prevista=body.fecha_entrega_prevista,
        )
        if necesidad is None:
            return _no_existe()
        aviso = avisos_pedido_sap.avisar_al_entrar(
            sesion, current_app.config["REMATE"], necesidad.id, fechas.hoy()
        )
        necesidad = sesion.get(type(necesidad), necesidad.id)
        return {**_a_dict(necesidad), "avisos": [aviso] if aviso else []}


@bp.post("/necesidades/<int:id>/adjuntos", responses={201: SalidaAdjunto, **ERRORES_ESTADO})
def anadir_adjuntos(path: RutaNecesidad, form: FormularioAdjuntos):
    """Añade adjuntos a la necesidad (solo en «Necesidad creada»)."""
    subidos, error = _leer_subidos(form.adjuntos)
    if error:
        return error
    with _sesion() as sesion:
        try:
            nuevos = necesidades.anadir_adjuntos(sesion, _raiz_archivos(), path.id, subidos)
        except ArchivoDemasiadoGrande as e:
            return _demasiado_grande(e)
        if nuevos is None:
            return _no_existe()
        return [_adjunto(a) for a in nuevos], 201


@bp.get("/necesidades/<int:id>/adjuntos/<int:adjunto_id>", responses=ERRORES_DESCARGA)
def descargar_adjunto(path: RutaAdjunto):
    """Descarga un adjunto con su nombre original."""
    with _sesion() as sesion:
        adjunto = necesidades.obtener_adjunto(sesion, path.id, path.adjunto_id)
        if adjunto is None:
            return respuesta_error(404, "no_encontrado", "El adjunto no existe.")
        return _enviar_archivo(adjunto)


@bp.post(
    "/necesidades/<int:id>/solicitud/borrador",
    responses={200: SalidaBorrador, **ERRORES_ESTADO},
)
def borrador_solicitud(path: RutaNecesidad, body: EntradaBorrador):
    """CU-002 — La IA redacta qué se pide; la aplicación pone el resto del correo."""
    with _sesion() as sesion:
        datos = solicitudes.borrador(
            sesion, current_app.config["REMATE"], path.id, body.adjunto_ids
        )
        if datos is None:
            return _no_existe()
        return datos


@bp.post("/necesidades/<int:id>/solicitud", responses={200: SalidaNecesidad, **ERRORES_ESTADO})
def generar_solicitud(path: RutaNecesidad, body: EntradaSolicitud):
    """CU-002 — Genera el .eml (proveedores en CCO) y pasa a «En cotización»."""
    with _sesion() as sesion:
        try:
            necesidad = solicitudes.generar(
                sesion,
                _raiz_archivos(),
                path.id,
                peticionario_id=body.peticionario_id,
                proveedor_ids=body.proveedor_ids,
                adjunto_ids=body.adjunto_ids,
                cuerpo=body.cuerpo,
                motivo_pocos_proveedores=body.motivo_pocos_proveedores,
            )
        except ArchivoDemasiadoGrande:
            return respuesta_error(
                413,
                "archivo_demasiado_grande",
                "Con los adjuntos elegidos, el correo supera los 25 MB: quita alguno.",
            )
        if necesidad is None:
            return _no_existe()
        current_app.logger.info("Solicitud de ofertas generada: %s", necesidad.codigo)
        return _a_dict(necesidad)


@bp.get("/necesidades/<int:id>/solicitud.eml", responses=ERRORES_DESCARGA)
def descargar_solicitud(path: RutaNecesidad):
    """Descarga (o vuelve a descargar) el .eml de la solicitud de ofertas."""
    with _sesion() as sesion:
        necesidad = necesidades.obtener(sesion, path.id)
        eml = necesidad.ultimo_adjunto("solicitud") if necesidad else None
        if eml is None:
            return respuesta_error(404, "no_encontrado", "No hay solicitud generada.")
        return _enviar_archivo(eml)
