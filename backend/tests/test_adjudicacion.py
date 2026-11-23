"""CU-005 — Pruebas de la adjudicación y de la información para SAP (la IA se simula)."""

import io
from datetime import UTC, date, datetime
from decimal import Decimal
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default

import pytest

from app.modelos.listas import Peticionario, Proveedor
from app.modelos.necesidades import Necesidad
from app.servicios import adjudicacion as servicio_adjudicacion
from app.servicios.adjudicacion import (
    formato_cantidad,
    formato_fecha,
    formato_precio,
    sin_codigo,
    texto_corto,
)

pytestmark = pytest.mark.usefixtures("limpiar")

# --- Formatos de SAP (criterios de aceptación de CU-005) -----------------------------------


@pytest.mark.parametrize(
    ("valor", "esperado"),
    [("1250.5", "1250,50"), ("1000", "1000,00"), ("12.3456", "12,3456"), ("0.10", "0,10")],
)
def test_formato_precio(valor, esperado):
    assert formato_precio(Decimal(valor)) == esperado


@pytest.mark.parametrize(("valor", "esperado"), [("2.5", "2,5"), ("2", "2"), ("2.000", "2")])
def test_formato_cantidad(valor, esperado):
    assert formato_cantidad(Decimal(valor)) == esperado


def test_formato_fecha():
    assert formato_fecha(date(2026, 11, 15)) == "15.11.2026"


@pytest.mark.parametrize(
    ("descripcion", "titulo", "esperado"),
    [
        # Una línea que solo trae la referencia.
        ("R12345", "Útil R12345", "Útil R12345"),
        ("R12345", "Rodamientos", "R12345 – Rodamientos"),
        # Como palabra entera: «R1234» no está en «Útil R12345».
        ("R1234", "Útil R12345", "R1234 – Útil R12345"),
        ("Rodamiento 6204-2RS inox", "Rodamientos", "Rodamiento 6204-2RS inox"),
        ("Montaje", "Rodamientos", "Montaje"),
    ],
)
def test_texto_corto_de_una_linea_que_solo_trae_la_referencia(descripcion, titulo, esperado):
    assert texto_corto(descripcion, titulo) == esperado


def test_quitar_el_codigo_no_toca_los_puntos_suspensivos():
    """Al quitar el código, «...» no se queda en «.» en ninguna parte del texto."""
    codigo = "2026102602"
    assert sin_codigo(f"Ver punto {codigo}... y más...", codigo) == "Ver punto... y más..."
    assert sin_codigo(f"Rodamientos. Ref. {codigo}.", codigo) == "Rodamientos. Ref."


# --- API ------------------------------------------------------------------------------------


def eml(remitente):
    mensaje = EmailMessage()
    mensaje["From"] = remitente
    mensaje["Subject"] = "Oferta"
    mensaje["Date"] = "Thu, 22 Oct 2026 09:15:00 +0200"
    mensaje.set_content("Oferta adjunta.")
    return mensaje.as_bytes()


@pytest.fixture
def datos(app, cliente):
    """Necesidad «En evaluación» con una oferta revisada de FICMEC y otra sin líneas de Acme."""
    with app.extensions["remate.sesiones"]() as s:
        ana = Peticionario(nombre_completo="Ana Prueba", email="ana@ejemplo.test")
        ficmec = Proveedor(nombre="FICMEC", email="ofertas@ficmec.test")
        acme = Proveedor(nombre="Acme", email="ventas@acme.test")
        # A Zeta también se le pide oferta, aunque no responde: con 3 proveedores no hace falta
        # motivo ni sale en el texto para SAP.
        zeta = Proveedor(nombre="Zeta", email="ofertas@zeta.test")
        s.add_all([ana, ficmec, acme, zeta])
        s.commit()
        ids = {"ana": ana.id, "ficmec": ficmec.id, "acme": acme.id, "zeta": zeta.id}
    necesidad = cliente.post(
        "/api/necesidades",
        data={
            "titulo": "Rodamientos",
            "proyecto": "Línea 3",
            "peticionario_id": str(ids["ana"]),
            "descripcion": "4 rodamientos 6204-2RS.",
        },
        content_type="multipart/form-data",
    ).json
    ids["necesidad"] = necesidad["id"]
    # Las fechas fijas de las pruebas (entrega prevista el 20/11/2026, etc.) no pueden depender
    # del día en que se ejecuta la suite: la creación queda antes de todas ellas.
    with app.extensions["remate.sesiones"]() as s:
        s.get(Necesidad, necesidad["id"]).creada_en = datetime(2026, 10, 22, tzinfo=UTC)
        s.commit()
    base = f"/api/necesidades/{necesidad['id']}"
    cliente.post(
        f"{base}/solicitud",
        json={
            "peticionario_id": ids["ana"],
            "proveedor_ids": [ids["ficmec"], ids["acme"], ids["zeta"]],
            "cuerpo": "Hola",
        },
    )
    for remitente, clave in (
        ("Ficmec S.L. <ofertas@ficmec.test>", "oferta"),
        ("ventas@acme.test", "sin_lineas"),
    ):
        oferta = cliente.post(
            f"{base}/ofertas",
            data={"correo": (io.BytesIO(eml(remitente)), "o.eml")},
            content_type="multipart/form-data",
        ).json
        ids[clave] = oferta["id"]
    cliente.patch(
        f"{base}/ofertas/{ids['oferta']}",
        json={
            "numero_oferta": "OF-77",
            "importe_sin_iva": "51.25",
            "fecha_entrega_estimada": "2026-11-15",
            "lineas": [
                {
                    "descripcion": "Rodamiento 6204-2RS inox",
                    "cantidad": "2.5",
                    "precio_unitario": "20.5",
                },
                {
                    "descripcion": "Montaje",
                    "cantidad": "1",
                    "precio_unitario": "0",
                    "fecha_entrega": "2026-11-20",
                },
            ],
            "revisada": True,
        },
    )
    cliente.patch(
        f"{base}/ofertas/{ids['sin_lineas']}",
        json={
            "importe_sin_iva": "40",
            "fecha_entrega_estimada": "2026-11-30",
            "revisada": True,
        },
    )
    assert (
        cliente.post(f"{base}/evaluacion", json={"peticionario_id": ids["ana"]}).status_code == 200
    )
    return ids


def url(datos, final):
    return f"/api/necesidades/{datos['necesidad']}{final}"


def adjudicacion(datos, **cambios):
    cuerpo = {
        "peticionario_id": datos["ana"],
        "oferta_id": datos["oferta"],
        "descripcion_inversion": "Cambio de rodamientos de la línea 3.",
        "cuerpo_correo": "Buenos días:\n\nSu oferta ha sido seleccionada.",
    }
    cuerpo.update(cambios)
    return cuerpo


def test_borrador_con_formatos_de_sap(cliente, datos):
    respuesta = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]}
    )
    assert respuesta.status_code == 200, respuesta.json
    borrador = respuesta.json
    assert borrador["texto_sap_fijo"].splitlines() == ["SOLICITADO POR: Ana Prueba", "IR: NO"]
    # Propuesta sin IA (ADR 0011): la necesidad, el proveedor y lo que se puede deducir de los
    # datos (FICMEC no es la más barata, pero sí la que entrega antes).
    assert borrador["descripcion_inversion"].splitlines() == [
        "Rodamientos",
        "Proyecto: Línea 3.",
        "4 rodamientos 6204-2RS.",
        "Proveedor seleccionado: FICMEC.",
        "Criterios objetivos: entrega más próxima.",
    ]
    assert borrador["tabla_sap"] == [
        {
            "short_text": "Rodamiento 6204-2RS inox",
            "quantity_requested": "2,5",
            "valuation_price": "20,50",
            "delivery_date": "15.11.2026",
            # El nombre de la lista de la aplicación, no el de la oferta («Ficmec S.L.»).
            "requisitioner": "FICMEC",
        },
        {
            "short_text": "Montaje",
            "quantity_requested": "1",
            "valuation_price": "0,00",
            "delivery_date": "20.11.2026",
            "requisitioner": "FICMEC",
        },
    ]
    correo = borrador["correo"]
    assert correo["para"] == "ofertas@ficmec.test"
    # El mismo asunto que los demás correos de la necesidad.
    assert correo["asunto"].endswith("| Línea 3 | Rodamientos")
    assert "su oferta OF-77 para la necesidad" in correo["cuerpo"]
    # Lo adjudicado son las líneas de la oferta, sin precios.
    assert "- 2,5 × Rodamiento 6204-2RS inox\n- 1 × Montaje" in correo["cuerpo"]
    assert "Fecha de entrega según su oferta: 15/11/2026." in correo["cuerpo"]
    assert correo["cuerpo"].rstrip().endswith("Ana Prueba\nIndustrias Ficticias")
    assert borrador["bloqueos"] == []
    # Elegir una más cara se avisa siempre; después, que la propuesta no es de la IA.
    assert borrador["avisos"] == [
        "No es la oferta más barata: Acme ofrece 40,00 EUR sin IVA (11,25 EUR menos). "
        "Explica en la descripción por qué se elige.",
        servicio_adjudicacion.AVISO_SIN_IA,
    ]


def test_sin_un_motivo_que_se_deduzca_de_los_datos_pide_escribirlo(cliente, datos):
    """Si la elegida no es la más barata ni la que entrega antes, el motivo solo lo sabe el
    ingeniero: se le pide que lo escriba (ADR 0011)."""
    cliente.patch(
        url(datos, f"/ofertas/{datos['sin_lineas']}"),
        json={"fecha_entrega_estimada": "2026-11-10", "revisada": True},
    )
    borrador = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]}
    ).json
    assert "Criterios objetivos" not in borrador["descripcion_inversion"]
    avisos = borrador["avisos"]
    assert len(avisos) == 4
    assert avisos[0].startswith("No es la oferta más barata: Acme")
    assert avisos[1] == (
        "No es la que antes entrega: Acme entrega el 10/11/2026 (la elegida, el 15/11/2026)."
    )
    assert avisos[2] == servicio_adjudicacion.AVISO_SIN_IA
    assert "motivo de elegir esta oferta" in avisos[3]


def test_con_una_sola_oferta_dice_que_es_proveedor_unico(app, cliente, datos):
    cliente.delete(url(datos, f"/ofertas/{datos['sin_lineas']}"))
    borrador = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]}
    ).json
    assert "Proveedor único consultado: FICMEC." in borrador["descripcion_inversion"]
    assert borrador["avisos"] == [servicio_adjudicacion.AVISO_SIN_IA]


def test_con_ia_tambien_avisa_si_no_es_la_mas_barata(cliente, datos, monkeypatch):
    """CU-005 — La IA recibe la comparación calculada y, aunque redacte ella, el aviso de elegir
    una oferta más cara lo pone el código."""
    recibido = []

    def redactar(_config, contexto):
        recibido.append(contexto)
        return {
            "descripcion": "Rodamientos para la línea 3.",
            "resumen": "4 rodamientos",
            "avisos": [],
        }

    monkeypatch.setattr(servicio_adjudicacion.ia, "redactar_adjudicacion", redactar)
    borrador = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]}
    ).json
    assert "Precio: no es la oferta más barata; Acme ofrece 40,00 EUR" in recibido[0]
    assert "Entrega: es la que antes entrega." in recibido[0]
    assert borrador["descripcion_inversion"] == "Rodamientos para la línea 3."
    assert "4 rodamientos" in borrador["correo"]["cuerpo"]
    assert len(borrador["avisos"]) == 1
    assert borrador["avisos"][0].startswith("No es la oferta más barata: Acme")


def test_no_se_elige_hasta_revisar_todas_las_ofertas(cliente, datos):
    """Para elegir, todas las ofertas tienen que estar revisadas: se compara con datos
    comprobados, no con lo que leyó la IA."""
    sin_revisar = cliente.patch(
        url(datos, f"/ofertas/{datos['sin_lineas']}"), json={"revisada": False}
    )
    assert sin_revisar.status_code == 200
    for ruta, cuerpo in (
        ("/adjudicacion/borrador", {"oferta_id": datos["oferta"]}),
        ("/adjudicacion", adjudicacion(datos)),
    ):
        respuesta = cliente.post(url(datos, ruta), json=cuerpo)
        assert respuesta.status_code == 400
        assert respuesta.json["mensaje"] == (
            "Revisa todas las ofertas antes de elegir una. Falta: Acme."
        )
        assert respuesta.json["detalles"] == {"campo": "oferta_id"}


def test_borrador_de_oferta_sin_lineas_avisa(cliente, datos):
    borrador = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["sin_lineas"]}
    ).json
    assert borrador["tabla_sap"] == []
    assert len(borrador["bloqueos"]) == 1
    assert "no tiene partidas" in borrador["bloqueos"][0]
    respuesta = cliente.post(
        url(datos, "/adjudicacion"), json=adjudicacion(datos, oferta_id=datos["sin_lineas"])
    )
    assert respuesta.status_code == 400


def test_adjudicar(cliente, datos):
    respuesta = cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos))
    assert respuesta.status_code == 200, respuesta.json
    necesidad = respuesta.json
    assert necesidad["estado"] == "pendiente_solicitud_sap"
    assert necesidad["oferta_adjudicada_id"] == datos["oferta"]
    assert necesidad["fecha_entrega_inicial"] == "2026-11-15"
    assert necesidad["historial"][-1]["estado_nuevo"] == "pendiente_solicitud_sap"

    sap = cliente.get(url(datos, "/sap")).json
    assert sap["proveedor"] == "FICMEC"
    assert sap["texto_sap"] == (
        "SOLICITADO POR: Ana Prueba\nIR: NO\nCambio de rodamientos de la línea 3."
    )
    assert len(sap["tabla_sap"]) == 2

    correo = message_from_bytes(cliente.get(url(datos, "/adjudicacion.eml")).data, policy=default)
    assert correo["To"] == "ofertas@ficmec.test"
    assert correo["Bcc"] is None
    assert correo["X-Unsent"] == "1"
    assert not correo["Subject"].endswith("- Adjudicación")

    # Ya no se puede adjudicar otra vez ni tocar las ofertas.
    assert cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos)).status_code == 409


@pytest.mark.parametrize(
    ("cambio", "campo"),
    [
        ({"descripcion_inversion": " "}, "descripcion_inversion"),
        ({"cuerpo_correo": ""}, "cuerpo_correo"),
        ({"peticionario_id": 999999}, "peticionario_id"),
        ({"oferta_id": 999999}, "oferta_id"),
    ],
)
def test_datos_no_validos(cliente, datos, cambio, campo):
    respuesta = cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos, **cambio))
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": campo}


def test_sin_adjudicar_no_hay_informacion_sap(cliente, datos):
    assert cliente.get(url(datos, "/sap")).status_code == 404
    assert cliente.get(url(datos, "/adjudicacion.eml")).status_code == 404


def test_salto_de_linea_en_el_titulo_no_rompe_el_eml(cliente, datos):
    """Un salto de línea en el título no da un error 500 al generar el .eml."""
    from app.modelos.necesidades import Necesidad

    with cliente.application.extensions["remate.sesiones"]() as s:
        s.get(Necesidad, datos["necesidad"]).titulo = "Rodamientos\nurgentes"
        s.commit()
    respuesta = cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos))
    assert respuesta.status_code == 200
    correo = message_from_bytes(cliente.get(url(datos, "/adjudicacion.eml")).data, policy=default)
    assert "Rodamientos urgentes" in correo["Subject"]


def test_oferta_revisada_que_pierde_la_fecha_deja_de_estar_revisada(cliente, datos):
    """Sin error 500 en la comparativa ni en el borrador."""
    ruta_oferta = url(datos, f"/ofertas/{datos['oferta']}")
    # La necesidad está «En evaluación»: se puede seguir corrigiendo la oferta.
    respuesta = cliente.patch(
        ruta_oferta, json={"fecha_entrega_estimada": None, "plazo_entrega_texto": "a convenir"}
    )
    assert respuesta.status_code == 200
    assert respuesta.json["revisada"] is False
    comparativa = cliente.get(url(datos, "/comparativa"))
    assert comparativa.status_code == 200
    # Sigue en la comparativa (salen también las sin revisar), pero marcada
    # y sin poder adjudicarse.
    revisadas = {o["id"]: o["revisada"] for o in comparativa.json}
    assert revisadas == {datos["sin_lineas"]: True, datos["oferta"]: False}
    borrador = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]}
    )
    assert borrador.status_code == 400


def test_la_descripcion_para_sap_no_lleva_el_codigo_de_la_necesidad(app, cliente, datos):
    """El código de la necesidad no le sirve a quien lee la
    descripción en SAP. Si la descripción del ingeniero lo lleva, se quita."""
    codigo = cliente.get(f"/api/necesidades/{datos['necesidad']}").json["codigo"]
    with app.extensions["remate.sesiones"]() as s:
        s.get(
            Necesidad, datos["necesidad"]
        ).descripcion = (
            f"Necesidad {codigo}: cambio de rodamientos ({codigo}) de la línea 3. Ref. {codigo}."
        )
        s.commit()
    borrador = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]}
    ).json
    assert codigo not in borrador["descripcion_inversion"]
    assert "Cambio de rodamientos de la línea 3. Ref." in borrador["descripcion_inversion"]


def test_plazo_relativo_se_cuenta_desde_el_pedido(cliente, datos, monkeypatch):
    """La oferta dice «3 semanas», sin fecha. La fecha
    calculada desde su correo sirve para comparar, pero al proveedor no se le dice una fecha que
    no ha dado, y para SAP se cuenta desde el día del pedido."""
    respuesta = cliente.patch(
        url(datos, f"/ofertas/{datos['oferta']}"),
        json={"plazo_entrega_texto": "3 semanas", "fecha_entrega_estimada": None, "revisada": True},
    )
    assert respuesta.status_code == 200, respuesta.json
    # Desde el correo (22/10): solo para comparar.
    assert respuesta.json["fecha_entrega_estimada"] == "2026-11-12"
    assert respuesta.json["fecha_calculada"] is True

    monkeypatch.setattr(servicio_adjudicacion, "_hoy", lambda: date(2026, 10, 27))
    borrador = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]}
    ).json
    # Desde hoy (27/10); la línea con su propia fecha la conserva.
    assert [f["delivery_date"] for f in borrador["tabla_sap"]] == ["17.11.2026", "20.11.2026"]
    cuerpo = borrador["correo"]["cuerpo"]
    assert "Plazo de entrega según su oferta: 3 semanas." in cuerpo
    assert "Fecha de entrega" not in cuerpo

    necesidad = cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos)).json
    assert necesidad["fecha_entrega_inicial"] == "2026-11-17"
    assert necesidad["plazo_entrega_relativo"] == "3 semanas"
    # Al meter el pedido en SAP días después, la fecha propuesta se cuenta desde ese día.
    monkeypatch.setattr(servicio_adjudicacion, "_hoy", lambda: date(2026, 11, 2))
    necesidad = cliente.get(f"/api/necesidades/{datos['necesidad']}").json
    assert necesidad["fecha_entrega_propuesta"] == "2026-11-23"
    # La tabla para SAP lleva la misma fecha.
    sap = cliente.get(url(datos, "/sap")).json
    assert [f["delivery_date"] for f in sap["tabla_sap"]] == ["23.11.2026", "20.11.2026"]


def test_con_fecha_dada_por_el_proveedor_se_usa_esa(cliente, datos, monkeypatch):
    monkeypatch.setattr(servicio_adjudicacion, "_hoy", lambda: date(2026, 11, 2))
    necesidad = cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos)).json
    assert necesidad["plazo_entrega_relativo"] is None
    assert necesidad["fecha_entrega_propuesta"] == "2026-11-15"


# --- Motivo de pedir ofertas a menos de 3 proveedores -----------------------------------------


def _con_motivo(app, datos, motivo, quedan):
    """Deja la necesidad como si se hubiera pedido oferta a `quedan` proveedores con `motivo`."""
    with app.extensions["remate.sesiones"]() as s:
        necesidad = s.get(Necesidad, datos["necesidad"])
        necesidad.motivo_pocos_proveedores = motivo
        for solicitado in list(necesidad.solicitados)[quedan:]:
            s.delete(solicitado)
        s.commit()


@pytest.mark.parametrize(
    ("quedan", "linea"),
    [
        (1, "Proveedor único por ser el fabricante del equipo."),
        (2, "Solo 2 proveedores consultados por ser el fabricante del equipo."),
    ],
)
def test_el_motivo_va_al_texto_para_sap(app, cliente, datos, quedan, linea):
    _con_motivo(app, datos, "ser el fabricante del equipo", quedan)
    borrador = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]}
    ).json
    assert borrador["texto_sap_fijo"].splitlines() == [
        "SOLICITADO POR: Ana Prueba",
        "IR: NO",
        linea,
    ]
    respuesta = cliente.post(url(datos, "/adjudicacion"), json=adjudicacion(datos))
    assert respuesta.status_code == 200, respuesta.json
    sap = cliente.get(url(datos, "/sap")).json["texto_sap"]
    assert sap.splitlines()[:3] == ["SOLICITADO POR: Ana Prueba", "IR: NO", linea]


def test_con_motivo_y_una_oferta_no_se_repite_lo_de_proveedor_unico(app, cliente, datos):
    _con_motivo(app, datos, "urgencia", 1)
    cliente.delete(url(datos, f"/ofertas/{datos['sin_lineas']}"))
    borrador = cliente.post(
        url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]}
    ).json
    assert "Proveedor único por urgencia." in borrador["texto_sap_fijo"]
    assert "Proveedor único" not in borrador["descripcion_inversion"]


def test_la_ia_sabe_que_la_linea_del_motivo_ya_esta(app, cliente, datos, monkeypatch):
    _con_motivo(app, datos, "urgencia", 2)
    recibido = []

    def redactar(_config, contexto):
        recibido.append(contexto)
        return {"descripcion": "Rodamientos.", "resumen": "4 rodamientos", "avisos": []}

    monkeypatch.setattr(servicio_adjudicacion.ia, "redactar_adjudicacion", redactar)
    cliente.post(url(datos, "/adjudicacion/borrador"), json={"oferta_id": datos["oferta"]})
    assert (
        "ya pone en la descripción para SAP: «Solo 2 proveedores consultados por urgencia.»"
        in (recibido[0])
    )
