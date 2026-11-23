"""CU-004 — Ofertas: subirlas, leerlas con la IA (todas a la vez), revisarlas, borrarlas,
pasar a evaluación y comparativa.

Reglas (docs/casos-de-uso/CU-004-recibir-y-comparar-ofertas.md):
- Solo en «En cotización» o «En evaluación».
- El correo va en un `.eml` o un `.msg` de Outlook (ADR 0013). Sus adjuntos se proponen al elegirlo
  (`leer_correo`) y se guardan los que se dejen, cada uno con su formato; se pueden añadir más.
- El proveedor se reconoce por el remitente o, si no coincide, por su dominio.
- Una segunda oferta del mismo proveedor sustituye a la anterior; nada se borra de verdad.
- El plazo relativo («4 semanas», también en inglés: «4 weeks», «25 working days») se convierte
  en fecha contando desde el envío del correo.
- Al subirla, la oferta solo se guarda. Cuando están todas, «Analizar y comparar» hace que la IA
  las lea a la vez y saca la comparativa.
- La IA lee el correo y los adjuntos y propone los datos; el ingeniero siempre los revisa, y solo
  se adjudica una oferta revisada. Si la IA falla, la oferta queda guardada y los datos
  se escriben a mano (flujo 3a).
"""

import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import fechas
from app.config import Config
from app.integraciones import adjuntos_ia, archivos, correos_entrada, ia
from app.modelos.listas import Proveedor
from app.modelos.necesidades import FORMATOS_ADJUNTO, Adjunto, CambioEstado, Necesidad
from app.modelos.ofertas import LineaOferta, Oferta
from app.servicios import condiciones
from app.servicios.listas import DatosNoValidos, peticionario_activo
from app.servicios.necesidades import ArchivoSubido, TransicionNoPermitida, necesidad_en

log = logging.getLogger(__name__)

ESTADOS_CON_OFERTAS = ("en_cotizacion", "en_evaluacion")
AVISO_REANALIZAR = "Escribe los datos a mano o pulsa «Reanalizar con IA»."
# Ofertas que lee la IA a la vez al «Analizar y comparar»: pocas, para no superar el límite de
# peticiones por minuto de la API.
LECTURAS_A_LA_VEZ = 4
# Todos los importes son sin IVA: el importe con IVA no se usa ni se lee.
OBLIGATORIOS_REVISADA = (
    ("moneda", "la moneda"),
    ("importe_sin_iva", "el importe sin IVA"),
    ("fecha_entrega_estimada", "la fecha de entrega"),
)
CAMPOS_EDITABLES = (
    "moneda",
    "numero_oferta",
    "importe_sin_iva",
    "plazo_entrega_texto",
    "fecha_entrega_estimada",
    "condiciones_pago",
    "otros",
    "condiciones",
)


class OfertaExistente(Exception):
    """El proveedor ya tiene una oferta vigente y no se ha confirmado la sustitución (CU-004 4c)."""

    def __init__(self, proveedor: Proveedor):
        super().__init__(
            f"{proveedor.nombre} ya tiene una oferta. Si la nueva la sustituye, confírmalo; si es "
            "su respuesta con datos que faltaban, añádelos a su oferta."
        )
        self.proveedor = proveedor


@dataclass(frozen=True)
class AdjuntoOferta:
    archivo: ArchivoSubido
    formato: str


@dataclass(frozen=True)
class LineaEntrada:
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    fecha_entrega: date | None = None
    plazo_entrega_texto: str | None = None


# --- Plazo de entrega ------------------------------------------------------------------------

_UNIDADES = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9,
}  # fmt: skip
_DECENAS = {
    "veinte": 20, "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
}  # fmt: skip
_NUMEROS = {
    **_UNIDADES, **_DECENAS, "diez": 10, "once": 11, "doce": 12, "trece": 13, "catorce": 14,
    "quince": 15, "dieciséis": 16, "dieciseis": 16, "dieciocho": 18, "veintiuno": 21,
    "veinticinco": 25,
}  # fmt: skip
# Más largas primero: «veinticinco» antes que «veinte», «una» antes que «un».
_EN_LETRA = "|".join(sorted(_NUMEROS, key=len, reverse=True))
_NUMERO = r"(\d+(?:[.,]\d+)?|" + _EN_LETRA + r")"
# Sin «hr»: «58-62 HR» es una dureza, no unas horas.
_UNIDAD = r"d[ií]as?|days?|semanas?|sem\.?|weeks?|wks?|meses|mes|months?|horas?|hours?|hrs|h"
# Un número o un rango: «18 - 20 días», «18 días - 20 días», «entre 18 y 20 días», «18/20 días».
_PLAZO = re.compile(
    r"(?<![\w.,])" + _NUMERO + r"\s*(?:(" + _UNIDAD + r")(?!\w)\s*)?"
    r"(?:(-|–|—|/|a|y|to|and)\s*" + _NUMERO + r"\s*)?"
    r"(?:(working|business|calendar)\s+)?"
    r"(" + _UNIDAD + r")(?!\w)"
    # Sin comerse el espacio de detrás si no hay «laborables»: lo que sigue (otra línea con el
    # pago, por ejemplo) se mira aparte.
    r"(?:[ \t]*(laborables?|h[aá]bil(?:es)?|naturales?))?",
    re.IGNORECASE,
)
_LABORABLES = ("laborable", "hábil", "habil", "working", "business")
# Qué plazo es el de entrega. Un texto puede traer también el
# pago, la validez o la garantía («Entrega 5 semanas. Pago 90 días»), en la misma línea o en otra:
# no cuentan los plazos que los nombran (como sustantivo y no como condición: «tras el pago» es de
# la entrega). De los que quedan, el más largo. La etiqueta de entrega («Precios netos, plazo 4
# semanas») solo sirve para saber que lo de delante ya no es del pago.
_ENTREGA = re.compile(
    r"\b(?:entrega\w*|plazo\w*|suministro|fabricaci[oó]n|env[ií]o|delivery|lead\s*time|"
    r"ready|shipment|lieferzeit|liefertermin)\b",
    re.IGNORECASE,
)
# Solo como sustantivo: «garantizamos la entrega» o «validados los planos» son de la entrega.
_OTRA_COSA = re.compile(
    r"\b(?:validez|validity|valid|v[aá]lid[ao]s?|pagos?|pagaderos?|payment|garant[ií]as?|"
    r"warranty|guarantee|vencimiento|facturas?|invoice|netos?|net|f\.\s?f|vacaciones|cerrado|"
    r"closed|holidays?|betriebsferien|werksurlaub|urlaub|geschlossen|zahlung\w*|netto|"
    r"g[uü]ltig\w*)\b",
    re.IGNORECASE,
)
# «Tras el pago», «desde la recepción del pago», «after payment»: el pago es la condición de la
# entrega, no otro plazo.
_CONDICION = re.compile(
    r"\b(?:tras|desde|despu[eé]s\s+de|una\s+vez|al\s+recibir|after|upon|on\s+receipt|from)\s+"
    r"(?:(?:el|la|los|las|del|de|al|su|recibir|recibido|recepci[oó]n|cobro|receipt|of|the)\s+)"
    r"{0,3}$",
    re.IGNORECASE,
)
# Cláusulas: lo que separa una idea de la siguiente.
_CLAUSULA = re.compile(r"[;\n]|\.\s")
# Trozos de frase: también comas, barras, paréntesis y guiones sueltos.
_CORTE = re.compile(r"[;\n/,()|]|\.\s|\s[-–—]\s")
# Justo detrás del plazo y en la misma línea: «24 meses de garantía», «30 días de validez», «30
# days validity», «45 días fecha factura», «60 días F.F.», «30 días netos».
_DETRAS_OTRA_COSA = re.compile(
    r"^[ \t]*(?:de[ \t]+|of[ \t]+)?(?:la[ \t]+|the[ \t]+)?(?:garant|valid|warrant|netos?\b|"
    r"net\b|fecha[ \t]+(?:de[ \t]+)?factura|f\.\s?f\b|invoice|pago|payment|vencimiento)",
    re.IGNORECASE,
)
# Plazos que se suman: «2 semanas + 3 días», «4 semanas, más 1 semana de transporte», «4 semanas
# (más 1 semana de transporte)», «4 semanas + transporte 1 semana»; y, si la segunda unidad es
# menor o lo que se suma es el transporte o el montaje, también «1 semana 3 días», «4 semanas y 2
# días» o «4 semanas y 1 semana de transporte».
_SUMA = re.compile(r"^\s*[,(]?\s*(?:\+|más\b|plus\b)[^\d;\n]*$", re.IGNORECASE)
_SUMA_MENOR = re.compile(r"^\s*(?:y|and|,)?\s*$", re.IGNORECASE)
_DE_TRANSPORTE = re.compile(
    r"^\s*(?:de\s+|of\s+)?(?:transporte|env[ií]o|montaje|instalaci[oó]n|shipping|transport|"
    r"delivery|installation)",
    re.IGNORECASE,
)
# «3 semanas desde pago, montaje 1 semana», «4 semanas; transporte: 3 días».
_SUMA_TRANSPORTE = re.compile(
    r"^\s*[,;]?\s*(?:y\s+|and\s+|más\s+)?(?:de\s+)?(?:transporte|env[ií]o|montaje|"
    r"instalaci[oó]n|shipping|transport|installation)\s*:?\s*$",
    re.IGNORECASE,
)
# De mayor a menor, para saber si «4 semanas y 2 días» es una suma.
_ORDEN_UNIDADES = {"m": 3, "s": 2, "d": 1, "h": 0}


def _normalizar_plazo(texto: str) -> str:
    """«cuarenta y cinco días» → «45 días»; «dos meses y medio» → «2,5 meses»."""
    unidades = "|".join(_UNIDADES)
    decenas = "|".join(_DECENAS)
    texto = re.sub(
        rf"\b({decenas})\s+y\s+({unidades})\b",
        lambda m: str(_DECENAS[m[1].lower()] + _UNIDADES[m[2].lower()]),
        texto,
        flags=re.IGNORECASE,
    )

    def medio(m: re.Match) -> str:
        numero = (m[1] or "un").lower()
        entero = _NUMEROS.get(numero) or int(numero)
        return f"{entero},5 {'meses' if m[2].lower() == 'mes' else 'semanas'}"

    return re.sub(
        rf"\b(?:(\d+|{_EN_LETRA})\s+)?(mes|semana)(?:es|s)?\s+y\s+medi[oa]\b",
        medio,
        texto,
        flags=re.IGNORECASE,
    )


def _sumar_meses(dia: date, meses: int) -> date:
    mes = dia.month - 1 + meses
    anio, mes = dia.year + mes // 12, mes % 12 + 1
    ultimo = (date(anio + mes // 12, mes % 12 + 1, 1) - timedelta(days=1)).day
    return date(anio, mes, min(dia.day, ultimo))


def _sumar_laborables(dia: date, dias: int) -> date:
    # Desde un sábado o un domingo se cuenta como desde el viernes: el primer laborable es el lunes.
    if dias > 0:
        while dia.weekday() >= 5:
            dia -= timedelta(days=1)
    # Semanas completas de golpe y el resto día a día (como mucho cuatro vueltas).
    semanas, resto = divmod(dias, 5)
    dia += timedelta(weeks=semanas)
    while resto > 0:
        dia += timedelta(days=1)
        if dia.weekday() < 5:
            resto -= 1
    return dia


def _otra_cosa_delante(trozo: str) -> bool:
    """El trozo nombra el pago, la validez o la garantía, y no como condición («tras el pago»)
    ni seguido de una etiqueta de entrega («Precios netos, plazo 4 semanas»)."""
    otra = list(_OTRA_COSA.finditer(trozo))
    if not otra:
        return False
    return not (
        _CONDICION.search(trozo[: otra[-1].start()]) or _ENTREGA.search(trozo[otra[-1].end() :])
    )


def _va_con_otra_cosa(texto: str, inicio: int, fin: int) -> bool:
    """El plazo (o la semana) es del pago, la validez o la garantía: lo dice su trozo de frase,
    delante, o lo que va justo detrás en la misma línea."""
    delante = _CORTE.split(texto[:inicio])[-1]
    # También la cláusula entera: en «pago 30, 60 y 90 días» o «validez (30 días)» una coma o
    # un paréntesis separan el número de su palabra; si después viene una etiqueta de entrega
    # («Validez 30 días, plazo 4 semanas»), ya no cuenta (`_otra_cosa_delante`).
    clausula = _CLAUSULA.split(texto[:inicio])[-1]
    # Con «5 Sem.» el punto ya cierra la frase: lo de detrás no es del plazo.
    detras = "" if texto[fin - 1 : fin] == "." else texto[fin:]
    return (
        _otra_cosa_delante(delante)
        or _otra_cosa_delante(clausula)
        or bool(_DETRAS_OTRA_COSA.match(detras))
    )


def _elegidos(texto: str, encontrados: list[re.Match]) -> list[re.Match]:
    """Los plazos (o semanas) que son de entrega: los que no van con el pago, la validez, la
    garantía o las vacaciones (con «Entrega parcial en 2 semanas. Resto en 6 semanas.» cuentan
    los dos, no solo el de la etiqueta)."""
    return [e for e in encontrados if not _va_con_otra_cosa(texto, e.start(), e.end())]


def fecha_desde_plazo(texto: str | None, desde: date | None, *, primero=False) -> date | None:
    """«4 semanas» desde el 22/10/2026 → 19/11/2026. Con un rango («3-4 semanas») se toma el
    número más alto. Si el texto trae varios plazos de entrega («18-20
    días / 5 semanas»), el más largo: el pedido no está completo hasta que llega todo; los del
    pago, la validez o la garantía no cuentan (`_elegidos`). None si no se entiende (el
    ingeniero pone la fecha a mano, flujo 4b). Los días laborables cuentan de lunes a viernes,
    sin festivos. `primero`: con el cálculo anterior, solo para reconocer las
    fechas ya guardadas (`fecha_calculada`)."""
    if not texto or desde is None:
        return None
    if primero:
        return _fecha_hasta_2026_11_18(texto, desde)
    texto = _normalizar_plazo(texto)
    todos = list(_PLAZO.finditer(texto))
    elegidos = _elegidos(texto, todos)
    fechas_plazo, anterior, actual = [], None, None
    for encontrado in todos:
        if encontrado not in elegidos:
            # «Entrega 3 semanas y 24 meses de garantía» se lee como un solo trozo: vale la
            # primera parte.
            if primera := _solo_la_primera(texto, encontrado, desde):
                fechas_plazo.append(primera)
            anterior = None
            continue
        # Cada plazo, con los que se le suman detrás, contado desde el anterior.
        if anterior is not None and actual and _se_suma(texto, anterior, encontrado):
            actual = _fecha_de(encontrado, actual)
            fechas_plazo[-1] = actual or fechas_plazo[-1]
        else:
            actual = _fecha_de(encontrado, desde)
            if actual:
                fechas_plazo.append(actual)
        anterior = encontrado
    return max(fechas_plazo, default=None)


def _solo_la_primera(texto: str, encontrado: re.Match, desde: date) -> date | None:
    numero, unidad_1, separador, hasta, *_ = encontrado.groups()
    if not (unidad_1 and hasta and separador.lower() in ("y", "and", "-", "–", "—")):
        return None
    if _otra_cosa_delante(_CORTE.split(texto[: encontrado.start()])[-1]):
        return None
    cantidad = _cantidad(numero)
    return _sumar(desde, cantidad, unidad_1, False) if cantidad is not None else None


def _se_suma(texto: str, anterior: re.Match, encontrado: re.Match) -> bool:
    entre = texto[anterior.end() : encontrado.start()]
    if _SUMA.match(entre) or _SUMA_TRANSPORTE.match(entre):
        return True
    if not _SUMA_MENOR.match(entre):
        return False
    menor = (
        _ORDEN_UNIDADES[_tipo_de_unidad(encontrado[6])]
        < _ORDEN_UNIDADES[_tipo_de_unidad(anterior[6])]
    )
    return menor or bool(_DE_TRANSPORTE.match(texto[encontrado.end() :]))


def _cantidad(numero: str) -> float | None:
    if numero.lower() in _NUMEROS:
        return _NUMEROS[numero.lower()]
    if len(numero) > 7:
        return None
    return float(numero.replace(",", "."))


def _tipo_de_unidad(unidad: str) -> str:
    """d (días), s (semanas), m (meses) o h (horas)."""
    unidad = unidad.lower()
    if unidad.startswith(("sem", "w")):
        return "s"
    return "m" if unidad.startswith("m") else unidad[0]


def _fecha_de(encontrado: re.Match, desde: date) -> date | None:
    numero, unidad_1, separador, hasta, tipo_ingles, unidad, tipo = encontrado.groups()
    tipo = tipo or tipo_ingles
    laborables = bool(tipo and tipo.lower().startswith(_LABORABLES))
    cantidades = [_cantidad(n) for n in (numero, hasta) if n]
    if None in cantidades:
        return None
    if unidad_1 and hasta and _tipo_de_unidad(unidad_1) != _tipo_de_unidad(unidad):
        # Dos unidades distintas. «4 semanas y 2 días» se suman; un rango («entre 2 semanas y
        # 20 días», «de 3 semanas a 1 mes», «15 días - 3 semanas»), el mayor.
        delante = encontrado.string[max(0, encontrado.start() - 10) : encontrado.start()]
        suma = (
            separador.lower() in ("y", "and")
            and not re.search(r"\bentre\s*$|\bbetween\s*$", delante, re.IGNORECASE)
            and _ORDEN_UNIDADES[_tipo_de_unidad(unidad)]
            < _ORDEN_UNIDADES[_tipo_de_unidad(unidad_1)]
        )
        if suma:
            intermedia = _sumar(desde, cantidades[0], unidad_1, False)
            return _sumar(intermedia, cantidades[1], unidad, laborables) if intermedia else None
        fechas_rango = [
            _sumar(desde, cantidades[0], unidad_1, False),
            _sumar(desde, cantidades[1], unidad, laborables),
        ]
        return max((f for f in fechas_rango if f), default=None)
    if (
        unidad_1
        and hasta
        and separador.lower() in ("y", "and")
        and _DE_TRANSPORTE.match(encontrado.string[encontrado.end() :])
    ):
        # «4 semanas y 1 semana de transporte»: se suman.
        return _sumar(desde, sum(cantidades), unidad, laborables)
    # El mayor, aunque el rango venga al revés («20-18 días»).
    return _sumar(desde, max(cantidades), unidad, laborables)


def _sumar(desde: date, cantidad: float, unidad: str, laborables: bool) -> date | None:
    tipo = _tipo_de_unidad(unidad)
    # Un plazo de más de unos diez años es casi seguro un error: se pide la fecha a mano.
    if cantidad > {"d": 3650, "s": 520, "m": 120, "h": 87600}[tipo]:
        return None
    try:
        if tipo == "m":
            # «1,5 meses»: el mes entero y la parte que sobra, en días de 30.
            meses = math.floor(cantidad)
            return _sumar_meses(desde, meses) + timedelta(days=math.ceil((cantidad - meses) * 30))
        # «48 horas»: días enteros, redondeando hacia arriba.
        dias = {"h": cantidad / 24, "d": cantidad, "s": cantidad * (5 if laborables else 7)}[tipo]
        if laborables:
            return _sumar_laborables(desde, math.ceil(dias))
        return desde + timedelta(days=math.ceil(dias))
    except OverflowError, ValueError:
        # Pasaría del año 9999: se pide la fecha a mano.
        return None


# Copia literal del cálculo anterior (el primer plazo del texto y, en un rango, el
# primer número): solo para reconocer como calculadas las fechas que se guardaron con él.
# No se usa para calcular fechas nuevas.
_NUMEROS_HASTA_2026_11_18 = {
    "un": 1, "una": 1, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "doce": 12, "quince": 15, "veinte": 20,
}  # fmt: skip
_PLAZO_HASTA_2026_11_18 = re.compile(
    r"(\d+|" + "|".join(_NUMEROS_HASTA_2026_11_18) + r")\s*(?:(?:-|–|a|to)\s*\d+\s*)?"
    r"(?:(working|business|calendar)\s+)?"
    r"(d[ií]as?|days?|semanas?|sem\.?|weeks?|wks?|meses|mes|months?)\b"
    r"\s*(laborables?|h[aá]bil(?:es)?|naturales?)?",
    re.IGNORECASE,
)


def _fecha_hasta_2026_11_18(texto: str, desde: date) -> date | None:
    encontrado = _PLAZO_HASTA_2026_11_18.search(texto)
    if not encontrado:
        return None
    numero, tipo_ingles, unidad, tipo = encontrado.groups()
    tipo = tipo or tipo_ingles
    if numero.isdigit() and len(numero) > 4:
        return None
    cantidad = int(numero) if numero.isdigit() else _NUMEROS_HASTA_2026_11_18[numero.lower()]
    unidad = unidad.lower()
    if cantidad > {"d": 3650, "s": 520, "w": 520, "m": 120}[unidad[0]]:
        return None
    try:
        if unidad.startswith("d"):
            if tipo and tipo.lower().startswith(_LABORABLES):
                return _sumar_laborables(desde, cantidad)
            return desde + timedelta(days=cantidad)
        if unidad.startswith(("sem", "w")):
            return desde + timedelta(weeks=cantidad)
        return _sumar_meses(desde, cantidad)
    except OverflowError, ValueError:
        return None


_ZONA = fechas.ZONA


def dia_del_correo(oferta: Oferta) -> date | None:
    """Día en que el proveedor envió el correo, en hora de Madrid (no en la de la sesión de la base
    de datos: un correo cerca de medianoche no cambia de día según el servidor)."""
    return oferta.fecha_correo.astimezone(_ZONA).date() if oferta.fecha_correo else None


def ultimo_viernes(anio: int, mes: int) -> date:
    siguiente = date(anio + (mes == 12), mes % 12 + 1, 1)
    ultimo = siguiente - timedelta(days=1)
    return ultimo - timedelta(days=(ultimo.weekday() - 4) % 7)


def fecha_desde_mes(mes, anio, desde: date | None) -> date | None:
    """Entrega cuando la oferta solo dice un mes («diciembre»): el último viernes de ese mes
    Sin año, el primer mes con ese nombre que no haya pasado
    el día del correo. None si el mes no vale o no se puede saber el año."""
    if not isinstance(mes, int) or isinstance(mes, bool) or not 1 <= mes <= 12:
        return None
    if isinstance(anio, int) and not isinstance(anio, bool) and 2000 <= anio <= 2100:
        return ultimo_viernes(anio, mes)
    if desde is None:
        return None
    fecha = ultimo_viernes(desde.year, mes)
    return fecha if fecha >= desde else ultimo_viernes(desde.year + 1, mes)


# «KW 50», «CW 50/2026», «semana 50», «week 50», «Sem. 50», «KW 48/49», «KW 50 o 51», «KW 50
# bis 52»: una semana del calendario, no un plazo. No si va detrás de un número («1 semana 3
# días») ni si le sigue una unidad o «tras/después/a partir» («semana 2 tras pedido»): eso es un
# plazo.
_SEMANA = re.compile(
    r"(?<![\w.,])(?<!\d )(?<!\d)(?:KW|CW|semana|week|wk|sem\.?)\s*(?:n[º°o]\.?\s*)?"
    r"(\d{1,2})(?!,\d)(?!\.\d(?!\d{3}\b))(?!\d)"
    r"(?:\s*(?:([/.\-–—])|\s(o|or|bis|a|al|to|y|and)\s)\s*(?:KW|CW|semana|week|wk|sem\.?)?\s*"
    r"(\d{4}|\d{1,2})(?!\d))?"
    r"(?!\s*(?:d[ií]as?|days?|semanas?|weeks?|meses|months?|horas?|hours?|tras|despu[eé]s|"
    r"desde|a\s+partir|after|from)\b)",
    re.IGNORECASE,
)


def fecha_desde_semana(texto: str | None, desde: date | None) -> date | None:
    """Entrega en una semana del calendario («KW 50»): el viernes de esa semana (ISO), como con
    los meses. Con un rango («KW 48/49») o varias semanas («1ª
    entrega semana 48, 2ª semana 50»), la última. Sin año, la primera que no haya pasado el día
    del correo. None si no hay semana o no vale."""
    if not texto:
        return None
    # Como con los plazos: no las de la validez, el pago o las vacaciones, y antes las que
    # tienen etiqueta de entrega.
    elegidas = _elegidos(texto, list(_SEMANA.finditer(texto)))
    fechas_semana = [f for e in elegidas if (f := _viernes_de(e, desde))]
    return max(fechas_semana, default=None)


def _viernes_de(encontrada: re.Match, desde: date | None) -> date | None:
    semana, _separador, palabra, segundo = encontrada.groups()
    semana, anio, siguiente_anio = int(semana), None, False
    if segundo and len(segundo) == 4:
        anio = int(segundo)
    elif segundo and palabra:
        # «KW 50 o 51», «KW 50 bis 52»: un rango, la última.
        siguiente_anio = int(segundo) < semana
        semana = int(segundo)
    elif segundo:
        # Con «/», «-» o «.»: «KW 48/49» o «semana 12-15» son un rango (la segunda, pocas
        # semanas después); «KW 52/01», un rango que cruza el año; «KW 50/26» o «KW 2/27», el
        # año (así «KW 48/49» no se lee como 2049 ni «KW 52/01» como 2001).
        diferencia = int(segundo) - semana
        if 0 < diferencia <= 4:
            semana = int(segundo)
        elif semana >= 50 and int(segundo) <= 4:
            semana, siguiente_anio = int(segundo), True
        elif desde is None or desde.year - 1 <= 2000 + int(segundo) <= desde.year + 5:
            anio = 2000 + int(segundo)
        else:
            return None
    try:
        if anio:
            return date.fromisocalendar(anio, semana, 5)
        if desde is None:
            return None
        # El año ISO del correo: del 1 al 3 de enero puede ser aún el anterior.
        anio_iso = desde.isocalendar().year
        if siguiente_anio:
            anio_iso += 1
        fecha = date.fromisocalendar(anio_iso, semana, 5)
        return fecha if fecha >= desde else date.fromisocalendar(anio_iso + 1, semana, 5)
    except ValueError:
        return None


def _lecturas(oferta: Oferta) -> list[dict]:
    """Las respuestas de la IA guardadas: la de la oferta y las de las respuestas del
    proveedor."""
    datos_ia = oferta.datos_ia or {}
    lecturas = [datos_ia.get("respuesta")]
    lecturas += [r.get("respuesta") for r in datos_ia.get("respuestas", []) if isinstance(r, dict)]
    return [r for r in lecturas if isinstance(r, dict)]


def idioma(oferta: Oferta) -> str | None:
    """Idioma en el que escribe el proveedor («en», «de»…), según la última lectura de la IA que
    lo dice; None si ninguna lo dice."""
    for lectura in reversed(_lecturas(oferta)):
        valor = ia.claves(lectura).get("idioma")
        if not isinstance(valor, str):
            continue
        valor = valor.strip().lower()
        # «en-GB», «pt_BR» → «en», «pt»; también algunos nombres y códigos de tres letras.
        if valor in _NOMBRES_IDIOMA:
            return _NOMBRES_IDIOMA[valor]
        if re.fullmatch(r"[a-z]{2}(?:[-_][a-z]{2,4})?", valor):
            return valor[:2]
    return None


_NOMBRES_IDIOMA = {
    "spa": "es", "español": "es", "espanol": "es", "spanish": "es", "castellano": "es",
    "eng": "en", "english": "en", "inglés": "en", "ingles": "en",
    "deu": "de", "ger": "de", "german": "de", "deutsch": "de", "alemán": "de", "aleman": "de",
    "fra": "fr", "fre": "fr", "french": "fr", "français": "fr", "francés": "fr",
    "ita": "it", "italian": "it", "italiano": "it", "por": "pt", "portuguese": "pt",
    "pol": "pl", "polish": "pl", "polaco": "pl", "cat": "ca", "catalán": "ca", "català": "ca",
    "sp": "es", "valenciano": "va", "valencià": "va", "galego": "gl", "gallego": "gl",
    "euskera": "eu", "euskara": "eu",
}  # fmt: skip
# Lenguas de España: se les escribe en español, no en inglés.
IDIOMAS_EN_ESPANOL = (None, "es", "ca", "va", "gl", "eu")


def fecha_de_mes(oferta: Oferta) -> bool:
    """La fecha de entrega sale del mes que dio el proveedor, no la dio él. Se reconoce con las
    respuestas guardadas de la IA; si el ingeniero cambia la fecha, ya es la suya."""
    if oferta.fecha_entrega_estimada is None:
        return False
    desde = dia_del_correo(oferta)
    for lectura in _lecturas(oferta):
        datos = ia.claves(lectura)
        mes = fecha_desde_mes(datos.get("mes_entrega"), datos.get("anio_mes_entrega"), desde)
        if mes == oferta.fecha_entrega_estimada:
            return True
    return False


def fecha_no_dada(oferta: Oferta) -> bool:
    """El proveedor no dio esa fecha (dio un plazo o un mes): no se le dice como si la hubiera
    dado (correo de la adjudicación)."""
    return fecha_calculada(oferta) or fecha_de_mes(oferta) or fecha_de_semana(oferta)


def fecha_de_semana(oferta: Oferta) -> bool:
    """La fecha de entrega es el viernes de la semana que dio el proveedor («KW 50»)."""
    fecha = oferta.fecha_entrega_estimada
    if fecha is None:
        return False
    return fecha_desde_semana(oferta.plazo_entrega_texto, dia_del_correo(oferta)) == fecha


def fecha_calculada(oferta: Oferta) -> bool:
    """La fecha de entrega no la dio el proveedor: es su plazo («3 semanas») contado desde su
    correo. Sirve para comparar ofertas, pero no es una fecha comprometida."""
    if oferta.fecha_entrega_estimada is None or oferta.fecha_correo is None:
        return False
    desde = dia_del_correo(oferta)
    # También con el primer número del rango, como en el cálculo anterior (fechas ya guardadas).
    return oferta.fecha_entrega_estimada in (
        fecha_desde_plazo(oferta.plazo_entrega_texto, desde),
        fecha_desde_plazo(oferta.plazo_entrega_texto, desde, primero=True),
    )


def linea_calculada(linea: LineaOferta, oferta: Oferta) -> bool:
    """La fecha de la línea es su plazo («5 Sem.») contado desde el correo: no la dio el
    proveedor ni la ha cambiado el ingeniero (CU-004)."""
    if linea.fecha_entrega is None or not linea.plazo_entrega_texto:
        return False
    desde = dia_del_correo(oferta)
    return fecha_desde_plazo(linea.plazo_entrega_texto, desde) == linea.fecha_entrega


def entrega_de_linea(linea: LineaOferta, oferta: Oferta, dia: date) -> date | None:
    """Fecha de la línea si el pedido se hace el día `dia`: con un plazo, contado desde ese día;
    si no, la suya (o None)."""
    if linea_calculada(linea, oferta):
        return fecha_desde_plazo(linea.plazo_entrega_texto, dia)
    return linea.fecha_entrega


# --- Avisos ----------------------------------------------------------------------------------


def moneda(valor) -> str | None:
    """Código de la moneda (tres letras, en mayúsculas) o None si no lo es (ADR 0010)."""
    if not isinstance(valor, str):
        return None
    # Se comprueba antes de pasar a mayúsculas: «ßa» daría SSA.
    limpio = valor.strip()
    return limpio.upper() if re.fullmatch(r"[A-Za-z]{3}", limpio) else None


def moneda_supuesta(oferta: Oferta) -> bool:
    """La IA no dio la moneda y sigue la de por defecto, sin revisar (ADR 0010). Se mira en su
    respuesta guardada, para que el aviso no se pierda al recargar."""
    lecturas = _lecturas(oferta)
    return (
        bool(lecturas)
        and not oferta.revisada
        and oferta.moneda == "EUR"
        and all(moneda(ia.claves(r).get("moneda")) is None for r in lecturas)
    )


def _fechas_raras(oferta: Oferta) -> list[str]:
    """Una entrega antes del correo de la oferta o a más de 3 años suele ser una fecha mal leída
    (el año de otra fecha, la de la propia oferta…): ganaría la comparativa sin que nadie lo
    vea."""
    desde = dia_del_correo(oferta)
    if desde is None:
        return []
    fechas_oferta = [("La fecha de entrega", oferta.fecha_entrega_estimada)]
    fechas_oferta += [
        (f"La entrega de la partida «{li.descripcion}»", li.fecha_entrega) for li in oferta.lineas
    ]
    lista = []
    for que, fecha in fechas_oferta:
        if fecha is None:
            continue
        if fecha < desde:
            lista.append(f"{que} ({fecha:%d/%m/%Y}) es anterior al correo de la oferta: revísala.")
        elif fecha > _sumar_meses(desde, 36):
            lista.append(f"{que} ({fecha:%d/%m/%Y}) es dentro de más de 3 años: revísala.")
    return lista


def _descuento(linea: dict) -> Decimal | None:
    """El importe (en positivo) de una línea de descuento o abono de la IA: con descripción y el
    precio o la cantidad en negativo. None si no lo es."""
    if not _texto_ia(linea.get("descripcion")):
        return None
    precio, cantidad = linea.get("precio_unitario"), linea.get("cantidad")
    precio_negativo, cantidad_negativa = _negativo(precio), _negativo(cantidad)
    if not (precio_negativo or cantidad_negativa):
        return None
    precio = precio_negativo or _numero_ia(precio, 4) or Decimal(0)
    cantidad = cantidad_negativa or _numero_ia(cantidad, 3) or Decimal(1)
    return precio * cantidad or None


def _lecturas_sin_revisar(oferta: Oferta) -> list[dict]:
    revisadas = (oferta.datos_ia or {}).get("lecturas_revisadas", 0)
    return _lecturas(oferta)[revisadas if isinstance(revisadas, int) else 0 :]


def _avisos_descuentos(oferta: Oferta) -> list[str]:
    lista = []
    for lectura in _lecturas_sin_revisar(oferta):
        lineas = ia.claves(lectura).get("lineas")
        for linea in lineas if isinstance(lineas, list) else []:
            linea = ia.claves(linea)
            if total := _descuento(linea):
                lista.append(
                    f"La oferta trae un descuento, «{_texto_ia(linea.get('descripcion'))}» "
                    f"(−{_importe(total)}). Las líneas no pueden ser negativas (tampoco en "
                    "SAP): repártelo en los precios de las partidas o pide al proveedor los "
                    "precios con el descuento aplicado, y comprueba el importe sin IVA."
                )
    return list(dict.fromkeys(lista))


def _importe_sumado(oferta: Oferta) -> bool:
    """El importe lo puso ReMate con la suma de las partidas (la oferta no daba total), sigue
    siendo ese y la lectura no se ha revisado (no sale con un importe escrito por el
    ingeniero)."""
    datos_ia = oferta.datos_ia or {}
    if datos_ia.get("lecturas_revisadas") or oferta.importe_sin_iva is None:
        return False
    return datos_ia.get("importe_sumado") == str(oferta.importe_sin_iva)


def marca_de_importe_sumado(oferta: Oferta, respuesta: dict) -> dict:
    """{"importe_sumado": …} para `datos_ia` si el importe de la oferta es la suma de las
    partidas porque la IA no daba total; si no, {}."""
    if oferta.importe_sin_iva is None:
        return {}
    if _numero_ia(ia.claves(respuesta).get("importe_sin_iva"), 2) is not None:
        return {}
    return {"importe_sumado": str(oferta.importe_sin_iva)}


def avisos(oferta: Oferta) -> list[str]:
    """Datos que faltan o no cuadran (se recalculan cada vez que se consulta la oferta)."""
    lista = []
    faltan = [
        texto
        for campo, texto in (
            ("moneda", "moneda"),
            ("importe_sin_iva", "importe sin IVA"),
            ("fecha_entrega_estimada", "fecha de entrega"),
        )
        if getattr(oferta, campo) is None
    ]
    if faltan:
        lista.append("Falta: " + ", ".join(faltan) + ".")
    if moneda_supuesta(oferta):
        lista.append("La IA no ha visto la moneda de la oferta: se ha puesto EUR. Compruébalo.")
    if not oferta.revisada:
        # Se recalculan desde la lectura guardada: si no, se perderían al recargar.
        lista += _avisos_descuentos(oferta)
        if _importe_sumado(oferta):
            lista.append(
                "La oferta no da el importe total: se ha puesto la suma de las partidas "
                f"({_importe(oferta.importe_sin_iva)}). Compruébalo."
            )
    lista += _fechas_raras(oferta)
    if oferta.lineas and oferta.importe_sin_iva is not None:
        suma = sum((linea.cantidad * linea.precio_unitario for linea in oferta.lineas), Decimal(0))
        if abs(suma - oferta.importe_sin_iva) > Decimal("0.01"):
            lista.append(
                f"La suma de las líneas ({_importe(suma)}) no coincide con el importe sin IVA "
                f"({_importe(oferta.importe_sin_iva)})."
            )
    return lista


# Lo que se le puede pedir al proveedor; también se le dice a la IA al leer su respuesta.
def que_falta(oferta: Oferta) -> list[str]:
    """Lo que falta en la oferta, dicho como se le pide al proveedor. Vacío si la IA aún no la
    ha leído: sin analizar, que falte todo es lo normal."""
    if pendiente_de_ia(oferta):
        return []
    faltan = []
    if oferta.importe_sin_iva is None:
        faltan.append("El importe total sin IVA")
    if moneda_supuesta(oferta):
        faltan.append("La moneda de los precios")
    if oferta.fecha_entrega_estimada is None and not oferta.plazo_entrega_texto:
        faltan.append("El plazo o la fecha de entrega")
    if not oferta.condiciones_pago:
        faltan.append("Las condiciones de pago")
    if not oferta.lineas:
        faltan.append("El desglose por partidas (cantidad y precio unitario de cada una)")
    faltan.extend(
        c["nombre"]
        for c in condiciones.en_orden(oferta.condiciones)
        if c["estado"] == condiciones.SIN_ESPECIFICAR
    )
    return faltan


# --- Acciones --------------------------------------------------------------------------------


def _necesidad_con_ofertas(sesion: Session, necesidad_id: int) -> Necesidad | None:
    # Bloqueo de la fila: dos peticiones a la vez no pueden pisarse el estado.
    necesidad = sesion.get(Necesidad, necesidad_id, with_for_update=True, populate_existing=True)
    if necesidad is not None and necesidad.estado not in ESTADOS_CON_OFERTAS:
        raise TransicionNoPermitida(
            "Las ofertas solo se gestionan en «En cotización» o «En evaluación»."
        )
    return necesidad


def vigentes(sesion: Session, necesidad_id: int) -> list[Oferta]:
    consulta = (
        select(Oferta)
        .where(Oferta.necesidad_id == necesidad_id, Oferta.estado_oferta == "vigente")
        .order_by(Oferta.id)
    )
    return list(sesion.scalars(consulta))


# Correos públicos: con ellos el dominio no dice de qué empresa es nadie (lista fija, sin
# consultar listas externas).
CORREOS_PUBLICOS = frozenset(
    {
        "gmail.com", "googlemail.com", "outlook.com", "outlook.es", "hotmail.com", "hotmail.es",
        "live.com", "live.es", "msn.com", "yahoo.com", "yahoo.es", "icloud.com", "me.com",
        "aol.com", "gmx.com", "gmx.es", "gmx.de", "web.de", "proton.me", "protonmail.com",
        "zoho.com", "yandex.com", "mail.com", "telefonica.net", "movistar.es",
    }
)  # fmt: skip


def _dominio(email: str | None) -> str:
    return (email or "").rsplit("@", 1)[-1].strip().lower() if "@" in (email or "") else ""


def mismo_dominio(a: str | None, b: str | None) -> bool:
    """Los dos correos son de la misma empresa: el mismo dominio o uno es subdominio del otro
    (`ventas.acme.es` y `acme.es`). Nunca con un correo público (gmail, outlook…)."""
    da, db = _dominio(a), _dominio(b)
    if not da or not db or da in CORREOS_PUBLICOS or db in CORREOS_PUBLICOS:
        return False
    return da == db or da.endswith(f".{db}") or db.endswith(f".{da}")


def reconocer_proveedor(
    sesion: Session, remitente: str | None, solicitados: set[int]
) -> tuple[Proveedor | None, str | None]:
    """Proveedor activo del remitente: primero el mismo correo y, si no, el mismo dominio. Con
    varios del mismo dominio, el que estaba entre los solicitados. Devuelve (proveedor, None) o
    (None, motivo para pedir que se elija)."""
    activos = list(sesion.scalars(select(Proveedor).where(Proveedor.activo.is_(True))))
    exactos = [p for p in activos if remitente and p.email.lower() == remitente.lower()]
    if exactos:
        return exactos[0], None
    candidatos = [p for p in activos if mismo_dominio(p.email, remitente)]
    if len(candidatos) > 1:
        candidatos = [p for p in candidatos if p.id in solicitados] or candidatos
    if len(candidatos) == 1:
        return candidatos[0], None
    quien = f" ({remitente})" if remitente else ""
    if candidatos:
        return None, (
            f"Hay varios proveedores con el dominio del remitente{quien}. Elígelo de la lista."
        )
    return None, f"No se ha reconocido al proveedor por el remitente{quien}. Elígelo de la lista."


def destinatarios(oferta: Oferta) -> list[str]:
    """«Para» de los correos al proveedor (adjudicación, pedido): su correo de la lista y, si la
    oferta la envió otra persona de la misma empresa, también ella."""
    propio, remitente = oferta.proveedor.email, oferta.remitente
    otro = remitente and remitente.lower() != propio.lower() and mismo_dominio(remitente, propio)
    return [propio, remitente] if otro else [propio]


def _proveedor(
    sesion: Session, proveedor_id: int | None, remitente: str | None, solicitados: set[int]
) -> Proveedor:
    if proveedor_id:
        proveedor = sesion.get(Proveedor, proveedor_id)
        if proveedor is None or not proveedor.activo:
            raise DatosNoValidos("proveedor_id", "El proveedor no existe o está desactivado.")
        return proveedor
    # Sin proveedor elegido, se busca por el remitente del correo (flujo 4).
    proveedor, motivo = reconocer_proveedor(sesion, remitente, solicitados)
    if proveedor is None:
        raise DatosNoValidos("proveedor_id", motivo)
    return proveedor


def leer_correo(sesion: Session, necesidad_id: int, correo: ArchivoSubido) -> dict | None:
    """Paso previo a subir la oferta: lee el correo sin guardar nada y devuelve sus
    adjuntos y el proveedor que reconoce. None si la necesidad no existe."""
    necesidad = _necesidad_con_ofertas(sesion, necesidad_id)
    if necesidad is None:
        return None
    leido = correos_entrada.leer(correo.nombre, correo.datos)
    solicitados = {s.proveedor_id for s in necesidad.solicitados}
    proveedor, motivo = reconocer_proveedor(sesion, leido.remitente, solicitados)
    return {
        "remitente": leido.remitente,
        "proveedor": proveedor,
        "aviso_proveedor": motivo,
        "adjuntos": [
            {"indice": i, "nombre": a.nombre, "tamano": len(a.datos)}
            for i, a in enumerate(leido.adjuntos)
        ],
    }


def _preparar_subida(
    sesion: Session,
    necesidad: Necesidad,
    proveedor_id: int | None,
    correo: ArchivoSubido | None,
    adjuntos: list[AdjuntoOferta],
    adjuntos_correo: list[tuple[int, str]],
):
    """Comprueba lo que se sube (correo, adjuntos, tipos, tamaños y proveedor), igual para una
    oferta nueva que para los datos que añade el proveedor.
    Devuelve (correo leído, adjuntos que se guardan, proveedor, ids de los solicitados)."""
    if correo is None:
        raise DatosNoValidos("correo", "Sube el correo de la oferta (.eml o .msg).")
    leido = correos_entrada.leer(correo.nombre, correo.datos)
    del_correo = []
    for indice, formato in adjuntos_correo:
        if not 0 <= indice < len(leido.adjuntos):
            raise DatosNoValidos("adjuntos_correo", "Algún adjunto no está en el correo.")
        a = leido.adjuntos[indice]
        del_correo.append(AdjuntoOferta(ArchivoSubido(a.nombre, a.tipo_mime, a.datos), formato))
    adjuntos = [*del_correo, *adjuntos]
    for adjunto in adjuntos:
        if adjunto.formato not in FORMATOS_ADJUNTO:
            raise DatosNoValidos("tipos_adjunto", "Indica el tipo de cada adjunto.")
    for archivo in [correo, *(a.archivo for a in adjuntos)]:
        archivos.comprobar_tamano(archivo.nombre, len(archivo.datos))
    solicitados = {s.proveedor_id for s in necesidad.solicitados}
    proveedor = _proveedor(sesion, proveedor_id, leido.remitente, solicitados)
    return leido, adjuntos, proveedor, solicitados


def _guardar_archivos(
    sesion: Session, raiz_archivos: Path, oferta: Oferta, lista: list[tuple]
) -> list[Adjunto]:
    """Guarda los archivos [(archivo, tipo, formato)] en la carpeta de la oferta y hace commit.
    Si algo falla, no queda nada a medias (ni en la base de datos ni en el disco)."""
    necesidad = oferta.necesidad
    guardados, nuevos = [], []
    try:
        sesion.flush()
        carpeta = f"{necesidad.codigo}/ofertas/{oferta.id}"
        for archivo, tipo, formato in lista:
            ruta = archivos.guardar(raiz_archivos, carpeta, archivo.nombre, archivo.datos)
            guardados.append(ruta)
            adjunto = Adjunto(
                tipo=tipo,
                formato=formato,
                nombre_archivo=archivo.nombre[:255],
                ruta=ruta,
                tipo_mime=archivo.tipo_mime or "application/octet-stream",
                tamano=len(archivo.datos),
            )
            necesidad.adjuntos.append(adjunto)
            oferta.archivos.append(adjunto)
            nuevos.append(adjunto)
        sesion.commit()
    except Exception:
        sesion.rollback()
        for ruta in guardados:
            archivos.borrar(raiz_archivos, ruta)
        raise
    return nuevos


def subir(
    sesion: Session,
    raiz_archivos: Path,
    necesidad_id: int,
    *,
    proveedor_id: int | None,
    correo: ArchivoSubido | None,
    adjuntos: list[AdjuntoOferta] = (),
    adjuntos_correo: list[tuple[int, str]] = (),
    confirmar_sustitucion: bool = False,
) -> tuple[Oferta, list[str]] | None:
    """Guarda una oferta nueva (vigente, sin revisar). `adjuntos_correo`: (índice, formato) de
    los adjuntos del correo que se guardan (los de `leer_correo`). Devuelve (oferta, avisos)."""
    necesidad = _necesidad_con_ofertas(sesion, necesidad_id)
    if necesidad is None:
        return None
    leido, adjuntos, proveedor, solicitados = _preparar_subida(
        sesion, necesidad, proveedor_id, correo, adjuntos, adjuntos_correo
    )

    avisos_subida = []
    if proveedor.id not in solicitados:
        avisos_subida.append(f"{proveedor.nombre} no estaba entre los proveedores solicitados.")
    anteriores = [o for o in vigentes(sesion, necesidad_id) if o.proveedor_id == proveedor.id]
    if anteriores and not confirmar_sustitucion:
        raise OfertaExistente(proveedor)
    for anterior in anteriores:
        anterior.estado_oferta = "sustituida"
    if anteriores:
        avisos_subida.append(f"Sustituye a la oferta anterior de {proveedor.nombre}.")

    oferta = Oferta(
        necesidad=necesidad,
        proveedor=proveedor,
        fecha_correo=leido.fecha,
        remitente=leido.remitente,
        asunto=(leido.asunto or "")[:500] or None,
    )
    sesion.add(oferta)
    _guardar_archivos(
        sesion,
        raiz_archivos,
        oferta,
        [
            (correo, "correo_oferta", None),
            *((a.archivo, "adjunto_oferta", a.formato) for a in adjuntos),
        ],
    )
    return oferta, avisos_subida


def anadir_datos_del_proveedor(
    sesion: Session,
    config: Config,
    raiz_archivos: Path,
    necesidad_id: int,
    *,
    proveedor_id: int | None,
    correo: ArchivoSubido | None,
    adjuntos: list[AdjuntoOferta] = (),
    adjuntos_correo: list[tuple[int, str]] = (),
) -> tuple[Oferta, list[str]] | None:
    """«Añadir datos del proveedor»: la respuesta del proveedor completa su oferta en
    lugar de sustituirla. Sus archivos se guardan en la misma oferta como `respuesta_oferta` y la
    IA lee solo la respuesta, con la lista de lo que faltaba; el código rellena lo que faltaba y
    cambia lo que la respuesta dice distinto, con aviso. Devuelve (oferta, avisos)."""
    necesidad = _necesidad_con_ofertas(sesion, necesidad_id)
    if necesidad is None:
        return None
    _, adjuntos, proveedor, _ = _preparar_subida(
        sesion, necesidad, proveedor_id, correo, adjuntos, adjuntos_correo
    )
    anteriores = [o for o in vigentes(sesion, necesidad_id) if o.proveedor_id == proveedor.id]
    if not anteriores:
        raise DatosNoValidos(
            "proveedor_id",
            f"{proveedor.nombre} no tiene ninguna oferta a la que añadir datos: súbela como "
            "oferta.",
        )
    oferta = anteriores[-1]
    nuevos = _guardar_archivos(
        sesion,
        raiz_archivos,
        oferta,
        [
            (correo, "respuesta_oferta", None),
            *((a.archivo, "respuesta_oferta", a.formato) for a in adjuntos),
        ],
    )
    if pendiente_de_ia(oferta):
        # Sin leer todavía: la IA leerá la oferta y la respuesta juntas al analizar.
        return oferta, [AVISO_RESPUESTA_SIN_LEER]
    return completar_con_respuesta(
        sesion, config, raiz_archivos, necesidad_id, oferta.id, [a.id for a in nuevos]
    )


def oferta_vigente(sesion: Session, necesidad_id: int, oferta_id: int) -> Oferta | None:
    if _necesidad_con_ofertas(sesion, necesidad_id) is None:
        return None
    oferta = sesion.get(Oferta, oferta_id)
    if oferta is None or oferta.necesidad_id != necesidad_id:
        return None
    if oferta.estado_oferta != "vigente":
        raise TransicionNoPermitida("La oferta ya no está vigente (sustituida o borrada).")
    return oferta


def actualizar(
    sesion: Session,
    necesidad_id: int,
    oferta_id: int,
    cambios: dict,
    lineas: list[LineaEntrada] | None = None,
    revisada: bool | None = None,
) -> Oferta | None:
    """Corrige los datos de la oferta. `cambios` solo trae los campos que se quieren cambiar.
    Si la fecha de entrega queda vacía, se calcula con el plazo desde el envío del correo."""
    oferta = oferta_vigente(sesion, necesidad_id, oferta_id)
    if oferta is None:
        return None
    for campo, valor in cambios.items():
        if campo not in CAMPOS_EDITABLES:
            continue
        if campo == "moneda":
            if valor and moneda(valor) is None:
                raise DatosNoValidos("moneda", "La moneda es un código de tres letras (EUR, USD…).")
            valor = moneda(valor)
        if campo == "condiciones":
            # Solo cambian las que se envían; las demás se quedan como estaban.
            valor = condiciones.normalizar({**(oferta.condiciones or {}), **(valor or {})})
        if isinstance(valor, str):
            valor = valor.strip() or None
        if campo == "importe_sin_iva" and valor is not None and valor < 0:
            raise DatosNoValidos(campo, "Los importes no pueden ser negativos.")
        setattr(oferta, campo, valor)
    # Sin fecha (no enviada o enviada vacía), se calcula a partir del plazo si se entiende.
    if oferta.fecha_entrega_estimada is None:
        desde = dia_del_correo(oferta)
        calculada = fecha_desde_semana(oferta.plazo_entrega_texto, desde) or fecha_desde_plazo(
            oferta.plazo_entrega_texto, desde
        )
        if calculada is not None:
            oferta.fecha_entrega_estimada = calculada
    if lineas is not None:
        for linea in lineas:
            if not linea.descripcion.strip():
                raise DatosNoValidos("lineas", "Cada línea necesita una descripción.")
            if linea.cantidad <= 0 or linea.precio_unitario < 0:
                raise DatosNoValidos("lineas", "Revisa las cantidades y los precios de las líneas.")
        oferta.lineas = [
            LineaOferta(
                orden=i,
                descripcion=linea.descripcion.strip(),
                cantidad=linea.cantidad,
                precio_unitario=linea.precio_unitario,
                # Sin fecha, se calcula con el plazo de la línea, como la de la oferta.
                fecha_entrega=linea.fecha_entrega
                or fecha_desde_semana(linea.plazo_entrega_texto, dia_del_correo(oferta))
                or fecha_desde_plazo(linea.plazo_entrega_texto, dia_del_correo(oferta)),
                plazo_entrega_texto=(linea.plazo_entrega_texto or "").strip() or None,
            )
            for i, linea in enumerate(lineas, start=1)
        ]
    faltan = [(c, t) for c, t in OBLIGATORIOS_REVISADA if getattr(oferta, c) is None]
    if revisada:
        if faltan:
            campo, texto = faltan[0]
            raise DatosNoValidos(campo, f"Para darla por revisada, indica {texto}.")
        oferta.revisada = True
        # Lo que avisaban las lecturas ya revisadas (descuentos, importe sumado) no vuelve a
        # salir si la oferta deja de estar revisada.
        oferta.datos_ia = {**(oferta.datos_ia or {}), "lecturas_revisadas": len(_lecturas(oferta))}
    elif revisada is False or faltan or cambios or lineas is not None:
        # Si se borra un dato obligatorio de una oferta revisada, deja de estar revisada
        # (si no, la comparativa y la adjudicación se quedarían sin ese dato). Tampoco sigue
        # revisada si cambia algo sin volver a confirmarlo.
        oferta.revisada = False
    sesion.commit()
    return oferta


def borrar(sesion: Session, necesidad_id: int, oferta_id: int) -> bool:
    """Marca la oferta como borrada (deja de contar). False si no existe."""
    oferta = oferta_vigente(sesion, necesidad_id, oferta_id)
    if oferta is None:
        return False
    oferta.estado_oferta = "borrada"
    sesion.commit()
    return True


# --- Lectura con IA (pasos 3 y 4) ------------------------------------------------------------


def _anadir_archivos(contenido: adjuntos_ia.Contenido, raiz: Path, lista: list[Adjunto]) -> None:
    """Los correos (cabeceras y cuerpo) y los adjuntos, en el orden de subida. La respuesta del
    proveedor es un correo más, con su título."""
    for adjunto in lista:
        try:
            datos = archivos.ruta_absoluta(raiz, adjunto.ruta).read_bytes()
        except OSError:
            contenido.avisos.append(f"No se encuentra el archivo «{adjunto.nombre_archivo}».")
            continue
        es_correo = adjunto.tipo == "correo_oferta" or (
            adjunto.tipo == "respuesta_oferta" and adjunto.formato is None
        )
        if es_correo:
            leido = correos_entrada.leer(adjunto.nombre_archivo, datos)
            fecha = leido.fecha.isoformat() if leido.fecha else "—"
            titulo = (
                "Correo del proveedor"
                if adjunto.tipo == "correo_oferta"
                else ("Respuesta del proveedor con datos que faltaban")
            )
            contenido.texto(
                titulo,
                f"Remitente: {leido.remitente or '—'}\nFecha de envío: {fecha}\n"
                f"Asunto: {leido.asunto or '—'}\n\n{leido.cuerpo or '(sin texto)'}",
            )
        else:
            adjuntos_ia.preparar(contenido, adjunto.nombre_archivo, adjunto.formato, datos)


def _contenido_para_ia(raiz: Path, oferta: Oferta) -> adjuntos_ia.Contenido:
    """Todo lo de la oferta: su correo, sus adjuntos y las respuestas del proveedor."""
    contenido = adjuntos_ia.Contenido()
    # Para elegir la opción que corresponde a lo pedido y avisar de lo que no se oferta.
    necesidad = oferta.necesidad
    contenido.texto(
        "Lo que pidió el cliente (no es parte de la oferta)",
        f"Título: {necesidad.titulo}\nDescripción del ingeniero:\n{necesidad.descripcion}",
    )
    _anadir_archivos(contenido, raiz, oferta.archivos)
    return contenido


def _texto_ia(valor, maximo: int | None = None) -> str | None:
    if isinstance(valor, int | float) and not isinstance(valor, bool):
        valor = str(valor)
    if not isinstance(valor, str) or not valor.strip():
        return None
    return valor.strip()[:maximo] if maximo else valor.strip()


def _numero_ia(valor, decimales: int) -> Decimal | None:
    """Número de la IA (o texto como «1.234,56 €») con `decimales` decimales; None si no vale.
    Las columnas son Numeric(14, decimales): no se admiten negativos ni números que no caben."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int | float):
        texto = str(valor)
    elif isinstance(valor, str):
        texto = re.sub(r"[^\d,.\-]", "", valor)
        if "," in texto and "." in texto:
            # El último separador es el decimal: «1.234,56» o «1,234.56».
            miles = "." if texto.rfind(",") > texto.rfind(".") else ","
            texto = texto.replace(miles, "")
        texto = texto.replace(",", ".")
    else:
        return None
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return None
    if not numero.is_finite() or numero < 0 or numero >= Decimal(10) ** (14 - decimales):
        return None
    return numero.quantize(Decimal(1).scaleb(-decimales), rounding=ROUND_HALF_UP)


def _negativo(valor) -> Decimal | None:
    """El valor absoluto de un precio negativo de la IA (un descuento), o None."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int | float) and valor < 0:
        return _numero_ia(-valor, 4)
    if isinstance(valor, str) and re.match(r"\s*[-−–]", valor):
        return _numero_ia(re.sub(r"[-−–]", "", valor, count=1), 4)
    return None


def _fecha_ia(valor) -> date | None:
    if not isinstance(valor, str):
        return None
    valor = valor.strip()
    try:
        # También «15/12/2026» o «15.12.2026», por si la IA no la da como se le pide.
        if espanola := re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", valor):
            dia, mes, anio = (int(n) for n in espanola.groups())
            return date(anio, mes, dia)
        return date.fromisoformat(valor[:10])
    except ValueError:
        return None


def _lectura(
    oferta: Oferta, respuesta: dict, incompletas: bool = False
) -> tuple[dict, list[LineaOferta], list[str]]:
    """Lo que propone la IA, sin tocar la oferta: (valores por campo, líneas, avisos). La moneda
    va en `valores` solo si la IA da un código claro. El plazo se cuenta desde el correo de la
    oferta (también cuando se lee una respuesta del proveedor)."""
    datos = ia.claves(respuesta)
    avisos_ia = datos.get("avisos") if isinstance(datos.get("avisos"), list) else []
    lista = [f"La IA avisa: {t}" for a in avisos_ia if (t := _texto_ia(a))]
    desde = dia_del_correo(oferta)
    # Plazo de cada línea con fecha calculada (para la fecha general si la oferta no da una).
    lineas, descartadas, plazos_de_lineas, sin_fecha = [], 0, [], []
    for linea in datos.get("lineas") if isinstance(datos.get("lineas"), list) else []:
        linea = ia.claves(linea)
        descripcion = _texto_ia(linea.get("descripcion"))
        cantidad = _numero_ia(linea.get("cantidad"), 3)
        precio = _numero_ia(linea.get("precio_unitario"), 4)
        # En la respuesta del proveedor (`incompletas`) basta la descripción y la cantidad o el
        # precio: puede dar solo el precio nuevo de una partida que ya está en la oferta.
        completa = bool(descripcion) and bool(cantidad) and precio is not None
        util = bool(descripcion) and (bool(cantidad) or precio is not None)
        if _descuento(linea):
            # Ni ReMate ni SAP admiten líneas negativas: no se guarda y `avisos` lo dice con su
            # importe.
            continue
        if not (util if incompletas else completa):
            descartadas += 1
            continue
        # Una fecha concreta manda; si no, el plazo de la línea contado desde el correo.
        # El plazo se guarda para contarlo desde el pedido al adjudicar.
        plazo_linea = _texto_ia(linea.get("plazo_entrega"), 200)
        fecha = _fecha_ia(linea.get("fecha_entrega")) or fecha_desde_semana(plazo_linea, desde)
        if fecha is None and plazo_linea:
            if fecha := fecha_desde_plazo(plazo_linea, desde):
                plazos_de_lineas.append((fecha, plazo_linea))
            else:
                sin_fecha.append(plazo_linea)
                lista.append(
                    f"La partida «{descripcion}» tiene un plazo que no se ha podido pasar a "
                    f"fecha («{plazo_linea}»): pon la fecha a mano."
                )
        lineas.append(
            LineaOferta(
                orden=len(lineas) + 1,
                descripcion=descripcion,
                cantidad=cantidad or None,
                precio_unitario=precio,
                fecha_entrega=fecha,
                plazo_entrega_texto=plazo_linea,
            )
        )
    if descartadas:
        lista.append(
            f"La IA ha leído {descartadas} línea(s) sin descripción, cantidad o precio: "
            "añádelas a mano si hacen falta."
        )
    plazo = _texto_ia(datos.get("plazo_entrega"), 200)
    # Una fecha concreta de la oferta manda; si solo dice un mes, su último viernes; si
    # no, la entrega más tardía entre su plazo (contado desde el envío, paso 4) y las líneas: el
    # pedido no está completo hasta que llega todo. En una respuesta del
    # proveedor (`incompletas`) las líneas pueden ser solo algunas: no cuentan.
    fecha = (
        _fecha_ia(datos.get("fecha_entrega"))
        or fecha_desde_mes(datos.get("mes_entrega"), datos.get("anio_mes_entrega"), desde)
        or fecha_desde_semana(plazo, desde)
    )
    if fecha is None:
        candidatas = [(f, plazo) for f in [fecha_desde_plazo(plazo, desde)] if f]
        if not incompletas:
            candidatas += plazos_de_lineas
            candidatas += [(li.fecha_entrega, None) for li in lineas if li.fecha_entrega]
        if candidatas:
            fecha, de_plazo = max(candidatas, key=lambda c: c[0])
            # Si sale del plazo de una línea, ese es el plazo de la oferta: así se sigue viendo
            # como calculada y al adjudicar se cuenta desde el día del pedido.
            plazo = de_plazo or plazo
        elif not plazo and sin_fecha and not incompletas:
            # Lo que dijo el proveedor no se pierde («KW 48»): el ingeniero pone la fecha (4b).
            plazo = "; ".join(dict.fromkeys(sin_fecha))[:200]
    valores = {
        "moneda": moneda(datos.get("moneda")),
        "numero_oferta": _texto_ia(datos.get("numero_oferta"), 100),
        "importe_sin_iva": _numero_ia(datos.get("importe_sin_iva"), 2),
        "plazo_entrega_texto": plazo,
        "fecha_entrega_estimada": fecha,
        "condiciones_pago": _texto_ia(datos.get("condiciones_pago")),
        "otros": _texto_ia(datos.get("otros")),
        "condiciones": condiciones.normalizar(datos.get("condiciones")),
    }
    # Sin total en la oferta (solo el de cada línea), la suma de las
    # partidas: si no, se le pediría al proveedor un dato que ya está. No en una
    # respuesta del proveedor, que puede traer solo algunas.
    if valores["importe_sin_iva"] is None and lineas and not incompletas:
        suma = _suma_lineas(lineas)
        if suma < Decimal(10) ** 12:
            # `avisos` lo dice mientras no se revise (`_importe_sumado`).
            valores["importe_sin_iva"] = suma
    # El proveedor lo elige el ingeniero o sale del remitente; la IA solo sirve para comprobarlo.
    proveedor = ia.claves(datos.get("proveedor"))
    email = _texto_ia(proveedor.get("email"))
    # Otra persona de la misma empresa (mismo dominio o subdominio) no es otro proveedor.
    conocidos = {_dominio(oferta.proveedor.email), _dominio(oferta.remitente)}
    if email and not (
        _dominio(email) in conocidos
        or mismo_dominio(email, oferta.proveedor.email)
        or mismo_dominio(email, oferta.remitente)
    ):
        nombre = _texto_ia(proveedor.get("nombre")) or email
        lista.append(
            f"La IA lee que la oferta es de «{nombre}» ({email}): comprueba que es de "
            f"{oferta.proveedor.nombre}."
        )
    return valores, lineas, lista


def _aplicar_lectura(oferta: Oferta, respuesta: dict, modelo: str) -> list[str]:
    """Sustituye los datos de la oferta por los que propone la IA. Devuelve los avisos."""
    valores, lineas, lista = _lectura(oferta, respuesta)
    # Si la IA no da un código claro, se pone EUR, la moneda por defecto, y se avisa (ADR 0010).
    valores["moneda"] = valores["moneda"] or "EUR"
    for campo, valor in valores.items():
        setattr(oferta, campo, valor)
    oferta.lineas = lineas
    oferta.revisada = False
    # Las respuestas del proveedor ya leídas se conservan.
    anteriores = (oferta.datos_ia or {}).get("respuestas", [])
    oferta.datos_ia = {
        "modelo": modelo,
        "respuesta": respuesta,
        "avisos": lista,
        **marca_de_importe_sumado(oferta, respuesta),
    }
    if anteriores:
        oferta.datos_ia["respuestas"] = anteriores
    return lista


def _importe(valor: Decimal) -> str:
    """4720 → «4.720,00», como en la pantalla (no «4720.00»)."""
    texto = f"{valor.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP):,.4f}"
    entero, decimales = texto.split(".")
    decimales = decimales.rstrip("0").ljust(2, "0")
    return f"{entero}.{decimales}".translate(str.maketrans(",.", ".,"))


def pendiente_de_ia(oferta: Oferta) -> bool:
    """Ni la ha leído la IA ni tiene datos escritos a mano: la lee «Analizar y comparar». Así no
    se pierde nada que haya escrito el ingeniero (por ejemplo, tras un fallo de la IA)."""
    return (
        oferta.datos_ia is None
        and not oferta.revisada
        and not oferta.lineas
        # La moneda solo cuenta si no es la de por defecto (EUR, ADR 0010): una escrita a mano no
        # se pisa.
        and oferta.moneda in (None, "EUR")
        and all(getattr(oferta, campo) is None for campo in CAMPOS_EDITABLES if campo != "moneda")
    )


def _leer(config: Config, contenido: adjuntos_ia.Contenido) -> tuple[dict | None, list[str]]:
    try:
        return ia.leer_oferta(config, contenido.partes), []
    except ia.ErrorIA as error:
        return None, [f"La IA no ha leído la oferta: {error} {AVISO_REANALIZAR}"]
    except Exception:
        # Un fallo inesperado con una oferta no puede tirar las demás lecturas (CU-004, 3a).
        log.exception("Fallo inesperado al leer una oferta con la IA")
        return None, [f"La IA no ha leído la oferta. {AVISO_REANALIZAR}"]


def _datos_editables(oferta: Oferta) -> tuple:
    """Lo que el ingeniero puede corregir, para saber si ha cambiado mientras leía la IA."""
    lineas = [
        (li.descripcion, li.cantidad, li.precio_unitario, li.fecha_entrega) for li in oferta.lineas
    ]
    return tuple(getattr(oferta, c) for c in CAMPOS_EDITABLES), oferta.revisada, lineas


def analizar(
    sesion: Session, config: Config, raiz_archivos: Path, necesidad_id: int, oferta_id: int
) -> tuple[Oferta, list[str]] | None:
    """Pasos 3 y 4 con una oferta («Reanalizar con IA»): la IA lee el correo y los adjuntos, y sus
    datos sustituyen a los que hubiera (la oferta queda sin revisar). Si la IA falla, los datos no
    cambian y se avisa (flujo 3a). Devuelve (oferta, avisos)."""
    oferta = oferta_vigente(sesion, necesidad_id, oferta_id)
    if oferta is None:
        return None
    contenido = _contenido_para_ia(raiz_archivos, oferta)
    antes = _datos_editables(oferta)
    # La IA puede tardar un minuto: mientras, no se bloquea la necesidad.
    sesion.rollback()
    datos, avisos_lectura = _leer(config, contenido)
    # Se vuelve a comprobar: la oferta puede haberse borrado o sustituido mientras tanto.
    oferta = oferta_vigente(sesion, necesidad_id, oferta_id)
    if oferta is None:
        return None
    if datos is not None and _datos_editables(oferta) != antes:
        # Alguien la ha corregido mientras leía la IA: eso no se pisa.
        sesion.commit()
        avisos_lectura = [
            "La oferta ha cambiado mientras la leía la IA: se quedan los datos corregidos. "
            "Pulsa «Reanalizar con IA» si quieres sustituirlos."
        ]
    elif datos is not None:
        try:
            avisos_lectura = _aplicar_lectura(oferta, datos, ia.modelo_usado(config))
            sesion.commit()
        except SQLAlchemyError, ValueError:
            # Como en «Analizar y comparar»: los datos no cambian y se avisa.
            sesion.rollback()
            log.exception("No se ha podido guardar la lectura de una oferta")
            avisos_lectura = [f"No se ha podido guardar lo que ha leído la IA. {AVISO_REANALIZAR}"]
            oferta = oferta_vigente(sesion, necesidad_id, oferta_id)
            if oferta is None:
                return None
    else:
        sesion.commit()
    return oferta, [*contenido.avisos, *avisos_lectura]


AVISO_RESPUESTA_SIN_LEER = (
    "Se han añadido los datos del proveedor. La IA los leerá junto con la oferta al pulsar "
    "«Analizar y comparar»."
)
ETIQUETAS_CAMPOS = {
    "moneda": "moneda",
    "numero_oferta": "número de oferta",
    "importe_sin_iva": "importe sin IVA",
    "plazo_entrega_texto": "plazo de entrega",
    "fecha_entrega_estimada": "fecha de entrega",
    "condiciones_pago": "condiciones de pago",
    "otros": "información adicional",
}


def _como_texto(valor) -> str:
    if isinstance(valor, Decimal):
        return _importe(valor)
    if isinstance(valor, date):
        return f"{valor:%d/%m/%Y}"
    return str(valor)


def _clave_linea(descripcion: str) -> str:
    return " ".join(descripcion.lower().split())


def _suma_lineas(lineas: list[LineaOferta]) -> Decimal:
    """Suma de las partidas, redondeada a céntimos como el importe sin IVA."""
    suma = sum((li.cantidad * li.precio_unitario for li in lineas), Decimal(0))
    return suma.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _completa(linea: LineaOferta) -> bool:
    return linea.cantidad is not None and linea.precio_unitario is not None


def _pares_de_lineas(
    actuales: list[LineaOferta], nuevas: list[LineaOferta]
) -> list[tuple[LineaOferta | None, LineaOferta]] | None:
    """Empareja cada partida de la respuesta con una de la oferta (None si es nueva). Por la
    descripción (sin mayúsculas ni espacios de más); si no se reconoce ninguna y son tantas como
    las de la oferta, por su orden. Con descripciones repetidas (en la oferta o en la respuesta)
    no se sabe cuál es cuál: por su orden si son tantas; si no, None (no se tocan)."""
    claves_actuales = [_clave_linea(li.descripcion) for li in actuales]
    claves_nuevas = [_clave_linea(li.descripcion) for li in nuevas]
    repetidas = len(set(claves_actuales)) < len(actuales) or len(set(claves_nuevas)) < len(nuevas)
    if repetidas:
        return list(zip(actuales, nuevas, strict=True)) if len(nuevas) == len(actuales) else None
    porclave = dict(zip(claves_actuales, actuales, strict=True))
    pares = [(porclave.get(c), n) for c, n in zip(claves_nuevas, nuevas, strict=True)]
    if all(actual is None for actual, _ in pares) and len(nuevas) == len(actuales):
        return list(zip(actuales, nuevas, strict=True))
    return pares


def _juntar_lineas(
    oferta: Oferta, lineas: list[LineaOferta], completados: list[str], cambiados: list[str]
) -> list[str]:
    """Partidas de la respuesta del proveedor: mandan sobre las de la oferta. Las
    reconocidas (`_pares_de_lineas`) cambian su cantidad, precio y fecha si la respuesta los da;
    las que no se reconocen se añaden si traen cantidad y precio;
    las que la respuesta no nombra se quedan. Devuelve los avisos de lo que no se ha cambiado."""
    sin_cambiar = []
    if not lineas:
        return sin_cambiar
    if not oferta.lineas:
        completas = [li for li in lineas if _completa(li)]
        for i, linea in enumerate(completas, start=1):
            linea.orden = i
        if completas:
            oferta.lineas = completas
            completados.append("partidas")
        sin_cambiar += [_aviso_incompleta(li) for li in lineas if not _completa(li)]
        return sin_cambiar
    pares = _pares_de_lineas(oferta.lineas, lineas)
    if pares is None:
        return [
            "partidas: hay descripciones repetidas y la respuesta trae otro número de partidas, "
            "así que no se sabe cuál es cuál; no se han cambiado"
        ]
    for actual, nueva in pares:
        if actual is None:
            if not _completa(nueva):
                sin_cambiar.append(_aviso_incompleta(nueva))
                continue
            nueva.orden = max(li.orden for li in oferta.lineas) + 1
            oferta.lineas.append(nueva)
            cambiados.append(
                f"partida nueva «{nueva.descripcion}» (comprueba que no es una de las que ya "
                "había con otro nombre)"
            )
            continue
        for campo, etiqueta in (
            ("cantidad", "cantidad"),
            ("precio_unitario", "precio unitario"),
            ("fecha_entrega", "fecha de entrega"),
        ):
            antes, despues = getattr(actual, campo), getattr(nueva, campo)
            if despues is None or despues == antes:
                continue
            setattr(actual, campo, despues)
            cambiados.append(
                f"partida «{actual.descripcion}», {etiqueta}: "
                f"{_como_texto(antes) if antes is not None else '—'} → {_como_texto(despues)}"
            )
        # El plazo va con su fecha: si la respuesta da uno nuevo, al adjudicar se cuenta ese.
        if nueva.plazo_entrega_texto and nueva.fecha_entrega is not None:
            actual.plazo_entrega_texto = nueva.plazo_entrega_texto
    return sin_cambiar


def _aviso_incompleta(linea: LineaOferta) -> str:
    return (
        f"partida «{linea.descripcion}»: la respuesta la trae sin cantidad o sin precio y no está "
        "en la oferta; añádela a mano si hace falta"
    )


def _completar(oferta: Oferta, respuesta: dict, modelo: str) -> list[str]:
    """Junta la respuesta del proveedor con su oferta. La respuesta manda: rellena lo que
    faltaba y cambia lo que ya tenía valor, también los precios y las cantidades de las
    partidas, y avisa de cada cambio. Lo que la respuesta no dice se queda como estaba. La
    oferta vuelve a «Sin revisar»."""
    valores, lineas, avisos = _lectura(oferta, respuesta, incompletas=True)
    supuesta = moneda_supuesta(oferta)
    completados, cambiados = [], []
    importe_era_la_suma = (
        bool(oferta.lineas)
        and oferta.importe_sin_iva is not None
        and oferta.importe_sin_iva == _suma_lineas(oferta.lineas)
    )
    nuevas_condiciones = valores.pop("condiciones")
    for campo, nuevo in valores.items():
        actual = None if campo == "moneda" and supuesta else getattr(oferta, campo)
        if nuevo is None or nuevo == actual:
            continue
        setattr(oferta, campo, nuevo)
        if actual is None:
            completados.append(ETIQUETAS_CAMPOS[campo])
        else:
            cambiados.append(
                f"{ETIQUETAS_CAMPOS[campo]}: {_como_texto(actual)} → {_como_texto(nuevo)}"
            )
    actuales = condiciones.normalizar(oferta.condiciones)
    for clave, nombre in condiciones.CONDICIONES:
        actual, nueva = actuales[clave], nuevas_condiciones[clave]
        if nueva["estado"] == condiciones.SIN_ESPECIFICAR or nueva == actual:
            continue
        actuales[clave] = nueva
        if actual["estado"] == condiciones.SIN_ESPECIFICAR:
            completados.append(nombre.lower())
        else:
            cambiados.append(
                f"{nombre}: {condiciones.como_texto(actual)} → {condiciones.como_texto(nueva)}"
            )
    oferta.condiciones = actuales
    sin_cambiar = _juntar_lineas(oferta, lineas, completados, cambiados)
    # Si el importe era la suma de las partidas y la respuesta cambia los precios sin dar otro
    # importe, se recalcula; si no, se queda y el aviso de la suma (`avisos`) lo señala.
    if importe_era_la_suma and valores["importe_sin_iva"] is None:
        suma = _suma_lineas(oferta.lineas)
        if suma != oferta.importe_sin_iva:
            cambiados.append(
                f"importe sin IVA (suma de las partidas): {_como_texto(oferta.importe_sin_iva)} "
                f"→ {_como_texto(suma)}"
            )
            oferta.importe_sin_iva = suma
    oferta.revisada = False
    if completados:
        avisos.insert(0, f"La respuesta del proveedor completa: {', '.join(completados)}.")
    if cambiados:
        avisos.insert(
            1 if completados else 0,
            "La respuesta del proveedor cambia (revísalo): " + "; ".join(cambiados) + ".",
        )
    if not completados and not cambiados:
        avisos.insert(0, "La respuesta del proveedor no trae ningún dato nuevo.")
    if sin_cambiar:
        avisos.append("Sin cambiar: " + "; ".join(sin_cambiar) + ".")
    datos_ia = dict(oferta.datos_ia or {})
    datos_ia["respuestas"] = [
        *datos_ia.get("respuestas", []),
        {"modelo": modelo, "respuesta": respuesta, "avisos": avisos},
    ]
    # El aviso del importe sumado sigue al importe: si la respuesta da el total, ya no es una
    # suma; si se ha vuelto a sumar, la marca es la nueva suma.
    if valores["importe_sin_iva"] is not None:
        datos_ia.pop("importe_sumado", None)
    elif "importe_sumado" in datos_ia and importe_era_la_suma:
        datos_ia["importe_sumado"] = str(oferta.importe_sin_iva)
    oferta.datos_ia = datos_ia
    return avisos


def completar_con_respuesta(
    sesion: Session,
    config: Config,
    raiz_archivos: Path,
    necesidad_id: int,
    oferta_id: int,
    archivo_ids: list[int],
) -> tuple[Oferta, list[str]] | None:
    """La IA lee solo los archivos de la respuesta (`archivo_ids`), con la lista de lo que
    faltaba, y el código los junta con la oferta. Si la IA falla, los archivos se quedan en la
    oferta y se avisa. Como «Reanalizar»: no se bloquea la necesidad mientras lee la IA."""
    oferta = oferta_vigente(sesion, necesidad_id, oferta_id)
    if oferta is None:
        return None
    contenido = adjuntos_ia.Contenido()
    faltaban = que_falta(oferta)
    contenido.texto(
        "Lo que se le pidió al proveedor",
        "Esto es la respuesta del proveedor a la petición de los datos que faltaban en su "
        "oferta. Extrae solo lo que diga la respuesta; lo que no diga, null o «no_especificado». "
        "Se le pidió:\n" + ("\n".join(f"- {f}" for f in faltaban) or "(nada en concreto)"),
    )
    _anadir_archivos(contenido, raiz_archivos, [a for a in oferta.archivos if a.id in archivo_ids])
    antes = _datos_editables(oferta)
    sesion.rollback()
    datos, avisos_lectura = _leer(config, contenido)
    oferta = oferta_vigente(sesion, necesidad_id, oferta_id)
    if oferta is None:
        return None
    if datos is None:
        sesion.commit()
        return oferta, [
            *contenido.avisos,
            "Los datos del proveedor se han añadido a la oferta, pero la IA no los ha leído: "
            "complétala a mano o pulsa «Reanalizar con IA».",
        ]
    if _datos_editables(oferta) != antes:
        sesion.commit()
        return oferta, [
            "La oferta ha cambiado mientras la IA leía la respuesta: no se ha completado. Pulsa "
            "«Reanalizar con IA» para leer la oferta y la respuesta juntas."
        ]
    try:
        avisos_lectura = _completar(oferta, datos, ia.modelo_usado(config))
        sesion.commit()
    except SQLAlchemyError, ValueError:
        sesion.rollback()
        log.exception("No se ha podido guardar la lectura de la respuesta del proveedor")
        avisos_lectura = [f"No se ha podido guardar lo que ha leído la IA. {AVISO_REANALIZAR}"]
        oferta = oferta_vigente(sesion, necesidad_id, oferta_id)
        if oferta is None:
            return None
    return oferta, [*contenido.avisos, *avisos_lectura]


def analizar_pendientes(
    sesion: Session, config: Config, raiz_archivos: Path, necesidad_id: int
) -> list[str]:
    """Pasos 3 y 4 con todas las ofertas a la vez: la IA lee las que
    siguen pendientes (`pendiente_de_ia`), varias a la vez, para que el ingeniero espere lo que
    tarde la más lenta y no la suma. Devuelve los avisos, cada uno con su proveedor. Solo la
    llama «Analizar y comparar», que ya ha comprobado que la necesidad existe."""
    _necesidad_con_ofertas(sesion, necesidad_id)
    pendientes = [
        (o.id, o.proveedor.nombre, _contenido_para_ia(raiz_archivos, o))
        for o in vigentes(sesion, necesidad_id)
        if pendiente_de_ia(o)
    ]
    # Mientras responde la IA, no se bloquea la necesidad.
    sesion.rollback()
    if not pendientes:
        return []
    with ThreadPoolExecutor(max_workers=min(LECTURAS_A_LA_VEZ, len(pendientes))) as grupo:
        leidas = list(grupo.map(lambda pendiente: _leer(config, pendiente[2]), pendientes))
    avisos_lectura = []
    for (oferta_id, nombre, contenido), (datos, avisos_oferta) in zip(
        pendientes, leidas, strict=True
    ):
        try:
            oferta = oferta_vigente(sesion, necesidad_id, oferta_id)
        except TransicionNoPermitida:
            oferta = None  # borrada o sustituida mientras la leía la IA
        if oferta is None or not pendiente_de_ia(oferta):
            # También si mientras tanto se ha escrito algo a mano: eso no se pisa.
            sesion.rollback()
            continue
        if datos is not None:
            try:
                avisos_oferta = _aplicar_lectura(oferta, datos, ia.modelo_usado(config))
                sesion.commit()
            except SQLAlchemyError, ValueError:
                # Si no se puede guardar una lectura, las demás sí se guardan. La oferta sigue
                # pendiente.
                sesion.rollback()
                log.exception("No se ha podido guardar la lectura de una oferta")
                avisos_oferta = [
                    f"No se ha podido guardar lo que ha leído la IA. {AVISO_REANALIZAR}"
                ]
        avisos_lectura += [f"{nombre}: {a}" for a in [*contenido.avisos, *avisos_oferta]]
    return avisos_lectura


def pasar_a_evaluacion(
    sesion: Session, necesidad_id: int, peticionario_id: int | None
) -> Necesidad | None:
    necesidad = necesidad_en(sesion, necesidad_id, "en_cotizacion", bloquear=True)
    if necesidad is None:
        return None
    peticionario = peticionario_activo(sesion, peticionario_id, "Elige quién pasa a evaluación.")
    if not vigentes(sesion, necesidad_id):
        raise TransicionNoPermitida("Sin ofertas no se puede pasar a evaluación.")
    necesidad.historial.append(
        CambioEstado(
            estado_anterior=necesidad.estado,
            estado_nuevo="en_evaluacion",
            peticionario=peticionario,
        )
    )
    necesidad.estado = "en_evaluacion"
    sesion.commit()
    return necesidad


def comparativa(sesion: Session, necesidad_id: int, solo_revisadas: bool = False) -> list[Oferta]:
    """Ofertas vigentes con datos (leídos por la IA o escritos a mano), de la más barata (sin IVA)
    a la más cara; las que no tienen importe, al final. La comparativa sale
    al analizar, antes de revisar: las sin revisar se marcan y no se pueden adjudicar.
    `solo_revisadas`: solo las revisadas con importe (contexto de la adjudicación, CU-005)."""
    if solo_revisadas:
        con_datos = [
            o
            for o in vigentes(sesion, necesidad_id)
            if o.revisada and o.importe_sin_iva is not None
        ]
    else:
        con_datos = [o for o in vigentes(sesion, necesidad_id) if not pendiente_de_ia(o)]
    return sorted(
        con_datos, key=lambda o: (o.importe_sin_iva is None, o.importe_sin_iva or 0, o.id)
    )
