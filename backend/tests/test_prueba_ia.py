"""Juego de ofertas de prueba para la IA (`flask --app app probar-ia`). Con la IA simulada:
comprueba que se prepara el contenido como en «Analizar» y que se compara bien."""

import json
from email.message import EmailMessage

from app.integraciones import ia


def _correo() -> bytes:
    mensaje = EmailMessage()
    mensaje["From"] = "ventas@coopemetal.test"
    mensaje["Subject"] = "Oferta 24422"
    mensaje["Date"] = "Thu, 22 Oct 2026 09:15:00 +0200"
    mensaje.set_content("Adjuntamos oferta.")
    mensaje.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="o.pdf")
    return mensaje.as_bytes()


RESPUESTA = {
    "moneda": "EUR",
    "numero_oferta": "24422",
    "lineas": [
        {"descripcion": "Distancial", "cantidad": 3, "precio_unitario": 13, "fecha_entrega": None,
         "plazo_entrega": "18 - 20 días"},
        {"descripcion": "Inserto", "cantidad": 1, "precio_unitario": 243, "fecha_entrega": None,
         "plazo_entrega": "5 semanas"},
    ],
    "importe_sin_iva": None,
    "plazo_entrega": None,
    "fecha_entrega": None,
    "condiciones": {"incoterm": {"estado": "especificado", "texto": "En sus dependencias"}},
    "avisos": ["No se ofertan los juegos de postizos."],
}  # fmt: skip


def _caso(carpeta, esperado, necesidad=True):
    carpeta.mkdir()
    (carpeta / "oferta.eml").write_bytes(_correo())
    (carpeta / "esperado.json").write_text(json.dumps(esperado), encoding="utf-8")
    if necesidad:
        (carpeta / "necesidad.txt").write_text(
            "Utillaje BLM\nDistanciales, inserto y juegos de postizos.", encoding="utf-8"
        )


def test_un_caso_que_coincide_y_otro_que_no(app, tmp_path, monkeypatch):
    recibido = []

    def leer_oferta(_config, partes):
        recibido.append(partes)
        return RESPUESTA

    monkeypatch.setattr(ia, "leer_oferta", leer_oferta)
    _caso(
        tmp_path / "1-coopemetal",
        {
            "moneda": "EUR",
            # Sin total en la oferta: la suma de las líneas.
            "importe_sin_iva": "282",
            "fecha_entrega_estimada": "2026-11-26",
            "lineas": [
                {"cantidad": "3", "precio_unitario": "13", "fecha_entrega": "2026-11-11"},
                {"precio_unitario": 243, "plazo_entrega_texto": "5 semanas"},
            ],
            "condiciones": {"incoterm": "especificado"},
            "avisos_contienen": ["postizos"],
        },
    )
    _caso(
        tmp_path / "2-mal",
        {"moneda": "USD", "lineas": [{}], "condiciones": {"validez": "especificado"},
         "avisos_contienen": ["descuento"]},
        necesidad=False,
    )  # fmt: skip
    (tmp_path / "sin-esperado").mkdir()

    salida = app.test_cli_runner().invoke(args=["probar-ia", str(tmp_path)])

    assert salida.exit_code == 1
    assert "BIEN   1-coopemetal" in salida.output
    assert "FALLA  2-mal" in salida.output
    assert "moneda: «USD» ≠ «EUR»" in salida.output
    assert "líneas: se esperaban 1 y hay 2" in salida.output
    assert "condición validez: «especificado» ≠ «no_especificado»" in salida.output
    assert "ningún aviso dice «descuento»" in salida.output
    assert "1 de 2 casos bien." in salida.output
    # Como en «Analizar»: lo que pidió el cliente (si lo hay), el correo y su PDF adjunto.
    pedido, correo, pdf = recibido[0]
    assert "Título: Utillaje BLM" in pedido["text"]
    assert "Remitente: ventas@coopemetal.test" in correo["text"]
    assert pdf["filename"] == "o.pdf"
    assert recibido[1][0]["text"].startswith("Correo del proveedor")


def test_si_la_ia_falla_se_dice_en_el_caso(app, tmp_path, monkeypatch):
    def falla(_config, _partes):
        raise ia.ErrorIA("La IA no ha respondido.")

    monkeypatch.setattr(ia, "leer_oferta", falla)
    _caso(tmp_path / "caso", {"moneda": "EUR"})
    salida = app.test_cli_runner().invoke(args=["probar-ia", str(tmp_path)])
    assert salida.exit_code == 1
    assert "ErrorIA: La IA no ha respondido." in salida.output


def test_un_esperado_raro_no_tira_los_demas_casos(app, tmp_path, monkeypatch):
    """Con un esperado.json que no es un objeto, o `"lineas": null`, no se cae todo ni se
    pierden los casos ya leídos (y pagados)."""
    llamadas = []
    monkeypatch.setattr(ia, "leer_oferta", lambda _c, partes: llamadas.append(1) or RESPUESTA)
    _caso(tmp_path / "1-bien", {"moneda": "EUR"})
    for nombre, esperado in [
        ("2-lista", []),
        ("3-lineas-null", {"lineas": None}),
        ("4-linea-numero", {"lineas": [1]}),
        ("5-condiciones-texto", {"condiciones": "incoterm"}),
        ("6-avisos-texto", {"avisos_contienen": "postizos"}),
    ]:
        _caso(tmp_path / nombre, esperado)
    salida = app.test_cli_runner().invoke(args=["probar-ia", str(tmp_path)])
    assert salida.exception is None or isinstance(salida.exception, SystemExit)
    assert "BIEN   1-bien" in salida.output
    assert "esperado.json tiene que ser un objeto" in salida.output
    assert "«lineas» tiene que ser una lista" in salida.output
    assert "cada línea tiene que ser un objeto" in salida.output
    assert "«condiciones» tiene que ser un objeto" in salida.output
    assert "«avisos_contienen» tiene que ser una lista" in salida.output
    assert "1 de 6 casos bien." in salida.output
    # Los casos con el esperado mal no se pagan.
    assert len(llamadas) == 1


def test_nombres_en_mayusculas_y_casos_vacios(app, tmp_path, monkeypatch):
    """«Esperado.json» y «Necesidad.txt» se reconocen sin mirar mayúsculas, también en Linux, y
    no se mandan a la IA como parte de la oferta; un caso sin oferta no se paga; y un
    necesidad.txt con BOM no lleva el carácter al título."""
    recibido = []
    monkeypatch.setattr(ia, "leer_oferta", lambda _c, partes: recibido.append(partes) or RESPUESTA)
    caso = tmp_path / "1-mayusculas"
    caso.mkdir()
    (caso / "oferta.eml").write_bytes(_correo())
    (caso / "Esperado.json").write_text('{"moneda": "EUR"}', encoding="utf-8")
    (caso / "Necesidad.txt").write_text("\ufeffUtillaje BLM\nDistanciales.", encoding="utf-8")
    vacio = tmp_path / "2-sin-oferta"
    vacio.mkdir()
    (vacio / "esperado.json").write_text('{"moneda": "EUR"}', encoding="utf-8")
    # Un archivo de Windows no es una oferta, ni una copia del esperado, que además llevaría
    # las respuestas a la IA.
    (vacio / "desktop.ini").write_text("[.ShellClassInfo]", encoding="utf-8")
    (vacio / "esperado - copia.json").write_text('{"moneda": "EUR"}', encoding="utf-8")
    (caso / "esperado - copia.json").write_text('{"moneda": "EUR"}', encoding="utf-8")

    salida = app.test_cli_runner().invoke(args=["probar-ia", str(tmp_path)])

    assert "BIEN   1-mayusculas" in salida.output
    assert "el caso no tiene archivos de la oferta" in salida.output
    assert len(recibido) == 1
    textos = [p.get("text", "") for p in recibido[0]]
    assert textos[0].startswith("Lo que pidió el cliente")
    assert "Título: Utillaje BLM" in textos[0]
    assert not any("Esperado.json" in t or "Necesidad.txt" in t for t in textos)
    assert not any("copia.json" in t for t in textos)


def test_sin_casos(app, tmp_path):
    salida = app.test_cli_runner().invoke(args=["probar-ia", str(tmp_path)])
    assert salida.exit_code == 1
    assert "No hay casos" in salida.output
