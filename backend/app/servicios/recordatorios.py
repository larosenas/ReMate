"""CU-009 — Recordatorio de entrega al peticionario una semana antes (ADR 0004).

Reglas (docs/casos-de-uso/CU-009-recordatorio-de-entrega.md):
- Necesidades en «Pendiente entrega» con la fecha prevista a 7 días o menos (también si ya pasó)
  y sin recordatorio enviado para esa fecha.
- Un retraso (CU-008) vacía `recordatorio_enviado_en` para avisar respecto a la nueva fecha.
- Si falla un envío, no se marca y se sigue con las demás; se reintentará al día siguiente.
- Modo de prueba: guarda los correos como `.eml` y no marca nada.
"""

import logging
import smtplib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Config
from app.integraciones import correo_saliente
from app.modelos.necesidades import Necesidad
from app.servicios.necesidades import asunto_correos

log = logging.getLogger(__name__)
DIAS_ANTES = 7
CARPETA_PRUEBA = "recordatorios-prueba"
REMITENTE_PRUEBA = "ReMate <remate@ejemplo.invalid>"


@dataclass
class Resumen:
    enviados: list[str] = field(default_factory=list)  # códigos de las necesidades
    fallidos: list[tuple[str, str]] = field(default_factory=list)  # (código, motivo)
    # Sin enviar a propósito: el peticionario está desactivado o eliminado (código, motivo).
    omitidos: list[tuple[str, str]] = field(default_factory=list)


def pendientes(sesion: Session, hoy: date) -> list[Necesidad]:
    consulta = (
        select(Necesidad)
        .where(
            Necesidad.estado == "pendiente_entrega",
            Necesidad.recordatorio_enviado_en.is_(None),
            Necesidad.fecha_entrega_prevista <= hoy + timedelta(days=DIAS_ANTES),
        )
        .order_by(Necesidad.fecha_entrega_prevista, Necesidad.codigo)
    )
    return list(sesion.scalars(consulta))


def _cuando(prevista: date, hoy: date) -> str:
    dias = (prevista - hoy).days
    if dias > 1:
        return f"dentro de {dias} días"
    if dias == 1:
        return "mañana"
    if dias == 0:
        return "hoy"
    return f"hace {-dias} día{'s' if dias < -1 else ''}: la fecha ya ha pasado"


def texto(config: Config, necesidad: Necesidad, hoy: date) -> tuple[str, str]:
    """Asunto y cuerpo del recordatorio (plantilla fija, sin IA)."""
    prevista = necesidad.fecha_entrega_prevista
    fecha = prevista.strftime("%d/%m/%Y")
    oferta = necesidad.oferta_adjudicada
    proveedor = f"{oferta.proveedor.nombre} ({oferta.proveedor.email})" if oferta else "—"
    enlace = (
        f"\nPuedes verla en ReMate: {config.app_url}/necesidades/{necesidad.id}\n"
        if config.app_url
        else ""
    )
    # El mismo asunto que los demás correos de la necesidad.
    asunto = asunto_correos(necesidad)
    cuerpo = (
        f"Hola, {necesidad.peticionario.nombre_completo}:\n\n"
        f"Te recordamos que el pedido de la necesidad «{necesidad.codigo} {necesidad.titulo}» "
        f"({necesidad.proyecto}) tiene la entrega prevista el {fecha} "
        f"({_cuando(prevista, hoy)}).\n\n"
        f"Proveedor: {proveedor}\n"
        f"Pedido SAP: {necesidad.numero_pedido_sap or 'sin número'}\n\n"
        "Si el proveedor avisa de un retraso, regístralo en ReMate; cuando llegue el pedido, "
        "confirma la entrega.\n"
        f"{enlace}\n"
        "Este correo lo envía ReMate automáticamente.\n"
    )
    return asunto, cuerpo


def enviar_recordatorios(
    sesion: Session, config: Config, hoy: date, *, prueba: bool = False
) -> Resumen:
    """Envía (o, en prueba, guarda como .eml) los recordatorios pendientes."""
    resumen = Resumen()
    necesidades = []
    for n in pendientes(sesion, hoy):
        # Si el peticionario ya no está (desactivado o eliminado), su buzón puede no existir: no se
        # envía y se avisa para que alguien se haga cargo.
        if not n.peticionario.activo or n.peticionario.eliminado_en is not None:
            resumen.omitidos.append(
                (n.codigo, f"el peticionario {n.peticionario.nombre_completo} está dado de baja")
            )
        else:
            necesidades.append(n)
    if not necesidades:
        return resumen
    remitente = config.smtp_from or REMITENTE_PRUEBA
    # Con cada mensaje van la fecha prevista de la que habla y su destinatario, para comprobarlos
    # antes de enviarlo.
    mensajes = [
        (
            n,
            (n.fecha_entrega_prevista, n.peticionario_id),
            correo_saliente.componer(remitente, n.peticionario.email, *texto(config, n, hoy)),
        )
        for n in necesidades
    ]
    if prueba:
        carpeta = Path(config.archivos_dir) / CARPETA_PRUEBA
        carpeta.mkdir(parents=True, exist_ok=True)
        for necesidad, _, mensaje in mensajes:
            (carpeta / f"{necesidad.codigo}.eml").write_bytes(mensaje.as_bytes())
            resumen.enviados.append(necesidad.codigo)
        return resumen

    with correo_saliente.conexion(config) as servidor:
        for necesidad, (prevista, peticionario_id), mensaje in mensajes:
            # Se vuelve a comprobar y se bloquea la fila: si mientras tanto se ha registrado un
            # retraso, se ha entregado, la ha avisado otra ejecución o ha pasado a otro
            # peticionario, no se envía. La fila queda
            # bloqueada hasta anotar el envío; el nuevo peticionario lo recibe en la próxima.
            vigente = sesion.scalars(
                select(Necesidad)
                .where(
                    Necesidad.id == necesidad.id,
                    Necesidad.estado == "pendiente_entrega",
                    Necesidad.recordatorio_enviado_en.is_(None),
                    Necesidad.fecha_entrega_prevista == prevista,
                    Necesidad.peticionario_id == peticionario_id,
                )
                .with_for_update(skip_locked=True)
            ).first()
            if vigente is None:
                sesion.rollback()
                continue
            try:
                servidor.send_message(mensaje)
            except (OSError, smtplib.SMTPException) as error:
                # Sin datos del correo en el log: solo la necesidad y el tipo de error.
                log.error(
                    "Recordatorio de %s no enviado: %s", necesidad.codigo, type(error).__name__
                )
                # Sin el texto del error: puede llevar el correo del peticionario y la salida del
                # comando acaba en el log del planificador.
                codigo = getattr(error, "smtp_code", None)
                resumen.fallidos.append(
                    (necesidad.codigo, type(error).__name__ + (f" ({codigo})" if codigo else ""))
                )
                sesion.rollback()
                continue
            # Se guarda tras cada envío: si el proceso se corta, no se repiten los ya enviados.
            necesidad.recordatorio_enviado_en = datetime.now(UTC)
            sesion.commit()
            resumen.enviados.append(necesidad.codigo)
    return resumen
