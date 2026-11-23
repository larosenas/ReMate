"""CU-006 — Confirmar el pedido en SAP y la fecha de entrega prevista."""

from datetime import UTC, datetime

import pytest

from app.modelos.necesidades import Necesidad
from tests.test_adjudicacion import adjudicacion, datos, url  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar")


@pytest.fixture
def adjudicada(app, cliente, datos):  # noqa: F811
    assert cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos)).status_code == 200
    # La validez de las fechas de CU-006 no puede depender del día en que se ejecuta la suite.
    with app.extensions["remate.sesiones"]() as sesion:
        necesidad = sesion.get(Necesidad, datos["necesidad"])
        necesidad.creada_en = datetime(2026, 10, 22, tzinfo=UTC)
        sesion.commit()
    return datos


def test_confirmar_con_la_fecha_inicial(cliente, adjudicada):
    respuesta = cliente.post(
        url(adjudicada, "/pedido-en-sap"),
        json={"peticionario_id": adjudicada["ana"], "fecha_entrega_prevista": "2026-11-15"},
    )
    assert respuesta.status_code == 200, respuesta.json
    necesidad = respuesta.json
    assert necesidad["estado"] == "pendiente_pedido_sap"
    assert necesidad["fecha_entrega_prevista"] == "2026-11-15"
    assert necesidad["historial"][-1]["estado_anterior"] == "pendiente_solicitud_sap"


def test_otra_fecha_no_cambia_la_inicial(cliente, adjudicada):
    necesidad = cliente.post(
        url(adjudicada, "/pedido-en-sap"),
        json={"peticionario_id": adjudicada["ana"], "fecha_entrega_prevista": "2026-11-27"},
    ).json
    assert necesidad["fecha_entrega_prevista"] == "2026-11-27"
    assert necesidad["fecha_entrega_inicial"] == "2026-11-15"


def test_sin_fecha_no_se_confirma(cliente, adjudicada):
    respuesta = cliente.post(
        url(adjudicada, "/pedido-en-sap"), json={"peticionario_id": adjudicada["ana"]}
    )
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "fecha_entrega_prevista"}


def test_solo_desde_pendiente_solicitud_sap(cliente, datos):  # noqa: F811
    respuesta = cliente.post(
        url(datos, "/pedido-en-sap"),
        json={"peticionario_id": datos["ana"], "fecha_entrega_prevista": "2026-11-15"},
    )
    assert respuesta.status_code == 409


def test_fecha_anterior_a_la_creacion(cliente, adjudicada):
    respuesta = cliente.post(
        url(adjudicada, "/pedido-en-sap"),
        json={"peticionario_id": adjudicada["ana"], "fecha_entrega_prevista": "2020-01-01"},
    )
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "fecha_entrega_prevista"}


def test_peticionario_no_valido_y_segunda_confirmacion(cliente, adjudicada):
    cuerpo = {"peticionario_id": 999999, "fecha_entrega_prevista": "2026-11-15"}
    respuesta = cliente.post(url(adjudicada, "/pedido-en-sap"), json=cuerpo)
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "peticionario_id"}
    cuerpo["peticionario_id"] = adjudicada["ana"]
    assert cliente.post(url(adjudicada, "/pedido-en-sap"), json=cuerpo).status_code == 200
    assert cliente.post(url(adjudicada, "/pedido-en-sap"), json=cuerpo).status_code == 409


def test_necesidad_inexistente(cliente):
    respuesta = cliente.post(
        "/api/necesidades/999999/pedido-en-sap",
        json={"peticionario_id": 1, "fecha_entrega_prevista": "2026-11-15"},
    )
    assert respuesta.status_code == 404


def test_listado_con_fecha_prevista(cliente, adjudicada):
    cliente.post(
        url(adjudicada, "/pedido-en-sap"),
        json={"peticionario_id": adjudicada["ana"], "fecha_entrega_prevista": "2026-11-27"},
    )
    [resumen] = cliente.get("/api/necesidades").json
    assert resumen["fecha_entrega_prevista"] == "2026-11-27"
