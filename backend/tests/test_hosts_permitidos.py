"""Protección frente a DNS rebinding. Con APP_URL (o HOSTS_PERMITIDOS), solo se atienden
peticiones dirigidas a la dirección de ReMate."""

from dataclasses import replace

import pytest


@pytest.fixture
def con_app_url(app, monkeypatch):
    config = replace(app.config["REMATE"], app_url="http://10.1.2.3:2905")
    monkeypatch.setitem(app.config, "REMATE", config)
    return app


def _salud(cliente, host):
    return cliente.get("/api/salud", headers={"Host": host})


def test_con_la_ip_de_app_url_y_localhost_si(con_app_url):
    cliente = con_app_url.test_client()
    for host in ("10.1.2.3:2905", "localhost:2905", "127.0.0.1:2905", "[::1]:2905"):
        assert _salud(cliente, host).status_code != 400, host


def test_otro_nombre_que_apunta_al_servidor_no(con_app_url):
    cliente = con_app_url.test_client()
    respuesta = _salud(cliente, "atacante.example:2905")
    assert respuesta.status_code == 400
    assert respuesta.json["error"] == "host_no_permitido"
    cambio = cliente.post(
        "/api/proveedores",
        json={"nombre": "X", "email": "x@x.example"},
        headers={"Host": "atacante.example:2905", "Origin": "http://atacante.example:2905"},
    )
    assert cambio.status_code == 400


def test_hosts_permitidos_anade_nombres(con_app_url, monkeypatch):
    config = replace(con_app_url.config["REMATE"], hosts_permitidos=("remate.empresa.local",))
    monkeypatch.setitem(con_app_url.config, "REMATE", config)
    cliente = con_app_url.test_client()
    assert _salud(cliente, "REMATE.empresa.local:2905").status_code != 400
    assert _salud(cliente, "10.1.2.3:2905").status_code != 400


def test_sin_app_url_no_se_comprueba(app):
    assert _salud(app.test_client(), "cualquiera.example:5000").status_code != 400


def test_la_variable_se_lee_del_entorno(monkeypatch):
    from app.config import cargar_config

    monkeypatch.setenv("HOSTS_PERMITIDOS", " Remate.Local , 10.0.0.9 ,")
    assert cargar_config().hosts_permitidos == ("remate.local", "10.0.0.9")


def test_app_url_mal_escrita_o_vacia_en_produccion(monkeypatch):
    """Sin `http://` toda la aplicación respondería «host_no_permitido»; vacía en producción, la
    protección quedaría desactivada sin avisar. Las dos cosas se detectan al cargar."""
    from app.config import ErrorDeConfiguracion, cargar_config

    monkeypatch.setenv("APP_URL", "remate.example:2905")
    with pytest.raises(ErrorDeConfiguracion, match="dirección completa"):
        cargar_config()
    monkeypatch.setenv("APP_URL", "")
    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(ErrorDeConfiguracion, match="Falta APP_URL"):
        cargar_config()
    monkeypatch.setenv("APP_URL", "http://10.1.2.3:2905/")
    assert cargar_config().app_url == "http://10.1.2.3:2905"


def test_hosts_permitidos_con_puerto_se_quita(monkeypatch):
    from app.config import cargar_config

    monkeypatch.setenv("HOSTS_PERMITIDOS", "remate.example:2905, [::1]:2905, http://otro:80")
    assert cargar_config().hosts_permitidos == ("remate.example", "::1", "otro")
