"""Pruebas del esqueleto andante: configuración, conexión y documentación de la API."""

from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.config import Config, ErrorDeConfiguracion, cargar_config


@pytest.mark.parametrize("contrasena", ["clave@con", "clave/con", "clave:con", "clave%con"])
def test_url_con_caracteres_reservados(contrasena):
    config = Config(
        entorno="development",
        db_host="localhost",
        db_port=5432,
        db_nombre="remate",
        db_usuario="usuario@prueba",
        db_contrasena=contrasena,
        frontend_dist=Path("dist"),
        archivos_dir=Path("archivos"),
    )
    url = make_url(config.url_base_de_datos())
    assert url.username == "usuario@prueba"
    assert url.password == contrasena
    assert url.host == "localhost"
    assert url.database == "remate"
    # Alembic necesita la URL serializada: también debe conservar las credenciales.
    assert make_url(url.render_as_string(hide_password=False)).password == contrasena
    assert make_url(config.url_base_de_datos("remate_test")).database == "remate_test"


def test_salud_responde_con_base_de_datos(cliente):
    respuesta = cliente.get("/api/salud")
    assert respuesta.status_code == 200
    assert respuesta.get_json() == {"estado": "ok", "base_de_datos": "ok"}


def test_documentacion_openapi_disponible(cliente):
    respuesta = cliente.get("/api/docs/openapi.json")
    assert respuesta.status_code == 200
    assert "/api/salud" in respuesta.get_json()["paths"]


def test_swagger_ui_disponible(cliente):
    respuesta = cliente.get("/api/docs/swagger")
    assert respuesta.status_code == 200


def test_falta_variable_obligatoria(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.delenv("DB_HOST", raising=False)
    monkeypatch.setenv("DB_PORT", "5432")
    with pytest.raises(ErrorDeConfiguracion, match="DB_HOST"):
        cargar_config()


def test_app_env_no_valido(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("APP_ENV", "pruebas")
    with pytest.raises(ErrorDeConfiguracion, match="APP_ENV"):
        cargar_config()
