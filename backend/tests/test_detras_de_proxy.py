"""ReMate detrás de un proxy inverso como Caddy (ADR 0016): con PROXY_DE_CONFIANZA, Waitress toma
la IP del equipo y el https de las cabeceras X-Forwarded-* que pone el proxy, y solo si la conexión
viene de él.

Sin esto, detrás del proxy todas las peticiones llegan desde su IP: cinco contraseñas mal puestas
por cualquiera bloquearían el modo admin a todos, y la cookie del modo admin no sería `Secure`.
"""

from dataclasses import replace
from unittest.mock import Mock

import pytest
from waitress.proxy_headers import proxy_headers_middleware
from werkzeug.security import generate_password_hash
from werkzeug.test import Client

from app import admin_sesion, config, servir
from app.config import ErrorDeConfiguracion
from tests.test_admin import CLAVE
from tests.test_servir import entorno  # noqa: F401

PROXY = "127.0.0.1"


def test_sin_proxy_por_defecto(entorno):  # noqa: F811
    assert config.cargar_config().proxy_de_confianza == ""


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [(" 127.0.0.1 ", "127.0.0.1"), ("10.0.0.20", "10.0.0.20"), ("0:0::1", "::1")],
)
def test_proxy_configurable(entorno, monkeypatch, valor, esperado):  # noqa: F811
    monkeypatch.setenv("PROXY_DE_CONFIANZA", valor)
    assert config.cargar_config().proxy_de_confianza == esperado


@pytest.mark.parametrize("valor", ["localhost", "127.0.0.1:2905", "*", "10.0.0.0/24"])
def test_rechaza_proxy_que_no_es_una_ip(entorno, monkeypatch, valor):  # noqa: F811
    """Una sola IP: con «*» o un nombre, cualquiera podría falsear su IP con X-Forwarded-For."""
    monkeypatch.setenv("PROXY_DE_CONFIANZA", valor)
    with pytest.raises(ErrorDeConfiguracion, match="PROXY_DE_CONFIANZA"):
        config.cargar_config()


def test_waitress_se_fia_solo_del_proxy(entorno, monkeypatch):  # noqa: F811
    monkeypatch.setenv("PROXY_DE_CONFIANZA", PROXY)
    crear = Mock(return_value=object())
    escuchar = Mock()
    monkeypatch.setattr(servir, "create_app", crear)
    monkeypatch.setattr(servir, "serve", escuchar)
    assert servir.main([]) == 0
    ajustes = escuchar.call_args.kwargs
    assert ajustes["trusted_proxy"] == PROXY
    assert ajustes["trusted_proxy_count"] == 1
    assert ajustes["trusted_proxy_headers"] == {"x-forwarded-for", "x-forwarded-proto"}
    assert ajustes.get("clear_untrusted_proxy_headers", True) is True


@pytest.fixture
def detras_de_caddy(app, monkeypatch):
    """La aplicación como la sirve Waitress con PROXY_DE_CONFIANZA (su propio middleware)."""
    admin_sesion.reiniciar()
    ajustes = replace(app.config["REMATE"], admin_clave_hash=generate_password_hash(CLAVE))
    monkeypatch.setitem(app.config, "REMATE", ajustes)
    envuelta = proxy_headers_middleware(
        app, **servir.ajustes_de_proxy(replace(ajustes, proxy_de_confianza=PROXY))
    )
    yield Client(envuelta)
    admin_sesion.reiniciar()


def _entrar(cliente, clave, desde, equipo=None, https=False):
    cabeceras = {}
    if equipo:
        cabeceras["X-Forwarded-For"] = equipo
    if https:
        cabeceras["X-Forwarded-Proto"] = "https"
    return cliente.post(
        "/api/admin/sesion",
        json={"clave": clave},
        headers=cabeceras,
        environ_base={"REMOTE_ADDR": desde},
    )


def test_detras_del_proxy_el_bloqueo_sigue_siendo_por_equipo(detras_de_caddy):
    for _ in range(admin_sesion.MAXIMO_FALLOS):
        _entrar(detras_de_caddy, "mala", PROXY, "10.0.0.66")
    assert _entrar(detras_de_caddy, CLAVE, PROXY, "10.0.0.66").status_code == 429
    assert _entrar(detras_de_caddy, CLAVE, PROXY, "10.0.0.5").status_code == 200


def test_con_https_en_el_proxy_la_cookie_es_secure(detras_de_caddy):
    respuesta = _entrar(detras_de_caddy, CLAVE, PROXY, "10.0.0.5", https=True)
    assert respuesta.status_code == 200
    assert "Secure" in respuesta.headers["Set-Cookie"]


def test_un_equipo_que_no_es_el_proxy_no_puede_falsear_su_ip(detras_de_caddy):
    """Quien llega directo al puerto de ReMate no se libra del bloqueo cambiando X-Forwarded-For,
    ni se hace pasar por https."""
    for intento in range(admin_sesion.MAXIMO_FALLOS):
        _entrar(detras_de_caddy, "mala", "10.0.0.66", f"10.9.9.{intento}")
    bloqueado = _entrar(detras_de_caddy, CLAVE, "10.0.0.66", "10.9.9.99", https=True)
    assert bloqueado.status_code == 429
    admin_sesion.reiniciar()
    directo = _entrar(detras_de_caddy, CLAVE, "10.0.0.66", https=True)
    assert "Secure" not in directo.headers["Set-Cookie"]
