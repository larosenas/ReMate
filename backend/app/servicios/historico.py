"""CU-010 — Histórico de retrasos por proveedor.

Un pedido es una necesidad adjudicada al proveedor (con oferta adjudicada), aunque después se
cancelara. Los días de un retraso son la diferencia entre la fecha nueva y la anterior (CU-008).

Lo que cuenta es el retraso real: si el pedido ya llegó, los
días entre la fecha prevista original y la de llegada. Si llegó el día previsto o antes, los
retrasos avisados quedan «sin efecto» y el pedido cuenta sin retraso. Si aún no ha llegado, cuenta
lo avisado.

Para comparar proveedores cuentan el retraso medio y la proporción de pedidos con retraso.
El retraso medio son los días de retraso entre todos los pedidos del proveedor, también los que
llegaron a tiempo.
"""

from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modelos.listas import Proveedor
from app.modelos.necesidades import Necesidad, Retraso
from app.modelos.ofertas import Oferta


def _pedidos(sesion: Session, proveedor_ids: list[int]) -> list[Necesidad]:
    consulta = (
        select(Necesidad)
        .join(Oferta, Necesidad.oferta_adjudicada_id == Oferta.id)
        .where(Oferta.proveedor_id.in_(proveedor_ids))
    )
    return list(sesion.scalars(consulta))


def _dias(retraso: Retraso) -> int:
    return (retraso.fecha_nueva - retraso.fecha_anterior).days


def dias_de_retraso(necesidad: Necesidad) -> int:
    """Días que se ha retrasado el pedido (0 si no tiene retrasos o si no se cumplieron)."""
    if not necesidad.retrasos:
        return 0
    if necesidad.fecha_entrega_real is None:
        return sum(_dias(r) for r in necesidad.retrasos)
    # Cada retraso mueve la fecha hacia delante: la más temprana es la prevista original.
    original = min(r.fecha_anterior for r in necesidad.retrasos)
    return max(0, (necesidad.fecha_entrega_real - original).days)


def sin_efecto(necesidad: Necesidad) -> bool:
    """Se avisó de algún retraso, pero el pedido llegó el día previsto o antes."""
    return bool(necesidad.retrasos) and dias_de_retraso(necesidad) == 0


def resumenes(sesion: Session, proveedor_ids: list[int]) -> dict[int, dict]:
    """{proveedor_id: {pedidos, con_retraso, dias_retraso, retraso_medio, comentarios}}.
    `comentarios`: los de la entrega de sus pedidos, del más reciente al más antiguo, cada uno
    {necesidad_id, codigo, titulo, fecha (la de entrega), texto}. `dias_retraso`: días
    de retraso de todos sus pedidos. `retraso_medio`: días por pedido, con un decimal (None si no
    tiene pedidos); para comparar proveedores se usa el valor sin redondear (1 día en
    21 pedidos se muestra 0,0, pero no empata con ningún retraso)."""
    resultado = {
        i: {
            "pedidos": 0,
            "con_retraso": 0,
            "dias_retraso": 0,
            "retraso_medio": None,
            "comentarios": [],
        }
        for i in proveedor_ids
    }
    if not proveedor_ids:
        return resultado
    for necesidad in _pedidos(sesion, proveedor_ids):
        datos = resultado[necesidad.oferta_adjudicada.proveedor_id]
        datos["pedidos"] += 1
        retraso = dias_de_retraso(necesidad)
        if retraso:
            datos["con_retraso"] += 1
            datos["dias_retraso"] += retraso
        if necesidad.comentario_entrega:
            datos["comentarios"].append(
                {
                    "necesidad_id": necesidad.id,
                    "codigo": necesidad.codigo,
                    "titulo": necesidad.titulo,
                    "fecha": necesidad.fecha_entrega_real,
                    "texto": necesidad.comentario_entrega,
                }
            )
    for datos in resultado.values():
        datos["comentarios"].sort(key=lambda c: (c["fecha"], c["codigo"]), reverse=True)
        if datos["pedidos"]:
            datos["retraso_medio"] = float(
                _redondeado(datos["dias_retraso"] / datos["pedidos"], "0.1")
            )
    return resultado


def historico(sesion: Session, proveedor_id: int) -> dict | None:
    """Resumen y lista de retrasos del proveedor, del más reciente al más antiguo. None si no
    existe."""
    proveedor = sesion.get(Proveedor, proveedor_id)
    if proveedor is None:
        return None
    retrasos = [
        (necesidad, retraso)
        for necesidad in _pedidos(sesion, [proveedor_id])
        for retraso in necesidad.retrasos
    ]
    retrasos.sort(key=lambda par: (par[1].registrado_en, par[1].id), reverse=True)
    return {
        "proveedor": proveedor,
        **resumenes(sesion, [proveedor_id])[proveedor_id],
        "retrasos": [
            {
                "necesidad": necesidad,
                "fecha_anterior": retraso.fecha_anterior,
                "fecha_nueva": retraso.fecha_nueva,
                "dias": _dias(retraso),
                "motivo": retraso.motivo,
                "peticionario": retraso.peticionario,
                "registrado_en": retraso.registrado_en,
                "sin_efecto": sin_efecto(necesidad),
            }
            for necesidad, retraso in retrasos
        ],
    }


def para_la_api(resumen: dict) -> dict:
    """El resumen con las fechas de los comentarios en ISO (Flask las daría en formato HTTP)."""
    return {
        **resumen,
        "comentarios": [
            {**c, "fecha": c["fecha"].isoformat() if c["fecha"] else ""}
            for c in resumen["comentarios"]
        ],
    }


def _redondeado(valor: float, paso: str) -> Decimal:
    """Redondeo de toda la vida (0,25 → 0,3), como `Math.round` en la pantalla: `round()` redondea
    al par (0,25 → 0,2) y el texto no coincidiría con la pantalla."""
    return Decimal(str(valor)).quantize(Decimal(paso), rounding=ROUND_HALF_UP)
