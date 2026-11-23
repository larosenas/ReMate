"""CU-008 — Registrar retrasos y confirmar la entrega.

Reglas (docs/casos-de-uso/CU-008-retrasos-y-entrega.md):
- Solo en «Pendiente entrega».
- Un retraso lleva motivo y una fecha posterior a la prevista, que pasa a ser la nueva prevista
  y vuelve a armar el recordatorio de CU-009.
- La entrega real no puede ser futura ni anterior a la creación de la necesidad. Si es posterior
  a la prevista, hace falta el motivo y se registra como un retraso más (histórico completo).
"""

from datetime import date

from sqlalchemy.orm import Session

from app import fechas
from app.modelos.necesidades import CambioEstado, Necesidad, Retraso
from app.servicios.listas import DatosNoValidos, peticionario_activo
from app.servicios.necesidades import necesidad_en

ESTADO = "pendiente_entrega"
# Largo máximo del comentario de la entrega.
MAXIMO_COMENTARIO = 1000


def _necesidad(sesion: Session, necesidad_id: int) -> Necesidad | None:
    # Bloqueo de la fila: dos peticiones a la vez no pueden pisarse la fecha ni el estado.
    return necesidad_en(sesion, necesidad_id, ESTADO, bloquear=True)


def _hoy() -> date:
    """Aparte para poder fijar «hoy» en las pruebas. En hora de España (`app/fechas.py`)."""
    return fechas.hoy()


def _fecha(dia: date) -> str:
    return dia.strftime("%d/%m/%Y")


def registrar_retraso(
    sesion: Session,
    necesidad_id: int,
    *,
    peticionario_id: int | None,
    fecha_nueva: date | None,
    motivo: str | None,
) -> Necesidad | None:
    """Guarda el retraso y mueve la fecha de entrega prevista. None si no existe."""
    necesidad = _necesidad(sesion, necesidad_id)
    if necesidad is None:
        return None
    prevista = necesidad.fecha_entrega_prevista
    if fecha_nueva is None:
        raise DatosNoValidos("fecha_nueva", "Indica la nueva fecha de entrega.")
    if fecha_nueva <= prevista:
        raise DatosNoValidos(
            "fecha_nueva",
            f"La nueva fecha tiene que ser posterior a la prevista ({_fecha(prevista)}).",
        )
    motivo = (motivo or "").strip()
    if not motivo:
        raise DatosNoValidos("motivo", "Indica el motivo del retraso.")
    peticionario = peticionario_activo(sesion, peticionario_id, "Elige quién registra el retraso.")
    necesidad.retrasos.append(
        Retraso(
            fecha_anterior=prevista,
            fecha_nueva=fecha_nueva,
            motivo=motivo,
            peticionario=peticionario,
        )
    )
    necesidad.fecha_entrega_prevista = fecha_nueva
    # CU-009: el recordatorio se vuelve a enviar respecto a la nueva fecha (ADR 0004).
    necesidad.recordatorio_enviado_en = None
    sesion.commit()
    return necesidad


def _comentario(texto: str | None) -> str | None:
    """Sin los espacios de los extremos (vacío, None), con el máximo contado después y sin
    el carácter nulo, que PostgreSQL no admite."""
    limpio = (texto or "").strip()
    if "\x00" in limpio:
        raise DatosNoValidos("comentario", "El comentario lleva un carácter no válido.")
    if len(limpio) > MAXIMO_COMENTARIO:
        raise DatosNoValidos(
            "comentario", f"El comentario no puede pasar de {MAXIMO_COMENTARIO} caracteres."
        )
    return limpio or None


def confirmar_entrega(
    sesion: Session,
    necesidad_id: int,
    *,
    peticionario_id: int | None,
    fecha_entrega_real: date | None,
    motivo_retraso: str | None = None,
    comentario: str | None = None,
) -> Necesidad | None:
    """Guarda la fecha real (hoy si no se indica) y pasa a «Entregado». None si no existe.
    `comentario`: opcional; vacío o solo espacios no se guarda."""
    necesidad = _necesidad(sesion, necesidad_id)
    if necesidad is None:
        return None
    # Se comprueba antes de tocar nada.
    comentario_limpio = _comentario(comentario)
    hoy = _hoy()
    real = fecha_entrega_real or hoy
    if real > hoy:
        raise DatosNoValidos("fecha_entrega_real", "La fecha de entrega no puede ser futura.")
    if real < necesidad.creada_en.date():
        raise DatosNoValidos(
            "fecha_entrega_real",
            "La fecha de entrega no puede ser anterior a la creación de la necesidad.",
        )
    peticionario = peticionario_activo(sesion, peticionario_id, "Elige quién confirma la entrega.")
    prevista = necesidad.fecha_entrega_prevista
    if real > prevista:
        motivo = (motivo_retraso or "").strip()
        if not motivo:
            raise DatosNoValidos(
                "motivo_retraso",
                f"Llega más tarde de lo previsto ({_fecha(prevista)}): indica el motivo del "
                "retraso.",
            )
        necesidad.retrasos.append(
            Retraso(
                fecha_anterior=prevista, fecha_nueva=real, motivo=motivo, peticionario=peticionario
            )
        )
        necesidad.fecha_entrega_prevista = real
    necesidad.fecha_entrega_real = real
    necesidad.comentario_entrega = comentario_limpio
    necesidad.historial.append(
        CambioEstado(
            estado_anterior=necesidad.estado, estado_nuevo="entregado", peticionario=peticionario
        )
    )
    necesidad.estado = "entregado"
    sesion.commit()
    return necesidad
