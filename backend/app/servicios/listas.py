"""CU-003 — Reglas de negocio de las listas de proveedores, peticionarios y avisados del pedido
SAP.

Reglas (docs/casos-de-uso/CU-003-gestionar-listas.md):
- Orden siempre de la A a la Z, sin distinguir mayúsculas ni tildes.
- Correo obligatorio, válido y único (sin distinguir mayúsculas); se guarda en minúsculas.
- Nombre obligatorio, sin espacios sobrantes; un nombre repetido con otro correo solo avisa.
- Nada se borra: los registros se desactivan. Uno desactivado se puede eliminar (baja definitiva)
  con un motivo obligatorio: deja de salir en las listas, pero sigue en las necesidades antiguas y
  su correo queda libre. Si es un peticionario con necesidades en curso, se avisa y
  hay que pasarlas a otro peticionario activo.
"""

import unicodedata
from datetime import UTC, datetime

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.modelos.listas import AvisadoPedidoSap, Peticionario, Proveedor
from app.modelos.necesidades import CambioPeticionario, Necesidad

Modelo = type[Proveedor] | type[Peticionario] | type[AvisadoPedidoSap]


class DatosNoValidos(ValueError):
    """Un dato de entrada no cumple las reglas; `campo` indica cuál."""

    def __init__(self, campo: str, mensaje: str):
        super().__init__(mensaje)
        self.campo = campo


def peticionario_activo(sesion: Session, peticionario_id: int | None, mensaje: str) -> Peticionario:
    """El peticionario que hace una acción: tiene que existir y estar activo; si no, `mensaje`."""
    peticionario = sesion.get(Peticionario, peticionario_id) if peticionario_id else None
    if peticionario is None or not peticionario.activo or peticionario.eliminado_en is not None:
        raise DatosNoValidos("peticionario_id", mensaje)
    return peticionario


class CorreoDuplicado(Exception):
    """Ya existe un registro con ese correo; `existente` es ese registro."""

    def __init__(self, existente):
        super().__init__(f"Ya existe un registro con el correo {existente.email}.")
        self.existente = existente


def _campo_nombre(modelo: Modelo) -> str:
    return "nombre_completo" if modelo is Peticionario else "nombre"


def clave_orden(texto: str) -> str:
    """Clave para ordenar de la A a la Z sin distinguir tildes ni mayúsculas («Á» va con la «A»)."""
    sin_tildes = unicodedata.normalize("NFD", texto)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    return sin_tildes.casefold()


def normalizar_nombre(nombre: str | None) -> str:
    limpio = " ".join((nombre or "").split())
    if not limpio:
        raise DatosNoValidos("nombre", "El nombre es obligatorio.")
    return limpio


def normalizar_email(email: str | None, solo_ascii: bool = False) -> str:
    """`solo_ascii`: sin tildes ni «ñ» (avisados del pedido SAP, que reciben correos de ReMate:
    un servidor sin SMTPUTF8 rechaza el mensaje entero)."""
    limpio = (email or "").strip().lower()
    if solo_ascii and not limpio.isascii():
        raise DatosNoValidos(
            "email",
            f"El correo «{limpio}» lleva tildes, «ñ» u otros caracteres especiales: ReMate no "
            "puede enviarle correos. Escribe la dirección sin ellos.",
        )
    try:
        validate_email(limpio, check_deliverability=False)
    except EmailNotValidError as error:
        raise DatosNoValidos("email", f"El correo «{limpio}» no es válido.") from error
    return limpio


class NoEliminable(Exception):
    """El registro sigue activo: primero se desactiva y después se elimina."""


MAXIMO_MOTIVO = 500


def _vigente(sesion: Session, modelo: Modelo, registro_id: int, bloquear: bool = False):
    """El registro si existe y no está eliminado; si no, None (para la API, «no existe»).

    Con `bloquear`, la fila queda bloqueada hasta el commit: así, desactivar, reactivar, eliminar
    o pasarle necesidades a la misma persona a la vez no se pisan.
    """
    registro = sesion.get(modelo, registro_id, with_for_update=bloquear)
    return None if registro is None or registro.eliminado_en is not None else registro


def listar(sesion: Session, modelo: Modelo, incluir_inactivos: bool = False) -> list:
    # Los eliminados no salen nunca, ni siquiera con los inactivos.
    consulta = select(modelo).where(modelo.eliminado_en.is_(None))
    if not incluir_inactivos:
        consulta = consulta.where(modelo.activo.is_(True))
    registros = sesion.scalars(consulta).all()
    campo = _campo_nombre(modelo)
    return sorted(registros, key=lambda r: (clave_orden(getattr(r, campo)), r.id))


def _buscar_por_email(sesion: Session, modelo: Modelo, email: str, excepto_id: int | None = None):
    consulta = select(modelo).where(modelo.email == email, modelo.eliminado_en.is_(None))
    if excepto_id is not None:
        consulta = consulta.where(modelo.id != excepto_id)
    return sesion.scalars(consulta).first()


def _avisos_de_nombre(sesion: Session, modelo: Modelo, nombre: str, excepto_id: int | None = None):
    campo = getattr(modelo, _campo_nombre(modelo))
    consulta = select(modelo).where(
        func.lower(campo) == nombre.lower(), modelo.eliminado_en.is_(None)
    )
    if excepto_id is not None:
        consulta = consulta.where(modelo.id != excepto_id)
    otro = sesion.scalars(consulta).first()
    if otro is None:
        return []
    return [f"Ya existe otro registro con el nombre «{getattr(otro, _campo_nombre(modelo))}»."]


def crear(sesion: Session, modelo: Modelo, nombre: str, email: str):
    """Crea un registro activo. Devuelve (registro, avisos)."""
    nombre = normalizar_nombre(nombre)
    email = normalizar_email(email, solo_ascii=modelo is AvisadoPedidoSap)
    existente = _buscar_por_email(sesion, modelo, email)
    if existente is not None:
        raise CorreoDuplicado(existente)
    avisos = _avisos_de_nombre(sesion, modelo, nombre)
    registro = modelo(**{_campo_nombre(modelo): nombre, "email": email, "activo": True})
    sesion.add(registro)
    try:
        sesion.commit()
    except IntegrityError:
        # Otra persona ha dado de alta el mismo correo a la vez: la restricción única lo frena.
        sesion.rollback()
        raise CorreoDuplicado(_buscar_por_email(sesion, modelo, email)) from None
    return registro, avisos


def actualizar(
    sesion: Session,
    modelo: Modelo,
    registro_id: int,
    nombre: str | None = None,
    email: str | None = None,
    activo: bool | None = None,
):
    """Modifica nombre, correo o estado. Devuelve el registro, o None si no existe."""
    registro = _vigente(sesion, modelo, registro_id, bloquear=True)
    if registro is None:
        sesion.rollback()
        return None
    if nombre is not None:
        setattr(registro, _campo_nombre(modelo), normalizar_nombre(nombre))
    if email is not None:
        try:
            email = normalizar_email(email, solo_ascii=modelo is AvisadoPedidoSap)
        except DatosNoValidos:
            sesion.rollback()
            raise
        existente = _buscar_por_email(sesion, modelo, email, excepto_id=registro_id)
        if existente is not None:
            sesion.rollback()
            raise CorreoDuplicado(existente)
        registro.email = email
    if activo is not None:
        registro.activo = activo
    sesion.commit()
    return registro


class NecesidadesEnCurso(Exception):
    """El peticionario lleva necesidades sin entregar ni cancelar: hay que pasarlas a otro."""

    def __init__(self, necesidades: list[Necesidad]):
        super().__init__(
            f"Lleva {len(necesidades)} necesidad(es) en curso: elige a quién pasárselas."
        )
        self.necesidades = necesidades


def necesidades_en_curso(sesion: Session, peticionario_id: int) -> list[Necesidad]:
    consulta = (
        select(Necesidad)
        .where(
            Necesidad.peticionario_id == peticionario_id,
            Necesidad.estado.not_in(("entregado", "cancelada")),
        )
        .order_by(Necesidad.codigo)
        .with_for_update()
    )
    return list(sesion.scalars(consulta))


def _reasignar(sesion: Session, registro: Peticionario, reasignar_a: int | None) -> None:
    """Pasa las necesidades en curso del peticionario que se elimina a `reasignar_a`.
    Sin necesidades en curso no hace nada; con ellas y sin `reasignar_a`, NecesidadesEnCurso."""
    necesidades = necesidades_en_curso(sesion, registro.id)
    if not necesidades:
        return
    if reasignar_a is None:
        raise NecesidadesEnCurso(necesidades)
    if reasignar_a == registro.id:
        raise DatosNoValidos("reasignar_a", "Elige a otra persona.")
    nuevo = _vigente(sesion, Peticionario, reasignar_a, bloquear=True)
    if nuevo is None or not nuevo.activo:
        raise DatosNoValidos("reasignar_a", "Elige un peticionario activo para sus necesidades.")
    for necesidad in necesidades:
        sesion.add(
            CambioPeticionario(
                necesidad=necesidad,
                peticionario_anterior_id=registro.id,
                peticionario_nuevo_id=nuevo.id,
            )
        )
        necesidad.peticionario = nuevo
        # CU-009: el recordatorio de la fecha prevista le llega también al nuevo.
        necesidad.recordatorio_enviado_en = None


def eliminar(
    sesion: Session,
    modelo: Modelo,
    registro_id: int,
    motivo: str | None,
    reasignar_a: int | None = None,
):
    """Baja definitiva de un registro desactivado, con su motivo. Un peticionario con necesidades
    en curso solo se elimina si se pasan a otro (`reasignar_a`). Devuelve el registro, o None si
    no existe o ya estaba eliminado."""
    registro = _vigente(sesion, modelo, registro_id, bloquear=True)
    if registro is None:
        sesion.rollback()
        return None
    if registro.activo:
        raise NoEliminable("Desactívalo antes de eliminarlo.")
    motivo = " ".join((motivo or "").split())
    if not motivo:
        raise DatosNoValidos("motivo", "Indica el motivo de la eliminación.")
    if len(motivo) > MAXIMO_MOTIVO:
        raise DatosNoValidos("motivo", f"El motivo no puede pasar de {MAXIMO_MOTIVO} caracteres.")
    if modelo is Peticionario:
        try:
            _reasignar(sesion, registro, reasignar_a)
        except NecesidadesEnCurso, DatosNoValidos:
            sesion.rollback()
            raise
    registro.eliminado_en = datetime.now(UTC)
    registro.motivo_eliminacion = motivo
    sesion.commit()
    return registro
