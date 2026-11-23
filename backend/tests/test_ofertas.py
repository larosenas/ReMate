"""CU-004 — Pruebas de las ofertas. La IA siempre se simula: nunca se llama a la red."""

import io
from datetime import UTC, date, datetime
from decimal import Decimal
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default
from types import SimpleNamespace

import pytest

from app.integraciones import correos_entrada, ia
from app.integraciones.correos_entrada import CorreoNoValido
from app.modelos.listas import Peticionario, Proveedor
from app.modelos.necesidades import Necesidad
from app.modelos.ofertas import Oferta
from app.servicios import adjudicacion as servicio_adjudicacion
from app.servicios import comparativa as servicio_comparativa
from app.servicios import condiciones
from app.servicios import ofertas as ofertas_servicio
from app.servicios.comparativa import destacados
from app.servicios.ofertas import _numero_ia, dia_del_correo, fecha_desde_plazo

pytestmark = pytest.mark.usefixtures("limpiar")


def eml(remitente="ventas@acme.test", fecha="Thu, 22 Oct 2026 09:15:00 +0200", html=False):
    mensaje = EmailMessage()
    mensaje["From"] = f"Acme Ventas <{remitente}>"
    mensaje["To"] = "ana@ejemplo.test"
    mensaje["Subject"] = "RE: 2026102301 | Línea 3 | Rodamiento roto"
    if fecha:
        mensaje["Date"] = fecha
    if html:
        mensaje.set_content(
            "<p>Precio: <b>120 &euro;</b></p><p>Plazo 4 semanas</p>", subtype="html"
        )
    else:
        mensaje.set_content("Les adjuntamos nuestra oferta. Plazo: 4 semanas.")
    return mensaje.as_bytes()


# --- Lector de .eml y plazos -----------------------------------------------------------------


def test_lee_fecha_remitente_asunto_y_cuerpo():
    leido = correos_entrada.leer("oferta.eml", eml())
    assert leido.fecha.isoformat() == "2026-10-22T09:15:00+02:00"
    assert leido.remitente == "ventas@acme.test"
    assert leido.asunto.startswith("RE: 2026102301")
    assert "Plazo: 4 semanas." in leido.cuerpo


def test_cuerpo_solo_en_html():
    leido = correos_entrada.leer("oferta.EML", eml(html=True))
    assert "Precio: 120 €" in leido.cuerpo
    assert "<p>" not in leido.cuerpo


@pytest.mark.parametrize(
    ("nombre", "datos", "mensaje"),
    [
        ("oferta.msg", b"cualquier cosa", "Guardar como"),
        ("oferta.pdf", b"%PDF", ".eml o .msg"),
        ("oferta.eml", b"esto no es un correo", "no parece un correo"),
    ],
)
def test_rechaza_lo_que_no_es_un_eml(nombre, datos, mensaje):
    with pytest.raises(CorreoNoValido, match=mensaje):
        correos_entrada.leer(nombre, datos)


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("4 semanas", date(2026, 11, 19)),
        # Con un rango se toma el número más alto.
        ("Plazo de entrega: 3-4 semanas", date(2026, 11, 19)),
        ("18 - 20 días", date(2026, 11, 11)),
        ("5 Sem.", date(2026, 11, 26)),
        # Al revés, con la unidad repetida o con palabras.
        ("20-18 días", date(2026, 11, 11)),
        ("18 días - 20 días", date(2026, 11, 11)),
        ("3 semanas a 4 semanas", date(2026, 11, 19)),
        ("tres a cuatro semanas", date(2026, 11, 19)),
        ("entre 18 y 20 días", date(2026, 11, 11)),
        ("5 semanas a partir del pedido", date(2026, 11, 26)),
        # Varios plazos en el texto: el más largo, aunque vaya detrás.
        ("18-20 días / 5 semanas", date(2026, 11, 26)),
        ("Distanciales 18 - 20 días; inserto y pines 5 Sem.", date(2026, 11, 26)),
        # Casos límite, raros pero posibles.
        ("1,5 semanas", date(2026, 11, 2)),
        ("1.5 months", date(2026, 12, 7)),
        ("mes y medio", date(2026, 12, 7)),
        ("2 meses y medio", date(2027, 1, 6)),
        ("48 horas", date(2026, 10, 24)),
        ("stock (24/48h)", date(2026, 10, 24)),
        ("treinta días", date(2026, 11, 21)),
        ("cuarenta y cinco días", date(2026, 12, 6)),
        ("veinticinco días", date(2026, 11, 16)),
        ("2 semanas + 3 días de transporte", date(2026, 11, 8)),
        ("4 semanas y 2 días", date(2026, 11, 21)),
        ("Plazo: 2 semanas. Validez de la oferta: 30 días", date(2026, 11, 5)),
        ("Entrega 3 semanas; pago a 60 días", date(2026, 11, 12)),
        ("6 semanas, garantía 12 meses", date(2026, 12, 3)),
        ("KW 50", None),
        # Fracciones, palabras, rangos y plazos junto a otras condiciones.
        ("dos meses y medio", date(2027, 1, 6)),
        ("tres semanas y media", date(2026, 11, 16)),
        ("1 semana 3 días", date(2026, 11, 1)),
        ("entre 2 semanas y 20 días", date(2026, 11, 11)),
        ("15 días - 3 semanas", date(2026, 11, 12)),
        ("de 3 semanas a 1 mes", date(2026, 11, 22)),
        ("3 weeks to 1 month", date(2026, 11, 22)),
        ("2 semanas / 10 días", date(2026, 11, 5)),
        ("Validez: 30 días / Entrega: 6 semanas", date(2026, 12, 3)),
        ("Tras validación de planos: 6 semanas", date(2026, 12, 3)),
        ("Pago por adelantado, entrega en 2 semanas", date(2026, 11, 5)),
        ("validez 30 días, plazo 4 semanas", date(2026, 11, 19)),
        ("Garantía 12 meses, entrega 3 semanas", date(2026, 11, 12)),
        ("45 días fecha factura", None),
        ("4 semanas, más 1 semana de transporte", date(2026, 11, 26)),
        ("4 semanas + transporte 1 semana", date(2026, 11, 26)),
        ("Dureza 58-62 HR", None),
        ("Ø20 h7, 4 semanas", date(2026, 11, 19)),
        # El pago, la validez o la garantía no son el plazo aunque vayan detrás o en el mismo
        # trozo de la frase.
        ("Entrega 3 semanas. Pago: 50 % a la firma y 50 % a 30 días", date(2026, 11, 12)),
        ("Entrega 3 semanas, pago 30, 60 y 90 días", date(2026, 11, 12)),
        ("Plazo 3 semanas. Garantía y soporte: 12 meses", date(2026, 11, 12)),
        ("Entrega 3 semanas; validez (30 días)", date(2026, 11, 12)),
        ("Entrega 3 semanas. Pago: transferencia / 30 días", date(2026, 11, 12)),
        (
            "Entrega 3 semanas. Forma de pago: recibo domiciliado con vencimiento a 60 días",
            date(2026, 11, 12),
        ),
        (
            "Entrega 2 semanas. Validez de esta oferta para su consideración: 90 días",
            date(2026, 11, 5),
        ),
        ("Entrega 3 semanas, 24 meses de garantía", date(2026, 11, 12)),
        ("Entrega 3 semanas y 24 meses de garantía", date(2026, 11, 12)),
        ("Delivery 4 weeks, 12 months warranty", date(2026, 11, 19)),
        ("Entrega: 4 semanas, 30 días de validez", date(2026, 11, 19)),
        ("Delivery 4 weeks, 30 days validity", date(2026, 11, 19)),
        ("3 semanas, 30 días netos", date(2026, 11, 12)),
        ("30 días de validez, entrega 4 semanas", date(2026, 11, 19)),
        ("4 semanas desde el pago de la factura proforma", date(2026, 11, 19)),
        ("3 semanas, 60 días F.F.", date(2026, 11, 12)),
        # Lo que se suma es el transporte o el montaje.
        ("4 semanas y 1 semana de transporte", date(2026, 11, 26)),
        ("4 semanas (más 1 semana de transporte)", date(2026, 11, 26)),
        ("10 días, 5 días de transporte", date(2026, 11, 6)),
        # Sigue siendo el más largo cuando no hay pago, validez ni garantía.
        ("Muestras 2 semanas, serie 6 semanas", date(2026, 12, 3)),
        ("2 semanas y 3 semanas", date(2026, 11, 12)),
        # El pago o la validez en otra línea, como verbo o con varias entregas; primero cuentan
        # los plazos con etiqueta de entrega.
        ("Entrega 5 semanas\nPago 90 días", date(2026, 11, 26)),
        ("Delivery 6 weeks\nPayment 30 days", date(2026, 12, 3)),
        ("Plazo 6-8 semanas\nGarantía 2 años", date(2026, 12, 17)),
        ("Entrega 5 semanas\nPago 90 días\nMontaje 2 días", date(2026, 11, 26)),
        ("Plazo de entrega: 3 semanas\nGarantía: 12 meses\nMontaje: 2 días", date(2026, 11, 12)),
        ("Garantizamos la entrega en 3 semanas", date(2026, 11, 12)),
        ("Una vez validados los planos: 6 semanas", date(2026, 12, 3)),
        ("Precios netos plazo 4 semanas", date(2026, 11, 19)),
        ("Entrega garantizada en 10 días laborables", date(2026, 11, 5)),
        ("Tras recibir el pago anticipado: 4 semanas", date(2026, 11, 19)),
        (
            "Pago 30 días; entrega: 2 semanas los distanciales, 5 semanas el inserto",
            date(2026, 11, 26),
        ),
        (
            "Lead time: 2 weeks for item 1, 8 weeks for item 2. Payment 30 days",
            date(2026, 12, 17),
        ),
        ("Validez 30 días\nPos. 1: 2 semanas\nPos. 2: 6 semanas", date(2026, 12, 3)),
        ("Validez 30 días - Entrega 6 semanas", date(2026, 12, 3)),
        ("Validez 30 días | Entrega 6 semanas", date(2026, 12, 3)),
        ("Entrega 6 semanas - 24 meses de garantía", date(2026, 12, 3)),
        ("Entrega 4 semanas, 2 días de transporte. Pago 30 días", date(2026, 11, 21)),
        ("Entrega 1 semana 3 días. Pago 30 días", date(2026, 11, 1)),
        ("Plazo de entrega a convenir. Validez 30 días", None),
        # Abreviaturas, varias entregas y condiciones en la misma frase que el plazo.
        ("Entrega 5 Sem. Pago 30 días", date(2026, 11, 26)),
        ("4 sem. Validez oferta 30 días", date(2026, 11, 19)),
        ("Plazo de entrega: 4 semanas desde pedido y pago a 60 días", date(2026, 11, 19)),
        ("Delivery time 2 weeks from receipt of PO and payment 30 days", date(2026, 11, 5)),
        ("Entrega 3 semanas desde la aceptación de esta oferta válida 30 días", date(2026, 11, 12)),
        ("Entrega parcial en 2 semanas. Resto en 6 semanas.", date(2026, 12, 3)),
        ("Plazo de entrega: 2 semanas\nMotor: 8 semanas", date(2026, 12, 17)),
        ("Delivery: bearings 1 week; motor 6 weeks", date(2026, 12, 3)),
        ("Entrega 4 semanas; transporte: 3 días", date(2026, 11, 22)),
        ("Lieferzeit: 4 weeks ab Auftragseingang, Zahlung 30 days netto", date(2026, 11, 19)),
        ("4 semanas tras la recepción del pago", date(2026, 11, 19)),
        ("10 días", date(2026, 11, 1)),
        ("10 días laborables", date(2026, 11, 5)),
        ("dos meses", date(2026, 12, 22)),
        ("1 mes", date(2026, 11, 22)),
        ("inmediato", None),
        # En inglés, por si no se traduce.
        ("Execution time 25 working days.", date(2026, 11, 26)),
        ("10 business days", date(2026, 11, 5)),
        ("4 weeks", date(2026, 11, 19)),
        ("3-4 weeks", date(2026, 11, 19)),
        ("2 to 3 weeks", date(2026, 11, 12)),
        ("2 a 3 semanas", date(2026, 11, 12)),
        ("2 months", date(2026, 12, 22)),
        ("10 days", date(2026, 11, 1)),
        # Números absurdos: no se calcula (antes colgaba el proceso o daba 500).
        ("999999999999 días laborables", None),
        ("99999999 días", None),
        ("4000 días", None),
        ("", None),
    ],
)
def test_fecha_desde_plazo(texto, esperada):
    assert fecha_desde_plazo(texto, date(2026, 10, 22)) == esperada


def test_mes_sin_ese_dia():
    assert fecha_desde_plazo("1 mes", date(2026, 1, 31)) == date(2026, 2, 28)


@pytest.mark.parametrize(
    ("desde", "texto", "esperada"),
    [
        # Desde un sábado o un domingo, el primer laborable es el lunes.
        (date(2026, 11, 7), "5 días laborables", date(2026, 11, 13)),
        (date(2026, 11, 8), "5 días laborables", date(2026, 11, 13)),
        (date(2026, 11, 7), "1 día laborable", date(2026, 11, 9)),
        (date(2026, 11, 7), "6 días laborables", date(2026, 11, 16)),
        (date(2026, 11, 6), "5 días laborables", date(2026, 11, 13)),
    ],
)
def test_laborables_desde_fin_de_semana(desde, texto, esperada):
    assert fecha_desde_plazo(texto, desde) == esperada


@pytest.mark.parametrize("texto", ["10 días", "10 días laborables", "4 semanas", "2 meses"])
def test_plazo_que_pasa_del_anio_9999(texto):
    # Fuera del calendario de Python: se pide la fecha a mano, sin error 500.
    assert fecha_desde_plazo(texto, date(9999, 12, 25)) is None


# --- API ------------------------------------------------------------------------------------


@pytest.fixture
def datos(app, cliente):
    """Necesidad en «En cotización» con Acme solicitado; Zeta existe pero no se le pidió oferta."""
    with app.extensions["remate.sesiones"]() as s:
        ana = Peticionario(nombre_completo="Ana Prueba", email="ana@ejemplo.test")
        acme = Proveedor(nombre="Acme", email="ventas@acme.test")
        zeta = Proveedor(nombre="Zeta", email="ofertas@zeta.test")
        s.add_all([ana, acme, zeta])
        s.commit()
        ids = {"ana": ana.id, "acme": acme.id, "zeta": zeta.id}
    necesidad = cliente.post(
        "/api/necesidades",
        data={
            "titulo": "Rodamiento roto",
            "proyecto": "Línea 3",
            "peticionario_id": str(ids["ana"]),
            "descripcion": "4 rodamientos 6204-2RS.",
        },
        content_type="multipart/form-data",
    ).json
    ids["necesidad"] = necesidad["id"]
    respuesta = cliente.post(
        f"/api/necesidades/{necesidad['id']}/solicitud",
        json={
            "peticionario_id": ids["ana"],
            "proveedor_ids": [ids["acme"]],
            "cuerpo": "Hola",
            "motivo_pocos_proveedores": "urgencia",
        },
    )
    assert respuesta.status_code == 200
    return ids


def url(datos, final=""):
    return f"/api/necesidades/{datos['necesidad']}/ofertas{final}"


def subir(cliente, datos, correo=None, nombre="oferta.eml", **extra):
    formulario = {"correo": (io.BytesIO(correo or eml()), nombre), **extra}
    return cliente.post(url(datos), data=formulario, content_type="multipart/form-data")


def test_sube_una_oferta_y_reconoce_al_proveedor_por_el_remitente(cliente, datos):
    respuesta = subir(
        cliente,
        datos,
        adjuntos=[(io.BytesIO(b"%PDF oferta"), "oferta 123.pdf")],
        tipos_adjunto=["pdf"],
    )
    assert respuesta.status_code == 201, respuesta.json
    oferta = respuesta.json
    assert oferta["proveedor"]["nombre"] == "Acme"
    assert oferta["fecha_correo"] == "2026-10-22T09:15:00+02:00"
    assert oferta["revisada"] is False
    assert oferta["estado_oferta"] == "vigente"
    assert [(a["tipo"], a["formato"], a["nombre_archivo"]) for a in oferta["archivos"]] == [
        ("correo_oferta", None, "oferta.eml"),
        ("adjunto_oferta", "pdf", "oferta 123.pdf"),
    ]
    # Al subirla solo se guarda: la IA la lee después, con las demás («Analizar y comparar»).
    assert oferta["sin_analizar"] is True
    assert not any("IA" in a for a in oferta["avisos"])
    assert "Falta: importe sin IVA, fecha de entrega." in oferta["avisos"]
    assert "importe_con_iva" not in oferta
    # Los archivos de la oferta no aparecen entre los adjuntos de la necesidad.
    detalle = cliente.get(f"/api/necesidades/{datos['necesidad']}").json
    assert detalle["adjuntos"] == []
    assert [o["id"] for o in cliente.get(url(datos)).json] == [oferta["id"]]


def test_un_msg_que_no_se_puede_leer_explica_como_guardarlo_como_eml(cliente, datos):
    respuesta = subir(cliente, datos, correo=b"x", nombre="oferta.msg")
    assert respuesta.status_code == 422
    assert respuesta.json["error"] == "archivo_no_aceptado"
    assert "Guardar como" in respuesta.json["mensaje"]


def test_remitente_desconocido_pide_elegir_proveedor(cliente, datos):
    respuesta = subir(cliente, datos, correo=eml(remitente="otro@desconocido.test"))
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "proveedor_id"}
    assert "otro@desconocido.test" in respuesta.json["mensaje"]
    elegido = subir(
        cliente,
        datos,
        correo=eml(remitente="otro@desconocido.test"),
        proveedor_id=str(datos["zeta"]),
    )
    assert elegido.status_code == 201
    assert "Zeta no estaba entre los proveedores solicitados." in elegido.json["avisos"]


def test_falta_el_tipo_de_un_adjunto(cliente, datos):
    respuesta = subir(cliente, datos, adjuntos=[(io.BytesIO(b"x"), "a.pdf")])
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "tipos_adjunto"}


def test_segunda_oferta_del_mismo_proveedor_sustituye_a_la_anterior(cliente, datos):
    primera = subir(cliente, datos).json
    sin_confirmar = subir(cliente, datos)
    # CU-004 4c: primero avisa y pide confirmación.
    assert sin_confirmar.status_code == 409
    assert sin_confirmar.json["error"] == "oferta_existente"
    assert sin_confirmar.json["detalles"]["proveedor"]["nombre"] == "Acme"
    assert [o["id"] for o in cliente.get(url(datos)).json] == [primera["id"]]
    segunda = subir(cliente, datos, confirmar_sustitucion="true").json
    assert "Sustituye a la oferta anterior de Acme." in segunda["avisos"]
    assert [o["id"] for o in cliente.get(url(datos)).json] == [segunda["id"]]
    corregir = cliente.patch(url(datos, f"/{primera['id']}"), json={"numero_oferta": "X"})
    assert corregir.status_code == 409


def test_corregir_y_revisar(cliente, datos):
    oferta = subir(cliente, datos).json
    ruta = url(datos, f"/{oferta['id']}")
    sin_datos = cliente.patch(ruta, json={"revisada": True})
    assert sin_datos.status_code == 400
    assert sin_datos.json["detalles"] == {"campo": "importe_sin_iva"}

    respuesta = cliente.patch(
        ruta,
        json={
            "numero_oferta": " OF-2026-123 ",
            "importe_sin_iva": "100.00",
            "plazo_entrega_texto": "4 semanas",
            "condiciones_pago": "30 días",
            "lineas": [
                {"descripcion": "Rodamiento 6204-2RS", "cantidad": "2.5", "precio_unitario": "40"}
            ],
            "revisada": True,
        },
    )
    assert respuesta.status_code == 200, respuesta.json
    corregida = respuesta.json
    assert corregida["numero_oferta"] == "OF-2026-123"
    assert corregida["importe_sin_iva"] == "100.00"
    # El plazo se cuenta desde el envío del correo (22/10/2026), no desde hoy.
    assert corregida["fecha_entrega_estimada"] == "2026-11-19"
    assert corregida["lineas"] == [
        {
            "descripcion": "Rodamiento 6204-2RS",
            "cantidad": "2.5",
            "precio_unitario": "40.00",
            "fecha_entrega": None,
            "plazo_entrega_texto": None,
            "fecha_calculada": False,
        }
    ]
    assert corregida["revisada"] is True
    assert corregida["avisos"] == []

    # Un cambio sin volver a confirmar la revisión la quita.
    cambiada = cliente.patch(ruta, json={"importe_sin_iva": "999"}).json
    assert cambiada["importe_sin_iva"] == "999.00"
    assert cambiada["revisada"] is False


def test_aviso_si_las_lineas_no_cuadran(cliente, datos):
    oferta = subir(cliente, datos).json
    respuesta = cliente.patch(
        url(datos, f"/{oferta['id']}"),
        json={
            "importe_sin_iva": "4620",
            "lineas": [{"descripcion": "Pieza", "cantidad": 2, "precio_unitario": "2360"}],
        },
    )
    # Con el formato de la pantalla («4.720,00», no «4720.00»).
    assert (
        "La suma de las líneas (4.720,00) no coincide con el importe sin IVA (4.620,00)."
        in respuesta.json["avisos"]
    )


def test_aviso_de_lineas_con_precios_de_cuatro_decimales(cliente, datos):
    """Con 4 decimales, el aviso y el editor dicen lo mismo («37,0368», no «37,04»): los dos usan
    de 2 a 4 decimales."""
    oferta = subir(cliente, datos).json
    respuesta = cliente.patch(
        url(datos, f"/{oferta['id']}"),
        json={
            "importe_sin_iva": "37",
            "lineas": [{"descripcion": "Pieza", "cantidad": 3, "precio_unitario": "12.3456"}],
        },
    )
    assert any("(37,0368)" in a for a in respuesta.json["avisos"])


def test_fecha_a_mano_si_el_plazo_no_se_entiende(cliente, datos):
    oferta = subir(cliente, datos).json
    ruta = url(datos, f"/{oferta['id']}")
    sin_fecha = cliente.patch(ruta, json={"plazo_entrega_texto": "según disponibilidad"}).json
    assert sin_fecha["fecha_entrega_estimada"] is None
    con_fecha = cliente.patch(
        ruta, json={"plazo_entrega_texto": "4 semanas", "fecha_entrega_estimada": "2026-12-01"}
    ).json
    assert con_fecha["fecha_entrega_estimada"] == "2026-12-01"


def test_borrar_y_pasar_a_evaluacion(cliente, datos):
    evaluacion = f"/api/necesidades/{datos['necesidad']}/evaluacion"
    sin_ofertas = cliente.post(evaluacion, json={"peticionario_id": datos["ana"]})
    assert sin_ofertas.status_code == 409

    oferta = subir(cliente, datos).json
    assert cliente.delete(url(datos, f"/{oferta['id']}")).status_code == 204
    assert cliente.get(url(datos)).json == []
    assert cliente.post(evaluacion, json={"peticionario_id": datos["ana"]}).status_code == 409

    subir(cliente, datos, confirmar_sustitucion="true")
    respuesta = cliente.post(evaluacion, json={"peticionario_id": datos["ana"]})
    assert respuesta.status_code == 200
    assert respuesta.json["necesidad"]["estado"] == "en_evaluacion"
    assert respuesta.json["necesidad"]["historial"][-1]["estado_nuevo"] == "en_evaluacion"
    # En evaluación se pueden seguir añadiendo ofertas.
    assert subir(cliente, datos, correo=eml(remitente="ofertas@zeta.test")).status_code == 201


def test_comparativa_solo_con_datos_y_de_mas_barata_a_mas_cara(cliente, datos, app):
    with app.extensions["remate.sesiones"]() as s:
        beta = Proveedor(nombre="Beta", email="beta@beta.test")
        s.add(beta)
        s.commit()
        beta_id = beta.id
    cara = subir(cliente, datos).json
    barata = subir(cliente, datos, correo=eml(remitente="ofertas@zeta.test")).json
    # Beta sigue sin analizar (sin datos): no entra en la comparativa.
    sin_analizar = subir(cliente, datos, correo=eml(remitente="beta@beta.test")).json
    assert sin_analizar["proveedor"]["id"] == beta_id
    for oferta, importe in ((cara, "500"), (barata, "300")):
        respuesta = cliente.patch(
            url(datos, f"/{oferta['id']}"),
            json={
                "importe_sin_iva": importe,
                "fecha_entrega_estimada": "2026-11-30",
                "revisada": True,
            },
        )
        assert respuesta.status_code == 200
    comparativa = cliente.get(f"/api/necesidades/{datos['necesidad']}/comparativa").json
    assert [o["proveedor"]["nombre"] for o in comparativa] == ["Zeta", "Acme"]


def test_ofertas_fuera_de_su_estado(cliente, app):
    with app.extensions["remate.sesiones"]() as s:
        ana = Peticionario(nombre_completo="Ana Prueba", email="ana@ejemplo.test")
        s.add(ana)
        s.commit()
        ana_id = ana.id
    necesidad = cliente.post(
        "/api/necesidades",
        data={"titulo": "t", "proyecto": "p", "peticionario_id": str(ana_id), "descripcion": "d"},
        content_type="multipart/form-data",
    ).json
    respuesta = cliente.post(
        f"/api/necesidades/{necesidad['id']}/ofertas",
        data={"correo": (io.BytesIO(eml()), "o.eml")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 409
    assert cliente.get("/api/necesidades/999999/ofertas").status_code == 404


def test_plazo_sin_fecha_al_revisar(cliente, datos):
    """Con «5 dias» y la fecha vacía, la fecha se calcula y no se pide ponerla a mano."""
    oferta = subir(cliente, datos).json
    respuesta = cliente.patch(
        url(datos, f"/{oferta['id']}"),
        json={
            "importe_sin_iva": "50",
            "plazo_entrega_texto": "5 dias",
            "fecha_entrega_estimada": None,
            "revisada": True,
        },
    )
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json["fecha_entrega_estimada"] == "2026-10-27"
    assert respuesta.json["revisada"] is True


def test_la_ultima_oferta_subida_sale_la_primera(cliente, datos):
    """Las nuevas, encima de las anteriores."""
    primera = subir(cliente, datos).json
    segunda = subir(cliente, datos, correo=eml(remitente="ofertas@zeta.test")).json
    assert [o["id"] for o in cliente.get(url(datos)).json] == [segunda["id"], primera["id"]]


def test_borrar_en_evaluacion_si_y_despues_no(cliente, datos, app):
    """CU-004 4d: se puede borrar en «En evaluación»; en estados posteriores, no."""
    evaluacion = f"/api/necesidades/{datos['necesidad']}/evaluacion"
    primera = subir(cliente, datos).json
    segunda = subir(cliente, datos, correo=eml(remitente="ofertas@zeta.test")).json
    assert cliente.post(evaluacion, json={"peticionario_id": datos["ana"]}).status_code == 200
    assert cliente.delete(url(datos, f"/{primera['id']}")).status_code == 204
    with app.extensions["remate.sesiones"]() as s:
        s.get(Necesidad, datos["necesidad"]).estado = "pendiente_pedido_sap"
        s.commit()
    assert cliente.delete(url(datos, f"/{segunda['id']}")).status_code == 409


# --- Lectura con IA (simulada) ---------------------------------------------------------------

RESPUESTA_IA = {
    "moneda": "EUR",
    "proveedor": {"nombre": "Acme", "email": "comercial@acme.test"},
    "numero_oferta": "OF-2026-55",
    "lineas": [
        {"descripcion": "Rodamiento 6204-2RS", "cantidad": 4, "precio_unitario": 12.5},
        {"descripcion": "Portes", "cantidad": None, "precio_unitario": 10},
    ],
    "importe_sin_iva": "50,00 €",
    "plazo_entrega": "4 semanas desde pedido",
    "fecha_entrega": None,
    "condiciones_pago": "Transferencia a 30 días",
    "otros": "Portes incluidos",
    "avisos": ["La oferta es válida 30 días."],
}


@pytest.fixture
def ia_simulada(monkeypatch):
    """Sustituye la IA: guarda lo que recibe y devuelve `respuesta` (o ErrorIA si es None)."""
    estado = {"respuesta": RESPUESTA_IA, "partes": None, "lecturas": []}

    def leer_oferta(config, partes):
        estado["partes"] = partes
        estado["lecturas"].append(partes)
        if estado["respuesta"] is None:
            raise ia.ErrorIA("La IA no ha respondido.")
        return estado["respuesta"]

    monkeypatch.setattr(ia, "leer_oferta", leer_oferta)
    return estado


def leida(cliente, datos, **extra):
    """Sube una oferta y la lee la IA con «Reanalizar con IA» (una sola oferta)."""
    oferta = subir(cliente, datos, **extra).json
    respuesta = cliente.post(url(datos, f"/{oferta['id']}/analisis"))
    assert respuesta.status_code == 200, respuesta.json
    return respuesta.json


def analizar_y_comparar(cliente, datos, **cuerpo):
    cuerpo = {"peticionario_id": datos["ana"], **cuerpo}
    return cliente.post(f"/api/necesidades/{datos['necesidad']}/evaluacion", json=cuerpo)


def test_la_ia_rellena_la_oferta_al_analizarla(cliente, datos, ia_simulada, app):
    oferta = leida(
        cliente,
        datos,
        adjuntos=[(io.BytesIO(b"%PDF oferta"), "oferta.pdf")],
        tipos_adjunto=["pdf"],
    )
    # La IA recibe lo que pidió el cliente (para elegir la opción y avisar de lo que no se oferta),
    # el correo (cabeceras y cuerpo) y el PDF.
    pedido, correo, pdf = ia_simulada["partes"]
    assert pedido["text"].startswith("Lo que pidió el cliente (no es parte de la oferta):")
    assert "Título: Rodamiento roto" in pedido["text"]
    assert "4 rodamientos 6204-2RS." in pedido["text"]
    assert "Remitente: ventas@acme.test" in correo["text"]
    assert "Plazo: 4 semanas." in correo["text"]
    # Formato de la Responses API de OpenAI; el PDF va con poca resolución en las imágenes de
    # página (el texto se extrae igual): menos tokens (ADR 0011).
    assert (pdf["type"], pdf["filename"], pdf["detail"]) == ("input_file", "oferta.pdf", "low")

    assert oferta["numero_oferta"] == "OF-2026-55"
    assert oferta["importe_sin_iva"] == "50.00"
    assert oferta["plazo_entrega_texto"] == "4 semanas desde pedido"
    # El plazo se cuenta desde el envío del correo (22/10/2026).
    assert oferta["fecha_entrega_estimada"] == "2026-11-19"
    assert oferta["condiciones_pago"] == "Transferencia a 30 días"
    assert oferta["otros"] == "Portes incluidos"
    assert oferta["lineas"] == [
        {
            "descripcion": "Rodamiento 6204-2RS",
            "cantidad": "4",
            "precio_unitario": "12.50",
            "fecha_entrega": None,
            "plazo_entrega_texto": None,
            "fecha_calculada": False,
        }
    ]
    assert oferta["revisada"] is False
    assert oferta["sin_analizar"] is False
    assert "La IA avisa: La oferta es válida 30 días." in oferta["avisos"]
    assert any("1 línea(s)" in a for a in oferta["avisos"])
    # Mismo dominio que el proveedor: no se avisa de que pueda ser de otro.
    assert not any("comprueba que es de" in a for a in oferta["avisos"])
    with app.extensions["remate.sesiones"]() as s:
        assert s.get(Oferta, oferta["id"]).datos_ia["respuesta"] == RESPUESTA_IA


def test_el_iva_no_se_lee_ni_se_calcula(cliente, datos, ia_simulada):
    """Todos los importes son sin IVA. Si la IA devuelve todavía un importe con IVA o un tipo de
    IVA (respuestas guardadas antes del cambio), no se usan ni se avisa."""
    ia_simulada["respuesta"] = {
        **RESPUESTA_IA,
        "importe_con_iva": 60.5,
        "iva_porcentaje": 21,
        "vat_rate": 21,
        "total_with_vat": 60.5,
    }
    oferta = leida(cliente, datos)
    assert oferta["importe_sin_iva"] == "50.00"
    assert "importe_con_iva" not in oferta
    assert not any("IVA" in a for a in oferta["avisos"])


def test_un_importe_enorme_se_guarda(cliente, datos, ia_simulada):
    """Un importe que cabe justo en la columna no rompe
    «Reanalizar con IA» y se guarda lo demás."""
    ia_simulada["respuesta"] = {
        **RESPUESTA_IA,
        "importe_sin_iva": 999999999999.99,
        "lineas": [],
    }
    oferta = leida(cliente, datos)
    assert oferta["importe_sin_iva"] == "999999999999.99"
    assert oferta["numero_oferta"] == "OF-2026-55"


def test_reanalizar_si_no_se_puede_guardar_avisa_sin_error(cliente, datos, monkeypatch):
    """Como en «Analizar y comparar», un fallo al guardar lo leído se avisa y los datos no
    cambian (sin error 500)."""
    rara = {**RESPUESTA_IA, "numero_oferta": "P\ud800"}
    monkeypatch.setattr(ia, "leer_oferta", lambda config, partes: rara)
    oferta = subir(cliente, datos).json
    respuesta = cliente.post(url(datos, f"/{oferta['id']}/analisis"))
    assert respuesta.status_code == 200, respuesta.json
    assert any("No se ha podido guardar" in a for a in respuesta.json["avisos"])
    assert cliente.get(url(datos)).json[0]["sin_analizar"] is True


def test_si_la_ia_falla_la_oferta_se_guarda_y_se_puede_reanalizar(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = None
    oferta = leida(cliente, datos)
    assert oferta["importe_sin_iva"] is None
    # Sigue pendiente: «Analizar y comparar» la volverá a intentar.
    assert oferta["sin_analizar"] is True
    assert any("Reanalizar con IA" in a for a in oferta["avisos"])
    assert [o["id"] for o in cliente.get(url(datos)).json] == [oferta["id"]]

    ia_simulada["respuesta"] = RESPUESTA_IA
    reanalizada = cliente.post(url(datos, f"/{oferta['id']}/analisis"))
    assert reanalizada.status_code == 200, reanalizada.json
    assert reanalizada.json["numero_oferta"] == "OF-2026-55"


def test_reanalizar_sustituye_los_datos_y_quita_la_revision(cliente, datos, ia_simulada):
    oferta = leida(cliente, datos)
    ruta = url(datos, f"/{oferta['id']}")
    revisada = cliente.patch(ruta, json={"numero_oferta": "A MANO", "revisada": True}).json
    assert revisada["revisada"] is True

    ia_simulada["respuesta"] = None
    fallida = cliente.post(f"{ruta}/analisis").json
    # Si la IA falla, los datos corregidos a mano no se tocan.
    assert fallida["numero_oferta"] == "A MANO"
    assert fallida["revisada"] is True

    ia_simulada["respuesta"] = {**RESPUESTA_IA, "numero_oferta": "OF-NUEVA"}
    nueva = cliente.post(f"{ruta}/analisis").json
    assert nueva["numero_oferta"] == "OF-NUEVA"
    assert nueva["revisada"] is False
    assert cliente.post(url(datos, "/999999/analisis")).status_code == 404


def test_reanalizar_no_pisa_lo_corregido_mientras_lee_la_ia(app, cliente, datos, monkeypatch):
    """Si alguien corrige la oferta mientras responde la IA, se queda lo corregido y se avisa (la
    lectura de la IA no lo sustituye)."""
    oferta = subir(cliente, datos).json

    def leer_y_corregir_a_la_vez(config, partes):
        with app.extensions["remate.sesiones"]() as s:
            s.get(Oferta, oferta["id"]).importe_sin_iva = Decimal("777")
            s.commit()
        return {**RESPUESTA_IA, "importe_sin_iva": 99}

    monkeypatch.setattr(ia, "leer_oferta", leer_y_corregir_a_la_vez)
    respuesta = cliente.post(url(datos, f"/{oferta['id']}/analisis"))
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json["importe_sin_iva"] == "777.00"
    assert any("ha cambiado mientras" in a for a in respuesta.json["avisos"])


def test_aviso_si_la_ia_lee_otro_proveedor(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = {
        **RESPUESTA_IA,
        "proveedor": {"nombre": "Zeta", "email": "ofertas@zeta.test"},
    }
    oferta = leida(cliente, datos)
    assert oferta["proveedor"]["nombre"] == "Acme"
    assert any("«Zeta»" in a and "comprueba que es de Acme" in a for a in oferta["avisos"])


def test_respuesta_de_la_ia_con_datos_raros(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = {
        "numero_oferta": 123,
        "lineas": "no es una lista",
        "importe_sin_iva": -5,
        "plazo_entrega": None,
        "fecha_entrega": "2026-12-01",
        "avisos": "no es una lista",
    }
    oferta = leida(cliente, datos)
    assert oferta["numero_oferta"] == "123"
    assert oferta["importe_sin_iva"] is None
    # Una fecha concreta de la oferta manda sobre el plazo.
    assert oferta["fecha_entrega_estimada"] == "2026-12-01"
    assert oferta["lineas"] == []


def test_claves_estropeadas_por_la_ia(cliente, datos, ia_simulada):
    """Algunos modelos devuelven claves como « descripcion» o «condiciones pago»."""
    ia_simulada["respuesta"] = {
        "lineas": [{" descripcion": "Grasa", "cantidad": 1, "Precio_Unitario": 18}],
        "condiciones pago": "60 días",
    }
    oferta = leida(cliente, datos)
    assert [linea["descripcion"] for linea in oferta["lineas"]] == ["Grasa"]
    assert oferta["condiciones_pago"] == "60 días"


@pytest.mark.parametrize("clave", ["description", "detalle", "concepto"])
def test_claves_en_ingles_o_sin_guion_bajo(cliente, datos, ia_simulada, clave):
    """La IA puede leer bien la línea pero con la clave «description» (o «detalle», en otra
    lectura): se entiende igual y la oferta no se queda sin líneas; lo mismo con
    «condicionespago»."""
    ia_simulada["respuesta"] = {
        "lineas": [{clave: "Útil R12345", "quantity": 2, "unit_price": 84.5}],
        "condicionespago": "Contado",
    }
    oferta = leida(cliente, datos)
    assert [(linea["descripcion"], linea["cantidad"]) for linea in oferta["lineas"]] == [
        ("Útil R12345", "2")
    ]
    assert oferta["condiciones_pago"] == "Contado"


def test_la_clave_pedida_gana_a_la_alternativa(cliente, datos, ia_simulada):
    """Si llegan a la vez la clave pedida y una alternativa, vale la pedida, aunque la
    alternativa venga antes; «precio» (a menudo el total) no se toma."""
    ia_simulada["respuesta"] = {
        "lineas": [
            {
                "producto": "Rodamiento",
                "descripcion": "Rodamiento 6204-2RS inox",
                "precio": 100,
                "precio_unitario": 25,
                "unidades": "uds",
                "cantidad": 4,
            }
        ]
    }
    oferta = leida(cliente, datos)
    assert [(x["descripcion"], x["cantidad"], x["precio_unitario"]) for x in oferta["lineas"]] == [
        ("Rodamiento 6204-2RS inox", "4", "25.00")
    ]


def test_el_dia_del_correo_es_el_de_madrid():
    """Un correo de las 23:30 UTC del 21/10 se envió el 22/10 en Madrid."""
    oferta = Oferta(fecha_correo=datetime(2026, 10, 21, 23, 30, tzinfo=UTC))
    assert dia_del_correo(oferta) == date(2026, 10, 22)


def test_toda_la_respuesta_con_claves_en_ingles(cliente, datos, ia_simulada):
    """Si el modelo responde con todas las claves en inglés, no se pierden los importes, el plazo
    ni las condiciones."""
    ia_simulada["respuesta"] = {
        "supplier": {"name": "Acme Rodamientos", "email": "ventas@acme.test"},
        "offer_number": "OF-2026-0417",
        "lines": [{"description": "Rodamientos", "quantity": 4, "unit_price": 11.9}],
        "total_without_vat": 65.6,
        "delivery_time": "2 semanas",
        "payment_terms": "Transferencia a 60 días",
        "others": "Portes pagados",
    }
    oferta = leida(cliente, datos)
    assert oferta["numero_oferta"] == "OF-2026-0417"
    assert oferta["importe_sin_iva"] == "65.60"
    assert oferta["plazo_entrega_texto"] == "2 semanas"
    assert oferta["condiciones_pago"] == "Transferencia a 60 días"
    assert oferta["otros"] == "Portes pagados"
    assert [linea["descripcion"] for linea in oferta["lineas"]] == ["Rodamientos"]


# --- «Analizar y comparar»: todas las ofertas a la vez ----------------------------------------


def test_subir_no_llama_a_la_ia_y_analizar_lee_todas_y_compara(cliente, datos, ia_simulada):
    acme = subir(cliente, datos).json
    zeta = subir(cliente, datos, correo=eml(remitente="ofertas@zeta.test")).json
    assert ia_simulada["lecturas"] == []
    assert (acme["sin_analizar"], zeta["sin_analizar"]) == (True, True)

    respuesta = analizar_y_comparar(cliente, datos)
    assert respuesta.status_code == 200, respuesta.json
    resultado = respuesta.json
    assert resultado["necesidad"]["estado"] == "en_evaluacion"
    assert len(ia_simulada["lecturas"]) == 2
    assert "Acme: La IA avisa: La oferta es válida 30 días." in resultado["avisos"]
    assert "Zeta: La IA avisa: La oferta es válida 30 días." in resultado["avisos"]
    # La comparativa sale con los datos de la IA aún sin revisar, y sin
    # resumen.
    assert "resumen" not in resultado
    comparativa = cliente.get(f"/api/necesidades/{datos['necesidad']}/comparativa").json
    assert {(o["id"], o["revisada"], o["sin_analizar"]) for o in comparativa} == {
        (acme["id"], False, False),
        (zeta["id"], False, False),
    }
    # Sin revisar no se puede adjudicar.
    borrador = cliente.post(
        f"/api/necesidades/{datos['necesidad']}/adjudicacion/borrador",
        json={"oferta_id": acme["id"]},
    )
    assert borrador.status_code == 400


def test_analizar_y_comparar_no_pisa_lo_escrito_a_mano_ni_repite(cliente, datos, ia_simulada):
    a_mano = subir(cliente, datos).json
    ruta = url(datos, f"/{a_mano['id']}")
    assert cliente.patch(ruta, json={"numero_oferta": "A MANO"}).status_code == 200
    subir(cliente, datos, correo=eml(remitente="ofertas@zeta.test"))

    assert analizar_y_comparar(cliente, datos).status_code == 200
    assert len(ia_simulada["lecturas"]) == 1
    numeros = {o["proveedor"]["nombre"]: o["numero_oferta"] for o in cliente.get(url(datos)).json}
    assert numeros == {"Acme": "A MANO", "Zeta": "OF-2026-55"}

    # En «En evaluación» solo se lee la que llega después, y no hace falta quién.
    tardia = subir(
        cliente, datos, correo=eml(remitente="ofertas@zeta.test"), confirmar_sustitucion="true"
    )
    assert tardia.status_code == 201
    respuesta = analizar_y_comparar(cliente, datos, peticionario_id=None)
    assert respuesta.status_code == 200, respuesta.json
    assert len(ia_simulada["lecturas"]) == 2


def test_si_la_ia_falla_con_todas_pasa_a_evaluacion(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = None
    subir(cliente, datos)
    resultado = analizar_y_comparar(cliente, datos).json
    assert resultado["necesidad"]["estado"] == "en_evaluacion"
    assert any(a.startswith("Acme: La IA no ha leído la oferta") for a in resultado["avisos"])
    # Sigue pendiente: se reintenta con el mismo botón o se escribe a mano (flujo 3a).
    assert cliente.get(url(datos)).json[0]["sin_analizar"] is True
    ia_simulada["respuesta"] = RESPUESTA_IA
    assert analizar_y_comparar(cliente, datos).status_code == 200
    assert cliente.get(url(datos)).json[0]["sin_analizar"] is False


def test_analizar_y_comparar_sin_ofertas_o_sin_quien(cliente, datos):
    assert analizar_y_comparar(cliente, datos).status_code == 409
    subir(cliente, datos)
    assert analizar_y_comparar(cliente, datos, peticionario_id=None).status_code == 400
    assert cliente.post("/api/necesidades/999999/evaluacion", json={}).status_code == 404


def de_zeta(partes) -> bool:
    return "zeta.test" in str(partes)


def test_un_fallo_inesperado_con_una_oferta_no_tira_las_demas(cliente, datos, monkeypatch):
    """Un error que no es ErrorIA no da un 500 ni hace perder todas las lecturas (CU-004, 3a: se
    avisa de esa oferta y se leen las demás)."""

    def leer_oferta(config, partes):
        if de_zeta(partes):
            raise ValueError("substring not found")
        return RESPUESTA_IA

    monkeypatch.setattr(ia, "leer_oferta", leer_oferta)
    subir(cliente, datos)
    subir(cliente, datos, correo=eml(remitente="ofertas@zeta.test"))
    respuesta = analizar_y_comparar(cliente, datos)
    assert respuesta.status_code == 200, respuesta.json
    assert any(a.startswith("Zeta: La IA no ha leído la oferta") for a in respuesta.json["avisos"])
    pendientes = {o["proveedor"]["nombre"]: o["sin_analizar"] for o in cliente.get(url(datos)).json}
    assert pendientes == {"Acme": False, "Zeta": True}


def test_una_lectura_que_no_se_puede_guardar_no_tira_las_demas(cliente, datos, monkeypatch):
    """PostgreSQL no admite un carácter sustituto suelto; si falla al guardar la primera oferta,
    no se pierde la lectura de las que van detrás."""
    rara = {**RESPUESTA_IA, "numero_oferta": "P\ud800"}
    monkeypatch.setattr(
        ia, "leer_oferta", lambda config, partes: RESPUESTA_IA if de_zeta(partes) else rara
    )
    subir(cliente, datos)  # Acme va primero
    subir(cliente, datos, correo=eml(remitente="ofertas@zeta.test"))
    respuesta = analizar_y_comparar(cliente, datos)
    assert respuesta.status_code == 200, respuesta.json
    assert any(
        a.startswith("Acme: No se ha podido guardar lo que ha leído la IA")
        for a in respuesta.json["avisos"]
    )
    pendientes = {o["proveedor"]["nombre"]: o["sin_analizar"] for o in cliente.get(url(datos)).json}
    assert pendientes == {"Acme": True, "Zeta": False}


def test_oferta_borrada_o_escrita_a_mano_mientras_se_analizan(cliente, datos, app, monkeypatch):
    """Mientras responde la IA no se bloquea la necesidad: lo que pase entretanto manda."""
    acme = subir(cliente, datos).json
    zeta = subir(cliente, datos, correo=eml(remitente="ofertas@zeta.test")).json

    def leer_oferta(config, partes):
        with app.extensions["remate.sesiones"]() as otra:
            if de_zeta(partes):
                otra.get(Oferta, zeta["id"]).numero_oferta = "A MANO"
            else:
                otra.get(Oferta, acme["id"]).estado_oferta = "borrada"
            otra.commit()
        return RESPUESTA_IA

    monkeypatch.setattr(ia, "leer_oferta", leer_oferta)
    assert analizar_y_comparar(cliente, datos).status_code == 200
    with app.extensions["remate.sesiones"]() as s:
        assert s.get(Oferta, acme["id"]).numero_oferta is None
        assert s.get(Oferta, zeta["id"]).numero_oferta == "A MANO"
        assert s.get(Oferta, zeta["id"]).datos_ia is None


def test_no_se_analiza_dos_veces_a_la_vez(cliente, datos, ia_simulada):
    """Con otra pestaña u otra persona a la vez, la IA no lee dos veces lo mismo."""
    subir(cliente, datos)
    servicio_comparativa._analizando.add(datos["necesidad"])
    try:
        respuesta = analizar_y_comparar(cliente, datos)
    finally:
        servicio_comparativa._analizando.discard(datos["necesidad"])
    assert respuesta.status_code == 409
    assert "Ya se están analizando" in respuesta.json["mensaje"]
    assert ia_simulada["lecturas"] == []
    # Al terminar (también si falla) se puede volver a analizar.
    assert analizar_y_comparar(cliente, datos).status_code == 200
    assert datos["necesidad"] not in servicio_comparativa._analizando


def test_un_solo_cambio_a_evaluacion_aunque_la_necesidad_ya_estuviera_cargada(
    cliente, datos, app, ia_simulada
):
    """SQLAlchemy no refresca al bloquear una necesidad ya cargada en la sesión; si otra
    petición acaba de pasarla a evaluación, no se guarda otro cambio encima."""
    subir(cliente, datos)
    sesiones = app.extensions["remate.sesiones"]
    with sesiones() as primera:
        cargada = primera.get(Necesidad, datos["necesidad"])
        assert cargada.estado == "en_cotizacion"
        assert analizar_y_comparar(cliente, datos).status_code == 200  # la otra petición
        resultado = servicio_comparativa.analizar_y_comparar(
            primera, app.config["REMATE"], app.config["REMATE"].archivos_dir,
            datos["necesidad"], datos["ana"],
        )  # fmt: skip
        assert resultado["necesidad"].estado == "en_evaluacion"
    with sesiones() as s:
        cambios = [c.estado_nuevo for c in s.get(Necesidad, datos["necesidad"]).historial]
    assert cambios.count("en_evaluacion") == 1


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [
        (1234.5, "1234.50"),
        ("1.234,56 €", "1234.56"),
        ("1,234.56", "1234.56"),
        ("12,5", "12.50"),
        (0.125, "0.13"),
        ("sin precio", None),
        (-1, None),
        (None, None),
        (10**13, None),
    ],
)
def test_numero_de_la_ia(valor, esperado):
    numero = _numero_ia(valor, 2)
    assert (str(numero) if numero is not None else None) == esperado


# --- Mejor y peor valor de la comparativa (paso 9) ----------------------------------------------


def en_evaluacion_con_dos_revisadas(cliente, datos):
    """Acme (500) y Zeta (300) revisadas y la necesidad en «En evaluación»."""
    ids = {}
    for remitente, importe in (("ventas@acme.test", "500"), ("ofertas@zeta.test", "300")):
        oferta = subir(cliente, datos, correo=eml(remitente=remitente)).json
        respuesta = cliente.patch(
            url(datos, f"/{oferta['id']}"),
            json={
                "importe_sin_iva": importe,
                "fecha_entrega_estimada": "2026-11-30",
                "revisada": True,
            },
        )
        assert respuesta.status_code == 200
        ids[oferta["proveedor"]["nombre"]] = oferta["id"]
    evaluacion = f"/api/necesidades/{datos['necesidad']}/evaluacion"
    assert cliente.post(evaluacion, json={"peticionario_id": datos["ana"]}).status_code == 200
    return ids


def destacados_de(cliente, datos):
    tabla = cliente.get(f"/api/necesidades/{datos['necesidad']}/comparativa").json
    return {o["proveedor"]["nombre"]: o["destacados"] for o in tabla}


def test_mejor_y_peor_con_todas_revisadas(cliente, datos):
    """En verde (mejor) y rojo (peor) el precio, la entrega y los retrasos. Las dos entregan el
    mismo día y ninguna tiene pedidos anteriores: ni la fecha ni los retrasos distinguen."""
    en_evaluacion_con_dos_revisadas(cliente, datos)
    assert destacados_de(cliente, datos) == {
        "Zeta": {"importe": "mejor", "entrega": None, "retrasos": None},
        "Acme": {"importe": "peor", "entrega": None, "retrasos": None},
    }
    # El resumen de la comparativa ya no existe.
    resumen = cliente.post(f"/api/necesidades/{datos['necesidad']}/comparativa/resumen")
    assert resumen.status_code in (404, 405)


def test_sin_marcas_mientras_falte_una_oferta_por_revisar(cliente, datos):
    """Solo se compara con todas revisadas; si llega otra (aunque esté sin analizar
    y no salga en la comparativa), las marcas se quitan hasta revisarla."""
    en_evaluacion_con_dos_revisadas(cliente, datos)
    tardia = subir(
        cliente, datos, correo=eml(remitente="ofertas@zeta.test"), confirmar_sustitucion="true"
    )
    assert tardia.status_code == 201
    sin_marcas = {"importe": None, "entrega": None, "retrasos": None}
    # La nueva de Zeta está sin analizar (no sale en la comparativa), pero ya quita las marcas.
    assert destacados_de(cliente, datos) == {"Acme": sin_marcas}
    otra = subir(cliente, datos, confirmar_sustitucion="true").json
    for oferta_id, importe in ((tardia.json["id"], "250"), (otra["id"], "400")):
        respuesta = cliente.patch(
            url(datos, f"/{oferta_id}"),
            json={
                "importe_sin_iva": importe,
                "fecha_entrega_estimada": "2026-11-30",
                "revisada": True,
            },
        )
        assert respuesta.status_code == 200
    assert destacados_de(cliente, datos) == {
        "Zeta": {"importe": "mejor", "entrega": None, "retrasos": None},
        "Acme": {"importe": "peor", "entrega": None, "retrasos": None},
    }


def test_con_monedas_distintas_se_marca_la_entrega_pero_no_el_precio(cliente, datos):
    ids = en_evaluacion_con_dos_revisadas(cliente, datos)
    cliente.patch(
        url(datos, f"/{ids['Acme']}"),
        json={"moneda": "USD", "fecha_entrega_estimada": "2026-11-20", "revisada": True},
    )
    assert destacados_de(cliente, datos) == {
        "Zeta": {"importe": None, "entrega": "peor", "retrasos": None},
        "Acme": {"importe": None, "entrega": "mejor", "retrasos": None},
    }


def _oferta_de_prueba(oferta_id, importe=None, entrega=None, revisada=True, moneda="EUR"):
    return SimpleNamespace(
        id=oferta_id,
        proveedor_id=oferta_id,
        importe_sin_iva=importe,
        fecha_entrega_estimada=entrega,
        revisada=revisada,
        moneda=moneda,
    )


def test_destacados_empates_datos_que_faltan_y_retrasos():
    """Un empate marca a todas las empatadas; un dato que falta no es peor; sin pedidos
    anteriores no hay retraso medio que comparar; con un solo valor distinto no se marca."""
    ofertas = [
        _oferta_de_prueba(1, Decimal(100), date(2026, 12, 1)),
        _oferta_de_prueba(2, Decimal(100), date(2026, 12, 9)),
        _oferta_de_prueba(3, Decimal(150), None),
        _oferta_de_prueba(4, None, date(2026, 12, 9)),
    ]
    historial = {
        1: {"pedidos": 3, "dias_retraso": 0},
        2: {"pedidos": 2, "dias_retraso": 7},
        3: {"pedidos": 0, "dias_retraso": 0},
        4: {"pedidos": 4, "dias_retraso": 14},
    }
    assert destacados(ofertas, ofertas, historial) == {
        1: {"importe": "mejor", "entrega": "mejor", "retrasos": "mejor"},
        2: {"importe": "mejor", "entrega": "peor", "retrasos": "peor"},
        3: {"importe": "peor", "entrega": None, "retrasos": None},
        4: {"importe": None, "entrega": "peor", "retrasos": "peor"},
    }
    iguales = [_oferta_de_prueba(1, Decimal(5)), _oferta_de_prueba(2, Decimal(5))]
    sin_pedidos = {"pedidos": 0, "dias_retraso": 0}
    assert destacados(iguales, iguales, {1: sin_pedidos, 2: sin_pedidos}) == {
        1: {"importe": None, "entrega": None, "retrasos": None},
        2: {"importe": None, "entrega": None, "retrasos": None},
    }


def test_destacados_compara_el_retraso_medio_sin_redondear():
    """1 día de retraso en 21 pedidos se muestra como 0,0 días, pero es peor que no tener ningún
    retraso: se compara el valor sin redondear, para que no empaten."""
    ofertas = [_oferta_de_prueba(1), _oferta_de_prueba(2)]
    historial = {
        1: {"pedidos": 21, "dias_retraso": 1, "retraso_medio": 0.0},
        2: {"pedidos": 5, "dias_retraso": 0, "retraso_medio": 0.0},
    }
    marcas = destacados(ofertas, ofertas, historial)
    assert (marcas[1]["retrasos"], marcas[2]["retrasos"]) == ("peor", "mejor")


def test_oferta_borrada_mientras_lee_la_ia(cliente, datos, app, monkeypatch):
    """Si la oferta se borra mientras responde la IA (la necesidad no
    queda bloqueada durante la llamada), no se guardan sus datos y se avisa con un 409."""
    oferta = subir(cliente, datos).json

    def leer_y_borrar(config, partes):
        with app.extensions["remate.sesiones"]() as otra:
            otra.get(Oferta, oferta["id"]).estado_oferta = "borrada"
            otra.commit()
        return RESPUESTA_IA

    monkeypatch.setattr(ia, "leer_oferta", leer_y_borrar)
    respuesta = cliente.post(url(datos, f"/{oferta['id']}/analisis"))
    assert respuesta.status_code == 409
    with app.extensions["remate.sesiones"]() as s:
        assert s.get(Oferta, oferta["id"]).numero_oferta is None


# --- Adjuntos del correo y proveedor por el dominio ---------------------------------------------


def eml_con_adjuntos(remitente="ventas@acme.test"):
    """Como los de Outlook: cuerpo en HTML con el logo de la firma incrustado (Content-ID), dos
    adjuntos de verdad y un correo reenviado adjunto."""
    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["Subject"] = "RE: 2026102301 | Línea 3 | Rodamiento roto"
    mensaje["Date"] = "Thu, 22 Oct 2026 09:15:00 +0200"
    mensaje.set_content("Les adjuntamos la oferta.")
    mensaje.add_alternative('<p>Les adjuntamos la oferta.</p><img src="cid:logo">', subtype="html")
    mensaje.get_payload()[1].add_related(
        b"\x89PNG logo", "image", "png", cid="<logo>", filename="logo.png"
    )
    mensaje.add_attachment(b"%PDF oferta", "application", "pdf", filename="oferta 123.pdf")
    mensaje.add_attachment(b"PK hoja", "application", "octet-stream", filename="a/../precios.xlsx")
    reenviado = EmailMessage()
    reenviado["Subject"] = "Plano revisado"
    reenviado.set_content("Ver plano.")
    mensaje.add_attachment(reenviado)
    return mensaje.as_bytes()


def test_el_lector_saca_los_adjuntos_sin_las_imagenes_del_cuerpo():
    leido = correos_entrada.leer("oferta.eml", eml_con_adjuntos())
    assert [(a.nombre, a.tipo_mime) for a in leido.adjuntos] == [
        ("oferta 123.pdf", "application/pdf"),
        # Sin carpetas en el nombre: no se puede salir de la carpeta de la oferta.
        ("precios.xlsx", "application/octet-stream"),
        ("Plano revisado.eml", "message/rfc822"),
    ]
    assert leido.adjuntos[0].datos == b"%PDF oferta"
    assert b"Ver plano." in leido.adjuntos[2].datos
    assert leido.cuerpo == "Les adjuntamos la oferta."


def test_un_correo_sin_adjuntos():
    assert correos_entrada.leer("oferta.eml", eml()).adjuntos == ()


def leer_correo(cliente, datos, correo):
    formulario = {"correo": (io.BytesIO(correo), "oferta.eml")}
    return cliente.post(url(datos, "/correo"), data=formulario, content_type="multipart/form-data")


def test_leer_el_correo_antes_de_subirlo(cliente, datos):
    respuesta = leer_correo(cliente, datos, eml_con_adjuntos())
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json["proveedor"]["nombre"] == "Acme"
    assert respuesta.json["aviso_proveedor"] is None
    assert [(a["indice"], a["nombre"]) for a in respuesta.json["adjuntos"]] == [
        (0, "oferta 123.pdf"),
        (1, "precios.xlsx"),
        (2, "Plano revisado.eml"),
    ]
    # No guarda nada.
    assert cliente.get(url(datos)).json == []


def test_leer_un_correo_que_no_vale(cliente, datos):
    respuesta = leer_correo(cliente, datos, b"esto no es un correo")
    assert respuesta.status_code == 422
    assert respuesta.json["detalles"] == {"campo": "correo"}


def test_subir_con_los_adjuntos_elegidos_del_correo(cliente, datos):
    respuesta = subir(
        cliente,
        datos,
        correo=eml_con_adjuntos(),
        adjuntos_correo=["2", "0"],
        tipos_adjunto_correo=["otro", "pdf"],
        adjuntos=[(io.BytesIO(b"%PDF plano"), "plano.pdf")],
        tipos_adjunto=["pdf"],
    )
    assert respuesta.status_code == 201, respuesta.json
    assert [(a["tipo"], a["formato"], a["nombre_archivo"]) for a in respuesta.json["archivos"]] == [
        ("correo_oferta", None, "oferta.eml"),
        ("adjunto_oferta", "otro", "Plano revisado.eml"),
        ("adjunto_oferta", "pdf", "oferta 123.pdf"),
        ("adjunto_oferta", "pdf", "plano.pdf"),
    ]


@pytest.mark.parametrize(
    ("extra", "campo"),
    [
        ({"adjuntos_correo": ["7"], "tipos_adjunto_correo": ["pdf"]}, "adjuntos_correo"),
        ({"adjuntos_correo": ["0"]}, "tipos_adjunto"),
        ({"adjuntos_correo": ["0"], "tipos_adjunto_correo": ["zip"]}, "tipos_adjunto"),
    ],
)
def test_adjuntos_del_correo_que_no_valen(cliente, datos, extra, campo):
    respuesta = subir(cliente, datos, correo=eml_con_adjuntos(), **extra)
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": campo}
    assert cliente.get(url(datos)).json == []


@pytest.mark.parametrize(
    "remitente", ["compras@acme.test", "Ana.Lopez@ventas.acme.test", "VENTAS@ACME.TEST"]
)
def test_reconoce_al_proveedor_por_el_dominio(cliente, datos, remitente):
    respuesta = subir(cliente, datos, correo=eml(remitente=remitente))
    assert respuesta.status_code == 201, respuesta.json
    assert respuesta.json["proveedor"]["nombre"] == "Acme"


@pytest.mark.parametrize("remitente", ["ventas@otroacme.test", "acme@gmail.com"])
def test_no_reconoce_otro_dominio_ni_un_correo_publico(app, cliente, datos, remitente):
    with app.extensions["remate.sesiones"]() as s:
        s.add(Proveedor(nombre="Autónomo", email="pepe@gmail.com"))
        s.commit()
    respuesta = subir(cliente, datos, correo=eml(remitente=remitente))
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "proveedor_id"}


def test_con_varios_del_mismo_dominio_elige_el_solicitado(app, cliente, datos):
    with app.extensions["remate.sesiones"]() as s:
        s.add(Proveedor(nombre="Acme Recambios", email="recambios@acme.test"))
        s.commit()
    respuesta = subir(cliente, datos, correo=eml(remitente="compras@acme.test"))
    assert respuesta.status_code == 201, respuesta.json
    assert respuesta.json["proveedor"]["nombre"] == "Acme"


def test_con_varios_del_mismo_dominio_sin_solicitar_pide_elegir(app, cliente, datos):
    with app.extensions["remate.sesiones"]() as s:
        s.add_all(
            [
                Proveedor(nombre="Zeta Norte", email="norte@zeta.test"),
                Proveedor(nombre="Zeta Sur", email="sur@zeta.test"),
            ]
        )
        s.commit()
    respuesta = leer_correo(cliente, datos, eml(remitente="compras@zeta.test"))
    assert respuesta.status_code == 200
    assert respuesta.json["proveedor"] is None
    assert "varios proveedores" in respuesta.json["aviso_proveedor"]


def test_la_ia_no_avisa_si_la_oferta_es_de_otra_persona_de_la_empresa(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = {
        **RESPUESTA_IA,
        "proveedor": {"nombre": "Acme", "email": "luis@ventas.acme.test"},
    }
    oferta = leida(cliente, datos, correo=eml(remitente="compras@acme.test"))
    assert not any("comprueba que es de" in a for a in oferta["avisos"])


@pytest.mark.parametrize(
    ("remitente", "para"),
    [
        ("ventas@acme.test", ["ventas@acme.test"]),
        ("Ventas@Acme.test", ["ventas@acme.test"]),
        ("luis@acme.test", ["ventas@acme.test", "luis@acme.test"]),
        ("luis@ventas.acme.test", ["ventas@acme.test", "luis@ventas.acme.test"]),
        # Otra empresa (por ejemplo, alguien del cliente que la reenvió) o sin remitente: solo el
        # correo de la lista.
        ("ana@empresa.test", ["ventas@acme.test"]),
        (None, ["ventas@acme.test"]),
    ],
)
def test_destinatarios_de_los_correos_al_proveedor(remitente, para):
    oferta = SimpleNamespace(
        proveedor=SimpleNamespace(email="ventas@acme.test"), remitente=remitente
    )
    assert ofertas_servicio.destinatarios(oferta) == para


# --- Si la oferta solo dice un mes, el último viernes de ese mes -------------------------------
# Fechas esperadas comprobadas con el módulo `calendar`.

CORREO = date(2026, 10, 22)


@pytest.mark.parametrize(
    ("mes", "anio", "esperada"),
    [
        (12, None, date(2026, 12, 25)),
        (12, 2027, date(2027, 12, 31)),
        # Sin año: el primer mes con ese nombre después del correo.
        (3, None, date(2027, 3, 26)),
        (10, None, date(2026, 10, 30)),
        (2, 2026, date(2026, 2, 27)),
        # Un año absurdo se ignora y se toma el del correo.
        (7, 1999, date(2027, 7, 30)),
        (13, None, None),
        (0, None, None),
        (True, None, None),
        ("12", None, None),
        (12.0, None, None),
        (None, 2026, None),
    ],
)
def test_ultimo_viernes_del_mes(mes, anio, esperada):
    assert ofertas_servicio.fecha_desde_mes(mes, anio, CORREO) == esperada


def test_un_mes_que_ya_paso_es_el_del_anio_siguiente():
    # El correo es del 31/10/2026, después del último viernes de octubre (el 30).
    assert ofertas_servicio.fecha_desde_mes(10, None, date(2026, 10, 31)) == date(2027, 10, 29)


def test_sin_anio_ni_fecha_del_correo_no_se_calcula():
    assert ofertas_servicio.fecha_desde_mes(12, None, None) is None
    assert ofertas_servicio.fecha_desde_mes(12, 2026, None) == date(2026, 12, 25)


DICIEMBRE = {
    **RESPUESTA_IA,
    "plazo_entrega": "diciembre",
    "fecha_entrega": None,
    "mes_entrega": 12,
    "anio_mes_entrega": None,
}


def test_la_lectura_con_solo_un_mes(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = DICIEMBRE
    oferta = leida(cliente, datos)
    assert oferta["fecha_entrega_estimada"] == "2026-12-25"
    assert oferta["plazo_entrega_texto"] == "diciembre"
    assert oferta["fecha_de_mes"] is True
    # No es un plazo: al hacer el pedido no se cuenta desde ese día.
    assert oferta["fecha_calculada"] is False

    # Si el ingeniero pone otra fecha, ya es la suya.
    corregida = cliente.patch(
        url(datos, f"/{oferta['id']}"), json={"fecha_entrega_estimada": "2026-12-18"}
    ).json
    assert corregida["fecha_de_mes"] is False


def test_una_fecha_concreta_manda_sobre_el_mes(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = {**DICIEMBRE, "fecha_entrega": "2026-12-04"}
    oferta = leida(cliente, datos)
    assert oferta["fecha_entrega_estimada"] == "2026-12-04"
    assert oferta["fecha_de_mes"] is False


# Una oferta con el plazo en cada línea y ninguno general.
PLAZOS_POR_LINEA = {
    **RESPUESTA_IA,
    "lineas": [
        {
            "descripcion": "Distancial D40 - E1",
            "cantidad": 3,
            "precio_unitario": 13,
            "fecha_entrega": None,
            "plazo_entrega": "18 - 20 días",
        },
        {
            "descripcion": "Inserto nivel 2",
            "cantidad": 1,
            "precio_unitario": 243,
            "fecha_entrega": None,
            "plazo_entrega": "5 Sem.",
        },
    ],
    "importe_sin_iva": 282,
    "plazo_entrega": None,
    "fecha_entrega": None,
}


def test_cada_linea_con_la_fecha_de_su_plazo(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = PLAZOS_POR_LINEA
    oferta = leida(cliente, datos)
    # Desde el correo (22/10/2026): 20 días (el número más alto del rango) y 5 semanas.
    assert [li["fecha_entrega"] for li in oferta["lineas"]] == ["2026-11-11", "2026-11-26"]
    # Sin plazo general, el de la línea que más tarda; sigue siendo un plazo (se cuenta desde el
    # día del pedido al adjudicar).
    assert oferta["fecha_entrega_estimada"] == "2026-11-26"
    assert oferta["plazo_entrega_texto"] == "5 Sem."
    assert oferta["fecha_calculada"] is True


def test_un_plazo_general_mas_corto_que_una_linea(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = {**PLAZOS_POR_LINEA, "plazo_entrega": "18-20 días"}
    oferta = leida(cliente, datos)
    assert oferta["fecha_entrega_estimada"] == "2026-11-26"
    assert oferta["plazo_entrega_texto"] == "5 Sem."


def test_un_plazo_general_mas_largo_que_las_lineas(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = {**PLAZOS_POR_LINEA, "plazo_entrega": "8 semanas"}
    oferta = leida(cliente, datos)
    assert oferta["fecha_entrega_estimada"] == "2026-12-17"
    assert oferta["plazo_entrega_texto"] == "8 semanas"


def test_una_fecha_concreta_de_linea(cliente, datos, ia_simulada):
    lineas = [
        PLAZOS_POR_LINEA["lineas"][0],
        {**PLAZOS_POR_LINEA["lineas"][1], "fecha_entrega": "2026-12-09", "plazo_entrega": None},
    ]
    ia_simulada["respuesta"] = {**PLAZOS_POR_LINEA, "lineas": lineas}
    oferta = leida(cliente, datos)
    assert [li["fecha_entrega"] for li in oferta["lineas"]] == ["2026-11-11", "2026-12-09"]
    # La fecha la dio el proveedor: no es un plazo calculado.
    assert oferta["fecha_entrega_estimada"] == "2026-12-09"
    assert oferta["plazo_entrega_texto"] is None
    assert oferta["fecha_calculada"] is False


def _leida(respuesta, fecha_correo=datetime(2026, 10, 22, 9, tzinfo=UTC)):
    """Lo que hace «Analizar» con la respuesta de la IA, sin base de datos."""
    oferta = SimpleNamespace(
        fecha_correo=fecha_correo,
        proveedor=SimpleNamespace(email="ventas@acme.test", nombre="Acme"),
        remitente="ventas@acme.test",
        numero_oferta="OF-1",
    )
    valores, lineas, avisos = ofertas_servicio._lectura(oferta, respuesta)
    for campo, valor in valores.items():
        setattr(oferta, campo, valor)
    oferta.lineas = lineas
    return oferta, avisos


PEDIDO = date(2026, 11, 18)


def test_en_sap_cada_linea_se_cuenta_desde_el_pedido():
    """Las líneas con plazo no se quedan con la fecha contada desde el correo (saldrían el 11/11,
    ya pasada, y el 26/11)."""
    oferta, _ = _leida(PLAZOS_POR_LINEA)
    entrega = servicio_adjudicacion.entrega_si_se_pide(oferta, PEDIDO)
    assert entrega == date(2026, 12, 23)
    tabla = servicio_adjudicacion.lineas_sap(oferta, "Útil", entrega, PEDIDO)
    assert [f["delivery_date"] for f in tabla] == ["08.12.2026", "23.12.2026"]
    necesidad = SimpleNamespace(oferta_adjudicada=oferta)
    assert servicio_adjudicacion.plazo_relativo(necesidad) == "5 Sem."


@pytest.mark.parametrize("plazo_general", ["5 semanas", None])
def test_una_fecha_fija_de_linea_no_quita_el_plazo(plazo_general, monkeypatch):
    """Una línea con fecha fija (27/11) no le gana al plazo de 5 semanas al leer la oferta: pedida
    el 18/11, la entrega sale el 23/12 y no el 27/11."""
    con_plazo = {"plazo_entrega": "5 semanas"} if plazo_general is None else {}
    lineas = [
        {**PLAZOS_POR_LINEA["lineas"][0], "plazo_entrega": None, **con_plazo},
        {**PLAZOS_POR_LINEA["lineas"][1], "fecha_entrega": "2026-11-27", "plazo_entrega": None},
    ]
    oferta, _ = _leida({**PLAZOS_POR_LINEA, "lineas": lineas, "plazo_entrega": plazo_general})
    assert oferta.fecha_entrega_estimada == date(2026, 11, 27)
    assert servicio_adjudicacion.entrega_si_se_pide(oferta, PEDIDO) == date(2026, 12, 23)
    monkeypatch.setattr(servicio_adjudicacion, "_hoy", lambda: PEDIDO)
    necesidad = SimpleNamespace(oferta_adjudicada=oferta)
    assert servicio_adjudicacion.plazo_relativo(necesidad) == "5 semanas"


def test_la_fecha_general_sigue_mandando_sobre_las_lineas():
    """Si la oferta da su fecha, esa es la entrega aunque una línea llegue después (como antes)."""
    oferta, _ = _leida({**PLAZOS_POR_LINEA, "fecha_entrega": "2026-11-20"})
    assert servicio_adjudicacion.entrega_si_se_pide(oferta, PEDIDO) == date(2026, 11, 20)
    tabla = servicio_adjudicacion.lineas_sap(oferta, "Útil", date(2026, 11, 20), PEDIDO)
    assert [f["delivery_date"] for f in tabla] == ["08.12.2026", "23.12.2026"]


def test_un_plazo_de_linea_que_no_se_entiende_se_conserva_y_se_avisa():
    """Un plazo que no se entiende («a convenir») no se pierde sin aviso ni se le vuelve a pedir
    al proveedor."""
    lineas = [{**li, "plazo_entrega": "a convenir"} for li in PLAZOS_POR_LINEA["lineas"]]
    oferta, avisos = _leida({**PLAZOS_POR_LINEA, "lineas": lineas})
    assert oferta.fecha_entrega_estimada is None
    assert oferta.plazo_entrega_texto == "a convenir"
    assert [li.plazo_entrega_texto for li in oferta.lineas] == ["a convenir", "a convenir"]
    # Con el plazo guardado, `que_falta` ya no se lo vuelve a pedir al proveedor.
    assert sum("no se ha podido pasar a fecha («a convenir»)" in a for a in avisos) == 2


def test_sin_fecha_del_correo_el_plazo_de_la_linea_no_se_pierde():
    lineas = [{**PLAZOS_POR_LINEA["lineas"][1]}]
    oferta, avisos = _leida({**PLAZOS_POR_LINEA, "lineas": lineas}, fecha_correo=None)
    assert oferta.plazo_entrega_texto == "5 Sem."
    assert oferta.lineas[0].plazo_entrega_texto == "5 Sem."
    assert any("«5 Sem.»" in a for a in avisos)


@pytest.mark.parametrize(
    ("respuesta", "aviso"),
    [
        ({"fecha_entrega": "2026-10-01"}, "La fecha de entrega (01/10/2026) es anterior al correo"),
        ({"fecha_entrega": "2062-12-15"}, "(15/12/2062) es dentro de más de 3 años"),
        (
            {"lineas": [{**PLAZOS_POR_LINEA["lineas"][0], "fecha_entrega": "2025-12-01"}]},
            "La entrega de la partida «Distancial D40 - E1» (01/12/2025) es anterior",
        ),
    ],
)
def test_una_fecha_de_entrega_rara_se_avisa(respuesta, aviso):
    """Una fecha mal leída (antes del correo, o un año de más) no gana la comparativa como la
    entrega más próxima sin ningún aviso."""
    oferta, _ = _leida({**PLAZOS_POR_LINEA, **respuesta})
    oferta.moneda, oferta.revisada, oferta.datos_ia = "EUR", False, None
    assert any(aviso in a for a in ofertas_servicio.avisos(oferta))


def test_una_fecha_normal_no_se_avisa():
    oferta, _ = _leida(PLAZOS_POR_LINEA)
    oferta.moneda, oferta.revisada, oferta.datos_ia = "EUR", False, None
    assert not any("revísala" in a for a in ofertas_servicio.avisos(oferta))


@pytest.mark.parametrize(
    ("valor", "esperada"),
    [
        ("2026-12-15", date(2026, 12, 15)),
        ("2026-12-15T00:00:00", date(2026, 12, 15)),
        ("15/12/2026", date(2026, 12, 15)),
        ("15.12.2026", date(2026, 12, 15)),
        ("30/02/2026", None),
        ("diciembre", None),
    ],
)
def test_fecha_de_la_ia(valor, esperada):
    assert ofertas_servicio._fecha_ia(valor) == esperada


@pytest.mark.parametrize(
    ("texto", "esperada"),
    [
        ("KW 50", date(2026, 12, 11)),
        ("Liefertermin KW50", date(2026, 12, 11)),
        ("CW 12/2027", date(2027, 3, 26)),
        ("semana 50", date(2026, 12, 11)),
        ("Sem. 50", date(2026, 12, 11)),
        ("semana nº 48", date(2026, 11, 27)),
        ("KW 50/26", date(2026, 12, 11)),
        # Ya pasada en el año del correo: la del año siguiente.
        ("KW 5", date(2027, 2, 5)),
        ("KW 60", None),
        # Rangos de semanas: la última («KW 48/49» no es el año 2049).
        ("KW 48/49", date(2026, 12, 4)),
        ("KW 50-51", date(2026, 12, 18)),
        ("semana 12-15", date(2027, 4, 16)),
        ("KW 2/27", date(2027, 1, 15)),
        # Plazos, no semanas del calendario.
        ("1 semana 3 días", None),
        ("1 week 3 days", None),
        ("Entrega: semana 2 tras pedido", None),
        ("semana 2 a partir del pedido", None),
        # Varias semanas: la última.
        ("1ª entrega semana 48, 2ª entrega semana 50", date(2026, 12, 11)),
        ("KW 50 bis KW 52", date(2026, 12, 25)),
        ("KW 50 - KW 52", date(2026, 12, 25)),
        ("KW 50 o 51", date(2026, 12, 18)),
        ("KW 52/01", date(2027, 1, 8)),
        ("KW 48/53", None),
        ("KW 50.2026", date(2026, 12, 11)),
        ("week 50, 2026", date(2026, 12, 11)),
        ("KW 1,5", None),
        # No las de la validez o las vacaciones; la raya como rango.
        ("Entrega KW 50 (cerrado por vacaciones semana 52 y 1)", date(2026, 12, 11)),
        ("Oferta válida hasta la semana 50. Entrega semana 48", date(2026, 11, 27)),
        ("Entrega 4 semanas. Oferta válida hasta semana 50", None),
        ("semana 50 – 52", date(2026, 12, 25)),
        # Varias semanas en frases distintas; vacaciones en alemán.
        ("Entrega semana 48. Resto semana 50", date(2026, 12, 11)),
        ("Liefertermin: KW 48\nRestmenge: KW 50", date(2026, 12, 11)),
        ("KW 50, Betriebsferien KW 52-1", date(2026, 12, 11)),
        ("KW 50, Werksurlaub KW 52", date(2026, 12, 11)),
        ("1 semana", None),
        ("2 semanas", None),
        ("3ª semana de diciembre", None),
        (None, None),
    ],
)
def test_fecha_desde_semana(texto, esperada):
    """«KW 50» (proveedores alemanes) es el viernes de esa semana."""
    assert ofertas_servicio.fecha_desde_semana(texto, date(2026, 10, 22)) == esperada


def test_una_semana_de_calendario_es_una_fecha_fija(monkeypatch):
    lineas = [{**PLAZOS_POR_LINEA["lineas"][0], "plazo_entrega": "KW 49"}]
    oferta, _ = _leida({**PLAZOS_POR_LINEA, "lineas": lineas, "plazo_entrega": "KW 50"})
    assert oferta.fecha_entrega_estimada == date(2026, 12, 11)
    assert oferta.lineas[0].fecha_entrega == date(2026, 12, 4)
    # No es un plazo: no se cuenta desde el pedido, ni en la oferta ni en la línea.
    assert ofertas_servicio.fecha_calculada(oferta) is False
    assert servicio_adjudicacion.entrega_si_se_pide(oferta, PEDIDO) == date(2026, 12, 11)
    tabla = servicio_adjudicacion.lineas_sap(oferta, "Útil", date(2026, 12, 11), PEDIDO)
    assert [f["delivery_date"] for f in tabla] == ["04.12.2026"]
    # Al proveedor se le repite lo que dijo.
    oferta.datos_ia = None
    necesidad = SimpleNamespace(
        codigo="2026102201", titulo="Útil", peticionario=SimpleNamespace(nombre_completo="Ana")
    )
    cuerpo = servicio_adjudicacion.cuerpo_adjudicacion(necesidad, oferta, "1 útil")
    assert "Plazo de entrega según su oferta: KW 50." in cuerpo
    assert "el proveedor dio la semana" in servicio_adjudicacion._entrega_para_ia(oferta)


def _con_avisos(respuesta):
    """La oferta leída y sus avisos como los ve el ingeniero (también al recargar)."""
    oferta, de_la_lectura = _leida(respuesta)
    oferta.moneda, oferta.revisada, oferta.datos_ia = "EUR", False, {"respuesta": respuesta}
    return oferta, [*de_la_lectura, *ofertas_servicio.avisos(oferta)]


@pytest.mark.parametrize(
    ("cantidad", "precio"), [(1, -100), (1, "-100,00"), (1, "−100,00 €"), (-1, 100)]
)
def test_un_descuento_como_linea_negativa_se_avisa(cantidad, precio):
    """La línea de descuento no se pierde con un aviso genérico («línea sin descripción,
    cantidad o precio»); tampoco un abono con la cantidad en negativo."""
    lineas = [
        PLAZOS_POR_LINEA["lineas"][1],
        {"descripcion": "Descuento 10 %", "cantidad": cantidad, "precio_unitario": precio},
    ]
    oferta, avisos = _con_avisos({**PLAZOS_POR_LINEA, "lineas": lineas})
    assert [li.descripcion for li in oferta.lineas] == ["Inserto nivel 2"]
    assert sum("«Descuento 10 %» (−100,00)" in a and "repártelo" in a for a in avisos) == 1
    assert not any("sin descripción, cantidad o precio" in a for a in avisos)
    # Revisada, ya no se avisa.
    oferta.revisada = True
    assert not any("Descuento" in a for a in ofertas_servicio.avisos(oferta))


def test_tras_revisar_no_vuelven_los_avisos_del_descuento_ni_de_la_suma(
    cliente, datos, ia_simulada
):
    """Tras repartir el descuento y revisar, al tocar otro dato no vuelve el aviso (riesgo de
    aplicarlo dos veces); y el de la suma no sale con un importe escrito por el ingeniero."""
    lineas = [
        PLAZOS_POR_LINEA["lineas"][1],
        {"descripcion": "Descuento 10 %", "cantidad": 1, "precio_unitario": -24.3},
    ]
    ia_simulada["respuesta"] = {**PLAZOS_POR_LINEA, "lineas": lineas, "importe_sin_iva": None}
    oferta = leida(cliente, datos)
    ruta = url(datos, f"/{oferta['id']}")
    revisada = cliente.patch(
        ruta,
        json={
            "importe_sin_iva": "218.70",
            "lineas": [{"descripcion": "Inserto", "cantidad": "1", "precio_unitario": "218.70"}],
            "revisada": True,
        },
    ).json
    assert revisada["revisada"] is True
    otra = cliente.patch(ruta, json={"otros": "Portes pagados"}).json
    assert otra["revisada"] is False
    assert not any("descuento" in a.lower() for a in otra["avisos"])
    assert not any("suma de las partidas" in a for a in otra["avisos"])


def test_el_aviso_de_la_suma_sigue_al_importe_tras_la_respuesta_del_proveedor():
    """Si la respuesta cambia un precio, el importe se vuelve a sumar y el aviso de que no da el
    total sigue; si la respuesta da el total, el aviso desaparece."""
    proveedor = SimpleNamespace(nombre="P", email="v@prov.test")
    respuesta = {
        "moneda": "EUR",
        "lineas": [{"descripcion": "Retén", "cantidad": 2, "precio_unitario": 10}],
        "importe_sin_iva": None,
        "plazo_entrega": "3 semanas",
    }
    oferta = Oferta(
        proveedor=proveedor, remitente="v@prov.test", revisada=False, datos_ia=None,
        fecha_correo=datetime(2026, 10, 22, 8, tzinfo=UTC), lineas=[], condiciones=None,
    )  # fmt: skip
    ofertas_servicio._aplicar_lectura(oferta, respuesta, "m")
    ofertas_servicio._completar(
        oferta, {"lineas": [{"descripcion": "Retén", "precio_unitario": 12}]}, "m"
    )
    assert oferta.importe_sin_iva == Decimal("24.00")
    assert any("no da el importe total" in a for a in ofertas_servicio.avisos(oferta))
    ofertas_servicio._completar(oferta, {"importe_sin_iva": 24}, "m")
    assert not any("no da el importe total" in a for a in ofertas_servicio.avisos(oferta))


def test_el_aviso_de_la_suma_no_sale_con_un_importe_del_ingeniero(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = {**PLAZOS_POR_LINEA, "importe_sin_iva": None}
    oferta = leida(cliente, datos)
    assert any("suma de las partidas (282,00)" in a for a in oferta["avisos"])
    lineas = [
        {"descripcion": "Distancial", "cantidad": "3", "precio_unitario": "13"},
        {"descripcion": "Inserto", "cantidad": "1", "precio_unitario": "243"},
        {"descripcion": "Portes", "cantidad": "1", "precio_unitario": "18"},
    ]
    cambiada = cliente.patch(
        url(datos, f"/{oferta['id']}"), json={"importe_sin_iva": "300", "lineas": lineas}
    ).json
    assert not any("suma de las partidas" in a for a in cambiada["avisos"])


def test_los_avisos_del_descuento_y_de_la_suma_siguen_al_recargar(cliente, datos, ia_simulada):
    """No se pierden al recargar la lista de ofertas."""
    lineas = [
        PLAZOS_POR_LINEA["lineas"][1],
        {"descripcion": "Dto. pronto pago", "cantidad": 1, "precio_unitario": -5},
    ]
    ia_simulada["respuesta"] = {**PLAZOS_POR_LINEA, "lineas": lineas, "importe_sin_iva": None}
    leida(cliente, datos)
    avisos = cliente.get(url(datos)).json[0]["avisos"]
    assert any("«Dto. pronto pago» (−5,00)" in a for a in avisos)
    assert any("se ha puesto la suma de las partidas (243,00)" in a for a in avisos)


@pytest.mark.parametrize(
    ("valor", "ingles"),
    [
        ("de", True), ("EN", True), ("en-GB", True), ("english", True), ("pt-BR", True),
        ("es", False), ("ES", False), ("spa", False), ("ca", False), ("gl", False),
        ("eu", False), (None, False), ("xx-raro-123", False), ("va", False),
        ("va-ES", False), ("valenciano", False), ("sp", False), ("galego", False),
    ],
)  # fmt: skip
def test_idioma_del_proveedor(valor, ingles):
    """Catalán, gallego y euskera no van en inglés; «en-GB» y «english» no van en español."""
    oferta = SimpleNamespace(datos_ia={"respuesta": {"idioma": valor}})
    idioma = ofertas_servicio.idioma(oferta)
    assert (idioma not in ofertas_servicio.IDIOMAS_EN_ESPANOL) is ingles


def test_dia_del_pedido_para_la_informacion_sap(monkeypatch):
    monkeypatch.setattr(servicio_adjudicacion, "_hoy", lambda: PEDIDO)
    sin_pedido = SimpleNamespace(historial=[])
    assert servicio_adjudicacion._dia_del_pedido(sin_pedido) == PEDIDO
    # Las 23:30 en UTC del 1/12 ya son el 2/12 en Madrid.
    con_pedido = SimpleNamespace(
        historial=[
            SimpleNamespace(
                estado_nuevo="pendiente_entrega",
                cambiado_en=datetime(2026, 12, 1, 23, 30, tzinfo=UTC),
            )
        ]
    )
    assert servicio_adjudicacion._dia_del_pedido(con_pedido) == date(2026, 12, 2)


def test_al_corregir_una_linea_con_plazo_se_calcula_su_fecha(cliente, datos):
    oferta = subir(cliente, datos).json
    lineas = [
        {"descripcion": "Inserto", "cantidad": "1", "precio_unitario": "243", "fecha_entrega": None,
         "plazo_entrega_texto": " 5 semanas "},
        {"descripcion": "Pines", "cantidad": "2", "precio_unitario": "210",
         "fecha_entrega": "2026-12-01", "plazo_entrega_texto": "5 semanas"},
    ]  # fmt: skip
    corregida = cliente.patch(url(datos, f"/{oferta['id']}"), json={"lineas": lineas}).json
    assert [(li["fecha_entrega"], li["plazo_entrega_texto"], li["fecha_calculada"]) for li in
            corregida["lineas"]] == [
        ("2026-11-26", "5 semanas", True),
        # El ingeniero puso otra fecha: es la suya, no se vuelve a contar.
        ("2026-12-01", "5 semanas", False),
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("correo", "texto", "esperada"),
    [
        # Del 1 al 3 de enero el año ISO puede ser aún el anterior.
        (date(2027, 1, 2), "KW 2", date(2027, 1, 15)),
        (date(2027, 1, 1), "semana 50", date(2027, 12, 17)),
        (date(2026, 12, 30), "KW 1", date(2027, 1, 8)),
    ],
)
def test_semana_a_principio_de_anio(correo, texto, esperada):
    assert ofertas_servicio.fecha_desde_semana(texto, correo) == esperada


@pytest.mark.parametrize(
    ("texto", "guardada"),
    [
        # Lo que se guardó con el cálculo anterior, aunque fuera raro.
        ("1,5 semanas", date(2026, 11, 26)),
        ("cuarenta y cinco días", date(2026, 10, 27)),
        ("entre 2 semanas y 20 días", date(2026, 11, 5)),
        ("2 semanas / 10 días", date(2026, 11, 5)),
        ("4 semanas y 2 días", date(2026, 11, 19)),
        ("3-4 semanas", date(2026, 11, 12)),
    ],
)
def test_lo_guardado_antes_se_reconoce_como_plazo(texto, guardada):
    oferta = SimpleNamespace(
        plazo_entrega_texto=texto,
        fecha_entrega_estimada=guardada,
        fecha_correo=datetime(2026, 10, 22, 9, tzinfo=UTC),
    )
    assert ofertas_servicio.fecha_calculada(oferta) is True


def test_un_rango_calculado_antes_con_el_primer_numero_sigue_siendo_un_plazo():
    """Antes se tomaba el primer número del rango: esas ofertas guardadas siguen
    contando como plazo (al adjudicar se cuenta desde el día del pedido)."""
    oferta = SimpleNamespace(
        plazo_entrega_texto="3-4 semanas",
        fecha_entrega_estimada=date(2026, 11, 12),
        fecha_correo=datetime(2026, 10, 22, 9, tzinfo=UTC),
    )
    assert ofertas_servicio.fecha_calculada(oferta) is True


def test_la_fecha_general_manda_sobre_las_lineas(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = {**PLAZOS_POR_LINEA, "fecha_entrega": "2026-11-20"}
    oferta = leida(cliente, datos)
    assert oferta["fecha_entrega_estimada"] == "2026-11-20"
    assert [li["fecha_entrega"] for li in oferta["lineas"]] == ["2026-11-11", "2026-11-26"]


def _oferta_de_diciembre(fecha=date(2026, 12, 25)):
    return SimpleNamespace(
        numero_oferta="OF-1",
        plazo_entrega_texto="diciembre de 2026",
        fecha_entrega_estimada=fecha,
        fecha_correo=datetime(2026, 10, 22, 9, tzinfo=UTC),
        datos_ia={"respuesta": {"mes_entrega": 12, "anio_mes_entrega": 2026}},
        lineas=[],
    )


def test_al_proveedor_se_le_repite_el_mes_y_la_fecha_no_se_mueve():
    oferta = _oferta_de_diciembre()
    necesidad = SimpleNamespace(
        codigo="2026102201", titulo="Útil", peticionario=SimpleNamespace(nombre_completo="Ana")
    )
    cuerpo = servicio_adjudicacion.cuerpo_adjudicacion(necesidad, oferta, "1 útil")
    assert "Plazo de entrega según su oferta: diciembre de 2026." in cuerpo
    assert "25/12/2026" not in cuerpo
    # Un mes es una fecha fija: no se vuelve a contar desde el día del pedido.
    assert servicio_adjudicacion.entrega_si_se_pide(oferta, date(2026, 11, 20)) == date(
        2026, 12, 25
    )
    assert "el proveedor dio solo el mes" in servicio_adjudicacion._entrega_para_ia(oferta)


def test_con_otra_fecha_se_le_dice_la_fecha():
    oferta = _oferta_de_diciembre(date(2026, 12, 18))
    necesidad = SimpleNamespace(
        codigo="2026102201", titulo="Útil", peticionario=SimpleNamespace(nombre_completo="Ana")
    )
    cuerpo = servicio_adjudicacion.cuerpo_adjudicacion(necesidad, oferta, "1 útil")
    assert "Fecha de entrega según su oferta: 18/12/2026." in cuerpo


# --- Condiciones de la oferta en una tabla ------------------------------------------------------

CON_CONDICIONES = {
    **RESPUESTA_IA,
    "condiciones": {
        "incoterm": {"estado": "especificado", "texto": "FCA Barcelona"},
        "transporte": {"estado": "no_incluido", "texto": "Portes a cargo del cliente"},
        "validez": {"estado": "especificado", "texto": "30 días"},
    },
    "otros": "Garantía de 12 meses",
}


def test_la_ia_rellena_la_tabla(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = CON_CONDICIONES
    oferta = leida(cliente, datos)
    porclave = {c["clave"]: c for c in oferta["condiciones"]}
    assert [c["clave"] for c in oferta["condiciones"]] == [c for c, _ in condiciones.CONDICIONES]
    assert porclave["incoterm"]["nombre"] == "Incoterm / condiciones de entrega"
    assert porclave["incoterm"]["texto"] == "FCA Barcelona"
    assert porclave["transporte"]["estado"] == "no_incluido"
    assert porclave["embalaje"]["estado"] == "no_especificado"
    assert oferta["otros"] == "Garantía de 12 meses"


def test_una_oferta_sin_leer_sale_sin_especificar(cliente, datos):
    oferta = subir(cliente, datos).json
    assert {c["estado"] for c in oferta["condiciones"]} == {"no_especificado"}


def test_corregir_una_condicion_no_toca_las_demas(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = CON_CONDICIONES
    oferta = leida(cliente, datos)
    respuesta = cliente.patch(
        url(datos, f"/{oferta['id']}"),
        json={"condiciones": {"embalaje": {"estado": "incluido", "texto": None}}},
    )
    assert respuesta.status_code == 200, respuesta.json
    porclave = {c["clave"]: c for c in respuesta.json["condiciones"]}
    assert porclave["embalaje"]["estado"] == "incluido"
    assert porclave["incoterm"]["texto"] == "FCA Barcelona"
    assert respuesta.json["revisada"] is False


def test_un_estado_que_no_existe_se_rechaza(cliente, datos):
    oferta = subir(cliente, datos).json
    respuesta = cliente.patch(
        url(datos, f"/{oferta['id']}"),
        json={"condiciones": {"embalaje": {"estado": "quizas", "texto": None}}},
    )
    assert respuesta.status_code in (400, 422)


# --- Pedir al proveedor los datos que faltan ---------------------------------------------------

NOMBRES_CONDICIONES = [nombre for _, nombre in condiciones.CONDICIONES]
# Sin condiciones de pago ni partidas; con dos condiciones respondidas.
INCOMPLETA = {
    **RESPUESTA_IA,
    "condiciones_pago": None,
    "lineas": [],
    "condiciones": {
        "incoterm": {"estado": "especificado", "texto": "FCA Barcelona"},
        "utillaje": {"estado": "no_incluido", "texto": None},
    },
}


def test_una_oferta_sin_analizar_no_pide_nada(cliente, datos):
    assert subir(cliente, datos).json["datos_que_faltan"] == []


def test_lo_que_falta_en_una_oferta_leida(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = INCOMPLETA
    oferta = leida(cliente, datos)
    respondidas = {"Incoterm / condiciones de entrega", "Utillaje"}
    assert oferta["datos_que_faltan"] == [
        "Las condiciones de pago",
        "El desglose por partidas (cantidad y precio unitario de cada una)",
        *[n for n in NOMBRES_CONDICIONES if n not in respondidas],
    ]


def test_borrador_redactado_por_la_ia(cliente, datos, ia_simulada, monkeypatch):
    ia_simulada["respuesta"] = INCOMPLETA
    oferta = leida(cliente, datos, correo=eml(remitente="luis@acme.test"))
    recibido = {}

    def redactar(_config, **datos_ia):
        recibido.update(datos_ia)
        return {"peticion": "- Condiciones de pago\n- Embalaje", "avisos": []}

    monkeypatch.setattr(ia, "redactar_peticion_datos", redactar)
    respuesta = cliente.post(url(datos, f"/{oferta['id']}/peticion-datos/borrador"))
    assert respuesta.status_code == 200, respuesta.json
    borrador = respuesta.json
    # A la IA solo le llega esto.
    assert set(recibido) == {"proveedor", "titulo", "numero_oferta", "faltan", "ingles"}
    assert recibido["ingles"] is False
    assert recibido["proveedor"] == "Acme"
    assert recibido["faltan"] == oferta["datos_que_faltan"]
    # Al proveedor y a la persona de su empresa que envió la oferta, con el asunto común.
    assert borrador["para"] == "ventas@acme.test, luis@acme.test"
    assert borrador["asunto"].endswith("| Línea 3 | Rodamiento roto")
    assert borrador["con_ia"] is True
    cuerpo = borrador["cuerpo"]
    assert "Gracias por su oferta OF-2026-55 para «Rodamiento roto»" in cuerpo
    assert "- Condiciones de pago\n- Embalaje" in cuerpo
    assert cuerpo.rstrip().endswith("Ana Prueba\nIndustrias Ficticias")


def test_a_un_proveedor_extranjero_se_le_escribe_en_ingles(
    cliente, datos, ia_simulada, monkeypatch
):
    """Si su oferta viene en otro idioma,
    el correo que le pide los datos va en inglés; sin la IA, en español."""
    ia_simulada["respuesta"] = {**INCOMPLETA, "idioma": "de"}
    oferta = leida(cliente, datos)
    recibido = {}

    def redactar(_config, **datos_ia):
        recibido.update(datos_ia)
        return {"peticion": "- Payment terms", "avisos": []}

    monkeypatch.setattr(ia, "redactar_peticion_datos", redactar)
    borrador = cliente.post(url(datos, f"/{oferta['id']}/peticion-datos/borrador")).json
    assert recibido["ingles"] is True
    assert borrador["cuerpo"].startswith("Good morning,\n\nThank you for your quotation OF-2026-55")
    assert "- Payment terms" in borrador["cuerpo"]
    assert "please keep the reference" in borrador["cuerpo"]
    assert any("en inglés" in a for a in borrador["avisos"])

    def falla(_config, **_datos):
        raise ia.ErrorIA("La IA no ha respondido.")

    monkeypatch.setattr(ia, "redactar_peticion_datos", falla)
    sin_ia = cliente.post(url(datos, f"/{oferta['id']}/peticion-datos/borrador")).json
    assert sin_ia["cuerpo"].startswith("Buenos días:")


def test_sin_total_el_importe_es_la_suma_de_las_lineas(cliente, datos, ia_simulada):
    """Una oferta que solo da el total de cada línea: el importe se suma de las líneas, con
    aviso, y no se le pide al proveedor un dato que ya está."""
    ia_simulada["respuesta"] = {**PLAZOS_POR_LINEA, "importe_sin_iva": None}
    oferta = leida(cliente, datos)
    assert oferta["importe_sin_iva"] == "282.00"
    assert any("no da el importe total" in a and "282,00" in a for a in oferta["avisos"])
    assert "El importe total sin IVA" not in oferta["datos_que_faltan"]


def test_sin_ia_va_la_lista_tal_cual(cliente, datos, ia_simulada, monkeypatch):
    ia_simulada["respuesta"] = INCOMPLETA
    oferta = leida(cliente, datos)

    def falla(_config, **_datos):
        raise ia.ErrorIA("La IA no ha respondido.")

    monkeypatch.setattr(ia, "redactar_peticion_datos", falla)
    borrador = cliente.post(url(datos, f"/{oferta['id']}/peticion-datos/borrador")).json
    assert borrador["con_ia"] is False
    assert "- Las condiciones de pago\n- El desglose por partidas" in borrador["cuerpo"]
    assert any("No se ha podido usar la IA" in a for a in borrador["avisos"])


def test_descarga_el_eml_sin_guardarlo(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = INCOMPLETA
    oferta = leida(cliente, datos)
    respuesta = cliente.post(
        url(datos, f"/{oferta['id']}/peticion-datos"), json={"cuerpo": "Hola,\n\n- Embalaje\n"}
    )
    assert respuesta.status_code == 200
    assert respuesta.mimetype == "message/rfc822"
    assert "datos que faltan.eml" in respuesta.headers["Content-Disposition"]
    correo = message_from_bytes(respuesta.data, policy=default)
    assert correo["To"] == "ventas@acme.test"
    assert correo["X-Unsent"] == "1"
    assert correo["Subject"].endswith("| Línea 3 | Rodamiento roto")
    assert "- Embalaje" in correo.get_content()
    # No se guarda: la oferta y la necesidad tienen los mismos archivos que antes.
    despues = cliente.get(url(datos)).json[0]
    assert [a["nombre_archivo"] for a in despues["archivos"]] == ["oferta.eml"]
    assert cliente.get(f"/api/necesidades/{datos['necesidad']}").json["adjuntos"] == []


def test_cuerpo_vacio_o_nada_que_pedir(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = INCOMPLETA
    oferta = leida(cliente, datos)
    vacio = cliente.post(url(datos, f"/{oferta['id']}/peticion-datos"), json={"cuerpo": "  "})
    assert vacio.status_code == 400
    assert vacio.json["detalles"] == {"campo": "cuerpo"}
    sin_analizar = subir(cliente, datos, confirmar_sustitucion="true").json
    nada = cliente.post(url(datos, f"/{sin_analizar['id']}/peticion-datos/borrador"))
    assert nada.status_code == 400
    assert nada.json["mensaje"] == "A esta oferta no le falta ningún dato que pedir."


# --- «Añadir datos del proveedor» -------------------------------------------------------------

RESPUESTA_DEL_PROVEEDOR = {
    "moneda": "EUR",
    "proveedor": {"nombre": "Acme", "email": "ventas@acme.test"},
    "numero_oferta": None,
    "lineas": [{"descripcion": "Rodamiento 6204-2RS", "cantidad": 4, "precio_unitario": 12.5}],
    # Otro importe: la respuesta manda y se cambia, con aviso.
    "importe_sin_iva": 999,
    "plazo_entrega": None,
    "fecha_entrega": None,
    "condiciones_pago": "Transferencia a 60 días",
    "condiciones": {
        "embalaje": {"estado": "incluido", "texto": None},
        # Ya estaba «FCA Barcelona»: se cambia, con aviso.
        "incoterm": {"estado": "especificado", "texto": "EXW Madrid"},
    },
    "otros": None,
    "avisos": [],
}


def correo_respuesta(remitente="ventas@acme.test"):
    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["Subject"] = "RE: 2026102301 | Línea 3 | Rodamiento roto"
    mensaje["Date"] = "Mon, 26 Oct 2026 10:00:00 +0100"
    mensaje.set_content("Pago a 60 días. El embalaje va incluido.")
    return mensaje.as_bytes()


def anadir_datos(cliente, datos, correo=None, **extra):
    return subir(cliente, datos, correo=correo or correo_respuesta(), anadir_datos="true", **extra)


def test_la_respuesta_completa_y_cambia_la_oferta(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = INCOMPLETA
    oferta = leida(cliente, datos)
    ia_simulada["respuesta"] = RESPUESTA_DEL_PROVEEDOR
    respuesta = anadir_datos(cliente, datos)
    assert respuesta.status_code == 200, respuesta.json
    completada = respuesta.json
    assert completada["id"] == oferta["id"]
    assert completada["condiciones_pago"] == "Transferencia a 60 días"
    assert [li["descripcion"] for li in completada["lineas"]] == ["Rodamiento 6204-2RS"]
    porclave = {c["clave"]: c for c in completada["condiciones"]}
    assert porclave["embalaje"]["estado"] == "incluido"
    # La respuesta manda: lo que ya tenía valor también cambia.
    assert porclave["incoterm"]["texto"] == "EXW Madrid"
    assert completada["importe_sin_iva"] == "999.00"
    # Lo que la respuesta no dice se queda: el plazo se sigue contando desde el correo de la oferta.
    assert completada["fecha_entrega_estimada"] == oferta["fecha_entrega_estimada"]
    assert completada["numero_oferta"] == oferta["numero_oferta"]
    assert completada["revisada"] is False
    avisos = " ".join(completada["avisos"])
    assert "completa: condiciones de pago, embalaje, partidas" in avisos
    assert "cambia (revísalo): importe sin IVA: 50,00 → 999,00" in avisos
    assert "Incoterm / condiciones de entrega: FCA Barcelona → EXW Madrid" in avisos
    assert [a["tipo"] for a in completada["archivos"]] == ["correo_oferta", "respuesta_oferta"]
    # Ya no se pide lo que ha llegado.
    assert "Las condiciones de pago" not in completada["datos_que_faltan"]
    assert "Embalaje" not in completada["datos_que_faltan"]
    # La IA lee solo la respuesta, con lo que se le pidió (no el correo de la oferta).
    textos = [p["text"] for p in ia_simulada["lecturas"][-1] if p.get("type") == "input_text"]
    assert any("Lo que se le pidió al proveedor" in t and "- Embalaje" in t for t in textos)
    assert any("Respuesta del proveedor" in t for t in textos)
    assert not any("Correo del proveedor" in t for t in textos)


def _respuesta_con_lineas(lineas, **extra):
    vacia = {campo: None for campo in RESPUESTA_DEL_PROVEEDOR}
    return {**vacia, "condiciones": {}, "avisos": [], "lineas": lineas, **extra}


def test_la_respuesta_cambia_el_precio_de_una_partida(cliente, datos, ia_simulada):
    """La respuesta cambia también el precio unitario de una partida que ya estaba, no solo la
    entrega."""
    oferta = leida(cliente, datos)
    assert oferta["lineas"][0]["precio_unitario"] == "12.50"
    ia_simulada["respuesta"] = _respuesta_con_lineas(
        [{"descripcion": "rodamiento  6204-2RS", "cantidad": 4, "precio_unitario": 15}],
        fecha_entrega="2026-12-04",
    )
    completada = anadir_datos(cliente, datos).json
    assert completada["lineas"][0]["precio_unitario"] == "15.00"
    assert completada["lineas"][0]["descripcion"] == "Rodamiento 6204-2RS"
    assert completada["fecha_entrega_estimada"] == "2026-12-04"
    # El importe era la suma de las partidas y la respuesta no da otro: se recalcula.
    assert completada["importe_sin_iva"] == "60.00"
    avisos = " ".join(completada["avisos"])
    assert "partida «Rodamiento 6204-2RS», precio unitario: 12,50 → 15,00" in avisos
    assert "importe sin IVA (suma de las partidas): 50,00 → 60,00" in avisos
    # Lo que no dice la respuesta no se toca.
    assert completada["condiciones_pago"] == "Transferencia a 30 días"


def _oferta_con_lineas(cliente, datos, ia_simulada, lineas, importe):
    ia_simulada["respuesta"] = {**RESPUESTA_IA, "lineas": lineas, "importe_sin_iva": importe}
    return leida(cliente, datos)


def _linea(descripcion, cantidad, precio):
    return {"descripcion": descripcion, "cantidad": cantidad, "precio_unitario": precio}


def _precios(oferta):
    return [(li["descripcion"], li["cantidad"], li["precio_unitario"]) for li in oferta["lineas"]]


def test_partidas_de_la_respuesta_por_orden_si_no_se_reconoce_ninguna(cliente, datos, ia_simulada):
    oferta = leida(cliente, datos)
    # Tantas como en la oferta y ninguna reconocida: por su orden, sin cambiar la descripción.
    ia_simulada["respuesta"] = _respuesta_con_lineas([_linea("Rodamiento rígido", 5, 12.5)])
    completada = anadir_datos(cliente, datos).json
    assert _precios(completada) == [("Rodamiento 6204-2RS", "5", "12.50")]
    assert completada["id"] == oferta["id"]


def test_partidas_reconocidas_a_medias_no_se_cruzan(cliente, datos, ia_simulada):
    """Con una reconocida y otra no, no se emparejan por orden (el rodamiento se quedaría con el
    precio del retén): la que no se reconoce se añade y las que la respuesta no nombra se
    quedan."""
    _oferta_con_lineas(
        cliente, datos, ia_simulada, [_linea("Rodamiento", 1, 10), _linea("Retén", 1, 3)], 13
    )
    ia_simulada["respuesta"] = _respuesta_con_lineas([_linea("Retén", 1, 4), _linea("Junta", 1, 1)])
    completada = anadir_datos(cliente, datos).json
    assert _precios(completada) == [
        ("Rodamiento", "1", "10.00"),
        ("Retén", "1", "4.00"),
        ("Junta", "1", "1.00"),
    ]
    assert completada["importe_sin_iva"] == "15.00"
    avisos = " ".join(completada["avisos"])
    assert "partida «Retén», precio unitario: 3,00 → 4,00" in avisos
    assert "partida nueva «Junta»" in avisos


def test_mas_partidas_en_la_respuesta_no_borran_las_que_no_nombra(cliente, datos, ia_simulada):
    """Las partidas nuevas no sustituyen a todas: el retén se queda."""
    _oferta_con_lineas(
        cliente, datos, ia_simulada, [_linea("Rodamiento", 1, 10), _linea("Retén", 2, 3)], 16
    )
    ia_simulada["respuesta"] = _respuesta_con_lineas(
        [_linea("Rodamiento", 1, 12), _linea("Portes", 1, 15), _linea("Embalaje", 1, 5)]
    )
    completada = anadir_datos(cliente, datos).json
    assert [li["descripcion"] for li in completada["lineas"]] == [
        "Rodamiento",
        "Retén",
        "Portes",
        "Embalaje",
    ]
    assert completada["importe_sin_iva"] == "38.00"


def test_descripciones_repetidas_se_emparejan_por_orden(cliente, datos, ia_simulada):
    """La misma pieza en dos partidas: cambian las dos, no solo la última."""
    _oferta_con_lineas(
        cliente,
        datos,
        ia_simulada,
        [_linea("Rodamiento 6204", 2, 10), _linea("Rodamiento 6204", 3, 10)],
        50,
    )
    ia_simulada["respuesta"] = _respuesta_con_lineas(
        [_linea("Rodamiento 6204", 2, 11), _linea("Rodamiento 6204", 3, 12)]
    )
    completada = anadir_datos(cliente, datos).json
    assert [li["precio_unitario"] for li in completada["lineas"]] == ["11.00", "12.00"]
    assert completada["importe_sin_iva"] == "58.00"
    # Con descripciones repetidas y distinto número de partidas no se sabe cuál es: no se tocan.
    ia_simulada["respuesta"] = _respuesta_con_lineas([_linea("Rodamiento 6204", 2, 20)])
    otra = anadir_datos(cliente, datos).json
    assert [li["precio_unitario"] for li in otra["lineas"]] == ["11.00", "12.00"]
    assert any("descripciones repetidas" in a for a in otra["avisos"])


def test_la_respuesta_da_solo_el_precio_nuevo(cliente, datos, ia_simulada):
    """Sin repetir la cantidad, la línea no se descarta y el cambio se aplica."""
    leida(cliente, datos)
    ia_simulada["respuesta"] = _respuesta_con_lineas([_linea("Rodamiento 6204-2RS", None, 15)])
    completada = anadir_datos(cliente, datos).json
    assert _precios(completada) == [("Rodamiento 6204-2RS", "4", "15.00")]
    assert not any("sin descripción, cantidad o precio" in a for a in completada["avisos"])
    # Una partida nueva sin cantidad no se puede añadir: se avisa.
    ia_simulada["respuesta"] = _respuesta_con_lineas(
        [_linea("Rodamiento 6204-2RS", None, 16), _linea("Portes", None, 9)]
    )
    otra = anadir_datos(cliente, datos).json
    assert _precios(otra) == [("Rodamiento 6204-2RS", "4", "16.00")]
    assert any("«Portes»" in a and "sin cantidad o sin precio" in a for a in otra["avisos"])


def test_partidas_de_la_respuesta_que_no_se_reconocen(cliente, datos, ia_simulada):
    """Menos partidas que en la oferta y ninguna reconocida: se añaden como nuevas y las
    de la oferta se quedan; el aviso pide comprobar que no son las mismas con otro nombre."""
    _oferta_con_lineas(
        cliente,
        datos,
        ia_simulada,
        [_linea("Rodamiento 6204-2RS", 4, 12.5), _linea("Retén", 4, 3)],
        62,
    )
    ia_simulada["respuesta"] = _respuesta_con_lineas([_linea("Junta tórica", 2, 1)])
    completada = anadir_datos(cliente, datos).json
    assert [li["precio_unitario"] for li in completada["lineas"]] == ["12.50", "3.00", "1.00"]
    assert any("comprueba que no es una de las que ya había" in a for a in completada["avisos"])


def test_reanalizar_lee_la_oferta_y_la_respuesta_juntas(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = INCOMPLETA
    oferta = leida(cliente, datos)
    ia_simulada["respuesta"] = RESPUESTA_DEL_PROVEEDOR
    anadir_datos(cliente, datos)
    ia_simulada["respuesta"] = INCOMPLETA
    cliente.post(url(datos, f"/{oferta['id']}/analisis"))
    textos = [p["text"] for p in ia_simulada["lecturas"][-1] if p.get("type") == "input_text"]
    assert any("Correo del proveedor" in t for t in textos)
    assert any("Respuesta del proveedor" in t for t in textos)


def test_la_respuesta_aclara_la_moneda(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = {**INCOMPLETA, "moneda": None}
    oferta = leida(cliente, datos)
    assert "La moneda de los precios" in oferta["datos_que_faltan"]
    ia_simulada["respuesta"] = RESPUESTA_DEL_PROVEEDOR
    completada = anadir_datos(cliente, datos).json
    assert completada["moneda"] == "EUR"
    assert "La moneda de los precios" not in completada["datos_que_faltan"]
    assert not any("no ha visto la moneda" in a for a in completada["avisos"])


def test_sin_analizar_la_respuesta_se_lee_al_analizar(cliente, datos, ia_simulada):
    oferta = subir(cliente, datos).json
    respuesta = anadir_datos(cliente, datos)
    assert respuesta.status_code == 200
    assert respuesta.json["id"] == oferta["id"]
    assert respuesta.json["sin_analizar"] is True
    assert any("al pulsar «Analizar y comparar»" in a for a in respuesta.json["avisos"])
    assert ia_simulada["lecturas"] == []


def test_si_la_ia_falla_los_archivos_se_quedan(cliente, datos, ia_simulada):
    ia_simulada["respuesta"] = INCOMPLETA
    leida(cliente, datos)
    ia_simulada["respuesta"] = None
    completada = anadir_datos(cliente, datos).json
    assert [a["tipo"] for a in completada["archivos"]] == ["correo_oferta", "respuesta_oferta"]
    assert completada["condiciones_pago"] is None
    assert any("la IA no los ha leído" in a for a in completada["avisos"])


def test_sin_oferta_no_hay_a_que_anadir_datos(cliente, datos):
    respuesta = anadir_datos(cliente, datos)
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "proveedor_id"}
    assert "no tiene ninguna oferta a la que añadir datos" in respuesta.json["mensaje"]
