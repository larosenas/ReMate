"""Arranque del servicio de Windows y configuración de escucha (ADR 0009)."""

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from app import config, servir
from app.config import ErrorDeConfiguracion


@pytest.fixture
def entorno(monkeypatch):
    # Sin leer el .env local ni conectar con la base de datos.
    monkeypatch.setattr(config, "load_dotenv", lambda *_: None)
    for nombre in ("HOST", "PORT", "APP_ENV", "IA_RAZONAMIENTO", "PROXY_DE_CONFIANZA"):
        monkeypatch.delenv(nombre, raising=False)
    for nombre in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"):
        monkeypatch.setenv(nombre, "ejemplo")
    monkeypatch.setenv("DB_PORT", "5432")


def test_escucha_por_defecto(entorno):
    ajustes = config.cargar_config()
    assert (ajustes.host, ajustes.port) == ("0.0.0.0", 2905)  # noqa: S104


@pytest.mark.parametrize("host", ["127.0.0.1", "10.0.0.10", "::1"])
def test_escucha_configurable(entorno, monkeypatch, host):
    monkeypatch.setenv("HOST", f" {host} ")
    monkeypatch.setenv("PORT", " 8080 ")
    ajustes = config.cargar_config()
    assert (ajustes.host, ajustes.port) == (host, 8080)


@pytest.mark.parametrize("nombre", ["HOST", "PORT"])
def test_variable_vacia_usa_el_valor_por_defecto(entorno, monkeypatch, nombre):
    monkeypatch.setenv(nombre, "  ")
    esperado = {"HOST": "0.0.0.0", "PORT": 2905}  # noqa: S104
    assert getattr(config.cargar_config(), nombre.lower()) == esperado[nombre]


@pytest.mark.parametrize("port", ["0", "65536", "-1", "1.5", "http", "²", "１２３", "9" * 5000])
def test_rechaza_puerto_invalido(entorno, monkeypatch, port):
    monkeypatch.setenv("PORT", port)
    with pytest.raises(ErrorDeConfiguracion, match="PORT debe ser un número entre 1 y 65535"):
        config.cargar_config()


def test_razonamiento_de_la_ia(entorno, monkeypatch):
    """ADR 0011: «low» si no se indica; se puede bajar desde el .env sin tocar el código."""
    assert config.cargar_config().ia_razonamiento == "low"
    monkeypatch.setenv("IA_RAZONAMIENTO", " Minimal ")
    assert config.cargar_config().ia_razonamiento == "minimal"


def test_razonamiento_mal_escrito_no_arranca(entorno, monkeypatch):
    monkeypatch.setenv("IA_RAZONAMIENTO", "bajo")
    with pytest.raises(ErrorDeConfiguracion, match="IA_RAZONAMIENTO"):
        config.cargar_config()


@pytest.mark.parametrize("host", ["http://127.0.0.1", "127.0.0.1:2905", "999.1.1.1"])
def test_rechaza_host_invalido(entorno, monkeypatch, host):
    monkeypatch.setenv("HOST", host)
    with pytest.raises(ErrorDeConfiguracion, match="HOST debe ser una dirección IP"):
        config.cargar_config()


def test_waitress_recibe_la_configuracion(entorno, monkeypatch):
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8080")
    crear = Mock(return_value=object())
    escuchar = Mock()
    monkeypatch.setattr(servir, "create_app", crear)
    monkeypatch.setattr(servir, "serve", escuchar)
    assert servir.main([]) == 0
    assert crear.call_args.args[0].port == 8080
    escuchar.assert_called_once_with(
        crear.return_value,
        host="127.0.0.1",
        port=8080,
        threads=16,
        max_request_body_size=101 * 1024 * 1024,
    )


def test_configuracion_invalida_no_arranca_waitress(entorno, monkeypatch):
    monkeypatch.setenv("PORT", "0")
    escuchar = Mock()
    monkeypatch.setattr(servir, "serve", escuchar)
    with pytest.raises(ErrorDeConfiguracion):
        servir.main([])
    escuchar.assert_not_called()


def test_error_de_arranque_queda_en_el_log(tmp_path):
    log = tmp_path / "remate.log"
    log.write_text("línea anterior\n", encoding="utf-8")
    resultado = subprocess.run(  # noqa: S603
        [sys.executable, "-m", "app.servir", "--log", str(log)],
        cwd=Path(__file__).resolve().parent.parent,
        env={**os.environ, "PORT": "0"},
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert resultado.returncode == 1
    assert resultado.stdout == resultado.stderr == b""
    contenido = log.read_text(encoding="utf-8")
    assert contenido.startswith("línea anterior\n")
    assert "PORT debe ser un número entre 1 y 65535" in contenido
