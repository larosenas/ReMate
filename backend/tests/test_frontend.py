"""Flask sirve el frontend compilado y deja las rutas /api para la API (ADR 0004)."""

from dataclasses import replace

import pytest

from app import create_app


@pytest.fixture
def cliente_con_dist(config_pruebas, tmp_path):
    (tmp_path / "index.html").write_text("<p>ReMate</p>", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return create_app(replace(config_pruebas, frontend_dist=tmp_path)).test_client()


def test_raiz_devuelve_index(cliente_con_dist):
    respuesta = cliente_con_dist.get("/")
    assert respuesta.status_code == 200
    assert b"ReMate" in respuesta.data


def test_archivo_estatico(cliente_con_dist):
    respuesta = cliente_con_dist.get("/assets/app.js")
    assert respuesta.status_code == 200
    assert b"console.log" in respuesta.data


def test_ruta_de_react_devuelve_index(cliente_con_dist):
    respuesta = cliente_con_dist.get("/necesidades/2026102301")
    assert respuesta.status_code == 200
    assert b"ReMate" in respuesta.data


def test_ruta_api_inexistente_da_404(cliente_con_dist):
    assert cliente_con_dist.get("/api/no-existe").status_code == 404


def test_sin_dist_avisa(config_pruebas, tmp_path):
    cliente = create_app(replace(config_pruebas, frontend_dist=tmp_path / "vacia")).test_client()
    respuesta = cliente.get("/")
    assert respuesta.status_code == 404
    assert "npm run build" in respuesta.get_data(as_text=True)


def test_ruta_de_la_api_inexistente_con_cualquier_metodo(cliente):
    for metodo in ("get", "post", "patch", "delete"):
        respuesta = getattr(cliente, metodo)("/api/no-existe")
        assert respuesta.status_code == 404
        assert respuesta.json["error"] == "ruta_no_encontrada"
