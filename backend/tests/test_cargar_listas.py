"""CU-003 — Comando `flask cargar-listas` (datos inventados, nunca los correos reales)."""

import pytest

from app.modelos.listas import Peticionario, Proveedor

pytestmark = pytest.mark.usefixtures("listas_vacias")

CSV = (
    "tipo;nombre;correo\n"
    "proveedor;Mecanizados Norte;ofertas@norte.example\n"
    "proveedor;Talleres Alfa;info@alfa.example\n"
    "peticionario;Ana Pérez Ruiz;ana@empresa.example\n"
)


def _ejecutar(app, ruta):
    return app.test_cli_runner().invoke(args=["cargar-listas", str(ruta)])


def test_carga_y_no_duplica_al_repetir(app, tmp_path):
    ruta = tmp_path / "listas.csv"
    ruta.write_text(CSV, encoding="utf-8")

    primera = _ejecutar(app, ruta)
    assert primera.exit_code == 0
    assert "Creados: 3" in primera.output

    segunda = _ejecutar(app, ruta)
    assert segunda.exit_code == 0
    assert "Creados: 0" in segunda.output
    assert "Omitidos (ya existían): 3" in segunda.output

    with app.extensions["remate.sesiones"]() as s:
        assert s.query(Proveedor).count() == 2
        assert s.query(Peticionario).count() == 1


def test_linea_mal_formada_se_informa_y_no_frena_las_demas(app, tmp_path):
    ruta = tmp_path / "listas.csv"
    ruta.write_text(
        "proveedor;Sin correo\n"
        "cliente;Otro;otro@ej.example\n"
        "proveedor;Correo malo;sin-arroba\n"
        "proveedor;Gamma;g@gamma.example\n",
        encoding="utf-8",
    )
    resultado = _ejecutar(app, ruta)
    assert resultado.exit_code == 1
    assert "Creados: 1" in resultado.output
    assert "Línea 1: Debe tener 3 columnas" in resultado.output
    assert "Línea 2: Tipo «cliente» no válido." in resultado.output
    assert "Línea 3: El correo «sin-arroba» no es válido." in resultado.output


def test_vaciar_listas_en_desarrollo(app, tmp_path):
    ruta = tmp_path / "listas.csv"
    ruta.write_text(CSV, encoding="utf-8")
    _ejecutar(app, ruta)
    resultado = app.test_cli_runner().invoke(args=["vaciar-listas"], input="y\n")
    assert resultado.exit_code == 0
    assert "Listas vaciadas." in resultado.output
    with app.extensions["remate.sesiones"]() as s:
        assert s.query(Proveedor).count() == 0
        assert s.query(Peticionario).count() == 0


def test_vaciar_listas_se_puede_cancelar(app, tmp_path):
    ruta = tmp_path / "listas.csv"
    ruta.write_text(CSV, encoding="utf-8")
    _ejecutar(app, ruta)
    resultado = app.test_cli_runner().invoke(args=["vaciar-listas"], input="n\n")
    assert resultado.exit_code != 0
    with app.extensions["remate.sesiones"]() as s:
        assert s.query(Proveedor).count() == 2


def test_vaciar_listas_bloqueado_en_produccion(app, monkeypatch):
    from dataclasses import replace

    monkeypatch.setitem(app.config, "REMATE", replace(app.config["REMATE"], entorno="production"))
    resultado = app.test_cli_runner().invoke(args=["vaciar-listas", "--si"])
    assert resultado.exit_code == 1
    assert "solo se puede usar con APP_ENV=development" in resultado.output


def test_vaciar_listas_no_borra_si_hay_necesidades(app, tmp_path):
    from app.modelos.necesidades import CambioEstado, Necesidad

    ruta = tmp_path / "listas.csv"
    ruta.write_text(CSV, encoding="utf-8")
    _ejecutar(app, ruta)
    with app.extensions["remate.sesiones"]() as s:
        peticionario = s.query(Peticionario).first()
        s.add(
            Necesidad(
                codigo="2026102201",
                titulo="t",
                proyecto="p",
                descripcion="d",
                estado="necesidad_creada",
                peticionario=peticionario,
            )
        )
        s.commit()
    try:
        resultado = app.test_cli_runner().invoke(args=["vaciar-listas", "--si"])
        assert resultado.exit_code == 1
        assert "Hay necesidades guardadas" in resultado.output
    finally:
        with app.extensions["remate.sesiones"]() as s:
            s.query(CambioEstado).delete()
            s.query(Necesidad).delete()
            s.commit()
