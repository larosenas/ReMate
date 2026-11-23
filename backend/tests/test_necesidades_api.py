"""CU-001 — Pruebas de la API de necesidades."""

import io
from datetime import UTC, datetime

import pytest
from sqlalchemy import event

from app.integraciones.archivos import nombre_limpio
from app.modelos.listas import Peticionario
from app.modelos.necesidades import CambioEstado, Necesidad

pytestmark = pytest.mark.usefixtures("limpiar")


@pytest.fixture
def ana_id(app):
    with app.extensions["remate.sesiones"]() as s:
        p = Peticionario(nombre_completo="Ana Prueba", email="ana@ejemplo.test")
        s.add(p)
        s.commit()
        return p.id


def formulario(ana_id, **cambios):
    datos = {
        "titulo": "Rodamiento roto",
        "proyecto": "2026",
        "peticionario_id": str(ana_id),
        "descripcion": "Cambiar el rodamiento 6204.",
    }
    datos.update(cambios)
    return datos


def test_cu010_panel_no_consulta_el_historial_por_cada_necesidad(cliente, app, ana_id):
    """El listado conserva la fecha del último estado con una sola consulta."""
    ids = [cliente.post("/api/necesidades", data=formulario(ana_id)).json["id"] for _ in range(3)]
    ultima = datetime(2026, 11, 2, 10, tzinfo=UTC)
    with app.extensions["remate.sesiones"]() as sesion:
        n = sesion.get(Necesidad, ids[0])
        n.estado = "en_cotizacion"
        n.historial.append(
            CambioEstado(
                estado_anterior="necesidad_creada",
                estado_nuevo="en_cotizacion",
                peticionario_id=ana_id,
                cambiado_en=ultima,
            )
        )
        sesion.commit()
    consultas = []

    def contar(conexion, cursor, sentencia, parametros, contexto, muchos):
        if sentencia.lstrip().upper().startswith("SELECT"):
            consultas.append(sentencia)

    motor = app.extensions["remate.motor"]
    event.listen(motor, "before_cursor_execute", contar)
    try:
        respuesta = cliente.get("/api/necesidades")
    finally:
        event.remove(motor, "before_cursor_execute", contar)
    assert respuesta.status_code == 200
    assert [n["id"] for n in respuesta.json] == list(reversed(ids))
    assert respuesta.json[-1]["estado"] == "en_cotizacion"
    assert datetime.fromisoformat(respuesta.json[-1]["estado_desde"]) == ultima
    assert len(consultas) == 1


def test_crea_y_consulta_una_necesidad(cliente, ana_id):
    datos = formulario(ana_id, adjuntos=[(io.BytesIO(b"contenido"), "foto pieza.jpg")])
    respuesta = cliente.post("/api/necesidades", data=datos, content_type="multipart/form-data")
    assert respuesta.status_code == 201, respuesta.json
    creada = respuesta.json
    assert len(creada["codigo"]) == 10
    assert creada["codigo"].endswith("01")
    assert creada["estado"] == "necesidad_creada"
    assert creada["estado_texto"] == "Necesidad creada"
    # «2026» llega como texto, no como número.
    assert creada["proyecto"] == "2026"
    assert creada["peticionario"] == {"id": ana_id, "nombre_completo": "Ana Prueba"}
    assert creada["historial"][0]["estado_nuevo"] == "necesidad_creada"
    [adjunto] = creada["adjuntos"]
    assert adjunto["nombre_archivo"] == "foto pieza.jpg"

    detalle = cliente.get(f"/api/necesidades/{creada['id']}")
    assert detalle.status_code == 200
    assert detalle.json["codigo"] == creada["codigo"]

    descarga = cliente.get(f"/api/necesidades/{creada['id']}/adjuntos/{adjunto['id']}")
    assert descarga.status_code == 200
    assert descarga.data == b"contenido"
    assert "attachment" in descarga.headers["Content-Disposition"]


def test_sin_adjuntos(cliente, ana_id):
    respuesta = cliente.post(
        "/api/necesidades", data=formulario(ana_id), content_type="multipart/form-data"
    )
    assert respuesta.status_code == 201
    assert respuesta.json["adjuntos"] == []


def test_campo_vacio_devuelve_400_con_el_campo(cliente, ana_id):
    respuesta = cliente.post(
        "/api/necesidades", data=formulario(ana_id, titulo="  "), content_type="multipart/form-data"
    )
    assert respuesta.status_code == 400
    assert respuesta.json["error"] == "datos_no_validos"
    assert respuesta.json["detalles"] == {"campo": "titulo"}


def test_falta_un_campo(cliente, ana_id):
    datos = formulario(ana_id)
    del datos["descripcion"]
    respuesta = cliente.post("/api/necesidades", data=datos, content_type="multipart/form-data")
    assert respuesta.status_code == 400
    assert "descripcion" in respuesta.json["detalles"]["campos"]


def test_peticionario_inexistente(cliente, ana_id):
    respuesta = cliente.post(
        "/api/necesidades",
        data=formulario(ana_id, peticionario_id="999999"),
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "peticionario_id"}


def test_adjunto_demasiado_grande_devuelve_413(cliente, ana_id):
    grande = io.BytesIO(b"0" * (25 * 1024 * 1024 + 1))
    respuesta = cliente.post(
        "/api/necesidades",
        data=formulario(ana_id, adjuntos=[(grande, "enorme.bin")]),
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 413
    assert respuesta.json["detalles"] == {"archivo": "enorme.bin"}


def test_subida_que_supera_el_total_devuelve_413(cliente, ana_id):
    """Cada archivo cabe en 25 MB, pero no se acepta cualquier total."""
    adjuntos = [(io.BytesIO(b"0" * (20 * 1024 * 1024)), f"parte{i}.bin") for i in range(6)]
    respuesta = cliente.post(
        "/api/necesidades",
        data=formulario(ana_id, adjuntos=adjuntos),
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 413
    assert respuesta.json["error"] == "subida_demasiado_grande"


def test_necesidad_o_adjunto_inexistente(cliente):
    assert cliente.get("/api/necesidades/999999").status_code == 404
    assert cliente.get("/api/necesidades/999999/adjuntos/1").status_code == 404


@pytest.mark.parametrize(
    ("nombre", "limpio"),
    [
        ("pla\r\nno.pdf", "plano.pdf"),
        ("plano\x00.pdf", "plano.pdf"),
        ("C:\\Usuarios\\ana\\plano.pdf", "plano.pdf"),
        ("carpeta/plano.pdf", "plano.pdf"),
        ("\r\n", "archivo"),
    ],
)
def test_nombre_de_archivo_limpio(nombre, limpio):
    """Un nombre con salto de línea (o NUL) rompería el .eml, la descarga y el guardado (error
    500). El navegador lo envía codificado (filename*=UTF-8''a%0D%0Ab.pdf)."""
    assert nombre_limpio(nombre) == limpio


def test_el_nombre_subido_se_guarda_sin_carpetas(cliente, ana_id):
    datos = formulario(ana_id)
    datos["adjuntos"] = [(io.BytesIO(b"%PDF"), "Usuarios/ana/plano.pdf")]
    respuesta = cliente.post("/api/necesidades", data=datos, content_type="multipart/form-data")
    assert respuesta.status_code == 201, respuesta.json
    [adjunto] = respuesta.json["adjuntos"]
    assert adjunto["nombre_archivo"] == "plano.pdf"
    descarga = cliente.get(f"/api/necesidades/{respuesta.json['id']}/adjuntos/{adjunto['id']}")
    assert descarga.status_code == 200
