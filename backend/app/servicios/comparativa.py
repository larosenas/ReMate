"""CU-004 — «Analizar y comparar» y mejor y peor valor de la comparativa (paso 9).

«Analizar y comparar»: con todas las ofertas subidas, pasa la necesidad a
«En evaluación» y la IA lee a la vez las que faltan. En «En evaluación» vuelve a hacerlo con las que
lleguen después.

Mejor y peor valor: en verde el
mejor y en rojo el peor precio, plazo de entrega y retrasos del proveedor. Lo calcula el código
(ADR 0011), no se guarda y solo se hace con **todas** las ofertas vigentes revisadas: si llega
otra, las marcas se quitan hasta revisarla y entonces se vuelven a calcular. No elige ni recomienda;
decide el ingeniero (CU-005).
"""

import threading
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Config
from app.modelos.necesidades import Necesidad
from app.modelos.ofertas import Oferta
from app.servicios import ofertas as servicio_ofertas
from app.servicios.necesidades import TransicionNoPermitida

# Necesidades que se están analizando ahora: un segundo «Analizar y comparar» (otra pestaña u otra
# persona) no vuelve a leer las mismas ofertas con la IA mientras dura el primero. Basta con un
# registro en memoria porque ReMate se ejecuta en un solo proceso (Waitress, con hilos; ADR 0006).
_analizando: set[int] = set()
_cerrojo = threading.Lock()

CAMPOS_DESTACADOS = ("importe", "entrega", "retrasos")


def _mejor_y_peor(valores: dict[int, object]) -> dict[int, str]:
    """{oferta_id: "mejor" | "peor"} con el menor valor como mejor. Solo si hay al menos dos valores
    distintos: si todas cuestan o entregan igual, ninguna destaca. En un empate se marcan todas las
    empatadas. Las ofertas sin el dato no se marcan (un dato que falta no es peor)."""
    con_dato = {i: v for i, v in valores.items() if v is not None}
    if len(set(con_dato.values())) < 2:
        return {}
    menor, mayor = min(con_dato.values()), max(con_dato.values())
    return {
        i: "mejor" if v == menor else "peor" for i, v in con_dato.items() if v in (menor, mayor)
    }


def importes_comparables(ofertas: list[Oferta]) -> dict[int, Decimal | None] | None:
    """{oferta_id: importe sin IVA}, o None si las ofertas están en monedas distintas: no se
    comparan (ADR 0010). La usan la comparativa y la adjudicación (`frente_a_las_demas`)."""
    if len({o.moneda for o in ofertas}) > 1:
        return None
    return {o.id: o.importe_sin_iva for o in ofertas}


def es_la_mejor(oferta_id: int, valores: dict[int, object]) -> bool:
    """La oferta tiene el menor valor (o empata con el menor). Misma regla que la comparativa."""
    if valores.get(oferta_id) is None:
        return False
    marcas = _mejor_y_peor(valores)
    return not marcas or marcas.get(oferta_id) == "mejor"


def _retraso_medio_exacto(datos: dict) -> Fraction | None:
    if not datos["pedidos"]:
        return None
    return Fraction(datos["dias_retraso"], datos["pedidos"])


def destacados(
    comparadas: list[Oferta], vigentes: list[Oferta], historial: dict[int, dict]
) -> dict[int, dict[str, str | None]]:
    """Mejor y peor valor de cada oferta de la comparativa: {oferta_id: {importe, entrega,
    retrasos}}, cada uno "mejor", "peor" o None. Todo None si alguna oferta vigente (aunque esté
    sin analizar) no está revisada. `historial`: el de cada proveedor (`historico.resumenes`)."""
    marcas = {o.id: dict.fromkeys(CAMPOS_DESTACADOS) for o in comparadas}
    if not comparadas or not all(o.revisada for o in vigentes):
        return marcas
    comparables = importes_comparables(comparadas)
    importes = _mejor_y_peor(comparables) if comparables is not None else {}
    entregas = _mejor_y_peor({o.id: o.fecha_entrega_estimada for o in comparadas})
    # Los proveedores sin pedidos anteriores no tienen retraso medio: no se comparan. Se compara
    # sin redondear.
    retrasos = _mejor_y_peor(
        {o.id: _retraso_medio_exacto(historial[o.proveedor_id]) for o in comparadas}
    )
    for oferta_id, valores in marcas.items():
        valores["importe"] = importes.get(oferta_id)
        valores["entrega"] = entregas.get(oferta_id)
        valores["retrasos"] = retrasos.get(oferta_id)
    return marcas


def analizar_y_comparar(
    sesion: Session,
    config: Config,
    raiz_archivos: Path,
    necesidad_id: int,
    peticionario_id: int | None,
) -> dict | None:
    """{necesidad, avisos}. En «En cotización» pasa antes a «En evaluación» (hace falta quién y al
    menos una oferta); después, la IA lee las ofertas pendientes. La comparativa se pide aparte."""
    with _cerrojo:
        if necesidad_id in _analizando:
            raise TransicionNoPermitida(
                "Ya se están analizando las ofertas de esta necesidad: espera a que termine."
            )
        _analizando.add(necesidad_id)
    try:
        return _analizar_y_comparar(sesion, config, raiz_archivos, necesidad_id, peticionario_id)
    finally:
        with _cerrojo:
            _analizando.discard(necesidad_id)


def _analizar_y_comparar(
    sesion: Session,
    config: Config,
    raiz_archivos: Path,
    necesidad_id: int,
    peticionario_id: int | None,
) -> dict | None:
    # Con bloqueo: si otra petición acaba de cambiar el estado, se lee el nuevo (sin
    # él se guardarían dos cambios a «En evaluación»).
    necesidad = sesion.get(Necesidad, necesidad_id, with_for_update=True, populate_existing=True)
    if necesidad is None:
        return None
    if necesidad.estado == "en_cotizacion":
        necesidad = servicio_ofertas.pasar_a_evaluacion(sesion, necesidad_id, peticionario_id)
    elif necesidad.estado != "en_evaluacion":
        raise TransicionNoPermitida(
            "Las ofertas solo se analizan en «En cotización» o «En evaluación»."
        )
    avisos = servicio_ofertas.analizar_pendientes(sesion, config, raiz_archivos, necesidad_id)
    sesion.refresh(necesidad)
    return {"necesidad": necesidad, "avisos": avisos}
