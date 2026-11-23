"""CU-004 — Preparación de los adjuntos de una oferta para la IA (sin llamar a la IA)."""

import base64
import io
import zipfile

import pytest

from app.integraciones import adjuntos_ia
from app.integraciones.adjuntos_ia import Contenido

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def zip_con(archivos: dict[str, str]) -> bytes:
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as paquete:
        for nombre, texto in archivos.items():
            paquete.writestr(nombre, texto)
    return salida.getvalue()


def docx() -> bytes:
    return zip_con(
        {
            "word/document.xml": f"""<w:document xmlns:w="{W}"><w:body>
              <w:p><w:r><w:t>Oferta </w:t></w:r><w:r><w:t>OF-77</w:t></w:r></w:p>
              <w:tbl>
                <w:tr><w:tc><w:p><w:r><w:t>Rodamiento</w:t></w:r></w:p></w:tc>
                      <w:tc><w:p><w:r><w:t>4</w:t></w:r></w:p></w:tc></w:tr>
              </w:tbl>
              <w:p><w:r><w:t>Plazo: 4 semanas</w:t></w:r></w:p>
            </w:body></w:document>"""
        }
    )


def xlsx() -> bytes:
    return zip_con(
        {
            "xl/workbook.xml": f"""<workbook xmlns="{S}" xmlns:r="{R}"><sheets>
              <sheet name="Oferta" sheetId="1" r:id="rId1"/></sheets></workbook>""",
            "xl/_rels/workbook.xml.rels": f"""<Relationships xmlns="{REL}">
              <Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>""",
            "xl/sharedStrings.xml": f"""<sst xmlns="{S}">
              <si><t>Descripción</t></si><si><t>Rodamiento 6204</t></si></sst>""",
            "xl/worksheets/sheet1.xml": f"""<worksheet xmlns="{S}"><sheetData>
              <row><c t="s"><v>0</v></c><c t="inlineStr"><is><t>Precio</t></is></c></row>
              <row><c t="s"><v>1</v></c><c><v>12.5</v></c></row>
            </sheetData></worksheet>""",
        }
    )


def test_texto_de_un_word_con_tabla():
    assert adjuntos_ia.texto_word(docx()) == "Oferta OF-77\nRodamiento | 4\nPlazo: 4 semanas"


def test_texto_de_un_excel():
    assert adjuntos_ia.texto_excel(xlsx()) == (
        "Hoja «Oferta»:\nDescripción\tPrecio\nRodamiento 6204\t12.5"
    )


def test_pdf_e_imagen_se_envian_como_archivo():
    contenido = Contenido()
    adjuntos_ia.preparar(contenido, "oferta.pdf", "pdf", b"%PDF-1.7")
    adjuntos_ia.preparar(contenido, "foto.JPG", "imagen", b"\xff\xd8")
    pdf, titulo, imagen = contenido.partes
    assert pdf["type"] == "input_file"
    assert pdf["filename"] == "oferta.pdf"
    assert pdf["file_data"] == (
        "data:application/pdf;base64," + base64.b64encode(b"%PDF-1.7").decode()
    )
    assert pdf["detail"] == "low"
    assert "foto.JPG" in titulo["text"]
    assert imagen["type"] == "input_image"
    assert imagen["image_url"].startswith("data:image/jpeg;base64,")
    assert contenido.avisos == []


def test_word_excel_y_texto_se_envian_como_texto():
    contenido = Contenido()
    adjuntos_ia.preparar(contenido, "oferta.docx", "word", docx())
    adjuntos_ia.preparar(contenido, "precios.xlsx", "excel", xlsx())
    adjuntos_ia.preparar(contenido, "notas.txt", "otro", b"Portes incluidos")
    textos = [p["text"] for p in contenido.partes]
    assert textos[0].startswith("Adjunto «oferta.docx» (Word):\nOferta OF-77")
    assert "Rodamiento 6204\t12.5" in textos[1]
    assert textos[2] == "Adjunto «notas.txt»:\nPortes incluidos"


@pytest.mark.parametrize(
    ("nombre", "formato", "datos", "consejo"),
    [
        ("oferta.doc", "word", b"\xd0\xcf", "formato nuevo"),
        ("precios.xls", "excel", b"\xd0\xcf", "formato nuevo"),
        ("plano.tiff", "imagen", b"II*", "PNG o JPEG"),
        ("oferta.zip", "otro", b"PK", "PDF"),
    ],
)
def test_lo_que_no_se_puede_leer_se_avisa(nombre, formato, datos, consejo):
    contenido = Contenido()
    adjuntos_ia.preparar(contenido, nombre, formato, datos)
    assert contenido.partes == []
    assert len(contenido.avisos) == 1
    assert nombre in contenido.avisos[0]
    assert consejo in contenido.avisos[0]


def test_office_danado():
    contenido = Contenido()
    adjuntos_ia.preparar(contenido, "oferta.docx", "word", b"no es un zip")
    assert contenido.partes == []
    assert "no se ha podido leer" in contenido.avisos[0]


def test_limites_de_tamano(monkeypatch):
    monkeypatch.setattr(adjuntos_ia, "MAXIMO_ENVIO", 10)
    monkeypatch.setattr(adjuntos_ia, "MAXIMO_TEXTO", 5)
    contenido = Contenido()
    adjuntos_ia.preparar(contenido, "a.pdf", "pdf", b"%PDF-1")
    adjuntos_ia.preparar(contenido, "b.pdf", "pdf", b"%PDF-2")
    adjuntos_ia.preparar(contenido, "c.txt", "otro", b"0123456789")
    assert [p.get("filename") for p in contenido.partes[:1]] == ["a.pdf"]
    assert contenido.partes[1]["text"] == "Adjunto «c.txt»:\n01234"
    assert any("b.pdf" in a and "pesan demasiado" in a for a in contenido.avisos)
    assert any("c.txt" in a and "principio" in a for a in contenido.avisos)


@pytest.mark.parametrize(
    ("nombre", "formato", "fabricar"),
    [("oferta.docx", "word", docx), ("precios.xlsx", "excel", xlsx)],
)
def test_office_con_un_archivo_interno_danado(nombre, formato, fabricar):
    """Un .docx o .xlsx que abre como zip pero tiene un archivo interno dañado (CRC incorrecto)
    no da un error 500 y la oferta se puede reanalizar."""
    datos = bytearray(fabricar())
    # Se cambia un byte de los datos comprimidos del primer archivo interno: falla el CRC.
    inicio = 30 + int.from_bytes(datos[26:28], "little") + int.from_bytes(datos[28:30], "little")
    datos[inicio + 2] ^= 0xFF
    contenido = Contenido()
    adjuntos_ia.preparar(contenido, nombre, formato, bytes(datos))
    assert contenido.partes == []
    assert "no se ha podido leer" in contenido.avisos[0]


# --- Seguridad: libros que se hinchan al descomprimir -------------------------------------------

_S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PR = "http://schemas.openxmlformats.org/package/2006/relationships"


def _libro(hojas: int, distintas: bool, mb: float = 0) -> bytes:
    """Un .xlsx con `hojas` hojas; si no son `distintas`, todas apuntan al mismo XML, que lleva
    un comentario de `mb` MB (se comprime a casi nada)."""
    import io
    import zipfile

    relleno = "<!--" + "x" * int(mb * 1024 * 1024) + "-->"
    cuantos = hojas if distintas else 1
    libro = (
        f'<workbook xmlns="{_S}" xmlns:r="{_R}"><sheets>'
        + "".join(
            f'<sheet name="H{i}" sheetId="{i + 1}" r:id="rId{i % cuantos + 1}"/>'
            for i in range(hojas)
        )
        + "</sheets></workbook>"
    )
    rels = (
        f'<Relationships xmlns="{_PR}">'
        + "".join(
            f'<Relationship Id="rId{i + 1}" Target="worksheets/sheet{i + 1}.xml"/>'
            for i in range(cuantos)
        )
        + "</Relationships>"
    )
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("xl/workbook.xml", libro)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        for i in range(cuantos):
            z.writestr(
                f"xl/worksheets/sheet{i + 1}.xml",
                f'<worksheet xmlns="{_S}"><sheetData><row><c t="inlineStr"><is><t>dato{i}</t>'
                f"</is></c></row></sheetData>{relleno}</worksheet>",
            )
    return salida.getvalue()


def test_la_misma_hoja_repetida_se_lee_una_vez():
    import time

    inicio = time.monotonic()
    texto = adjuntos_ia.texto_excel(_libro(200, distintas=False, mb=8))
    assert time.monotonic() - inicio < 5
    assert texto.count("dato0") == 1


def test_lo_descomprimido_tiene_un_limite_total():
    with pytest.raises(adjuntos_ia.ArchivoIlegible):
        adjuntos_ia.texto_excel(_libro(3, distintas=True, mb=8))


def test_como_mucho_50_hojas():
    texto = adjuntos_ia.texto_excel(_libro(60, distintas=True))
    assert "dato49" in texto
    assert "dato50" not in texto
    assert "más de 50 hojas" in texto


def _falsear_tamano(datos: bytes, nombre: bytes, falso: int) -> bytes:
    """Cambia el tamaño descomprimido que declara el ZIP para `nombre` (cabecera local y
    directorio central), como haría un archivo fabricado."""
    import struct

    datos = bytearray(datos)
    i = datos.find(b"PK\x03\x04")
    while i >= 0:
        largo = struct.unpack_from("<H", datos, i + 26)[0]
        if bytes(datos[i + 30 : i + 30 + largo]) == nombre:
            struct.pack_into("<I", datos, i + 22, falso)
        i = datos.find(b"PK\x03\x04", i + 4)
    i = datos.find(b"PK\x01\x02")
    while i >= 0:
        largo = struct.unpack_from("<H", datos, i + 28)[0]
        if bytes(datos[i + 46 : i + 46 + largo]) == nombre:
            struct.pack_into("<I", datos, i + 24, falso)
        i = datos.find(b"PK\x01\x02", i + 4)
    return bytes(datos)


def test_el_tamano_que_declara_el_zip_no_vale():
    """Con `file_size` falseado a 1000, un .xlsx de 400 KB no llega a descomprimir 400 MB antes
    de comprobar nada."""
    import time

    datos = _falsear_tamano(_libro(1, distintas=True, mb=30), b"xl/worksheets/sheet1.xml", 1000)
    inicio = time.monotonic()
    with pytest.raises(adjuntos_ia.ArchivoIlegible):
        adjuntos_ia.texto_excel(datos)
    assert time.monotonic() - inicio < 3
