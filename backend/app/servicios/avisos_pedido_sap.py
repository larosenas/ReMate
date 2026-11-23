"""Aviso del paso 5 (pedido en SAP) a los avisados del pedido SAP.

Reglas (docs/casos-de-uso/CU-006-confirmar-pedido-en-sap.md):
- Al confirmar el paso 5 (CU-006: la necesidad pasa a «Pendiente pedido SAP») se envía en el
  momento un correo a los avisados activos de la lista «Avisados del pedido SAP».
- Mientras siga en el paso 5 (sin enviar el pedido al proveedor, paso 6), cada 7 días un
  recordatorio a los mismos. Lo envía la tarea diaria, junto con el recordatorio de entrega.
- `aviso_pedido_sap_en` guarda el último envío. Si falla, no se cambia: la tarea diaria lo
  reintenta (también el primer aviso). Sin avisados activos no se envía ni se marca nada.
- Modo de prueba: guarda los correos como `.eml` y no marca nada.
"""

import logging
import smtplib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.fechas import ZONA
from app.integraciones import correo_saliente
from app.modelos.listas import AvisadoPedidoSap
from app.modelos.necesidades import Necesidad
from app.servicios import listas
from app.servicios.necesidades import asunto_correos

log = logging.getLogger(__name__)
ESTADO = "pendiente_pedido_sap"
DIAS_ENTRE_AVISOS = 7
CARPETA_PRUEBA = "recordatorios-prueba"
REMITENTE_PRUEBA = "ReMate <remate@ejemplo.invalid>"
AVISO_NO_ENVIADO = (
    "No se ha podido avisar a los avisados del pedido SAP: se reintentará mañana con la tarea "
    "diaria."
)
AVISO_SIN_AVISADOS = (
    "No hay nadie en la lista «Avisados del pedido SAP»: no se ha enviado el aviso del paso 5. "
    "Añádelos en «Proveedores y peticionarios»."
)

AVISO_RECHAZADOS = (
    "El servidor de correo ha rechazado alguna dirección de la lista «Avisados del pedido SAP»: "
    "revisa la lista (los demás sí lo han recibido)."
)


@dataclass
class Resumen:
    enviados: list[str] = field(default_factory=list)  # códigos de las necesidades
    fallidos: list[tuple[str, str]] = field(default_factory=list)  # (código, motivo)
    # Enviados, pero el servidor rechazó a algún destinatario (código, motivo sin correos).
    rechazados: list[tuple[str, str]] = field(default_factory=list)
    sin_avisados: bool = False


def _dia(momento: datetime) -> date:
    return momento.astimezone(ZONA).date()


def en_paso_5_desde(necesidad: Necesidad) -> date | None:
    """Día (hora de España) en que la necesidad entró en el paso 5."""
    cambios = [c for c in necesidad.historial if c.estado_nuevo == ESTADO]
    return _dia(cambios[-1].cambiado_en) if cambios else None


def toca(necesidad: Necesidad, hoy: date) -> bool:
    """Sin aviso todavía, o el último hace 7 días o más."""
    ultimo = necesidad.aviso_pedido_sap_en
    return ultimo is None or (hoy - _dia(ultimo)).days >= DIAS_ENTRE_AVISOS


def texto(config: Config, necesidad: Necesidad, hoy: date) -> tuple[str, str]:
    """Asunto y cuerpo (plantilla fija, sin IA). El primero es el aviso; los siguientes, el
    recordatorio semanal."""
    oferta = necesidad.oferta_adjudicada
    proveedor = f"{oferta.proveedor.nombre} ({oferta.proveedor.email})" if oferta else "—"
    prevista = necesidad.fecha_entrega_prevista
    confirmado = [c for c in necesidad.historial if c.estado_nuevo == ESTADO]
    quien = confirmado[-1].peticionario.nombre_completo if confirmado else "—"
    nombre = f"«{necesidad.codigo} {necesidad.titulo}» ({necesidad.proyecto})"
    if necesidad.aviso_pedido_sap_en is None:
        inicio = (
            f"Se ha metido en SAP la solicitud de compra de la necesidad {nombre}. Queda "
            "pendiente el pedido en SAP y enviarlo al proveedor (paso 6 en ReMate).\n\n"
        )
    else:
        desde = en_paso_5_desde(necesidad) or hoy
        dias = (hoy - desde).days
        inicio = (
            f"Recordatorio: la necesidad {nombre} sigue pendiente del pedido en SAP desde el "
            f"{desde:%d/%m/%Y} ({dias} día{'' if dias == 1 else 's'}). Cuando esté el pedido, "
            "hay que enviarlo al proveedor (paso 6 en ReMate).\n\n"
        )
    enlace = (
        f"\nPuedes verla en ReMate: {config.app_url}/necesidades/{necesidad.id}\n"
        if config.app_url
        else ""
    )
    fecha = f"Fecha de entrega prevista: {prevista:%d/%m/%Y}\n" if prevista else ""
    cuerpo = (
        f"Hola:\n\n{inicio}"
        f"Proveedor adjudicado: {proveedor}\n"
        f"{fecha}"
        f"Peticionario: {necesidad.peticionario.nombre_completo}\n"
        f"Paso 5 confirmado por: {quien}\n"
        f"{enlace}\n"
        "Este correo lo envía ReMate automáticamente.\n"
    )
    return asunto_correos(necesidad), cuerpo


def _mensaje(config: Config, necesidad: Necesidad, para: list[str], hoy: date):
    remitente = config.smtp_from or REMITENTE_PRUEBA
    return correo_saliente.componer(remitente, ", ".join(para), *texto(config, necesidad, hoy))


def _vigente(sesion: Session, necesidad_id: int, hoy: date) -> Necesidad | None:
    """Se vuelve a leer de la base de datos y se bloquea la fila hasta anotar el envío: si
    mientras tanto ha pasado al paso 6, se ha cancelado o la ha avisado otra ejecución, no se
    envía. Se comprueba con lo que hay ahora en la fila, no con lo leído antes (tras un
    rollback se recargaría el valor de la otra ejecución y se enviaría dos veces)."""
    vigente = sesion.scalars(
        select(Necesidad)
        .where(Necesidad.id == necesidad_id, Necesidad.estado == ESTADO)
        .with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    ).first()
    return vigente if vigente is not None and toca(vigente, hoy) else None


def _enviar(
    sesion: Session,
    servidor,
    config: Config,
    necesidad_id: int,
    para: list[str],
    hoy: date,
    resumen: Resumen,
) -> None:
    vigente = _vigente(sesion, necesidad_id, hoy)
    if vigente is None:
        sesion.rollback()
        return
    codigo = vigente.codigo
    # El texto se compone con la fila ya bloqueada: primer aviso o recordatorio según lo que hay.
    mensaje = _mensaje(config, vigente, para, hoy)
    try:
        rechazados = servidor.send_message(mensaje)
    except (OSError, smtplib.SMTPException) as error:
        # Sin datos del correo en el log: solo la necesidad y el tipo de error.
        log.error("Aviso del pedido SAP de %s no enviado: %s", codigo, type(error).__name__)
        error_smtp = getattr(error, "smtp_code", None)
        resumen.fallidos.append(
            (codigo, type(error).__name__ + (f" ({error_smtp})" if error_smtp else ""))
        )
        sesion.rollback()
        return
    vigente.aviso_pedido_sap_en = datetime.now(UTC)
    sesion.commit()
    resumen.enviados.append(codigo)
    # Con varios en el «Para», el servidor puede rechazar a alguno y aceptar a los demás sin
    # lanzar excepción: se anota cuántos, sin sus correos.
    if rechazados:
        n = len(rechazados)
        motivo = f"{n} destinatario{'' if n == 1 else 's'} rechazado{'' if n == 1 else 's'}"
        log.warning("Aviso del pedido SAP de %s: %s", codigo, motivo)
        resumen.rechazados.append((codigo, motivo))


def avisar_al_entrar(sesion: Session, config: Config, necesidad_id: int, hoy: date) -> str | None:
    """Primer aviso, al confirmar el paso 5. Devuelve un aviso para la pantalla si no se ha
    podido enviar (la tarea diaria lo reintenta) o None."""
    para = [a.email for a in listas.listar(sesion, AvisadoPedidoSap)]
    if not para:
        return AVISO_SIN_AVISADOS
    resumen = Resumen()
    try:
        with correo_saliente.conexion(config) as servidor:
            _enviar(sesion, servidor, config, necesidad_id, para, hoy, resumen)
    except correo_saliente.ErrorCorreo as error:
        sesion.rollback()
        log.error("Aviso del pedido SAP de la necesidad %s no enviado: %s", necesidad_id, error)
        return AVISO_NO_ENVIADO
    if resumen.fallidos:
        return AVISO_NO_ENVIADO
    if resumen.rechazados:
        return AVISO_RECHAZADOS
    return None


def pendientes(sesion: Session, hoy: date) -> list[Necesidad]:
    consulta = select(Necesidad).where(Necesidad.estado == ESTADO).order_by(Necesidad.codigo)
    return [n for n in sesion.scalars(consulta) if toca(n, hoy)]


def enviar_pendientes(
    sesion: Session, config: Config, hoy: date, *, prueba: bool = False
) -> Resumen:
    """Tarea diaria: primeros avisos que fallaron y recordatorios semanales (o, en prueba, los
    guarda como .eml)."""
    resumen = Resumen()
    necesidades = pendientes(sesion, hoy)
    if not necesidades:
        return resumen
    para = [a.email for a in listas.listar(sesion, AvisadoPedidoSap)]
    if not para:
        resumen.sin_avisados = True
        return resumen
    if prueba:
        carpeta = Path(config.archivos_dir) / CARPETA_PRUEBA
        carpeta.mkdir(parents=True, exist_ok=True)
        for necesidad in necesidades:
            mensaje = _mensaje(config, necesidad, para, hoy)
            (carpeta / f"{necesidad.codigo}-pedido-sap.eml").write_bytes(mensaje.as_bytes())
            resumen.enviados.append(necesidad.codigo)
        return resumen
    ids = [n.id for n in necesidades]
    with correo_saliente.conexion(config) as servidor:
        for necesidad_id in ids:
            _enviar(sesion, servidor, config, necesidad_id, para, hoy, resumen)
    return resumen
