"""CU-001 — Reglas de negocio para crear necesidades.

Reglas (docs/casos-de-uso/CU-001-crear-necesidad.md):
- Título, proyecto, peticionario (activo) y descripción obligatorios; adjuntos opcionales.
- Adjuntos de cualquier tipo, hasta 25 MB cada uno.
- Código AAAAMMDDNN: fecha de creación en Europe/Madrid y orden dentro del día.
- Se registra el primer cambio de estado («Necesidad creada») con el peticionario y la hora.
"""

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.integraciones import archivos
from app.modelos.listas import Peticionario
from app.modelos.necesidades import ESTADOS, Adjunto, CambioEstado, CodigoBorrado, Necesidad
from app.modelos.ofertas import Oferta
from app.servicios.listas import DatosNoValidos, peticionario_activo

ZONA_HORARIA = "Europe/Madrid"
INTENTOS_CODIGO = 5


@dataclass(frozen=True)
class ArchivoSubido:
    nombre: str
    tipo_mime: str
    datos: bytes


class DemasiadasNecesidades(RuntimeError):
    """Ya hay 99 necesidades hoy: el código AAAAMMDDNN no admite más."""


class TransicionNoPermitida(RuntimeError):
    """La acción no se puede hacer en el estado actual de la necesidad."""


def necesidad_en(
    sesion: Session, necesidad_id: int, estado: str, bloquear: bool = False
) -> Necesidad | None:
    """La necesidad, que tiene que estar en `estado` (si no, TransicionNoPermitida). None si no
    existe. `bloquear`: bloquea la fila para que dos peticiones a la vez no se pisen."""
    # Al bloquear se vuelve a leer: si la necesidad ya estaba cargada en la sesión, SQLAlchemy no
    # la refresca y se comprobaría un estado antiguo.
    necesidad = sesion.get(
        Necesidad, necesidad_id, with_for_update=bloquear, populate_existing=bloquear
    )
    if necesidad is not None and necesidad.estado != estado:
        raise TransicionNoPermitida(f"La necesidad no está en «{ESTADOS[estado]}».")
    return necesidad


def asunto_correos(necesidad: Necesidad) -> str:
    """Asunto de todos los correos de la necesidad (petición de ofertas, adjudicación, pedido SAP y
    recordatorio): `AAAAMMDDNN | Proyecto | Título`, sin añadir nada al final, para que el cliente
    de correo los agrupe en la misma conversación. El título y el proyecto
    solo se pueden cambiar antes de pedir ofertas, así que el asunto no cambia después."""
    return f"{necesidad.codigo} | {necesidad.proyecto} | {necesidad.titulo}"


def firma(necesidad: Necesidad, empresa: str, despedida: str = "Un saludo,") -> str:
    """Final de los correos a proveedores: despedida, peticionario y empresa (EMPRESA_NOMBRE;
    si está vacío, sin esa línea)."""
    lineas = [despedida, necesidad.peticionario.nombre_completo, empresa.strip()]
    return "\n".join(linea for linea in lineas if linea) + "\n"


def _texto(
    valor: str | None,
    campo: str,
    mensaje: str,
    maximo: int | None = None,
    una_linea: bool = False,
) -> str:
    limpio = (valor or "").strip()
    if una_linea:
        # El título y el proyecto van en el asunto de los correos, que no admite saltos de línea.
        limpio = " ".join(limpio.split())
    if not limpio:
        raise DatosNoValidos(campo, mensaje)
    if maximo is not None and len(limpio) > maximo:
        raise DatosNoValidos(campo, f"Máximo {maximo} caracteres.")
    return limpio


def _validar_datos(sesion: Session, titulo, proyecto, descripcion, peticionario_id):
    titulo = _texto(titulo, "titulo", "El título es obligatorio.", 200, una_linea=True)
    proyecto = _texto(proyecto, "proyecto", "El proyecto es obligatorio.", 200, una_linea=True)
    descripcion = _texto(descripcion, "descripcion", "La descripción es obligatoria.")
    peticionario = peticionario_activo(
        sesion, peticionario_id, "Elige un peticionario de la lista."
    )
    return titulo, proyecto, descripcion, peticionario


def _ahora_en_madrid(sesion: Session) -> datetime:
    # La hora la da PostgreSQL, que trae su propia base de zonas horarias (en Windows,
    # Python no la tiene sin instalar el paquete tzdata).
    return sesion.scalar(select(func.timezone(ZONA_HORARIA, func.now())))


def siguiente_codigo(sesion: Session, dia: datetime) -> str:
    prefijo = dia.strftime("%Y%m%d")
    # También los de las necesidades borradas con el modo admin: no se reutilizan (ADR 0015).
    ultimo = max(
        (
            sesion.scalar(select(func.max(modelo.codigo)).where(modelo.codigo.startswith(prefijo)))
            or ""
            for modelo in (Necesidad, CodigoBorrado)
        ),
        default="",
    )
    numero = int(ultimo[8:]) + 1 if ultimo else 1
    if numero > 99:
        raise DemasiadasNecesidades("Hoy ya se han creado 99 necesidades; no caben más códigos.")
    return f"{prefijo}{numero:02d}"


def crear(
    sesion: Session,
    raiz_archivos: Path,
    *,
    titulo: str | None,
    proyecto: str | None,
    descripcion: str | None,
    peticionario_id: int | None,
    adjuntos: list[ArchivoSubido] = (),
    ahora: datetime | None = None,
) -> Necesidad:
    """Crea la necesidad en «Necesidad creada» con sus adjuntos. `ahora` es para las pruebas."""
    titulo, proyecto, descripcion, peticionario = _validar_datos(
        sesion, titulo, proyecto, descripcion, peticionario_id
    )
    for adjunto in adjuntos:
        archivos.comprobar_tamano(adjunto.nombre, len(adjunto.datos))

    for intento in range(INTENTOS_CODIGO):
        dia = ahora or _ahora_en_madrid(sesion)
        necesidad = Necesidad(
            codigo=siguiente_codigo(sesion, dia),
            titulo=titulo,
            proyecto=proyecto,
            descripcion=descripcion,
            estado="necesidad_creada",
            peticionario=peticionario,
        )
        necesidad.historial.append(
            CambioEstado(estado_nuevo="necesidad_creada", peticionario=peticionario)
        )
        sesion.add(necesidad)
        try:
            sesion.flush()
            break
        except IntegrityError:
            # Otra persona ha creado una necesidad a la vez y se ha llevado ese código.
            sesion.rollback()
            peticionario = sesion.get(Peticionario, peticionario_id)
            if intento == INTENTOS_CODIGO - 1:
                raise

    _guardar_adjuntos(sesion, raiz_archivos, necesidad, adjuntos)
    return necesidad


def _guardar_adjuntos(
    sesion: Session, raiz_archivos: Path, necesidad: Necesidad, adjuntos: list[ArchivoSubido]
) -> list[Adjunto]:
    """Escribe los archivos, crea sus `Adjunto` y confirma la transacción."""
    guardados, nuevos = [], []
    try:
        for adjunto in adjuntos:
            ruta = archivos.guardar(raiz_archivos, necesidad.codigo, adjunto.nombre, adjunto.datos)
            guardados.append(ruta)
            nuevo = Adjunto(
                tipo="necesidad",
                nombre_archivo=adjunto.nombre[:255],
                ruta=ruta,
                tipo_mime=adjunto.tipo_mime or "application/octet-stream",
                tamano=len(adjunto.datos),
            )
            necesidad.adjuntos.append(nuevo)
            nuevos.append(nuevo)
        sesion.commit()
    except Exception:
        # No deja archivos huérfanos si falla la escritura o el guardado en la base de datos.
        sesion.rollback()
        for ruta in guardados:
            archivos.borrar(raiz_archivos, ruta)
        raise
    return nuevos


def anadir_adjuntos(
    sesion: Session, raiz_archivos: Path, necesidad_id: int, adjuntos: list[ArchivoSubido]
) -> list[Adjunto] | None:
    """Añade adjuntos a una necesidad en «Necesidad creada» (CU-002, paso 4). None si no existe."""
    necesidad = sesion.get(Necesidad, necesidad_id, with_for_update=True)
    if necesidad is None:
        return None
    if necesidad.estado != "necesidad_creada":
        raise TransicionNoPermitida("Solo se añaden adjuntos en «Necesidad creada».")
    for adjunto in adjuntos:
        archivos.comprobar_tamano(adjunto.nombre, len(adjunto.datos))
    return _guardar_adjuntos(sesion, raiz_archivos, necesidad, adjuntos)


def actualizar(
    sesion: Session,
    necesidad_id: int,
    *,
    titulo: str | None,
    proyecto: str | None,
    descripcion: str | None,
    peticionario_id: int | None,
) -> Necesidad | None:
    """Corrige los datos del paso 1 mientras siga en «Necesidad creada» («Atrás» desde el
    paso 2). El código no cambia. None si la necesidad no existe."""
    necesidad = sesion.get(Necesidad, necesidad_id, with_for_update=True)
    if necesidad is None:
        return None
    if necesidad.estado != "necesidad_creada":
        raise TransicionNoPermitida(
            "Los datos solo se pueden cambiar en «Necesidad creada», antes de pedir ofertas."
        )
    titulo, proyecto, descripcion, peticionario = _validar_datos(
        sesion, titulo, proyecto, descripcion, peticionario_id
    )
    necesidad.titulo = titulo
    necesidad.proyecto = proyecto
    necesidad.descripcion = descripcion
    necesidad.peticionario = peticionario
    sesion.commit()
    return necesidad


def cancelar(
    sesion: Session, necesidad_id: int, *, peticionario_id: int | None, motivo: str | None
) -> Necesidad | None:
    """Cancela la necesidad con un motivo (obligatorio), desde cualquier estado salvo
    «Entregado» o «Cancelada». Se conserva todo el histórico. None si no existe."""
    necesidad = sesion.get(Necesidad, necesidad_id, with_for_update=True)
    if necesidad is None:
        return None
    if necesidad.estado in ("entregado", "cancelada"):
        raise TransicionNoPermitida("No se puede cancelar una necesidad entregada o ya cancelada.")
    motivo = _texto(motivo, "motivo", "Indica el motivo de la cancelación.")
    peticionario = peticionario_activo(sesion, peticionario_id, "Elige quién cancela la necesidad.")
    necesidad.historial.append(
        CambioEstado(
            estado_anterior=necesidad.estado, estado_nuevo="cancelada", peticionario=peticionario
        )
    )
    necesidad.estado = "cancelada"
    necesidad.motivo_cancelacion = motivo
    sesion.commit()
    return necesidad


def confirmar_pedido_en_sap(
    sesion: Session,
    necesidad_id: int,
    *,
    peticionario_id: int | None,
    fecha_entrega_prevista: date | None,
) -> Necesidad | None:
    """CU-006 — Confirma que el pedido está en SAP con la fecha de entrega prevista y pasa a
    «Pendiente pedido SAP». Cambiar aquí la fecha no cuenta como retraso. None si no existe."""
    necesidad = necesidad_en(sesion, necesidad_id, "pendiente_solicitud_sap", bloquear=True)
    if necesidad is None:
        return None
    if fecha_entrega_prevista is None:
        raise DatosNoValidos("fecha_entrega_prevista", "Indica la fecha de entrega prevista.")
    if fecha_entrega_prevista < necesidad.creada_en.date():
        raise DatosNoValidos(
            "fecha_entrega_prevista",
            "La fecha de entrega prevista no puede ser anterior a la creación de la necesidad.",
        )
    peticionario = peticionario_activo(sesion, peticionario_id, "Elige quién confirma el pedido.")
    necesidad.fecha_entrega_prevista = fecha_entrega_prevista
    necesidad.historial.append(
        CambioEstado(
            estado_anterior=necesidad.estado,
            estado_nuevo="pendiente_pedido_sap",
            peticionario=peticionario,
        )
    )
    necesidad.estado = "pendiente_pedido_sap"
    sesion.commit()
    return necesidad


def listar(sesion: Session) -> list[tuple[Necesidad, datetime | None]]:
    """CU-010: necesidades y fecha del último estado, sin cargar sus historiales."""
    estado_desde = (
        select(CambioEstado.cambiado_en)
        .where(CambioEstado.necesidad_id == Necesidad.id)
        .order_by(CambioEstado.id.desc())
        .limit(1)
        .correlate(Necesidad)
        .scalar_subquery()
    )
    consulta = (
        select(Necesidad, estado_desde)
        .options(
            joinedload(Necesidad.peticionario),
            joinedload(Necesidad.oferta_adjudicada).joinedload(Oferta.proveedor),
        )
        .order_by(Necesidad.codigo.desc())
    )
    return [(n, fecha) for n, fecha in sesion.execute(consulta)]


def obtener(sesion: Session, necesidad_id: int) -> Necesidad | None:
    return sesion.get(Necesidad, necesidad_id)


def obtener_adjunto(sesion: Session, necesidad_id: int, adjunto_id: int) -> Adjunto | None:
    adjunto = sesion.get(Adjunto, adjunto_id)
    if adjunto is None or adjunto.necesidad_id != necesidad_id:
        return None
    return adjunto
