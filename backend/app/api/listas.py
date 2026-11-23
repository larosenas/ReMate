"""CU-003 — API de las listas de proveedores, peticionarios y avisados del pedido SAP."""

from flask import current_app
from flask_openapi3 import APIBlueprint, Tag
from pydantic import BaseModel, ConfigDict, Field

from app.api.errores import RespuestaError, respuesta_error
from app.api.tipos import Id
from app.modelos.listas import AvisadoPedidoSap, Peticionario, Proveedor
from app.servicios import historico, listas
from app.servicios.listas import (
    CorreoDuplicado,
    NecesidadesEnCurso,
    NoEliminable,
)

bp = APIBlueprint("listas", __name__, url_prefix="/api", abp_tags=[Tag(name="Listas (CU-003)")])


class RutaId(BaseModel):
    id: Id


class FiltroListas(BaseModel):
    incluir_inactivos: bool = False


class EntradaProveedor(BaseModel):
    nombre: str = Field(max_length=200)
    email: str = Field(max_length=254)


class CambioProveedor(BaseModel):
    nombre: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    activo: bool | None = None


class EntradaPeticionario(BaseModel):
    nombre_completo: str = Field(max_length=200)
    email: str = Field(max_length=254)


class CambioPeticionario(BaseModel):
    nombre_completo: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    activo: bool | None = None


class SalidaProveedor(BaseModel):
    id: int
    nombre: str
    email: str
    activo: bool
    avisos: list[str] = []


class SalidaPeticionario(BaseModel):
    id: int
    nombre_completo: str
    email: str
    activo: bool
    avisos: list[str] = []


def _sesion():
    return current_app.extensions["remate.sesiones"]()


def _a_dict(registro, avisos=None) -> dict:
    datos = {"id": registro.id, "email": registro.email, "activo": registro.activo}
    if isinstance(registro, Peticionario):
        datos["nombre_completo"] = registro.nombre_completo
    else:
        datos["nombre"] = registro.nombre
    if avisos is not None:
        datos["avisos"] = avisos
    return datos


def _listar(modelo, query: FiltroListas):
    with _sesion() as sesion:
        return [_a_dict(r) for r in listas.listar(sesion, modelo, query.incluir_inactivos)]


def _crear(modelo, nombre: str, email: str):
    with _sesion() as sesion:
        try:
            registro, avisos = listas.crear(sesion, modelo, nombre, email)
        except CorreoDuplicado as e:
            return respuesta_error(
                409, "correo_duplicado", str(e), {"existente": _a_dict(e.existente)}
            )
        current_app.logger.info("Alta en %s: id %s", modelo.__tablename__, registro.id)
        return _a_dict(registro, avisos), 201


def _actualizar(modelo, registro_id: int, nombre, email, activo):
    with _sesion() as sesion:
        try:
            registro = listas.actualizar(sesion, modelo, registro_id, nombre, email, activo)
        except CorreoDuplicado as e:
            return respuesta_error(
                409, "correo_duplicado", str(e), {"existente": _a_dict(e.existente)}
            )
        if registro is None:
            return respuesta_error(404, "no_encontrado", "El registro no existe.")
        return _a_dict(registro)


def _eliminar(modelo, registro_id: int, motivo, reasignar_a=None):
    with _sesion() as sesion:
        try:
            registro = listas.eliminar(sesion, modelo, registro_id, motivo, reasignar_a)
        except NoEliminable as e:
            return respuesta_error(409, "sigue_activo", str(e))
        except NecesidadesEnCurso as e:
            necesidades = [
                {"id": n.id, "codigo": n.codigo, "titulo": n.titulo} for n in e.necesidades
            ]
            return respuesta_error(
                409, "necesidades_en_curso", str(e), {"necesidades": necesidades}
            )
        if registro is None:
            return respuesta_error(404, "no_encontrado", "El registro no existe.")
        # El motivo no va al log: puede llevar datos de una persona.
        current_app.logger.info("Baja definitiva en %s: id %s", modelo.__tablename__, registro.id)
        return "", 204


class EntradaBaja(BaseModel):
    # Campos de más (como `reasignar_a` en un proveedor) dan 400 en lugar de ignorarse.
    model_config = ConfigDict(extra="forbid")
    # Uno de los motivos de la lista de la pantalla o el que escriba el usuario («Otro»).
    motivo: str | None = None


class EntradaBajaPeticionario(EntradaBaja):
    # A quién pasan sus necesidades en curso (obligatorio si las tiene).
    reasignar_a: Id | None = None


ERRORES = {400: RespuestaError, 404: RespuestaError, 409: RespuestaError}


@bp.get("/proveedores", responses={200: SalidaProveedor})
def listar_proveedores(query: FiltroListas):
    """Proveedores ordenados de la A a la Z (solo activos, salvo `incluir_inactivos`)."""
    return _listar(Proveedor, query)


@bp.post("/proveedores", responses={201: SalidaProveedor, **ERRORES})
def crear_proveedor(body: EntradaProveedor):
    """Alta de un proveedor («Otro»). 409 si el correo ya existe."""
    return _crear(Proveedor, body.nombre, body.email)


@bp.patch("/proveedores/<int:id>", responses={200: SalidaProveedor, **ERRORES})
def actualizar_proveedor(path: RutaId, body: CambioProveedor):
    """Editar, desactivar o reactivar un proveedor (nunca se borra)."""
    return _actualizar(Proveedor, path.id, body.nombre, body.email, body.activo)


@bp.get("/peticionarios", responses={200: SalidaPeticionario})
def listar_peticionarios(query: FiltroListas):
    """Peticionarios ordenados de la A a la Z (solo activos, salvo `incluir_inactivos`)."""
    return _listar(Peticionario, query)


@bp.post("/peticionarios", responses={201: SalidaPeticionario, **ERRORES})
def crear_peticionario(body: EntradaPeticionario):
    """Alta de un peticionario («Otro»). 409 si el correo ya existe."""
    return _crear(Peticionario, body.nombre_completo, body.email)


@bp.patch("/peticionarios/<int:id>", responses={200: SalidaPeticionario, **ERRORES})
def actualizar_peticionario(path: RutaId, body: CambioPeticionario):
    """Editar, desactivar o reactivar un peticionario (nunca se borra)."""
    return _actualizar(Peticionario, path.id, body.nombre_completo, body.email, body.activo)


@bp.post("/proveedores/<int:id>/baja", responses={204: None, **ERRORES})
def eliminar_proveedor(path: RutaId, body: EntradaBaja):
    """Baja definitiva de un proveedor desactivado, con motivo. Deja de salir en las listas
    (también en los inactivos), sigue en las necesidades antiguas y su correo queda libre.
    409 `sigue_activo` si no se ha desactivado antes."""
    return _eliminar(Proveedor, path.id, body.motivo)


@bp.post("/peticionarios/<int:id>/baja", responses={204: None, **ERRORES})
def eliminar_peticionario(path: RutaId, body: EntradaBajaPeticionario):
    """Baja definitiva de un peticionario desactivado, con motivo (como la de los proveedores).
    Si lleva necesidades en curso, 409 `necesidades_en_curso` con la lista; con `reasignar_a`
    (un peticionario activo) pasan a él, queda constancia en cada una y se elimina."""
    return _eliminar(Peticionario, path.id, body.motivo, body.reasignar_a)


@bp.get("/avisados-pedido-sap", responses={200: SalidaProveedor})
def listar_avisados(query: FiltroListas):
    """Quién recibe el aviso del paso 5 (pedido en SAP) y su recordatorio semanal, de la A
    a la Z (solo activos, salvo `incluir_inactivos`). Mismos campos que un proveedor."""
    return _listar(AvisadoPedidoSap, query)


@bp.post("/avisados-pedido-sap", responses={201: SalidaProveedor, **ERRORES})
def crear_avisado(body: EntradaProveedor):
    """Alta de un avisado del pedido SAP. 409 si el correo ya existe."""
    return _crear(AvisadoPedidoSap, body.nombre, body.email)


@bp.patch("/avisados-pedido-sap/<int:id>", responses={200: SalidaProveedor, **ERRORES})
def actualizar_avisado(path: RutaId, body: CambioProveedor):
    """Editar, desactivar o reactivar un avisado del pedido SAP."""
    return _actualizar(AvisadoPedidoSap, path.id, body.nombre, body.email, body.activo)


@bp.post("/avisados-pedido-sap/<int:id>/baja", responses={204: None, **ERRORES})
def eliminar_avisado(path: RutaId, body: EntradaBaja):
    """Baja definitiva de un avisado desactivado, con motivo (como la de los proveedores)."""
    return _eliminar(AvisadoPedidoSap, path.id, body.motivo)


class RetrasoNecesidad(BaseModel):
    id: int
    codigo: str
    titulo: str


class SalidaRetrasoProveedor(BaseModel):
    necesidad: RetrasoNecesidad
    fecha_anterior: str
    fecha_nueva: str
    dias: int
    motivo: str
    peticionario: str
    registrado_en: str
    # El pedido llegó el día previsto o antes: el retraso avisado no se cumplió y no cuenta.
    sin_efecto: bool


class ComentarioEntrega(BaseModel):
    """Comentario de la entrega de un pedido anterior del proveedor."""

    necesidad_id: int
    codigo: str
    titulo: str
    fecha: str
    texto: str


class SalidaHistorico(BaseModel):
    proveedor: SalidaProveedor
    pedidos: int
    con_retraso: int
    # Días de retraso de todos sus pedidos.
    dias_retraso: int
    # Días de retraso por pedido, contando también los que llegaron a tiempo (None sin pedidos).
    retraso_medio: float | None
    # Comentarios de la entrega, del más reciente al más antiguo.
    comentarios: list[ComentarioEntrega]
    retrasos: list[SalidaRetrasoProveedor]


@bp.get("/proveedores/<int:id>/retrasos", responses={200: SalidaHistorico, 404: RespuestaError})
def retrasos_de_proveedor(path: RutaId):
    """CU-010 — Histórico de retrasos del proveedor: pedidos adjudicados, cuántos con retraso,
    retraso medio y cada retraso (del más reciente al más antiguo)."""
    with _sesion() as sesion:
        datos = historico.historico(sesion, path.id)
        if datos is None:
            return respuesta_error(404, "no_encontrado", "El proveedor no existe.")
        return {
            **historico.para_la_api(datos),
            "proveedor": _a_dict(datos["proveedor"]),
            "retrasos": [
                {
                    "necesidad": {
                        "id": r["necesidad"].id,
                        "codigo": r["necesidad"].codigo,
                        "titulo": r["necesidad"].titulo,
                    },
                    "fecha_anterior": r["fecha_anterior"].isoformat(),
                    "fecha_nueva": r["fecha_nueva"].isoformat(),
                    "dias": r["dias"],
                    "motivo": r["motivo"],
                    "peticionario": r["peticionario"].nombre_completo,
                    "registrado_en": r["registrado_en"].isoformat(),
                    "sin_efecto": r["sin_efecto"],
                }
                for r in datos["retrasos"]
            ],
        }
