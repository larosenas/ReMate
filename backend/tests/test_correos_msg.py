"""Lector propio de correos `.msg` (ADR 0013), sin dependencias.

Con la biblioteca estándar no se puede crear un `.msg` completo: las pruebas usan contenedores
fabricados a mano o sustituyen el lector por un mensaje ya leído.
"""

from datetime import UTC, datetime
from email import message_from_bytes
from email.policy import default

import pytest

from app.integraciones import correos_entrada, correos_msg
from app.integraciones.correos_entrada import CorreoNoValido
from app.integraciones.correos_msg import AdjuntoMsg, MensajeMsg, MsgNoValido


@pytest.mark.parametrize(
    "datos",
    [
        b"",
        b"esto no es un msg" * 50,
        correos_msg.FIRMA + b"\x00" * 600,
    ],
    ids=["vacio", "texto", "solo-la-firma"],
)
def test_un_msg_danado_explica_como_guardarlo_como_eml(datos):
    with pytest.raises(CorreoNoValido, match="Guardar como"):
        correos_entrada.leer("oferta.msg", datos)


def _con(monkeypatch, *adjuntos, html="", texto="Les adjuntamos la oferta."):
    mensaje = MensajeMsg(
        fecha=None,
        remitente="ventas@acme.test",
        asunto="Oferta",
        texto=texto,
        html=html,
        adjuntos=adjuntos,
    )
    monkeypatch.setattr(correos_msg, "leer", lambda datos: mensaje)


def test_sin_las_imagenes_del_cuerpo(monkeypatch):
    _con(
        monkeypatch,
        AdjuntoMsg("image001.png", "image/png", b"logo", content_id="image001.png@01dc"),
        AdjuntoMsg("firma.jpg", "image/jpeg", b"firma", oculto=True),
        AdjuntoMsg("foto pieza.jpg", "image/jpeg", b"foto"),
        AdjuntoMsg("a/../oferta.pdf", "application/pdf", b"%PDF"),
        html='<p>Oferta</p><img src="cid:image001.png@01DC">',
    )
    leido = correos_entrada.leer("oferta.msg", b"")
    assert [a.nombre for a in leido.adjuntos] == ["foto pieza.jpg", "oferta.pdf"]


def test_sin_texto_se_usa_el_html(monkeypatch):
    _con(monkeypatch, texto="", html="<p>Precio: <b>120 &euro;</b></p>")
    assert correos_entrada.leer("oferta.msg", b"").cuerpo == "Precio: 120 €"


def test_un_correo_adjunto_se_convierte_en_eml():
    reenviado = MensajeMsg(
        fecha=datetime(2026, 10, 14, 4, 47, tzinfo=UTC),
        remitente="luis@acme.test",
        asunto="Plano\r\nrevisado",
        texto="Ver plano.",
        html="<p>Ver plano.</p>",
        adjuntos=(AdjuntoMsg("plano.pdf", "application/pdf", b"%PDF plano"),),
    )
    eml = message_from_bytes(correos_msg.a_eml(reenviado), policy=default)
    assert eml["From"] == "luis@acme.test"
    assert eml["Subject"] == "Plano revisado"
    assert eml.get_body(("plain",)).get_content().strip() == "Ver plano."
    adjunto = next(eml.iter_attachments())
    assert adjunto.get_filename() == "plano.pdf"
    assert adjunto.get_content() == b"%PDF plano"


def test_la_firma_no_basta_para_ser_un_msg():
    with pytest.raises(MsgNoValido):
        correos_msg.leer(correos_msg.FIRMA + b"\xff" * 1000)


def test_difat_en_ciclo_se_rechaza_al_momento():
    """Un .msg de 1 KB con la DIFAT apuntándose a sí misma no llena la memoria (más de 100
    millones de entradas) antes de fallar."""
    import struct
    import time

    cabecera = bytearray(512)
    cabecera[:8] = correos_msg.FIRMA
    struct.pack_into("<H", cabecera, 0x1E, 9)
    struct.pack_into("<H", cabecera, 0x20, 6)
    struct.pack_into("<II", cabecera, 0x44, 0, 1_000_000)
    struct.pack_into("<109I", cabecera, 0x4C, *([0xFFFFFFFF] * 109))
    datos = bytes(cabecera) + struct.pack("<128I", *([0] * 128))
    inicio = time.monotonic()
    with pytest.raises(correos_msg.MsgNoValido):
        correos_msg.leer(datos)
    assert time.monotonic() - inicio < 2


def test_eml_con_partes_anidadas_sin_fin_se_rechaza():
    """Con miles de partes unas dentro de otras se rechaza con un mensaje claro, sin
    RecursionError (error 500)."""
    from app.integraciones import correos_entrada

    def anidado(niveles):
        partes = ["From: a@b.example\r\nSubject: x\r\nMIME-Version: 1.0\r\n"]
        for i in range(niveles):
            partes.append(f'Content-Type: multipart/mixed; boundary="b{i}"\r\n\r\n--b{i}\r\n')
        partes.append("Content-Type: text/plain\r\n\r\nhola\r\n")
        partes.extend(f"--b{i}--\r\n" for i in reversed(range(niveles)))
        return "".join(partes).encode()

    assert correos_entrada.leer("oferta.eml", anidado(5)).cuerpo == "hola"
    for niveles in (correos_entrada.MAXIMO_ANIDADO + 5, 2000):
        # Con 2000 niveles ya lo frena antes el número de partes.
        with pytest.raises(correos_entrada.CorreoNoValido, match=r"demasiadas partes|fuera de lo"):
            correos_entrada.leer("oferta.eml", anidado(niveles))


def _contenedor_de_prueba(fat, minifat=(), mini_datos=b"", sectores=4):
    """Un contenedor sin pasar por la cabecera, para probar las cadenas."""
    c = object.__new__(correos_msg._Contenedor)
    c.datos = bytes(512 * (sectores + 1))
    c.sector, c.mini_sector = 512, 64
    c.fat, c.minifat, c.mini_datos = list(fat), list(minifat), mini_datos
    c.leido, c.maximo_lectura = 0, 10_000
    return c


def test_cadenas_en_ciclo_se_rechazan():
    with pytest.raises(correos_msg.MsgNoValido):
        _contenedor_de_prueba([1, 0, 0, 0])._cadena(0)
    # La minicadena era cuadrática: un minisector que se apunta a sí mismo con un tamaño enorme.
    c = _contenedor_de_prueba([], minifat=[0] * 1000, mini_datos=bytes(64 * 1000))
    with pytest.raises(correos_msg.MsgNoValido):
        c._mini_cadena(0, 0xFFFFFFF0)


def test_leer_el_mismo_flujo_muchas_veces_tiene_un_tope():
    """Muchos adjuntos (o correos adjuntos) que apuntan al mismo contenido lo releían y copiaban
    sin fin."""
    c = _contenedor_de_prueba([correos_msg._FIN_CADENA] * 4)
    c.corte_mini = 0
    c.entradas = [correos_msg._Entrada("x", correos_msg._ARCHIVO, 0, 0, 0, 0, 512)]
    for _ in range(19):
        c.leer(0)
    with pytest.raises(correos_msg.MsgNoValido):
        c.leer(0)


def test_eml_con_correos_reenviados_unos_dentro_de_otros():
    """300 correos reenviados uno dentro de otro no dan RecursionError al copiarlos (error
    500)."""
    from app.integraciones import correos_entrada

    reenviado = "Hola\n"
    for i in range(300):
        reenviado = (
            f"From: p{i}@prov.example\nSubject: s{i}\nContent-Type: message/rfc822\n\n" + reenviado
        )
    correo = (
        "From: ventas@acme.example\nSubject: oferta\nDate: Thu, 22 Oct 2026 09:15:00 +0200\n"
        "Content-Type: multipart/mixed; boundary=B\n\n--B\nContent-Type: text/plain\n\ncuerpo\n"
        "--B\nContent-Type: message/rfc822\nContent-Disposition: attachment\n\n"
        + reenviado
        + "\n--B--\n"
    ).encode()
    with pytest.raises(correos_entrada.CorreoNoValido):
        correos_entrada.leer("oferta.eml", correo)


def test_eml_con_cabecera_enorme_o_demasiadas_partes():
    """Una cabecera de 1 MB plegada o 100 000 partes se rechazan sin tardar decenas de
    segundos."""
    from app.integraciones import correos_entrada

    plegada = "Subject: x" + "\r\n y" * (correos_entrada.MAXIMO_CABECERA // 3)
    with pytest.raises(correos_entrada.CorreoNoValido, match="fuera de lo normal"):
        correos_entrada.leer("oferta.eml", f"From: a@b.example\r\n{plegada}\r\n\r\nx".encode())
    partes = "".join(
        "--B\r\nContent-Type: text/plain\r\n\r\nx\r\n"
        for _ in range(correos_entrada.MAXIMO_PARTES + 1)
    )
    correo = (
        "From: a@b.example\r\nSubject: x\r\nContent-Type: multipart/mixed; boundary=B\r\n\r\n"
        + partes
        + "--B--\r\n"
    ).encode()
    with pytest.raises(correos_entrada.CorreoNoValido, match="fuera de lo normal"):
        correos_entrada.leer("oferta.eml", correo)
