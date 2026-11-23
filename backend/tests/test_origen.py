"""Peticiones desde otra web y la aplicación dentro de un marco."""

import pytest


@pytest.mark.parametrize(
    "cabeceras",
    [
        {"Origin": "http://otra-web.test"},
        {"Origin": "null"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_rechaza_cambios_desde_otra_web(cliente, cabeceras):
    respuesta = cliente.post("/api/necesidades", data={}, headers=cabeceras)
    assert respuesta.status_code == 403
    assert respuesta.json["error"] == "origen_no_permitido"


@pytest.mark.parametrize(
    "cabeceras",
    [{}, {"Origin": "http://localhost"}, {"Sec-Fetch-Site": "same-origin"}],
)
def test_acepta_la_propia_aplicacion_y_los_clientes_sin_navegador(cliente, cabeceras):
    # Sin Origin (curl, pruebas) o desde la misma dirección: llega a la ruta (que valida los datos).
    respuesta = cliente.post("/api/necesidades", data={}, headers=cabeceras)
    assert respuesta.status_code == 400


def test_las_lecturas_desde_otra_web_no_se_bloquean(cliente):
    # Un GET no cambia nada, y el navegador no deja a la otra web leer la respuesta.
    assert cliente.get("/api/salud", headers={"Origin": "http://otra-web.test"}).status_code == 200


def test_no_se_puede_mostrar_dentro_de_un_marco(cliente):
    respuesta = cliente.get("/api/salud")
    assert respuesta.headers["X-Frame-Options"] == "DENY"
    assert respuesta.headers["Content-Security-Policy"] == "frame-ancestors 'none'"
    assert respuesta.headers["X-Content-Type-Options"] == "nosniff"
