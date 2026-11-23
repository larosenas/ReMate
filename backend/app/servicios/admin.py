"""Operaciones del modo admin (ADR 0015). Solo las usa el administrador; cada una queda en `logs`.

- Borrar una necesidad de verdad, con todo lo suyo (ofertas, partidas, adjuntos y sus archivos,
  historial, retrasos, cambios de peticionario y proveedores solicitados).
- Deshacer el último paso: vuelve al estado anterior, quita lo que guardó ese paso y borra su
  línea del historial.
- Corregir datos que la aplicación ya no deja tocar.
- Estado del servidor y registros, para no tener que entrar con DBeaver.
"""

import contextlib
import logging
import os
import re
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import fechas
from app.integraciones import archivos
from app.modelos.logs import Log
from app.modelos.necesidades import (
    ESTADOS,
    Adjunto,
    CambioEstado,
    CambioPeticionario,
    CodigoBorrado,
    Necesidad,
    ProveedorSolicitado,
    Retraso,
)
from app.modelos.ofertas import LineaOferta, Oferta
from app.servicios.entrega import _comentario
from app.servicios.listas import DatosNoValidos

log = logging.getLogger(__name__)

# Lo que guarda cada paso y se quita al deshacerlo: tipos de adjunto y campos de la necesidad.
DESHACER = {
    "en_cotizacion": (("solicitud",), ("motivo_pocos_proveedores",)),
    "en_evaluacion": ((), ()),
    "pendiente_solicitud_sap": (
        ("adjudicacion",),
        ("oferta_adjudicada_id", "texto_sap", "fecha_entrega_inicial"),
    ),
    "pendiente_pedido_sap": ((), ("fecha_entrega_prevista", "aviso_pedido_sap_en")),
    "pendiente_entrega": (
        ("pedido_sap", "envio_pedido"),
        ("numero_pedido_sap", "recordatorio_enviado_en"),
    ),
    "entregado": ((), ("fecha_entrega_real", "comentario_entrega")),
    "cancelada": ((), ("motivo_cancelacion",)),
}
MAXIMO_NUMERO_PEDIDO = 50


def _borrar_del_disco(raiz: Path, rutas: list[str]) -> int:
    """Borra los archivos (después del commit). Devuelve cuántos no se han podido borrar."""
    fallos = 0
    for ruta in rutas:
        try:
            archivos.borrar(raiz, ruta)
        except (OSError, ValueError) as error:
            fallos += 1
            log.warning("Modo admin: no se ha podido borrar un archivo: %s", type(error).__name__)
    return fallos


def _quitar_carpetas_vacias(raiz: Path, codigo: str) -> None:
    carpeta = (raiz / codigo).resolve()
    if not carpeta.is_relative_to(raiz.resolve()) or carpeta == raiz.resolve():
        return
    for actual, _, _ in sorted(os.walk(carpeta), key=lambda c: len(c[0]), reverse=True):
        # Solo se quitan las vacías; si no lo está o ya no existe, se deja.
        with contextlib.suppress(OSError):
            Path(actual).rmdir()


def borrar_necesidad(sesion: Session, raiz: Path, necesidad_id: int, codigo: str) -> dict | None:
    """Borra la necesidad y todo lo suyo. `codigo` tiene que coincidir (confirmación). None si no
    existe."""
    necesidad = sesion.get(Necesidad, necesidad_id, with_for_update=True)
    if necesidad is None:
        return None
    if (codigo or "").strip() != necesidad.codigo:
        raise DatosNoValidos("codigo", "Escribe el código de la necesidad para confirmar.")
    codigo = necesidad.codigo
    rutas = [a.ruta for a in necesidad.adjuntos]
    ofertas = select(Oferta.id).where(Oferta.necesidad_id == necesidad_id)
    # Necesidades y ofertas se referencian entre sí: primero se suelta la oferta adjudicada.
    necesidad.oferta_adjudicada_id = None
    sesion.flush()
    for consulta in (
        delete(Retraso).where(Retraso.necesidad_id == necesidad_id),
        delete(CambioEstado).where(CambioEstado.necesidad_id == necesidad_id),
        delete(CambioPeticionario).where(CambioPeticionario.necesidad_id == necesidad_id),
        delete(ProveedorSolicitado).where(ProveedorSolicitado.necesidad_id == necesidad_id),
        delete(LineaOferta).where(LineaOferta.oferta_id.in_(ofertas)),
        delete(Adjunto).where(Adjunto.necesidad_id == necesidad_id),
        delete(Oferta).where(Oferta.necesidad_id == necesidad_id),
        delete(Necesidad).where(Necesidad.id == necesidad_id),
    ):
        sesion.execute(consulta)
    # El código no se vuelve a usar: los correos ya enviados con él apuntarían a otra necesidad.
    sesion.add(CodigoBorrado(codigo=codigo))
    sesion.commit()
    no_borrados = _borrar_del_disco(raiz, rutas)
    _quitar_carpetas_vacias(raiz, codigo)
    log.warning("Modo admin: necesidad %s borrada (%s archivos)", codigo, len(rutas))
    return {"codigo": codigo, "archivos": len(rutas), "no_borrados": no_borrados}


def paso_a_deshacer(necesidad: Necesidad) -> CambioEstado | None:
    """La última línea del historial, si lleva al estado actual y se puede deshacer."""
    if not necesidad.historial:
        return None
    ultimo = necesidad.historial[-1]
    if ultimo.estado_nuevo != necesidad.estado or ultimo.estado_anterior is None:
        return None
    if necesidad.estado not in DESHACER:
        return None
    return ultimo


class EstadoCambiado(Exception):
    """La necesidad ya no está en el estado que se quería deshacer (otro «deshacer» a la vez o
    un reintento)."""


def _quitar_retraso_de_la_entrega(
    sesion: Session, necesidad: Necesidad, cambio: CambioEstado
) -> None:
    """Si la entrega se confirmó tarde, `confirmar_entrega` registró un retraso (con el motivo) y
    movió la prevista a la fecha real, en la misma transacción que el cambio a «Entregado»: tienen
    la misma hora. Se quita ese retraso y vuelve la prevista anterior; los registrados antes se
    quedan."""
    de_la_entrega = [
        r
        for r in necesidad.retrasos
        if r.registrado_en == cambio.cambiado_en and r.fecha_nueva == necesidad.fecha_entrega_real
    ]
    for retraso in de_la_entrega:
        necesidad.fecha_entrega_prevista = retraso.fecha_anterior
        necesidad.retrasos.remove(retraso)
        sesion.delete(retraso)


def deshacer(
    sesion: Session, raiz: Path, necesidad_id: int, estado_esperado: str
) -> Necesidad | None:
    """Vuelve al estado anterior y quita lo que guardó ese paso. `estado_esperado`: el estado en
    el que la ve quien deshace; si ya no lo es, EstadoCambiado (así, dos a la
    vez no deshacen dos pasos). None si no existe."""
    necesidad = sesion.get(Necesidad, necesidad_id, with_for_update=True)
    if necesidad is None:
        return None
    if necesidad.estado != estado_esperado:
        sesion.rollback()
        raise EstadoCambiado(
            f"La necesidad ya está en «{ESTADOS.get(necesidad.estado, necesidad.estado)}»: vuelve "
            "a buscarla antes de deshacer."
        )
    ultimo = paso_a_deshacer(necesidad)
    if ultimo is None:
        raise DatosNoValidos("estado", "Esta necesidad no tiene ningún paso que deshacer.")
    # Solo las ofertas que no se han borrado (borrar una solo cambia su estado).
    if necesidad.estado == "en_cotizacion" and sesion.scalar(
        select(func.count()).where(
            Oferta.necesidad_id == necesidad_id, Oferta.estado_oferta != "borrada"
        )
    ):
        raise DatosNoValidos(
            "estado", "Ya tiene ofertas: bórralas antes de deshacer la solicitud de ofertas."
        )
    tipos, campos = DESHACER[necesidad.estado]
    quitar = [a for a in necesidad.adjuntos if a.tipo in tipos]
    rutas = [a.ruta for a in quitar if a.caducado_en is None]
    for adjunto in quitar:
        necesidad.adjuntos.remove(adjunto)
        sesion.delete(adjunto)
    if necesidad.estado == "entregado":
        _quitar_retraso_de_la_entrega(sesion, necesidad, ultimo)
    for campo in campos:
        setattr(necesidad, campo, None)
    if necesidad.estado == "en_cotizacion":
        sesion.execute(
            delete(ProveedorSolicitado).where(ProveedorSolicitado.necesidad_id == necesidad_id)
        )
    antes, despues = necesidad.estado, ultimo.estado_anterior
    necesidad.estado = despues
    necesidad.historial.remove(ultimo)
    sesion.delete(ultimo)
    sesion.commit()
    _borrar_del_disco(raiz, rutas)
    log.warning(
        "Modo admin: necesidad %s, deshecho el paso «%s» → «%s»",
        necesidad.codigo,
        ESTADOS[despues],
        ESTADOS[antes],
    )
    return necesidad


# En qué estados existe cada dato que se puede corregir (aceptarlos en cualquiera saltaría las
# reglas del flujo).
CON_PREVISTA = ("pendiente_pedido_sap", "pendiente_entrega", "entregado")
CON_PEDIDO = ("pendiente_entrega", "entregado")


def _numero_pedido(texto: str | None) -> str | None:
    """Como en el flujo normal (CU-007): espacios juntados, sin el carácter nulo."""
    numero = " ".join((texto or "").split()) or None
    if numero and "\x00" in numero:
        raise DatosNoValidos(
            "numero_pedido_sap", "El número de pedido lleva un carácter no válido."
        )
    if numero and len(numero) > MAXIMO_NUMERO_PEDIDO:
        raise DatosNoValidos("numero_pedido_sap", "El número de pedido es demasiado largo.")
    return numero


def corregir(sesion: Session, necesidad_id: int, cambios: dict) -> Necesidad | None:
    """Corrige datos que la aplicación ya no deja tocar, con las reglas del flujo normal (CU-006 a
    CU-008): la fecha prevista desde el paso 5, el número de pedido desde el 6 y la fecha real y el
    comentario en una entregada. None si no existe."""
    necesidad = sesion.get(Necesidad, necesidad_id, with_for_update=True)
    if necesidad is None:
        return None
    if not cambios:
        raise DatosNoValidos("cambios", "No hay nada que corregir.")
    estado, creada = necesidad.estado, necesidad.creada_en.date()
    for campo, estados in (
        ("fecha_entrega_prevista", CON_PREVISTA),
        ("numero_pedido_sap", CON_PEDIDO),
        ("fecha_entrega_real", ("entregado",)),
        ("comentario_entrega", ("entregado",)),
    ):
        if campo in cambios and estado not in estados:
            raise DatosNoValidos(
                campo, f"En «{ESTADOS[estado]}» la necesidad todavía no tiene este dato."
            )
    if "fecha_entrega_prevista" in cambios:
        prevista = cambios["fecha_entrega_prevista"]
        if prevista is None:
            raise DatosNoValidos("fecha_entrega_prevista", "Indica la fecha de entrega prevista.")
        if prevista < creada:
            raise DatosNoValidos(
                "fecha_entrega_prevista",
                "La fecha prevista no puede ser anterior a la creación de la necesidad.",
            )
        if prevista != necesidad.fecha_entrega_prevista:
            necesidad.fecha_entrega_prevista = prevista
            # Como al registrar un retraso: el recordatorio se envía respecto a la fecha nueva.
            necesidad.recordatorio_enviado_en = None
    if "fecha_entrega_real" in cambios:
        real = cambios["fecha_entrega_real"]
        if real is None:
            raise DatosNoValidos("fecha_entrega_real", "Una necesidad entregada necesita fecha.")
        if real > fechas.hoy():
            raise DatosNoValidos("fecha_entrega_real", "La fecha de entrega no puede ser futura.")
        if real < creada:
            raise DatosNoValidos(
                "fecha_entrega_real",
                "La fecha de entrega no puede ser anterior a la creación de la necesidad.",
            )
        necesidad.fecha_entrega_real = real
    if estado == "entregado" and necesidad.fecha_entrega_real > necesidad.fecha_entrega_prevista:
        raise DatosNoValidos(
            "fecha_entrega_real",
            "La fecha en que llegó es posterior a la prevista: sería un retraso sin registrar. "
            "Corrige también la fecha prevista.",
        )
    if "numero_pedido_sap" in cambios:
        necesidad.numero_pedido_sap = _numero_pedido(cambios["numero_pedido_sap"])
    if "comentario_entrega" in cambios:
        try:
            necesidad.comentario_entrega = _comentario(cambios["comentario_entrega"])
        except DatosNoValidos as error:
            raise DatosNoValidos("comentario_entrega", str(error)) from None
    sesion.commit()
    log.warning(
        "Modo admin: necesidad %s corregida (%s)", necesidad.codigo, ", ".join(sorted(cambios))
    )
    return necesidad


_TOKENS = re.compile(r"^OpenAI .*: entrada=(\d+), salida=(\d+)")


def _ultima_copia(copias_dir: Path | None) -> dict | None:
    """None sin COPIAS_DIR; `accesible: false` si está configurada pero no se puede leer (no
    existe, es un archivo, sin permisos o una unidad de red caída)."""
    if copias_dir is None:
        return None
    patron = re.compile(r"remate-\d{8}-\d{6}")
    try:
        copias = sorted(
            (c for c in copias_dir.iterdir() if c.is_dir() and patron.fullmatch(c.name)),
            reverse=True,
        )
        completa = bool(copias) and (copias[0] / ".remate-copia-completa").is_file()
    except OSError:
        return {"carpeta": None, "completa": False, "accesible": False}
    return {
        "carpeta": copias[0].name if copias else None,
        "completa": completa,
        "accesible": True,
    }


def estado(sesion: Session, raiz: Path, copias_dir: Path | None) -> dict:
    """Lo que antes solo se veía con DBeaver o en el servidor."""
    por_estado = dict(
        sesion.execute(select(Necesidad.estado, func.count()).group_by(Necesidad.estado)).all()
    )
    vigentes = sesion.execute(
        select(func.count(), func.coalesce(func.sum(Adjunto.tamano), 0)).where(
            Adjunto.caducado_en.is_(None)
        )
    ).one()
    hace_30 = datetime.now(UTC) - timedelta(days=30)
    hace_7 = datetime.now(UTC) - timedelta(days=7)
    entrada = salida = llamadas = 0
    for mensaje in sesion.scalars(
        select(Log.mensaje).where(Log.creado_en >= hace_30, Log.mensaje.like("OpenAI %"))
    ):
        if m := _TOKENS.match(mensaje):
            llamadas += 1
            entrada += int(m.group(1))
            salida += int(m.group(2))
    problemas = sesion.scalar(
        select(func.count()).where(Log.creado_en >= hace_7, Log.nivel.in_(("WARNING", "ERROR")))
    )
    try:
        disco = shutil.disk_usage(raiz)
        libre = {"total": disco.total, "libre": disco.free}
    except OSError:
        libre = None
    return {
        "necesidades": {codigo: por_estado.get(codigo, 0) for codigo in ESTADOS},
        "archivos": {"cantidad": vigentes[0], "bytes": int(vigentes[1])},
        "disco": libre,
        "ultima_copia": _ultima_copia(copias_dir),
        "ia_30_dias": {"llamadas": llamadas, "entrada": entrada, "salida": salida},
        "avisos_y_errores_7_dias": problemas,
    }


NIVELES = ("INFO", "WARNING", "ERROR", "CRITICAL")


def registros(sesion: Session, nivel: str | None, limite: int) -> list[Log]:
    """Los últimos mensajes de `logs`, del más reciente al más antiguo; con `nivel`, ese nivel y
    los más graves."""
    consulta = select(Log).order_by(Log.id.desc()).limit(limite)
    if nivel:
        consulta = consulta.where(Log.nivel.in_(NIVELES[NIVELES.index(nivel) :]))
    return list(sesion.scalars(consulta))
