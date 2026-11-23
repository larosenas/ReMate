"""CU-002 — Pruebas de la solicitud de ofertas (la IA se simula; nunca se llama a la red)."""

import io
from email import message_from_bytes
from email.policy import default
from types import SimpleNamespace

import pytest

from app.modelos.listas import Peticionario, Proveedor
from app.modelos.necesidades import Necesidad
from app.servicios import solicitudes

pytestmark = pytest.mark.usefixtures("limpiar")


@pytest.fixture
def datos(app, cliente):
    """Una necesidad con un adjunto, dos proveedores activos, uno inactivo y una peticionaria."""
    with app.extensions["remate.sesiones"]() as s:
        ana = Peticionario(nombre_completo="Ana Prueba", email="ana@ejemplo.test")
        zeta = Proveedor(nombre="Zeta Mecanizados", email="ofertas@zeta.test")
        acme = Proveedor(nombre="Acme", email="ventas@acme.test")
        baja = Proveedor(nombre="Baja SL", email="baja@baja.test", activo=False)
        s.add_all([ana, zeta, acme, baja])
        s.commit()
        ids = {"ana": ana.id, "zeta": zeta.id, "acme": acme.id, "baja": baja.id}
    respuesta = cliente.post(
        "/api/necesidades",
        data={
            "titulo": "Rodamiento roto",
            "proyecto": "Línea 3",
            "peticionario_id": str(ids["ana"]),
            "descripcion": "Necesitamos 4 rodamientos 6204-2RS.",
            "adjuntos": [(io.BytesIO(b"%PDF plano"), "plano.pdf")],
        },
        content_type="multipart/form-data",
    )
    necesidad = respuesta.json
    ids["necesidad"] = necesidad["id"]
    ids["codigo"] = necesidad["codigo"]
    ids["adjunto"] = necesidad["adjuntos"][0]["id"]
    return ids


def ruta(datos, final=""):
    return f"/api/necesidades/{datos['necesidad']}/solicitud{final}"


def solicitud(datos, **cambios):
    cuerpo = {
        "peticionario_id": datos["ana"],
        "proveedor_ids": [datos["zeta"], datos["acme"]],
        "adjunto_ids": [datos["adjunto"]],
        "cuerpo": "Buenos días:\n\nPedimos oferta.\n\nUn saludo,\nAna Prueba\nIndustrias Ficticias",
        # Con menos de 3 proveedores hace falta el motivo.
        "motivo_pocos_proveedores": "ser los únicos homologados para esta pieza",
    }
    cuerpo.update(cambios)
    return cuerpo


def test_borrador_con_la_descripcion_del_ingeniero(cliente, datos):
    """Sin IA (en las pruebas no hay clave), la parte central es la descripción tal cual."""
    respuesta = cliente.post(ruta(datos, "/borrador"), json={"adjunto_ids": [datos["adjunto"]]})
    assert respuesta.status_code == 200
    borrador = respuesta.json
    assert borrador["asunto"] == f"{datos['codigo']} | Línea 3 | Rodamiento roto"
    assert borrador["cuerpo"].startswith("Buenos días:")
    assert "Necesitamos 4 rodamientos 6204-2RS." in borrador["cuerpo"]
    assert f"la referencia {datos['codigo']} en el asunto" in borrador["cuerpo"]
    assert "Adjuntamos la documentación disponible." in borrador["cuerpo"]
    # Siempre se pide el precio y el plazo de entrega, pero no se exige un formato de oferta.
    assert "indiquen por favor el precio y el plazo de entrega." in borrador["cuerpo"]
    assert "rogamos" not in borrador["cuerpo"]
    assert "precio unitario" not in borrador["cuerpo"]
    assert borrador["cuerpo"].rstrip().endswith("Ana Prueba\nIndustrias Ficticias")
    assert borrador["avisos"] == [solicitudes.AVISO_SIN_IA]
    assert borrador["con_ia"] is False


def test_borrador_redactado_por_la_ia(cliente, datos, monkeypatch):
    """CU-002 — La IA recibe la descripción y los nombres de los adjuntos (ADR 0011)."""
    recibido = {}

    def redactar(_config, descripcion, nombres_adjuntos):
        recibido.update(descripcion=descripcion, adjuntos=nombres_adjuntos)
        return {"peticion": "Solicitamos 4 rodamientos 6204-2RS.", "avisos": ["Revisa el plano."]}

    monkeypatch.setattr(solicitudes.ia, "redactar_peticion", redactar)
    borrador = cliente.post(ruta(datos, "/borrador"), json={"adjunto_ids": [datos["adjunto"]]}).json
    assert recibido == {
        "descripcion": "Necesitamos 4 rodamientos 6204-2RS.",
        "adjuntos": ["plano.pdf"],
    }
    assert "Solicitamos 4 rodamientos 6204-2RS." in borrador["cuerpo"]
    assert "Necesitamos" not in borrador["cuerpo"]
    assert borrador["avisos"] == ["Revisa el plano."]
    assert borrador["con_ia"] is True


def test_borrador_sin_adjuntos_no_dice_que_se_adjunta(cliente, datos):
    borrador = cliente.post(ruta(datos, "/borrador"), json={}).json
    assert "Adjuntamos" not in borrador["cuerpo"]


@pytest.mark.parametrize(
    ("descripcion", "avisa"),
    [
        ("Se han partido los rodamientos de la línea.", True),
        ("Necesitamos dos rodamientos.", False),
        ("Tornillos M8, 50 unidades.", False),
        # «dos» dentro de otra palabra no es una cantidad.
        ("Rodamientos para los todos los ejes.", True),
    ],
)
def test_avisa_si_la_descripcion_no_dice_cuantas_unidades(app, cliente, datos, descripcion, avisa):
    """Si la IA falla (CU-002): sin cantidad, el proveedor no sabe cuánto ofertar."""
    with app.extensions["remate.sesiones"]() as s:
        s.get(Necesidad, datos["necesidad"]).descripcion = descripcion
        s.commit()
    borrador = cliente.post(ruta(datos, "/borrador"), json={}).json
    sin_cantidad = [solicitudes.AVISO_SIN_CANTIDAD] if avisa else []
    assert borrador["avisos"] == [solicitudes.AVISO_SIN_IA, *sin_cantidad]


def test_borrador_con_adjunto_ajeno(cliente, datos):
    respuesta = cliente.post(ruta(datos, "/borrador"), json={"adjunto_ids": [999999]})
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "adjunto_ids"}


def test_genera_el_eml_y_pasa_a_en_cotizacion(cliente, datos):
    respuesta = cliente.post(ruta(datos), json=solicitud(datos))
    assert respuesta.status_code == 200, respuesta.json
    necesidad = respuesta.json
    assert necesidad["estado"] == "en_cotizacion"
    assert [p["nombre"] for p in necesidad["proveedores_solicitados"]] == [
        "Acme",
        "Zeta Mecanizados",
    ]
    assert necesidad["historial"][-1]["estado_anterior"] == "necesidad_creada"
    assert necesidad["historial"][-1]["estado_nuevo"] == "en_cotizacion"
    # El .eml no aparece entre los adjuntos de la necesidad.
    assert [a["nombre_archivo"] for a in necesidad["adjuntos"]] == ["plano.pdf"]
    assert necesidad["solicitud_eml"]["nombre_archivo"].endswith("solicitud de oferta.eml")

    descarga = cliente.get(ruta(datos, ".eml"))
    assert descarga.status_code == 200
    correo = message_from_bytes(descarga.data, policy=default)
    assert correo["Subject"] == f"{datos['codigo']} | Línea 3 | Rodamiento roto"
    assert correo["Bcc"] == "ofertas@zeta.test, ventas@acme.test"
    assert correo["To"] is None
    assert correo["X-Unsent"] == "1"
    # El .eml usa saltos de línea CRLF, como exige el formato de correo.
    texto = correo.get_body(("plain",)).get_content().replace("\r\n", "\n")
    assert texto.rstrip().endswith("Ana Prueba\nIndustrias Ficticias")
    [adjunto] = list(correo.iter_attachments())
    assert adjunto.get_filename() == "plano.pdf"
    assert adjunto.get_content() == b"%PDF plano"


def test_sin_proveedores_no_genera_nada(cliente, datos):
    respuesta = cliente.post(ruta(datos), json=solicitud(datos, proveedor_ids=[]))
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "proveedor_ids"}
    detalle = cliente.get(f"/api/necesidades/{datos['necesidad']}").json
    assert detalle["estado"] == "necesidad_creada"
    assert detalle["solicitud_eml"] is None
    assert cliente.get(ruta(datos, ".eml")).status_code == 404


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"proveedor_ids": ["baja"]}, "proveedor_ids"),
        ({"cuerpo": "   "}, "cuerpo"),
        ({"peticionario_id": 999999}, "peticionario_id"),
    ],
)
def test_datos_no_validos(cliente, datos, cambio, campo):
    if cambio.get("proveedor_ids") == ["baja"]:
        cambio = {"proveedor_ids": [datos["baja"]]}
    respuesta = cliente.post(ruta(datos), json=solicitud(datos, **cambio))
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": campo}


def test_quitar_un_adjunto_no_lo_borra_de_la_necesidad(cliente, datos):
    cliente.post(ruta(datos), json=solicitud(datos, adjunto_ids=[]))
    correo = message_from_bytes(cliente.get(ruta(datos, ".eml")).data, policy=default)
    assert list(correo.iter_attachments()) == []
    detalle = cliente.get(f"/api/necesidades/{datos['necesidad']}").json
    assert [a["nombre_archivo"] for a in detalle["adjuntos"]] == ["plano.pdf"]


def test_no_se_repite_la_solicitud(cliente, datos):
    assert cliente.post(ruta(datos), json=solicitud(datos)).status_code == 200
    segunda = cliente.post(ruta(datos), json=solicitud(datos))
    assert segunda.status_code == 409
    assert segunda.json["error"] == "transicion_no_permitida"
    assert cliente.post(ruta(datos, "/borrador"), json={}).status_code == 409


def test_anadir_adjuntos_solo_en_necesidad_creada(cliente, datos):
    url = f"/api/necesidades/{datos['necesidad']}/adjuntos"
    respuesta = cliente.post(
        url,
        data={"adjuntos": [(io.BytesIO(b"hoja"), "medidas.xlsx")]},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 201
    assert [a["nombre_archivo"] for a in respuesta.json] == ["medidas.xlsx"]
    cliente.post(ruta(datos), json=solicitud(datos))
    tarde = cliente.post(
        url, data={"adjuntos": [(io.BytesIO(b"x"), "x.txt")]}, content_type="multipart/form-data"
    )
    assert tarde.status_code == 409


def test_listado_de_necesidades(cliente, datos):
    [resumen] = cliente.get("/api/necesidades").json
    assert resumen["codigo"] == datos["codigo"]
    assert resumen["estado_texto"] == "Necesidad creada"


def test_necesidad_inexistente(cliente):
    assert cliente.post("/api/necesidades/999999/solicitud/borrador", json={}).status_code == 404
    assert cliente.get("/api/necesidades/999999/solicitud.eml").status_code == 404


def test_corregir_los_datos_antes_de_pedir_ofertas(cliente, datos):
    url = f"/api/necesidades/{datos['necesidad']}"
    nuevos = {
        "titulo": "Rodamientos de la cinta",
        "proyecto": "Línea 3",
        "peticionario_id": datos["ana"],
        "descripcion": "  Necesitamos 6 rodamientos 6204-2RS de acero inoxidable.  ",
    }
    respuesta = cliente.put(url, json=nuevos)
    assert respuesta.status_code == 200
    assert respuesta.json["codigo"] == datos["codigo"]
    assert respuesta.json["titulo"] == "Rodamientos de la cinta"
    assert (
        respuesta.json["descripcion"] == "Necesitamos 6 rodamientos 6204-2RS de acero inoxidable."
    )
    assert respuesta.json["estado"] == "necesidad_creada"

    vacia = cliente.put(url, json={**nuevos, "descripcion": " "})
    assert vacia.status_code == 400
    assert vacia.json["detalles"] == {"campo": "descripcion"}

    cliente.post(ruta(datos), json=solicitud(datos))
    tarde = cliente.put(url, json=nuevos)
    assert tarde.status_code == 409
    assert tarde.json["error"] == "transicion_no_permitida"


def test_corregir_una_necesidad_inexistente(cliente, datos):
    respuesta = cliente.put(
        "/api/necesidades/999999",
        json={"titulo": "t", "proyecto": "p", "peticionario_id": datos["ana"], "descripcion": "d"},
    )
    assert respuesta.status_code == 404


def test_cancelar_con_motivo(cliente, datos):
    url = f"/api/necesidades/{datos['necesidad']}/cancelar"
    sin_motivo = cliente.post(url, json={"peticionario_id": datos["ana"], "motivo": "  "})
    assert sin_motivo.status_code == 400
    assert sin_motivo.json["detalles"] == {"campo": "motivo"}

    respuesta = cliente.post(
        url, json={"peticionario_id": datos["ana"], "motivo": "Se ha reparado la pieza."}
    )
    assert respuesta.status_code == 200
    assert respuesta.json["estado"] == "cancelada"
    assert respuesta.json["motivo_cancelacion"] == "Se ha reparado la pieza."
    assert respuesta.json["historial"][-1]["estado_anterior"] == "necesidad_creada"
    assert respuesta.json["historial"][-1]["estado_nuevo"] == "cancelada"

    otra_vez = cliente.post(url, json={"peticionario_id": datos["ana"], "motivo": "x"})
    assert otra_vez.status_code == 409
    # Cancelada, ya no se pueden pedir ofertas.
    assert cliente.post(ruta(datos), json=solicitud(datos)).status_code == 409


def test_cancelar_en_cotizacion(cliente, datos):
    cliente.post(ruta(datos), json=solicitud(datos))
    respuesta = cliente.post(
        f"/api/necesidades/{datos['necesidad']}/cancelar",
        json={"peticionario_id": datos["ana"], "motivo": "Ya no hace falta."},
    )
    assert respuesta.status_code == 200
    assert respuesta.json["historial"][-1]["estado_anterior"] == "en_cotizacion"


def test_adjunto_que_falta_en_disco(cliente, datos, app):
    from app.integraciones import archivos
    from app.modelos.necesidades import Adjunto

    with app.extensions["remate.sesiones"]() as s:
        ruta = s.get(Adjunto, datos["adjunto"]).ruta
    archivos.borrar(app.config["REMATE"].archivos_dir, ruta)
    respuesta = cliente.post(ruta_solicitud(datos), json=solicitud(datos))
    assert respuesta.status_code == 400
    assert "no está en el servidor" in respuesta.json["mensaje"]


def ruta_solicitud(datos):
    return ruta(datos)


def test_no_se_cancela_una_necesidad_entregada(cliente, datos, app):
    from app.modelos.necesidades import Necesidad

    with app.extensions["remate.sesiones"]() as s:
        s.get(Necesidad, datos["necesidad"]).estado = "entregado"
        s.commit()
    respuesta = cliente.post(
        f"/api/necesidades/{datos['necesidad']}/cancelar",
        json={"peticionario_id": datos["ana"], "motivo": "x"},
    )
    assert respuesta.status_code == 409


@pytest.mark.parametrize(
    "frase",
    [
        "Buenos días:",
        "les solicitamos oferta para lo siguiente:",
        "En su oferta, indiquen por favor el precio y el plazo de entrega.",
        "Adjuntamos la documentación disponible.",
        "Para facilitar el seguimiento, mantengan por favor la referencia",
        "Quedamos a la espera de su respuesta.",
    ],
)
def test_las_instrucciones_de_la_ia_describen_la_plantilla_de_verdad(frase):
    # La IA sabe qué dice el resto del correo para no repetirlo. Si cambia la plantilla,
    # hay que cambiar también INSTRUCCIONES_PETICION.
    necesidad = SimpleNamespace(
        codigo="2026111002", peticionario=SimpleNamespace(nombre_completo="Ana Prueba")
    )
    cuerpo = solicitudes.componer_cuerpo(necesidad, "Fabricación de dos piezas.", True)
    assert frase in cuerpo
    assert frase in solicitudes.ia.INSTRUCCIONES_PETICION


# --- 3 proveedores como mínimo ----------------------------------------------------------------


def test_con_menos_de_3_proveedores_hace_falta_el_motivo(cliente, datos):
    for motivo in (None, "", "   ", "."):
        respuesta = cliente.post(
            ruta(datos), json=solicitud(datos, motivo_pocos_proveedores=motivo)
        )
        assert respuesta.status_code == 400, motivo
        assert respuesta.json["detalles"] == {"campo": "motivo_pocos_proveedores"}
    assert (
        cliente.get(f"/api/necesidades/{datos['necesidad']}").json["estado"] == "necesidad_creada"
    )


def test_el_motivo_se_guarda_sin_punto_final(cliente, datos):
    respuesta = cliente.post(
        ruta(datos), json=solicitud(datos, motivo_pocos_proveedores="  ser el\nfabricante.  ")
    )
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json["motivo_pocos_proveedores"] == "ser el fabricante"


def test_con_3_proveedores_no_hace_falta_motivo_ni_se_guarda(app, cliente, datos):
    with app.extensions["remate.sesiones"]() as s:
        beta = Proveedor(nombre="Beta", email="beta@beta.test")
        s.add(beta)
        s.commit()
        beta_id = beta.id
    tres = [datos["zeta"], datos["acme"], beta_id]
    respuesta = cliente.post(
        ruta(datos),
        json=solicitud(datos, proveedor_ids=tres, motivo_pocos_proveedores="no hace falta"),
    )
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json["motivo_pocos_proveedores"] is None


def test_si_la_ia_esta_ocupada_se_dice_al_redactar(cliente, datos, monkeypatch):
    """Al redactar sale el aviso general «No se ha podido usar la IA»; si solo está ocupada, se
    dice delante, para que se sepa que basta con repetir."""
    from app.integraciones import ia

    def ocupada(*a, **k):
        raise ia.IAOcupada("La IA está atendiendo muchas peticiones a la vez.")

    monkeypatch.setattr(solicitudes.ia, "redactar_peticion", ocupada)
    borrador = cliente.post(ruta(datos, "/borrador"), json={"adjunto_ids": [datos["adjunto"]]}).json
    assert borrador["avisos"] == [
        f"La IA está atendiendo muchas peticiones a la vez. {solicitudes.AVISO_SIN_IA}"
    ]
    assert ia.aviso_sin_ia(ia.ErrorIA("Otra cosa."), "Sin IA.") == "Sin IA."
