"""CU-003 — Reglas de negocio de las listas de proveedores y peticionarios (datos inventados)."""

import pytest

from app.modelos.listas import Peticionario, Proveedor
from app.servicios import listas
from app.servicios.listas import CorreoDuplicado, DatosNoValidos


@pytest.fixture
def sesion(app):
    fabrica = app.extensions["remate.sesiones"]
    with fabrica() as s:
        yield s
        s.rollback()
        s.query(Proveedor).delete()
        s.query(Peticionario).delete()
        s.commit()


def test_orden_a_z_sin_tildes_ni_mayusculas(sesion):
    for nombre, email in [
        ("TORNIMEC", "u@ej.example"),
        ("Abedul", "a@ej.example"),
        ("ÁBACO TEC", "b@ej.example"),
    ]:
        listas.crear(sesion, Proveedor, nombre, email)
    nombres = [p.nombre for p in listas.listar(sesion, Proveedor)]
    assert nombres == ["ÁBACO TEC", "Abedul", "TORNIMEC"]


def test_correo_se_guarda_normalizado(sesion):
    proveedor, _ = listas.crear(
        sesion, Proveedor, "  Talleres   Alfa ", "  Ofertas@Talleres-Alfa.EXAMPLE "
    )
    assert proveedor.email == "ofertas@talleres-alfa.example"
    assert proveedor.nombre == "Talleres Alfa"


def test_correo_duplicado_sin_distinguir_mayusculas(sesion):
    existente, _ = listas.crear(sesion, Proveedor, "Industrias Beta", "ventas@beta.example")
    with pytest.raises(CorreoDuplicado) as error:
        listas.crear(sesion, Proveedor, "Beta", "VENTAS@beta.example")
    assert error.value.existente.id == existente.id


@pytest.mark.parametrize("email", ["sin-arroba.example", "con espacio@beta.example", ""])
def test_correo_no_valido(sesion, email):
    with pytest.raises(DatosNoValidos):
        listas.crear(sesion, Proveedor, "Beta", email)


def test_nombre_vacio(sesion):
    with pytest.raises(DatosNoValidos):
        listas.crear(sesion, Peticionario, "   ", "ana@empresa.example")


def test_nombre_repetido_con_otro_correo_avisa(sesion):
    listas.crear(sesion, Proveedor, "Mecanizados Norte", "a@norte.example")
    _, avisos = listas.crear(sesion, Proveedor, "mecanizados norte", "b@norte.example")
    assert avisos == ["Ya existe otro registro con el nombre «Mecanizados Norte»."]


def test_inactivos_no_se_listan_por_defecto(sesion):
    proveedor, _ = listas.crear(sesion, Proveedor, "Gamma", "g@gamma.example")
    listas.actualizar(sesion, Proveedor, proveedor.id, activo=False)
    assert listas.listar(sesion, Proveedor) == []
    assert [p.id for p in listas.listar(sesion, Proveedor, incluir_inactivos=True)] == [
        proveedor.id
    ]


def test_actualizar_a_correo_existente(sesion):
    listas.crear(sesion, Peticionario, "Ana Pérez", "ana@empresa.example")
    luis, _ = listas.crear(sesion, Peticionario, "Luis Prueba", "luis@empresa.example")
    with pytest.raises(CorreoDuplicado):
        listas.actualizar(sesion, Peticionario, luis.id, email="ANA@empresa.example")


def test_actualizar_inexistente(sesion):
    assert listas.actualizar(sesion, Proveedor, 999999, nombre="X") is None
