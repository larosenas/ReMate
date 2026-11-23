"""CU-010 — Histórico de retrasos por proveedor, proveedor adjudicado en el panel e histórico en
la comparativa (también para la IA, simulada)."""

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.modelos.necesidades import Necesidad, Retraso
from app.modelos.ofertas import Oferta
from app.servicios import historico
from tests.test_adjudicacion import adjudicacion, datos, url  # noqa: F401
from tests.test_entrega import hoy, pendiente_entrega, retraso  # noqa: F401
from tests.test_pedido_sap_envio import enviar, pendiente_pedido  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar")


def otro_pedido_sin_retrasos(app, datos):  # noqa: F811
    """Una segunda necesidad adjudicada a FICMEC (cancelada después), sin retrasos."""
    with app.extensions["remate.sesiones"]() as s:
        necesidad = Necesidad(
            codigo="2026010101",
            titulo="Pedido antiguo",
            proyecto="Línea 1",
            descripcion="d",
            estado="cancelada",
            peticionario_id=datos["ana"],
        )
        oferta = Oferta(necesidad=necesidad, proveedor_id=datos["ficmec"])
        s.add_all([necesidad, oferta])
        s.flush()
        necesidad.oferta_adjudicada = oferta
        s.commit()


def test_historico_de_retrasos_del_proveedor(cliente, app, pendiente_entrega):  # noqa: F811
    otro_pedido_sin_retrasos(app, pendiente_entrega)
    assert (
        retraso(cliente, pendiente_entrega, fecha_nueva="2026-11-27", motivo="Material").status_code
        == 200
    )
    assert (
        retraso(
            cliente, pendiente_entrega, fecha_nueva="2026-11-30", motivo="Transporte"
        ).status_code
        == 200
    )

    respuesta = cliente.get(f"/api/proveedores/{pendiente_entrega['ficmec']}/retrasos")
    assert respuesta.status_code == 200, respuesta.json
    historico = respuesta.json
    assert historico["proveedor"]["nombre"] == "FICMEC"
    assert (historico["pedidos"], historico["con_retraso"], historico["retraso_medio"]) == (
        2,
        1,
        5.0,  # 10 días entre los 2 pedidos (también el que no tuvo retraso)
    )
    # Del más reciente al más antiguo.
    assert [
        (r["fecha_anterior"], r["fecha_nueva"], r["dias"], r["motivo"])
        for r in historico["retrasos"]
    ] == [
        ("2026-11-27", "2026-11-30", 3, "Transporte"),
        ("2026-11-20", "2026-11-27", 7, "Material"),
    ]
    assert historico["retrasos"][0]["necesidad"]["id"] == pendiente_entrega["necesidad"]
    assert historico["retrasos"][0]["peticionario"] == "Ana Prueba"


def test_proveedor_sin_pedidos_y_que_no_existe(cliente, datos):  # noqa: F811
    acme = cliente.get(f"/api/proveedores/{datos['acme']}/retrasos").json
    assert (acme["pedidos"], acme["con_retraso"], acme["retraso_medio"], acme["retrasos"]) == (
        0,
        0,
        None,
        [],
    )
    assert cliente.get("/api/proveedores/999999/retrasos").status_code == 404


def test_el_panel_lleva_el_proveedor_adjudicado(cliente, pendiente_entrega):  # noqa: F811
    listado = {n["id"]: n for n in cliente.get("/api/necesidades").json}
    adjudicado = listado[pendiente_entrega["necesidad"]]["proveedor_adjudicado"]
    assert (adjudicado["id"], adjudicado["nombre"]) == (pendiente_entrega["ficmec"], "FICMEC")


def test_la_comparativa_lleva_el_historico(cliente, app, datos):  # noqa: F811
    otro_pedido_sin_retrasos(app, datos)
    comparativa = cliente.get(url(datos, "/comparativa")).json
    ficmec = next(o for o in comparativa if o["proveedor"]["nombre"] == "FICMEC")
    assert ficmec["historial_proveedor"] == {
        "pedidos": 1,
        "con_retraso": 0,
        "dias_retraso": 0,
        "retraso_medio": 0.0,
        "comentarios": [],
    }
    # El resumen de la comparativa ya no existe.
    assert cliente.post(url(datos, "/comparativa/resumen")).status_code in (404, 405)


def test_la_comparativa_marca_los_retrasos_con_el_historico_real(cliente, app, datos):  # noqa: F811
    """Las marcas de retrasos, por la API y no solo en la prueba unitaria.
    FICMEC tuvo un pedido con 3 días de retraso avisado; Acme, uno sin retraso."""
    otro_pedido_sin_retrasos(app, datos)
    with app.extensions["remate.sesiones"]() as s:
        ficmec_antiguo = s.scalars(select(Necesidad).where(Necesidad.codigo == "2026010101")).one()
        s.add(
            Retraso(
                necesidad=ficmec_antiguo,
                fecha_anterior=date(2026, 1, 10),
                fecha_nueva=date(2026, 1, 13),
                motivo="Transporte",
                peticionario_id=datos["ana"],
            )
        )
        acme_antiguo = Necesidad(
            codigo="2026010102",
            titulo="Otro pedido antiguo",
            proyecto="Línea 1",
            descripcion="d",
            estado="cancelada",
            peticionario_id=datos["ana"],
        )
        oferta = Oferta(necesidad=acme_antiguo, proveedor_id=datos["acme"])
        s.add_all([acme_antiguo, oferta])
        s.flush()
        acme_antiguo.oferta_adjudicada = oferta
        s.commit()
    comparativa = {
        o["proveedor"]["nombre"]: o for o in cliente.get(url(datos, "/comparativa")).json
    }
    assert comparativa["FICMEC"]["historial_proveedor"]["dias_retraso"] == 3
    assert comparativa["FICMEC"]["destacados"]["retrasos"] == "peor"
    assert comparativa["Acme"]["destacados"]["retrasos"] == "mejor"


def test_un_proveedor_eliminado_sigue_en_las_necesidades_antiguas(cliente, pendiente_entrega):  # noqa: F811
    """CU-003 (criterio pendiente): desactivado y eliminado, deja de salir en las listas pero su
    nombre sigue en las necesidades en las que participó."""
    proveedor = f"/api/proveedores/{pendiente_entrega['ficmec']}"
    assert cliente.patch(proveedor, json={"activo": False}).status_code == 200
    assert (
        cliente.post(f"{proveedor}/baja", json={"motivo": "Registro duplicado"}).status_code == 204
    )
    nombres = [p["nombre"] for p in cliente.get("/api/proveedores?incluir_inactivos=true").json]
    assert "FICMEC" not in nombres
    listado = {n["id"]: n for n in cliente.get("/api/necesidades").json}
    assert listado[pendiente_entrega["necesidad"]]["proveedor_adjudicado"]["nombre"] == "FICMEC"
    ofertas = cliente.get(f"/api/necesidades/{pendiente_entrega['necesidad']}/ofertas").json
    assert "FICMEC" in [o["proveedor"]["nombre"] for o in ofertas]
    assert cliente.get(f"{proveedor}/retrasos").json["proveedor"]["nombre"] == "FICMEC"


def test_el_panel_lleva_la_fecha_del_estado_actual(cliente, pendiente_entrega):  # noqa: F811
    """Junto al estado, la fecha en que se pasó a él."""
    detalle = cliente.get(f"/api/necesidades/{pendiente_entrega['necesidad']}").json
    ultimo = detalle["historial"][-1]
    assert ultimo["estado_nuevo"] == "pendiente_entrega"
    listado = {n["id"]: n for n in cliente.get("/api/necesidades").json}
    assert listado[pendiente_entrega["necesidad"]]["estado_desde"] == ultimo["cambiado_en"]


def entregar(cliente, datos, dia):  # noqa: F811
    cuerpo = {"peticionario_id": datos["ana"], "fecha_entrega_real": dia}
    return cliente.post(url(datos, "/entrega"), json=cuerpo)


def test_un_retraso_avisado_que_no_se_cumple_no_cuenta(cliente, pendiente_entrega, hoy):  # noqa: F811
    """Se avisó de un retraso, pero llegó el día previsto o antes."""
    assert retraso(cliente, pendiente_entrega, fecha_nueva="2026-11-27").status_code == 200
    hoy(date(2026, 11, 19))
    necesidad = entregar(cliente, pendiente_entrega, "2026-11-19").json
    assert [r["sin_efecto"] for r in necesidad["retrasos"]] == [True]

    historico = cliente.get(f"/api/proveedores/{pendiente_entrega['ficmec']}/retrasos").json
    assert (historico["pedidos"], historico["con_retraso"], historico["retraso_medio"]) == (
        1,
        0,
        0.0,
    )
    assert [r["sin_efecto"] for r in historico["retrasos"]] == [True]


def test_si_llega_antes_de_lo_avisado_cuentan_los_dias_reales(cliente, pendiente_entrega, hoy):  # noqa: F811
    """Prevista el 20/11, se avisa del 30/11 y llega el 23/11: 3 días de retraso, no 10."""
    assert retraso(cliente, pendiente_entrega, fecha_nueva="2026-11-30").status_code == 200
    hoy(date(2026, 11, 23))
    necesidad = entregar(cliente, pendiente_entrega, "2026-11-23").json
    assert [r["sin_efecto"] for r in necesidad["retrasos"]] == [False]

    historico = cliente.get(f"/api/proveedores/{pendiente_entrega['ficmec']}/retrasos").json
    assert (historico["pedidos"], historico["con_retraso"], historico["retraso_medio"]) == (
        1,
        1,
        3.0,
    )


def test_redondeo_como_en_la_pantalla():
    """`round()` redondea al par (0,25 → 0,2; 12,5 % → 12 %) y la pantalla, con `Math.round`,
    al alza (0,3 y 13 %): el texto de la IA tiene que coincidir con la pantalla."""
    assert historico._redondeado(1 / 4, "0.1") == Decimal("0.3")


# --- Comentario de la entrega -------------------------------------------------------------------


def entregar_con_comentario(app, datos, codigo, dia, texto):  # noqa: F811
    """Otra necesidad de FICMEC ya entregada, con su comentario."""
    with app.extensions["remate.sesiones"]() as s:
        necesidad = Necesidad(
            codigo=codigo,
            titulo=f"Pedido {codigo}",
            proyecto="Línea 1",
            descripcion="d",
            estado="entregado",
            peticionario_id=datos["ana"],
            fecha_entrega_real=dia,
            comentario_entrega=texto,
        )
        oferta = Oferta(necesidad=necesidad, proveedor_id=datos["ficmec"])
        s.add_all([necesidad, oferta])
        s.flush()
        necesidad.oferta_adjudicada = oferta
        s.commit()
        return necesidad.id


def test_comentario_de_la_entrega_en_el_historico(cliente, pendiente_entrega, hoy):  # noqa: F811
    hoy(date(2026, 11, 19))
    respuesta = cliente.post(
        url(pendiente_entrega, "/entrega"),
        json={
            "peticionario_id": pendiente_entrega["ana"],
            "comentario": "  El paquete llegó destrozado.  ",
        },
    )
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json["comentario_entrega"] == "El paquete llegó destrozado."
    historico_ficmec = cliente.get(f"/api/proveedores/{pendiente_entrega['ficmec']}/retrasos").json
    [comentario] = historico_ficmec["comentarios"]
    assert comentario["texto"] == "El paquete llegó destrozado."
    assert comentario["fecha"] == "2026-11-19"
    assert comentario["necesidad_id"] == pendiente_entrega["necesidad"]


def test_comentario_demasiado_largo_o_solo_espacios(cliente, pendiente_entrega, hoy):  # noqa: F811
    largo = cliente.post(
        url(pendiente_entrega, "/entrega"),
        json={"peticionario_id": pendiente_entrega["ana"], "comentario": "x" * 1001},
    )
    assert largo.status_code == 400
    assert cliente.get(f"/api/necesidades/{pendiente_entrega['necesidad']}").json["estado"] == (
        "pendiente_entrega"
    )
    assert largo.json["detalles"] == {"campo": "comentario"}
    # Un carácter nulo no da un error 500 (PostgreSQL no lo admite).
    nulo = cliente.post(
        url(pendiente_entrega, "/entrega"),
        json={"peticionario_id": pendiente_entrega["ana"], "comentario": "con\u0000nulo"},
    )
    assert nulo.status_code == 400
    assert nulo.json["detalles"] == {"campo": "comentario"}
    # El máximo se cuenta sin los espacios de los extremos.
    con_espacios = cliente.post(
        url(pendiente_entrega, "/entrega"),
        json={"peticionario_id": pendiente_entrega["ana"], "comentario": "  " + "x" * 1000 + "  "},
    )
    assert con_espacios.status_code == 200, con_espacios.json
    assert len(con_espacios.json["comentario_entrega"]) == 1000


def test_comentario_solo_espacios_no_se_guarda(cliente, pendiente_entrega, hoy):  # noqa: F811
    respuesta = cliente.post(
        url(pendiente_entrega, "/entrega"),
        json={"peticionario_id": pendiente_entrega["ana"], "comentario": "   "},
    )
    assert respuesta.json["comentario_entrega"] is None


def test_la_comparativa_y_la_ia_llevan_los_comentarios(cliente, app, datos, monkeypatch):  # noqa: F811
    from app.servicios import adjudicacion as servicio_adjudicacion

    entregar_con_comentario(app, datos, "2026010101", date(2026, 10, 1), "Llegó tarde y mojado.")
    entregar_con_comentario(app, datos, "2026010201", date(2026, 10, 20), "Embalaje roto.")
    comparativa = cliente.get(url(datos, "/comparativa")).json
    ficmec = next(o for o in comparativa if o["proveedor"]["nombre"] == "FICMEC")
    # Del más reciente al más antiguo.
    assert [(c["fecha"], c["texto"]) for c in ficmec["historial_proveedor"]["comentarios"]] == [
        ("2026-10-20", "Embalaje roto."),
        ("2026-10-01", "Llegó tarde y mojado."),
    ]
    recibido = []

    def redactar(_config, contexto):
        recibido.append(contexto)
        return {"descripcion": "d", "resumen": "r", "avisos": []}

    monkeypatch.setattr(servicio_adjudicacion.ia, "redactar_adjudicacion", redactar)
    cliente.post(url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]})
    assert "Comentarios de ingeniería al recibir pedidos anteriores" in recibido[0]
    assert "- FICMEC, entrega del 20.10.2026 («Pedido 2026010201»): Embalaje roto." in recibido[0]
