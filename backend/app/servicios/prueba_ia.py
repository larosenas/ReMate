"""Juego de ofertas de prueba para comprobar las instrucciones de la IA.

Con `flask --app app probar-ia <carpeta>` se leen con la IA real unas ofertas de ejemplo y se
compara lo que sale con lo esperado, igual que lo haría «Analizar» (mismo contenido, mismas
instrucciones y mismo tratamiento de la respuesta). Sirve para comprobar un cambio en las
instrucciones o de modelo sin probar a mano oferta por oferta. No toca la base de datos.

La carpeta va fuera del repositorio (son ofertas reales, aunque se cambien los datos sensibles).
Cada subcarpeta es un caso:
- los archivos de la oferta: el correo (`.eml` o `.msg`, con sus adjuntos) y otros adjuntos
  sueltos (PDF, imágenes, Word, Excel o texto);
- `necesidad.txt` (opcional): en la primera línea el título y debajo la descripción, como lo
  que pidió el cliente;
- `esperado.json`: solo lo que se quiere comprobar, por ejemplo
  {"moneda": "EUR", "importe_sin_iva": "819.00", "fecha_entrega_estimada": "2026-11-26",
   "lineas": [{"cantidad": "3", "precio_unitario": "13", "fecha_entrega": "2026-11-11"}],
   "condiciones": {"incoterm": "especificado"}, "avisos_contienen": ["no oferta"]}

Cada llamada se paga (unos céntimos por oferta) y envía la oferta a OpenAI, como «Analizar»
(CU-004).
"""

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import SimpleNamespace

from app.config import Config
from app.integraciones import adjuntos_ia, correos_entrada, ia
from app.servicios import ofertas

CORREOS = (".eml", ".msg")
FORMATOS = {".pdf": "pdf", ".docx": "word", ".docm": "word", ".xlsx": "excel", ".xlsm": "excel"}
ESPECIALES = ("esperado.json", "necesidad.txt")  # sin mayúsculas: en Windows da igual


def _especial(archivo: Path) -> bool:
    """El esperado o la necesidad, también sus copias («esperado - copia.json»): nunca van a la
    IA, que vería las respuestas."""
    nombre = archivo.name.lower()
    return nombre in ESPECIALES or nombre.startswith(("esperado", "necesidad"))


@dataclass
class Resultado:
    caso: str
    diferencias: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def bien(self) -> bool:
        return self.error is None and not self.diferencias


def _formato(nombre: str) -> str:
    extension = Path(nombre).suffix.lower()
    if extension in adjuntos_ia.IMAGENES:
        return "imagen"
    return FORMATOS.get(extension, "otro")


def preparar_caso(carpeta: Path) -> tuple[adjuntos_ia.Contenido, SimpleNamespace]:
    """El contenido para la IA, como en `ofertas._contenido_para_ia`, y una oferta sin guardar con
    la fecha y el remitente del correo."""
    contenido = adjuntos_ia.Contenido()
    oferta = SimpleNamespace(
        fecha_correo=None,
        remitente=None,
        proveedor=SimpleNamespace(nombre="(prueba)", email=None),
        numero_oferta=None,
        moneda=None,
        revisada=False,
        datos_ia=None,
        lineas=[],
    )
    necesidad = carpeta / "necesidad.txt"
    if necesidad.is_file():
        titulo, _, descripcion = necesidad.read_text(encoding="utf-8-sig").partition("\n")
        contenido.texto(
            "Lo que pidió el cliente (no es parte de la oferta)",
            f"Título: {titulo.strip()}\nDescripción del ingeniero:\n{descripcion.strip()}",
        )
    archivos = sorted(
        (a for a in carpeta.iterdir() if a.is_file() and not _especial(a)),
        # El correo primero, como en la aplicación.
        key=lambda a: (a.suffix.lower() not in CORREOS, a.name),
    )
    for archivo in archivos:
        datos = archivo.read_bytes()
        if archivo.suffix.lower() in CORREOS:
            leido = correos_entrada.leer(archivo.name, datos)
            oferta.fecha_correo = oferta.fecha_correo or leido.fecha
            oferta.remitente = oferta.remitente or leido.remitente
            fecha = leido.fecha.isoformat() if leido.fecha else "—"
            contenido.texto(
                "Correo del proveedor",
                f"Remitente: {leido.remitente or '—'}\nFecha de envío: {fecha}\n"
                f"Asunto: {leido.asunto or '—'}\n\n{leido.cuerpo or '(sin texto)'}",
            )
            for adjunto in leido.adjuntos:
                adjuntos_ia.preparar(
                    contenido, adjunto.nombre, _formato(adjunto.nombre), adjunto.datos
                )
        else:
            adjuntos_ia.preparar(contenido, archivo.name, _formato(archivo.name), datos)
    return contenido, oferta


def _tiene_oferta(carpeta: Path) -> bool:
    """Hay algún archivo que la IA puede leer (no basta un desktop.ini o un Thumbs.db)."""
    legibles = (*CORREOS, *FORMATOS, *adjuntos_ia.IMAGENES, *adjuntos_ia.TEXTO)
    return any(
        a.is_file() and not _especial(a) and a.suffix.lower() in legibles for a in carpeta.iterdir()
    )


def _igual(esperado, obtenido) -> bool:
    """Compara números como números («13» y 13.0000) y lo demás como texto."""
    if esperado is None or obtenido is None:
        return esperado is obtenido
    try:
        return Decimal(str(esperado)) == Decimal(str(obtenido))
    except InvalidOperation:
        return str(esperado).strip() == str(obtenido).strip()


def _texto(valor) -> str | None:
    if valor is None:
        return None
    return valor.isoformat() if hasattr(valor, "isoformat") else str(valor)


def comparar(esperado: dict, oferta, avisos: list[str]) -> list[str]:
    """Lo que no coincide con `esperado` (solo se miran las claves que trae)."""
    diferencias = []
    for campo, valor in esperado.items():
        if campo == "lineas":
            if len(valor) != len(oferta.lineas):
                diferencias.append(f"líneas: se esperaban {len(valor)} y hay {len(oferta.lineas)}")
            for i, (linea_esperada, linea) in enumerate(zip(valor, oferta.lineas, strict=False), 1):
                for clave, dato in linea_esperada.items():
                    obtenido = _texto(getattr(linea, clave, None))
                    if not _igual(dato, obtenido):
                        diferencias.append(f"línea {i}, {clave}: «{dato}» ≠ «{obtenido}»")
        elif campo == "condiciones":
            leidas = oferta.condiciones or {}
            for clave, estado in valor.items():
                obtenido = (leidas.get(clave) or {}).get("estado")
                if obtenido != estado:
                    diferencias.append(f"condición {clave}: «{estado}» ≠ «{obtenido}»")
        elif campo == "avisos_contienen":
            for texto in valor:
                if not any(texto.lower() in a.lower() for a in avisos):
                    diferencias.append(f"ningún aviso dice «{texto}»")
        else:
            obtenido = _texto(getattr(oferta, campo, None))
            if not _igual(valor, obtenido):
                diferencias.append(f"{campo}: «{valor}» ≠ «{obtenido}»")
    return diferencias


def _formato_esperado(esperado) -> str | None:
    """Qué está mal en `esperado.json`, antes de pagar la llamada; None si está bien (con una
    lista o `"lineas": null` se caería todo y se perderían los casos leídos)."""
    if not isinstance(esperado, dict):
        return "esperado.json tiene que ser un objeto {…}"
    tipos = {"lineas": list, "condiciones": dict, "avisos_contienen": list}
    for campo, tipo in tipos.items():
        if campo in esperado and not isinstance(esperado[campo], tipo):
            forma = "una lista" if tipo is list else "un objeto"
            return f"en esperado.json, «{campo}» tiene que ser {forma}"
    if not all(isinstance(linea, dict) for linea in esperado.get("lineas", [])):
        return "en esperado.json, cada línea tiene que ser un objeto {…}"
    if not all(isinstance(t, str) for t in esperado.get("avisos_contienen", [])):
        return "en esperado.json, «avisos_contienen» tiene que ser una lista de textos"
    return None


def probar_caso(config: Config, carpeta: Path) -> Resultado:
    resultado = Resultado(carpeta.name)
    try:
        esperado = json.loads((carpeta / "esperado.json").read_text(encoding="utf-8-sig"))
        if problema := _formato_esperado(esperado):
            resultado.error = problema
            return resultado
        if not _tiene_oferta(carpeta):
            # No se paga una llamada sin oferta.
            resultado.error = "el caso no tiene archivos de la oferta"
            return resultado
        contenido, oferta = preparar_caso(carpeta)
        respuesta = ia.leer_oferta(config, contenido.partes)
    except (OSError, ValueError, correos_entrada.CorreoNoValido, ia.ErrorIA) as error:
        resultado.error = f"{type(error).__name__}: {error}"
        return resultado
    try:
        valores, lineas, avisos = ofertas._lectura(oferta, respuesta)
        for campo, valor in valores.items():
            setattr(oferta, campo, valor)
        oferta.lineas = lineas
        oferta.datos_ia = {
            "respuesta": respuesta,
            **ofertas.marca_de_importe_sumado(oferta, respuesta),
        }
        avisos = [*contenido.avisos, *avisos, *ofertas.avisos(oferta)]
        resultado.diferencias = comparar(esperado, oferta, avisos)
    except Exception as error:
        # Un caso raro no puede tirar los demás, que ya se han pagado.
        resultado.error = f"{type(error).__name__}: {error}"
    return resultado


def probar(config: Config, carpeta: Path) -> list[Resultado]:
    """Un resultado por cada subcarpeta con `esperado.json`, en orden alfabético."""
    casos = sorted(c for c in carpeta.iterdir() if (c / "esperado.json").is_file())
    return [probar_caso(config, caso) for caso in casos]
