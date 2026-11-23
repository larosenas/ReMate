"""Caducidad de los archivos y de la tabla `logs` (ADR 0014), para que ReMate ocupe lo mínimo en
el servidor.

Reglas:
- Solo necesidades cerradas («Entregado» o «Cancelada»), contando desde el día en que se
  cerraron (hora de España).
- Los adjuntos de la necesidad (planos, STEP…) se borran a los 24 meses: sirven para volver a
  pedir la misma pieza. Todo lo demás (correos y adjuntos de las ofertas, respuestas de los
  proveedores, `.eml` generados y el pedido SAP) a los 6 meses: los correos siguen en Outlook y
  el pedido en SAP.
- Se borra el archivo del disco y la fila se queda con `caducado_en`: la necesidad conserva sus
  datos (proveedor, precios, fechas, retrasos, comentarios) y la descarga responde 410.
- La tabla `logs` guarda 6 meses.
- Modo de prueba: solo cuenta lo que se borraría.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.fechas import ZONA
from app.integraciones import archivos
from app.modelos.logs import Log
from app.modelos.necesidades import Adjunto, Necesidad
from app.servicios.ofertas import _sumar_meses

log = logging.getLogger(__name__)
CERRADAS = ("entregado", "cancelada")
MESES_ADJUNTOS_NECESIDAD = 24
MESES_DOCUMENTOS = 6
MESES_LOGS = 6


@dataclass
class Resumen:
    archivos: int = 0
    bytes: int = 0
    logs: int = 0
    # Archivos que no se han podido borrar del disco (siguen marcados como caducados).
    no_borrados: int = 0
    # Caducados de días anteriores que seguían en el disco y se han borrado ahora.
    reintentados: int = 0


def cerrada_el(necesidad: Necesidad) -> date | None:
    """Día (hora de España) en que pasó a «Entregado» o «Cancelada»."""
    cierres = [c for c in necesidad.historial if c.estado_nuevo in CERRADAS]
    return cierres[-1].cambiado_en.astimezone(ZONA).date() if cierres else None


def meses_de(adjunto: Adjunto) -> int:
    return MESES_ADJUNTOS_NECESIDAD if adjunto.tipo == "necesidad" else MESES_DOCUMENTOS


def caducados(sesion: Session, hoy: date, bloquear: bool = False) -> list[Adjunto]:
    """Adjuntos de necesidades cerradas cuyo plazo ya ha pasado y que siguen en el disco. Con
    `bloquear`, las filas quedan bloqueadas hasta el commit y otra ejecución a la vez se las salta
    (si no, las dos contarían lo mismo)."""
    consulta = (
        select(Adjunto)
        .join(Necesidad, Adjunto.necesidad_id == Necesidad.id)
        .where(Necesidad.estado.in_(CERRADAS), Adjunto.caducado_en.is_(None))
        .order_by(Adjunto.id)
    )
    if bloquear:
        consulta = consulta.with_for_update(skip_locked=True, of=Adjunto)
    resultado = []
    for adjunto in sesion.scalars(consulta):
        cierre = cerrada_el(adjunto.necesidad)
        if cierre is not None and hoy >= _sumar_meses(cierre, meses_de(adjunto)):
            resultado.append(adjunto)
    return resultado


def _sigue_en_el_disco(raiz, ruta: str) -> bool:
    try:
        return archivos.ruta_absoluta(raiz, ruta).exists()
    except ValueError:
        return False


def _limite_logs(hoy: date) -> datetime:
    return datetime.combine(_sumar_meses(hoy, -MESES_LOGS), time(), tzinfo=ZONA).astimezone(UTC)


def caducar(sesion: Session, raiz_archivos, hoy: date, *, prueba: bool = False) -> Resumen:
    """Borra los archivos caducados y los `logs` antiguos (o, en prueba, solo los cuenta)."""
    resumen = Resumen()
    lista = caducados(sesion, hoy, bloquear=not prueba)
    resumen.archivos = len(lista)
    resumen.bytes = sum(a.tamano for a in lista)
    limite = _limite_logs(hoy)
    if prueba:
        resumen.logs = sesion.scalar(
            select(func.count()).select_from(Log).where(Log.creado_en < limite)
        )
        return resumen
    # Primero se anota y después se borra del disco: si el borrado falla, queda un archivo de
    # más (se avisa), nunca una fila que apunte a un archivo que ya no está.
    # Los de días anteriores que no se pudieron borrar (un archivo abierto en Windows) se vuelven a
    # intentar.
    pendientes = [
        (a.id, a.ruta)
        for a in sesion.scalars(select(Adjunto).where(Adjunto.caducado_en.is_not(None)))
        if _sigue_en_el_disco(raiz_archivos, a.ruta)
    ]
    rutas = [(a.id, a.ruta) for a in lista]
    ahora = datetime.now(UTC)
    for adjunto in lista:
        adjunto.caducado_en = ahora
    resumen.logs = sesion.execute(delete(Log).where(Log.creado_en < limite)).rowcount
    sesion.commit()
    for (adjunto_id, ruta), reintento in [
        *((r, False) for r in rutas),
        *((r, True) for r in pendientes),
    ]:
        try:
            archivos.borrar(raiz_archivos, ruta)
            resumen.reintentados += reintento
        except (OSError, ValueError) as error:
            resumen.no_borrados += 1
            log.warning(
                "No se ha podido borrar el archivo caducado del adjunto %s: %s",
                adjunto_id,
                type(error).__name__,
            )
    return resumen
