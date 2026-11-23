"""Modo admin (ADR 0015): sesión con contraseña y herramientas de administración.

Todas las rutas, salvo entrar y consultar la sesión, piden una sesión de admin vigente
(`admin_sesion.requiere_admin`). Los cambios pasan además por la comprobación de origen de
`app/origen.py`.
"""

from dataclasses import asdict
from datetime import date
from typing import Literal

from flask import current_app, request
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, ConfigDict, Field

from app import admin_sesion, fechas
from app.api.errores import RespuestaError, respuesta_error
from app.api.necesidades import SalidaNecesidad, _a_dict, _raiz_archivos, _sesion
from app.api.tipos import Id
from app.integraciones.correo_saliente import ErrorCorreo
from app.servicios import admin, avisos_pedido_sap, caducidad, recordatorios

bp = APIBlueprint("admin", __name__, url_prefix="/api/admin", abp_tags=[Tag(name="Modo admin")])
ERRORES = {
    400: RespuestaError,
    401: RespuestaError,
    404: RespuestaError,
    503: RespuestaError,
}


class EntradaSesion(BaseModel):
    clave: str = Field(max_length=200)


class SalidaSesion(BaseModel):
    activa: bool
    configurado: bool


class RutaNecesidad(BaseModel):
    id: Id


class EntradaBorrado(BaseModel):
    # Con margen para espacios alrededor; el servicio los quita.
    codigo: str = Field(max_length=40)


class EntradaDeshacer(BaseModel):
    # El estado en el que está ahora: si ya no coincide (otro «deshacer» a la vez o un
    # reintento), 409 y no se deshace un segundo paso.
    estado: str = Field(max_length=30)


class SalidaBorrado(BaseModel):
    codigo: str
    archivos: int
    no_borrados: int


class EntradaCorreccion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fecha_entrega_prevista: date | None = None
    fecha_entrega_real: date | None = None
    numero_pedido_sap: str | None = None
    comentario_entrega: str | None = None


class RutaTarea(BaseModel):
    nombre: Literal["recordatorios", "avisos", "caducidad"]


class EntradaTarea(BaseModel):
    prueba: bool = True


class FiltroRegistros(BaseModel):
    nivel: Literal["INFO", "WARNING", "ERROR", "CRITICAL"] | None = None
    limite: int = Field(default=100, ge=1, le=1000)


def _no_existe():
    return respuesta_error(404, "no_encontrado", "La necesidad no existe.")


@bp.get("/sesion", responses={200: SalidaSesion})
def ver_sesion():
    """Si hay una sesión de admin vigente y si el modo admin está configurado."""
    return {
        "activa": admin_sesion.configurado()
        and admin_sesion.vigente(request.cookies.get(admin_sesion.COOKIE)),
        "configurado": admin_sesion.configurado(),
    }


@bp.post("/sesion", responses={200: SalidaSesion, 401: RespuestaError, 429: RespuestaError})
def entrar(body: EntradaSesion):
    """Entra con la contraseña. 401 si no vale; 429 tras 5 fallos seguidos (15 minutos)."""
    if not admin_sesion.configurado():
        return respuesta_error(
            503, "admin_no_configurado", "El modo admin no está configurado (ADR 0015)."
        )
    if espera := admin_sesion.bloqueado_durante():
        return respuesta_error(
            429,
            "demasiados_intentos",
            f"Demasiados intentos fallidos: espera {espera // 60 + 1} minuto(s).",
        )
    token = admin_sesion.entrar(body.clave)
    if token is None and (espera := admin_sesion.bloqueado_durante()):
        return respuesta_error(
            429,
            "demasiados_intentos",
            f"Demasiados intentos fallidos: espera {espera // 60 + 1} minuto(s).",
        )
    if token is None:
        # Sin la contraseña en el registro: solo que ha fallado.
        current_app.logger.warning("Modo admin: contraseña incorrecta")
        return respuesta_error(401, "clave_incorrecta", "La contraseña no es correcta.")
    current_app.logger.warning("Modo admin: sesión iniciada")
    respuesta = current_app.response_class(
        current_app.json.dumps({"activa": True, "configurado": True}),
        mimetype="application/json",
    )
    respuesta.set_cookie(
        admin_sesion.COOKIE,
        token,
        # Sin max_age: la caducidad por falta de uso la lleva el servidor.
        path=admin_sesion.RUTA_COOKIE,
        httponly=True,
        samesite="Strict",
        # `Secure` solo con HTTPS: detrás de un proxy con HTTPS (ADR 0016); sin él (ADR 0006), no
        # puede serlo.
        secure=request.is_secure,
    )
    return respuesta


@bp.delete("/sesion", responses={204: None})
def salir():
    """Cierra la sesión de admin."""
    admin_sesion.salir(request.cookies.get(admin_sesion.COOKIE))
    respuesta = current_app.response_class(status=204)
    respuesta.delete_cookie(admin_sesion.COOKIE, path=admin_sesion.RUTA_COOKIE)
    return respuesta


@bp.get("/estado", responses=ERRORES)
@admin_sesion.requiere_admin
def ver_estado():
    """Necesidades por estado, archivos, disco, última copia, consumo de la IA (30 días) y
    avisos y errores del registro (7 días)."""
    config = current_app.config["REMATE"]
    with _sesion() as sesion:
        return admin.estado(sesion, _raiz_archivos(), config.copias_dir)


@bp.get("/registros", responses=ERRORES)
@admin_sesion.requiere_admin
def ver_registros(query: FiltroRegistros):
    """Los últimos mensajes de la tabla `logs` (con `nivel`, ese y los más graves)."""
    with _sesion() as sesion:
        return [
            {
                "id": r.id,
                "creado_en": r.creado_en.isoformat(),
                "nivel": r.nivel,
                "origen": r.origen,
                "mensaje": r.mensaje,
                "traza": r.traza,
            }
            for r in admin.registros(sesion, query.nivel, query.limite)
        ]


@bp.post("/necesidades/<int:id>/borrado", responses={200: SalidaBorrado, **ERRORES})
@admin_sesion.requiere_admin
def borrar_necesidad(path: RutaNecesidad, body: EntradaBorrado):
    """Borra de verdad la necesidad y todo lo suyo, también sus archivos. Hay que escribir su
    código para confirmar. No se puede deshacer."""
    with _sesion() as sesion:
        resultado = admin.borrar_necesidad(sesion, _raiz_archivos(), path.id, body.codigo)
        if resultado is None:
            return _no_existe()
        return resultado


@bp.post(
    "/necesidades/<int:id>/deshacer",
    responses={200: SalidaNecesidad, 409: RespuestaError, **ERRORES},
)
@admin_sesion.requiere_admin
def deshacer(path: RutaNecesidad, body: EntradaDeshacer):
    """Vuelve al estado anterior: quita lo que guardó el último paso y su línea del historial.
    `estado`: el actual; si ya no lo es, 409 `estado_cambiado`."""
    with _sesion() as sesion:
        try:
            necesidad = admin.deshacer(sesion, _raiz_archivos(), path.id, body.estado)
        except admin.EstadoCambiado as e:
            return respuesta_error(409, "estado_cambiado", str(e))
        if necesidad is None:
            return _no_existe()
        return _a_dict(necesidad)


@bp.patch("/necesidades/<int:id>", responses={200: SalidaNecesidad, **ERRORES})
@admin_sesion.requiere_admin
def corregir(path: RutaNecesidad, body: EntradaCorreccion):
    """Corrige fechas de entrega, número de pedido SAP o comentario de la entrega (solo los
    campos que se envían)."""
    with _sesion() as sesion:
        necesidad = admin.corregir(sesion, path.id, body.model_dump(exclude_unset=True))
        if necesidad is None:
            return _no_existe()
        return _a_dict(necesidad)


@bp.post("/tareas/<nombre>", responses={**ERRORES, 502: RespuestaError})
@admin_sesion.requiere_admin
def lanzar_tarea(path: RutaTarea, body: EntradaTarea):
    """Lanza a mano una tarea diaria: `recordatorios`, `avisos` (del pedido SAP) o `caducidad`.
    Con `prueba` (por defecto), no envía ni borra: dice lo que haría."""
    config = current_app.config["REMATE"]
    with _sesion() as sesion:
        try:
            if path.nombre == "recordatorios":
                resumen = recordatorios.enviar_recordatorios(
                    sesion, config, fechas.hoy(), prueba=body.prueba
                )
            elif path.nombre == "avisos":
                resumen = avisos_pedido_sap.enviar_pendientes(
                    sesion, config, fechas.hoy(), prueba=body.prueba
                )
            else:
                resumen = caducidad.caducar(
                    sesion, config.archivos_dir, fechas.hoy(), prueba=body.prueba
                )
        except ErrorCorreo as e:
            sesion.rollback()
            return respuesta_error(502, "correo_no_disponible", str(e))
    current_app.logger.warning(
        "Modo admin: tarea %s%s", path.nombre, " (prueba)" if body.prueba else ""
    )
    return {"tarea": path.nombre, "prueba": body.prueba, "resumen": asdict(resumen)}
