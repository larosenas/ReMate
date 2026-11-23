"""CU-004/CU-005: moneda de cada oferta, sin conversiones (ADR 0010)."""

from datetime import date

import pytest

from app.integraciones import ia
from app.modelos.ofertas import Oferta
from app.servicios.adjudicacion import lineas_sap
from tests.test_ofertas import datos as datos
from tests.test_ofertas import subir, url

pytestmark = pytest.mark.usefixtures("limpiar")

REVISADA = {
    "importe_sin_iva": "125",
    "fecha_entrega_estimada": "2026-12-01",
    "revisada": True,
}


def test_cu004_eur_por_defecto_y_sin_moneda_no_se_da_por_revisada(cliente, datos):
    oferta = subir(cliente, datos).json
    assert oferta["moneda"] == "EUR"
    ruta = url(datos, f"/{oferta['id']}")
    r = cliente.patch(ruta, json={**REVISADA, "moneda": ""})
    assert r.status_code == 400
    assert r.json["detalles"] == {"campo": "moneda"}
    r = cliente.patch(ruta, json={**REVISADA, "moneda": "usd"})
    assert r.status_code == 200, r.json
    assert r.json["moneda"] == "USD"
    assert r.json["revisada"] is True


# Letras que no son A-Z no pueden pasar a SSA, FFA o ISO al ponerlas en mayúsculas.
@pytest.mark.parametrize("moneda", ["$", "EU", "12A", "ßa", "ﬀa", "ıso"])
def test_cu004_rechaza_un_codigo_que_no_es_de_tres_letras(cliente, datos, moneda):
    oferta = subir(cliente, datos).json
    r = cliente.patch(url(datos, f"/{oferta['id']}"), json={"moneda": moneda})
    assert r.status_code == 400


@pytest.mark.parametrize("moneda", [None, "$", "EURO", 123])
def test_cu004_si_la_ia_no_ve_la_moneda_pone_eur_y_avisa(cliente, datos, monkeypatch, moneda):
    monkeypatch.setattr(
        ia,
        "leer_oferta",
        lambda *_: {
            "moneda": moneda,
            "importe_sin_iva": 10,
            "fecha_entrega": "2026-12-01",
        },
    )
    oferta = subir(cliente, datos).json
    leida = cliente.post(url(datos, f"/{oferta['id']}/analisis")).json
    assert leida["moneda"] == "EUR"
    assert sum("no ha visto la moneda" in a for a in leida["avisos"]) == 1
    # El aviso sigue en la oferta, no solo en la respuesta del análisis, hasta que se corrige la
    # moneda.
    assert any("no ha visto la moneda" in a for a in cliente.get(url(datos)).json[0]["avisos"])
    cliente.patch(url(datos, f"/{oferta['id']}"), json={"moneda": "USD"})
    assert not any("no ha visto la moneda" in a for a in cliente.get(url(datos)).json[0]["avisos"])


def test_cu004_ia_lee_la_moneda(cliente, datos, monkeypatch):
    monkeypatch.setattr(ia, "leer_oferta", lambda *_: {"moneda": "pln", "importe_sin_iva": 10})
    oferta = subir(cliente, datos).json
    assert cliente.post(url(datos, f"/{oferta['id']}/analisis")).json["moneda"] == "PLN"


def test_cu004_con_monedas_distintas_no_se_comparan_importes(cliente, datos):
    primera = subir(cliente, datos).json
    segunda = subir(cliente, datos, proveedor_id=str(datos["zeta"])).json
    for oferta, moneda in [(primera, "USD"), (segunda, "EUR")]:
        r = cliente.patch(url(datos, f"/{oferta['id']}"), json={**REVISADA, "moneda": moneda})
        assert r.status_code == 200, r.json
    r = cliente.post(
        f"/api/necesidades/{datos['necesidad']}/evaluacion", json={"peticionario_id": datos["ana"]}
    )
    assert r.status_code == 200, r.json
    tabla = cliente.get(f"/api/necesidades/{datos['necesidad']}/comparativa").json
    # Ni mejor ni peor precio entre importes de monedas distintas (sin conversiones).
    assert all(o["destacados"]["importe"] is None for o in tabla)
    assert {o["moneda"] for o in tabla} == {"EUR", "USD"}
    assert all(o["importe_sin_iva"] == "125.00" for o in tabla)


def test_cu005_sap_conserva_la_moneda_y_el_precio_original(cliente, datos, app):
    oferta = subir(cliente, datos).json
    cliente.patch(
        url(datos, f"/{oferta['id']}"),
        json={
            **REVISADA,
            "moneda": "JPY",
            "importe_sin_iva": "16000",
            "lineas": [{"descripcion": "Rodamiento", "cantidad": "2", "precio_unitario": "8000"}],
        },
    )
    with app.extensions["remate.sesiones"]() as s:
        original = s.get(Oferta, oferta["id"])
        assert (
            lineas_sap(original, "Rodamiento", None, date(2026, 11, 18))[0]["valuation_price"]
            == "8000,00"
        )


def _ia_sin_moneda(*_):
    return {"importe_sin_iva": 10, "fecha_entrega": "2026-12-01"}


def _analizar_y_comparar(cliente, datos):
    r = cliente.post(
        f"/api/necesidades/{datos['necesidad']}/evaluacion", json={"peticionario_id": datos["ana"]}
    )
    assert r.status_code == 200, r.json


def test_cu004_la_moneda_escrita_antes_de_analizar_no_se_pierde(cliente, datos, monkeypatch):
    """Si solo se cambia la moneda, «Analizar y comparar» no la pisa."""
    monkeypatch.setattr(ia, "leer_oferta", _ia_sin_moneda)
    oferta = subir(cliente, datos).json
    r = cliente.patch(url(datos, f"/{oferta['id']}"), json={"moneda": "USD", "revisada": False})
    assert r.json["sin_analizar"] is False
    _analizar_y_comparar(cliente, datos)
    assert cliente.get(url(datos)).json[0]["moneda"] == "USD"


def test_cu004_la_moneda_cambiada_mientras_lee_la_ia_no_se_pisa(app, cliente, datos, monkeypatch):
    oferta = subir(cliente, datos).json

    def leer_y_cambiar_la_moneda(*_):
        with app.extensions["remate.sesiones"]() as s:
            s.get(Oferta, oferta["id"]).moneda = "GBP"
            s.commit()
        return _ia_sin_moneda()

    monkeypatch.setattr(ia, "leer_oferta", leer_y_cambiar_la_moneda)
    _analizar_y_comparar(cliente, datos)
    assert cliente.get(url(datos)).json[0]["moneda"] == "GBP"
