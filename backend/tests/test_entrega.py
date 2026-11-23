"""CU-008 — Registrar retrasos y confirmar la entrega. «Hoy» se fija en cada prueba."""

from datetime import date

import pytest

from app.servicios import entrega
from tests.test_adjudicacion import adjudicacion, datos, url  # noqa: F401
from tests.test_pedido_sap_envio import enviar, pendiente_pedido  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar")


@pytest.fixture
def pendiente_entrega(cliente, pendiente_pedido):  # noqa: F811
    """Pedido enviado; entrega prevista el 20/11/2026."""
    assert enviar(cliente, pendiente_pedido).status_code == 200
    return pendiente_pedido


@pytest.fixture
def hoy(monkeypatch):
    def fijar(dia):
        monkeypatch.setattr(entrega, "_hoy", lambda: dia)

    fijar(date(2026, 11, 20))
    return fijar


def retraso(cliente, datos, **cambios):  # noqa: F811
    cuerpo = {
        "peticionario_id": datos["ana"],
        "fecha_nueva": "2026-11-27",
        "motivo": "Falta material en el proveedor",
        **cambios,
    }
    return cliente.post(url(datos, "/retrasos"), json=cuerpo)


def test_registrar_un_retraso_mueve_la_fecha_prevista(cliente, pendiente_entrega):
    respuesta = retraso(cliente, pendiente_entrega)
    assert respuesta.status_code == 200, respuesta.json
    necesidad = respuesta.json
    assert necesidad["estado"] == "pendiente_entrega"
    assert necesidad["fecha_entrega_prevista"] == "2026-11-27"
    [registrado] = necesidad["retrasos"]
    assert registrado["fecha_anterior"] == "2026-11-20"
    assert registrado["fecha_nueva"] == "2026-11-27"
    assert registrado["motivo"] == "Falta material en el proveedor"
    assert registrado["peticionario"]["nombre_completo"] == "Ana Prueba"
    # Un segundo retraso parte de la nueva fecha.
    otro = retraso(cliente, pendiente_entrega, fecha_nueva="2026-12-04", motivo="Transporte").json
    assert [(r["fecha_anterior"], r["fecha_nueva"]) for r in otro["retrasos"]] == [
        ("2026-11-20", "2026-11-27"),
        ("2026-11-27", "2026-12-04"),
    ]
    # No es un cambio de estado.
    assert otro["historial"][-1]["estado_nuevo"] == "pendiente_entrega"


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"motivo": "  "}, "motivo"),
        ({"fecha_nueva": None}, "fecha_nueva"),
        ({"fecha_nueva": "2026-11-20"}, "fecha_nueva"),  # igual a la prevista
        ({"fecha_nueva": "2026-11-10"}, "fecha_nueva"),  # anterior
        ({"peticionario_id": 999999}, "peticionario_id"),
    ],
)
def test_retraso_que_no_vale(cliente, pendiente_entrega, cambios, campo):
    respuesta = retraso(cliente, pendiente_entrega, **cambios)
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": campo}
    detalle = cliente.get(f"/api/necesidades/{pendiente_entrega['necesidad']}").json
    assert detalle["retrasos"] == []
    assert detalle["fecha_entrega_prevista"] == "2026-11-20"


def test_confirmar_la_entrega_a_tiempo(cliente, pendiente_entrega, hoy):
    hoy(date(2026, 11, 19))
    # Sin fecha, se toma la de hoy.
    respuesta = cliente.post(
        url(pendiente_entrega, "/entrega"), json={"peticionario_id": pendiente_entrega["ana"]}
    )
    assert respuesta.status_code == 200, respuesta.json
    necesidad = respuesta.json
    assert necesidad["estado"] == "entregado"
    assert necesidad["fecha_entrega_real"] == "2026-11-19"
    assert necesidad["retrasos"] == []
    assert necesidad["historial"][-1]["estado_anterior"] == "pendiente_entrega"
    # Ya no se puede registrar un retraso, volver a confirmar ni cancelar.
    assert retraso(cliente, pendiente_entrega).status_code == 409
    assert (
        cliente.post(
            url(pendiente_entrega, "/entrega"), json={"peticionario_id": pendiente_entrega["ana"]}
        ).status_code
        == 409
    )
    cancelar = cliente.post(
        url(pendiente_entrega, "/cancelar"),
        json={"peticionario_id": pendiente_entrega["ana"], "motivo": "x"},
    )
    assert cancelar.status_code == 409


def test_entrega_tarde_pide_el_motivo_y_lo_registra_como_retraso(cliente, pendiente_entrega, hoy):
    hoy(date(2026, 11, 26))
    cuerpo = {"peticionario_id": pendiente_entrega["ana"], "fecha_entrega_real": "2026-11-24"}
    sin_motivo = cliente.post(url(pendiente_entrega, "/entrega"), json=cuerpo)
    assert sin_motivo.status_code == 400
    assert sin_motivo.json["detalles"] == {"campo": "motivo_retraso"}
    assert "20/11/2026" in sin_motivo.json["mensaje"]

    cuerpo["motivo_retraso"] = "El transportista se retrasó"
    necesidad = cliente.post(url(pendiente_entrega, "/entrega"), json=cuerpo).json
    assert necesidad["estado"] == "entregado"
    assert necesidad["fecha_entrega_real"] == "2026-11-24"
    [registrado] = necesidad["retrasos"]
    assert (registrado["fecha_anterior"], registrado["fecha_nueva"]) == ("2026-11-20", "2026-11-24")
    assert registrado["motivo"] == "El transportista se retrasó"


def test_fecha_real_futura_o_anterior_a_la_creacion(cliente, pendiente_entrega, hoy):
    hoy(date(2026, 11, 19))
    base = {"peticionario_id": pendiente_entrega["ana"]}
    futura = cliente.post(
        url(pendiente_entrega, "/entrega"), json={**base, "fecha_entrega_real": "2026-11-20"}
    )
    assert futura.status_code == 400
    assert futura.json["detalles"] == {"campo": "fecha_entrega_real"}
    antigua = cliente.post(
        url(pendiente_entrega, "/entrega"), json={**base, "fecha_entrega_real": "2020-01-01"}
    )
    assert antigua.status_code == 400


def test_solo_en_pendiente_entrega(cliente, pendiente_pedido):  # noqa: F811
    assert retraso(cliente, pendiente_pedido).status_code == 409
    respuesta = cliente.post(
        url(pendiente_pedido, "/entrega"), json={"peticionario_id": pendiente_pedido["ana"]}
    )
    assert respuesta.status_code == 409
    assert cliente.post("/api/necesidades/999999/retrasos", json={}).status_code == 404
