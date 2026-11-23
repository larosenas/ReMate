"""CU-003 — API de las listas de proveedores y peticionarios (datos inventados)."""

import pytest

from app.modelos.listas import Peticionario, Proveedor

pytestmark = pytest.mark.usefixtures("listas_vacias")


def test_alta_y_listado_de_proveedores_ordenado(cliente):
    for nombre, email in [("TORNIMEC", "u@ej.example"), ("Abedul", "a@ej.example")]:
        assert (
            cliente.post("/api/proveedores", json={"nombre": nombre, "email": email}).status_code
            == 201
        )
    respuesta = cliente.get("/api/proveedores")
    assert respuesta.status_code == 200
    assert [p["nombre"] for p in respuesta.get_json()] == ["Abedul", "TORNIMEC"]


def test_alta_devuelve_registro_normalizado_y_avisos(cliente):
    cliente.post("/api/proveedores", json={"nombre": "Talleres Alfa", "email": "a@alfa.example"})
    respuesta = cliente.post(
        "/api/proveedores", json={"nombre": " talleres alfa ", "email": " B@Alfa.EXAMPLE "}
    )
    datos = respuesta.get_json()
    assert respuesta.status_code == 201
    assert datos["email"] == "b@alfa.example"
    assert datos["activo"] is True
    assert datos["avisos"] == ["Ya existe otro registro con el nombre «Talleres Alfa»."]


def test_correo_duplicado_devuelve_409_con_el_existente(cliente):
    primero = cliente.post("/api/proveedores", json={"nombre": "Beta", "email": "v@beta.example"})
    respuesta = cliente.post("/api/proveedores", json={"nombre": "Otra", "email": "V@beta.example"})
    assert respuesta.status_code == 409
    datos = respuesta.get_json()
    assert datos["error"] == "correo_duplicado"
    assert datos["detalles"]["existente"]["id"] == primero.get_json()["id"]


def test_correo_no_valido_devuelve_400(cliente):
    respuesta = cliente.post("/api/proveedores", json={"nombre": "Beta", "email": "sin-arroba"})
    assert respuesta.status_code == 400
    assert respuesta.get_json()["error"] == "datos_no_validos"
    assert respuesta.get_json()["detalles"]["campo"] == "email"


def test_falta_un_campo_devuelve_400(cliente):
    respuesta = cliente.post("/api/proveedores", json={"nombre": "Beta"})
    assert respuesta.status_code == 400
    assert respuesta.get_json()["error"] == "datos_no_validos"


def test_desactivar_y_ver_inactivos(cliente):
    proveedor = cliente.post(
        "/api/proveedores", json={"nombre": "Gamma", "email": "g@gamma.example"}
    )
    id_ = proveedor.get_json()["id"]
    respuesta = cliente.patch(f"/api/proveedores/{id_}", json={"activo": False})
    assert respuesta.status_code == 200
    assert respuesta.get_json()["activo"] is False
    assert cliente.get("/api/proveedores").get_json() == []
    todos = cliente.get("/api/proveedores?incluir_inactivos=true").get_json()
    assert [p["id"] for p in todos] == [id_]


def test_editar_inexistente_devuelve_404(cliente):
    respuesta = cliente.patch("/api/proveedores/999999", json={"nombre": "X"})
    assert respuesta.status_code == 404
    assert respuesta.get_json()["error"] == "no_encontrado"


def test_peticionarios_usan_nombre_completo(cliente):
    respuesta = cliente.post(
        "/api/peticionarios",
        json={"nombre_completo": "Ana Pérez Ruiz", "email": "ana@empresa.example"},
    )
    assert respuesta.status_code == 201
    assert respuesta.get_json()["nombre_completo"] == "Ana Pérez Ruiz"
    assert [p["nombre_completo"] for p in cliente.get("/api/peticionarios").get_json()] == [
        "Ana Pérez Ruiz"
    ]


def test_listas_aparecen_en_swagger(cliente):
    rutas = cliente.get("/api/docs/openapi.json").get_json()["paths"]
    assert "/api/proveedores" in rutas
    assert "/api/peticionarios/{id}" in rutas


# --- Baja definitiva ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ruta", "campo"), [("/api/proveedores", "nombre"), ("/api/peticionarios", "nombre_completo")]
)
def test_baja_definitiva_con_motivo(cliente, app, ruta, campo):
    registro = cliente.post(ruta, json={campo: "Antiguo", "email": "antiguo@alfa.example"}).json
    baja = f"{ruta}/{registro['id']}/baja"
    # Primero hay que desactivarlo.
    activo = cliente.post(baja, json={"motivo": "Duplicado"})
    assert activo.status_code == 409
    assert activo.json["error"] == "sigue_activo"
    assert cliente.patch(f"{ruta}/{registro['id']}", json={"activo": False}).status_code == 200
    # El motivo es obligatorio.
    sin_motivo = cliente.post(baja, json={"motivo": "   "})
    assert sin_motivo.status_code == 400
    assert sin_motivo.json["detalles"] == {"campo": "motivo"}

    assert (
        cliente.post(baja, json={"motivo": "Otro: se ha  fusionado con otra empresa"}).status_code
        == 204
    )
    # Ya no sale en ninguna lista, ni con los inactivos, y no se puede editar ni volver a eliminar.
    assert cliente.get(f"{ruta}?incluir_inactivos=true").json == []
    assert cliente.patch(f"{ruta}/{registro['id']}", json={"activo": True}).status_code == 404
    assert cliente.post(baja, json={"motivo": "x"}).status_code == 404
    modelo = Proveedor if campo == "nombre" else Peticionario
    with app.extensions["remate.sesiones"]() as s:
        guardado = s.get(modelo, registro["id"])
        assert guardado.motivo_eliminacion == "Otro: se ha fusionado con otra empresa"
        assert guardado.eliminado_en is not None
    # Su correo queda libre para otro registro, y no avisa de su nombre como repetido.
    nuevo = cliente.post(ruta, json={campo: "Antiguo", "email": "antiguo@alfa.example"})
    assert nuevo.status_code == 201
    assert nuevo.json["avisos"] == []


def test_baja_de_un_registro_que_no_existe(cliente):
    assert cliente.post("/api/proveedores/999999/baja", json={"motivo": "x"}).status_code == 404
