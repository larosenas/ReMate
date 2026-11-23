"""CU-007 — Adjuntar el pedido oficial de SAP y generar el .eml al proveedor."""

import io
import zlib
from email import message_from_bytes
from email.policy import default

import pytest

from app.integraciones import pedido_pdf
from app.modelos.necesidades import Adjunto
from app.modelos.ofertas import Oferta
from app.servicios.pedido_sap import numero_en_nombre
from tests.test_adjudicacion import adjudicacion, datos, url  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar")

PEDIDO = (b"%PDF pedido 4500012345", "Pedido 4500012345.pdf")


@pytest.fixture
def pendiente_pedido(cliente, datos):  # noqa: F811
    """Adjudicada a FICMEC (oferta OF-77) y confirmada en SAP con entrega el 20/11/2026."""
    assert cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos)).status_code == 200
    confirmada = cliente.post(
        url(datos, "/pedido-en-sap"),
        json={"peticionario_id": datos["ana"], "fecha_entrega_prevista": "2026-11-20"},
    )
    assert confirmada.status_code == 200
    return datos


def enviar(cliente, datos, **cambios):  # noqa: F811
    formulario = {
        "peticionario_id": str(datos["ana"]),
        "pedido": (io.BytesIO(PEDIDO[0]), PEDIDO[1]),
        "numero_oferta": "OF-77",
        "numero_pedido": "4500012345",
        "cuerpo_correo": "Buenos días:\n\nLes adjuntamos el pedido.\n",
        **cambios,
    }
    formulario = {k: v for k, v in formulario.items() if v is not None}
    return cliente.post(
        url(datos, "/pedido-sap"), data=formulario, content_type="multipart/form-data"
    )


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("Oferta HN-1182.pdf", "HN-1182"),
        ("oferta-acme-OF-2026-0417.pdf", "OF-2026-0417"),
        ("oferta 123.pdf", "123"),
        ("Oferta_TZ-81.xlsx", "TZ-81"),
        ("presupuesto 2026102301.pdf", None),  # el código de la necesidad no cuenta
        ("oferta.pdf", None),
        ("plano rev 2.pdf", None),
    ],
)
def test_numero_de_oferta_en_el_nombre_del_archivo(nombre, esperado):
    assert numero_en_nombre(nombre, excluir="2026102301") == esperado


def test_propone_el_numero_de_la_oferta_revisada(cliente, pendiente_pedido):
    propuesta = cliente.get(url(pendiente_pedido, "/pedido-sap/propuesta")).json
    assert propuesta["proveedor"] == "FICMEC"
    assert propuesta["para"] == "ofertas@ficmec.test"
    assert propuesta["numero_oferta"] == "OF-77"
    assert propuesta["origen_numero_oferta"] == "oferta"
    assert propuesta["fecha_entrega_prevista"] == "2026-11-20"


def test_sin_numero_revisado_lo_busca_en_el_adjunto(cliente, pendiente_pedido, app):
    with app.extensions["remate.sesiones"]() as s:
        oferta = s.get(Oferta, pendiente_pedido["oferta"])
        oferta.numero_oferta = None
        oferta.archivos.append(
            Adjunto(
                necesidad_id=oferta.necesidad_id,
                tipo="adjunto_oferta",
                formato="pdf",
                nombre_archivo="Oferta IND-5521 rev1.pdf",
                ruta="no/existe.pdf",
                tipo_mime="application/pdf",
                tamano=1,
            )
        )
        s.commit()
    propuesta = cliente.get(url(pendiente_pedido, "/pedido-sap/propuesta")).json
    assert propuesta["numero_oferta"] == "IND-5521"
    assert propuesta["origen_numero_oferta"] == "archivo"


def test_borrador_del_correo(cliente, pendiente_pedido):
    respuesta = cliente.post(
        url(pendiente_pedido, "/pedido-sap/borrador"),
        json={"numero_oferta": " OF-77 ", "numero_pedido": "4500012345"},
    )
    assert respuesta.status_code == 200, respuesta.json
    correo = respuesta.json
    assert correo["para"] == "ofertas@ficmec.test"
    # El mismo asunto que los demás correos de la necesidad, sin el número.
    assert correo["asunto"].endswith("| Línea 3 | Rodamientos")
    assert "Pedido SAP" not in correo["asunto"]
    assert (
        "Les adjuntamos el pedido 4500012345 correspondiente a su oferta OF-77"
        in (correo["cuerpo"])
    )
    assert "Fecha de entrega prevista: 20/11/2026." in correo["cuerpo"]
    assert correo["cuerpo"].endswith("Ana Prueba\nIndustrias Ficticias\n")
    sin_pedido = cliente.post(
        url(pendiente_pedido, "/pedido-sap/borrador"), json={"numero_oferta": "OF-77"}
    ).json
    assert sin_pedido["asunto"] == correo["asunto"]
    assert "Les adjuntamos el pedido oficial de SAP correspondiente" in sin_pedido["cuerpo"]
    sin_oferta = cliente.post(url(pendiente_pedido, "/pedido-sap/borrador"), json={})
    assert sin_oferta.status_code == 400
    assert sin_oferta.json["detalles"] == {"campo": "numero_oferta"}


def test_enviar_el_pedido(cliente, pendiente_pedido, app):
    respuesta = enviar(cliente, pendiente_pedido, numero_oferta="OF-77-B")
    assert respuesta.status_code == 200, respuesta.json
    necesidad = respuesta.json
    assert necesidad["estado"] == "pendiente_entrega"
    assert necesidad["historial"][-1]["estado_anterior"] == "pendiente_pedido_sap"
    assert necesidad["numero_pedido_sap"] == "4500012345"
    assert necesidad["pedido_sap"]["nombre_archivo"] == "Pedido 4500012345.pdf"
    # El pedido no aparece entre los adjuntos de la necesidad.
    assert necesidad["adjuntos"] == []

    descarga = cliente.get(url(pendiente_pedido, "/pedido-sap.eml"))
    assert descarga.status_code == 200
    correo = message_from_bytes(descarga.data, policy=default)
    assert correo["To"] == "ofertas@ficmec.test"
    assert correo["Subject"].endswith("| Línea 3 | Rodamientos")
    assert correo["X-Unsent"] == "1"
    adjunto = next(correo.iter_attachments())
    assert adjunto.get_filename() == "Pedido 4500012345.pdf"
    assert adjunto.get_content() == b"%PDF pedido 4500012345"
    # El número confirmado queda en la oferta adjudicada.
    with app.extensions["remate.sesiones"]() as s:
        assert s.get(Oferta, pendiente_pedido["oferta"]).numero_oferta == "OF-77-B"
    pedido = cliente.get(url(pendiente_pedido, f"/adjuntos/{necesidad['pedido_sap']['id']}"))
    assert pedido.data == b"%PDF pedido 4500012345"


@pytest.mark.parametrize(
    ("cambios", "campo"),
    [
        ({"pedido": None}, "pedido"),
        ({"numero_oferta": "  "}, "numero_oferta"),
        ({"cuerpo_correo": " "}, "cuerpo_correo"),
        ({"peticionario_id": "999999"}, "peticionario_id"),
    ],
)
def test_lo_que_falta_no_deja_enviar(cliente, pendiente_pedido, cambios, campo):
    respuesta = enviar(cliente, pendiente_pedido, **cambios)
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": campo}
    detalle = cliente.get(f"/api/necesidades/{pendiente_pedido['necesidad']}").json
    assert detalle["estado"] == "pendiente_pedido_sap"
    assert detalle["pedido_sap"] is None


def test_solo_desde_pendiente_pedido_sap(cliente, datos):  # noqa: F811
    assert enviar(cliente, datos).status_code == 409
    assert cliente.get(url(datos, "/pedido-sap/propuesta")).status_code == 409
    assert cliente.get(url(datos, "/pedido-sap.eml")).status_code == 404
    assert cliente.get("/api/necesidades/999999/pedido-sap/propuesta").status_code == 404


def test_no_se_envia_dos_veces(cliente, pendiente_pedido):
    assert enviar(cliente, pendiente_pedido).status_code == 200
    assert enviar(cliente, pendiente_pedido).status_code == 409


# --- Número de pedido leído del PDF de SAP -----------------------------------------------------
# PDF inventados con la estructura de los pedidos reales de SAP NetWeaver 750 (que no están en el
# repositorio): el texto en hexadecimal (`<…> Tj`), el número detrás de «PURCHASE ORDER NO.».


def _hexa(texto):
    return "<" + texto.encode("cp1252").hex().upper() + ">"


def pdf_de_sap(lineas, comprimido=False, como="hexa"):
    partes = []
    for i, linea in enumerate(lineas):
        cadena = _hexa(linea) if como == "hexa" else "(" + linea.replace("(", r"\(") + ")"
        partes.append(f"BT /F1 9 Tf 40 {800 - 12 * i} Td {cadena}Tj ET")
    contenido = "\r\n".join(partes).encode("latin-1")
    if comprimido:
        contenido = zlib.compress(contenido)
    filtro = b" /Filter /FlateDecode" if comprimido else b""
    return (
        b"%PDF-1.3\n1 0 obj << /Length "
        + str(len(contenido)).encode()
        + filtro
        + b" >>\nstream\r\n"
        + contenido
        + b"\r\nendstream\nendobj\n%%EOF\n"
    )


CABECERA = ["Data wydruku:  12.08.2026", "Wersja: 0", "PURCHASE ORDER NO. 4510000001", "Buyer"]


@pytest.mark.parametrize(
    ("pdf", "numero"),
    [
        (pdf_de_sap(CABECERA), "4510000001"),
        (pdf_de_sap(CABECERA, comprimido=True), "4510000001"),
        (pdf_de_sap(CABECERA, como="literal"), "4510000001"),
        (pdf_de_sap(["Purchase Order No.: 4510000002"]), "4510000002"),
        # Sin la frase, o sin número detrás, no hay número: se escribe a mano.
        (pdf_de_sap(["Pedido 4510000003"]), None),
        (pdf_de_sap(["PURCHASE ORDER NO."]), None),
        (b"%PDF-1.3 roto stream\r\n<ZZ>Tj\r\nendstream", None),
        (b"no es un pdf PURCHASE ORDER NO. 4510000004", None),
    ],
)
def test_numero_de_pedido_del_pdf(pdf, numero):
    assert pedido_pdf.numero_de_pedido(pdf) == numero


def test_la_api_propone_el_numero_del_pdf(cliente, pendiente_pedido):
    def leer(pdf):
        return cliente.post(
            url(pendiente_pedido, "/pedido-sap/numero"),
            data={"pedido": (io.BytesIO(pdf), "pedido.pdf")},
            content_type="multipart/form-data",
        )

    respuesta = leer(pdf_de_sap(CABECERA))
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json == {"numero_pedido": "4510000001"}
    assert leer(b"%PDF sin numero").json == {"numero_pedido": None}
    # No guarda nada: sigue pendiente de enviar el pedido.
    detalle = cliente.get(f"/api/necesidades/{pendiente_pedido['necesidad']}").json
    assert detalle["pedido_sap"] is None


def test_leer_el_numero_solo_en_su_paso(cliente, datos):  # noqa: F811
    respuesta = cliente.post(
        url(datos, "/pedido-sap/numero"),
        data={"pedido": (io.BytesIO(pdf_de_sap(CABECERA)), "pedido.pdf")},
        content_type="multipart/form-data",
    )
    assert respuesta.status_code == 409
