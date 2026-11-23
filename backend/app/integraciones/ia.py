"""Cliente de IA con la API de OpenAI (Responses API; ADR 0011).

La IA lee las ofertas (CU-004: el correo del proveedor y sus adjuntos) y redacta los textos que
el ingeniero revisa: la parte central del correo de petición (CU-002) y la descripción para SAP
con el resumen del correo de adjudicación (CU-005). La comparativa la calcula el código.

La respuesta se pide con un esquema JSON estricto (salidas estructuradas): siempre trae todos los
campos, con null si no aparecen. Cualquier fallo (sin configurar, red, tiempo de espera,
respuesta cortada o no válida) se convierte en `ErrorIA`, y la oferta se completa a mano.

Datos que se envían: solo los que necesita cada tarea (las ofertas de los proveedores, la
necesidad y, al adjudicar, los comentarios de entregas anteriores). Con `store=False`, OpenAI
no guarda la respuesta para reutilizarla.
"""

import json
import logging
import math
import threading

from openai import APIConnectionError, InternalServerError, OpenAI, OpenAIError

from app.config import Config
from app.servicios.condiciones import CONDICIONES, ESTADOS

log = logging.getLogger(__name__)
# Segundos por intento: leer un PDF o una imagen tarda más que un texto, y una oferta de muchas
# líneas da una respuesta larga.
TIEMPO_OFERTA = 120
INTENTOS = 2  # el segundo, solo si falla la conexión o el servidor de OpenAI
# Llamadas a la API a la vez en toda la aplicación y cuánto se espera turno. Sin login,
# cualquiera de la red podría lanzar llamadas de pago sin límite y ocupar los hilos de Waitress.
# 8: dos «Analizar y comparar» a la vez (4 lecturas
# cada uno); app/servir.py usa 16 hilos, así que siempre quedan libres para el resto.
LLAMADAS_A_LA_VEZ = 8
# Espera corta: con 30 s, los hilos que esperan turno dejarían sin atender al resto.
ESPERA_TURNO = 2  # segundos
_turnos = threading.BoundedSemaphore(LLAMADAS_A_LA_VEZ)
# Incluye el razonamiento (documentación de OpenAI, guía «Reasoning»). Una oferta normal ocupa
# bastante menos; si se pasa, la respuesta llega cortada y no se repite (se pagaría otra vez).
# Solo se paga lo que se usa: con 4.000, una oferta de 80-100 líneas (tornillería, recambios) no
# cabía y no se leía nada.
MAXIMO_SALIDA = 16_000


class ErrorIA(RuntimeError):
    """OpenAI no está configurado, no responde o su respuesta no sirve."""


class IAOcupada(ErrorIA):
    """Ya hay LLAMADAS_A_LA_VEZ llamadas en curso: basta con esperar un momento."""


def aviso_sin_ia(error: ErrorIA, por_defecto: str) -> str:
    """El aviso de cada pantalla cuando falla la IA; si solo estaba ocupada, se dice delante,
    para que se sepa que basta con repetir en un momento."""
    return f"{error} {por_defecto}" if isinstance(error, IAOcupada) else por_defecto


def _cliente(config: Config) -> OpenAI:
    if not (config.ia_api_key and config.ia_modelo):
        raise ErrorIA("La IA no está configurada (IA_API_KEY o IA_MODELO).")
    # Los reintentos los hace _pedir_json, solo cuando tiene sentido.
    return OpenAI(api_key=config.ia_api_key, timeout=TIEMPO_OFERTA, max_retries=0)


def _registrar_uso(respuesta, etiqueta: str) -> None:
    """Deja en el registro los tokens de cada llamada, para medir el consumo (nunca el contenido
    de la oferta ni la respuesta)."""
    uso = getattr(respuesta, "usage", None)
    if uso is None:
        return
    cache = getattr(getattr(uso, "input_tokens_details", None), "cached_tokens", 0) or 0
    razonamiento = getattr(getattr(uso, "output_tokens_details", None), "reasoning_tokens", 0) or 0
    log.info(
        "OpenAI %s: entrada=%s, salida=%s, caché=%s, razonamiento=%s tokens",
        etiqueta,
        getattr(uso, "input_tokens", 0) or 0,
        getattr(uso, "output_tokens", 0) or 0,
        cache,
        razonamiento,
    )


def instrucciones(texto: str, config: Config) -> str:
    """Las instrucciones con el nombre de la empresa (EMPRESA_NOMBRE) o, si está vacío, «la
    empresa»."""
    return texto.replace("<EMPRESA>", config.empresa_nombre or "la empresa")


def _una_peticion(cliente: OpenAI, config: Config, tarea: dict, partes: list[dict]) -> dict:
    modelo = config.ia_modelo
    respuesta = cliente.responses.create(
        model=modelo,
        instructions=instrucciones(tarea["instrucciones"], config),
        input=[{"role": "user", "content": partes}],
        text={"format": tarea["formato"]},
        # Poco razonamiento («low» por defecto, IA_RAZONAMIENTO): leer un documento o redactar un
        # texto corto no necesita mucho y se paga como salida.
        reasoning={"effort": config.ia_razonamiento},
        max_output_tokens=MAXIMO_SALIDA,
        store=False,
        timeout=TIEMPO_OFERTA,
    )
    # Con la tarea y el nivel de razonamiento, para comparar el consumo en la tabla `logs`.
    _registrar_uso(
        respuesta, f"{modelo}, razonamiento {config.ia_razonamiento}, {tarea['formato']['name']}"
    )
    if getattr(respuesta, "status", None) == "incomplete":
        motivo = getattr(getattr(respuesta, "incomplete_details", None), "reason", None)
        log.warning("OpenAI ha dejado la respuesta a medias: %s", motivo)
        raise ErrorIA("La respuesta de la IA ha quedado cortada (el texto es muy largo).")
    return _json_de(respuesta.output_text or "")


def _pedir_json(config: Config, tarea: dict, contenido: str | list[dict]) -> dict:
    """Pide la respuesta. `tarea`: {instrucciones, formato}; `contenido`, texto o partes (texto,
    archivos e imágenes). Solo se repite si falla la conexión o el servidor de OpenAI: una
    respuesta que no sirve volvería a salir igual y se pagaría dos veces."""
    if isinstance(contenido, str):
        contenido = [{"type": "input_text", "text": contenido}]
    if not _turnos.acquire(timeout=ESPERA_TURNO):
        log.warning("OpenAI: demasiadas llamadas a la vez; no se ha llamado")
        raise IAOcupada(
            "La IA está atendiendo muchas peticiones a la vez: inténtalo en un momento."
        )
    try:
        return _pedir_con_turno(config, tarea, contenido)
    finally:
        _turnos.release()


def _pedir_con_turno(config: Config, tarea: dict, contenido: list[dict]) -> dict:
    cliente = _cliente(config)
    for intento in range(1, INTENTOS + 1):
        try:
            return _una_peticion(cliente, config, tarea, contenido)
        except (APIConnectionError, InternalServerError) as error:
            log.warning("OpenAI no responde (intento %s): %s", intento, type(error).__name__)
            if intento == INTENTOS:
                raise ErrorIA("La IA no ha respondido.") from error
        except (OpenAIError, AttributeError, TypeError) as error:
            # Clave no válida, sin saldo, límite de uso, petición rechazada…: solo el tipo.
            log.warning("OpenAI ha fallado: %s", type(error).__name__)
            raise ErrorIA("La IA no ha respondido.") from error
    raise AssertionError("inalcanzable")


def _sin_constantes(nombre: str):
    """NaN e Infinity no son JSON válido para PostgreSQL (JSONB): la respuesta no sirve."""
    raise ValueError(f"Constante no admitida en el JSON: {nombre}")


def _numero_finito(texto: str) -> float | None:
    """1e400 da «inf» al leerlo, y PostgreSQL no lo admite en JSONB: se queda en null."""
    numero = float(texto)
    return numero if math.isfinite(numero) else None


def _json_de(texto: str) -> dict:
    # Por si el modelo envuelve el JSON en un bloque de código ```json … ```.
    texto = texto.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
    # PostgreSQL no admite el carácter NUL en texto ni en JSONB.
    texto = texto.replace("\\u0000", "").replace("\x00", "")
    try:
        datos = json.loads(texto, parse_constant=_sin_constantes, parse_float=_numero_finito)
    except (json.JSONDecodeError, ValueError) as error:
        raise ErrorIA("La IA no ha devuelto un JSON válido.") from error
    if not isinstance(datos, dict):
        raise ErrorIA("La IA no ha devuelto un objeto JSON.")
    return claves(_sin_sustitutos(datos))


def _sin_sustitutos(valor):
    """Quita los caracteres sustitutos sueltos («\\ud800»): JSON los admite, pero PostgreSQL no
    puede guardarlos y fallaría al guardar la oferta."""
    if isinstance(valor, str):
        return valor.encode("utf-8", "replace").decode("utf-8")
    if isinstance(valor, list):
        return [_sin_sustitutos(v) for v in valor]
    if isinstance(valor, dict):
        return {_sin_sustitutos(c): _sin_sustitutos(v) for c, v in valor.items()}
    return valor


# Otras claves que algunos modelos usan en lugar de las pedidas (en inglés o con otra palabra,
# como «detalle» en lugar de «descripcion»). Con el esquema estricto ya no
# deberían llegar, pero las lecturas guardadas antes (`ofertas.datos_ia`) sí las tienen. No se
# pone aquí ninguna clave que ya se pida con otro sentido (como «nombre»).
_SINONIMOS = {
    "currency": "moneda",
    "description": "descripcion",
    "detalle": "descripcion",
    "concepto": "descripcion",
    "articulo": "descripcion",
    "artículo": "descripcion",
    "producto": "descripcion",
    "warnings": "avisos",
    "quantity": "cantidad",
    "unit_price": "precio_unitario",
    "delivery_date": "fecha_entrega",
    # Respuestas con todas las claves en inglés.
    "supplier": "proveedor",
    "name": "nombre",
    "offer_number": "numero_oferta",
    "lines": "lineas",
    "total_without_vat": "importe_sin_iva",
    "delivery_time": "plazo_entrega",
    "payment_terms": "condiciones_pago",
    "others": "otros",
}
# Claves pedidas con guion bajo, por si el modelo lo quita («condicionespago»).
_SIN_GUION = {
    c.replace("_", ""): c
    for c in (
        "precio_unitario",
        "fecha_entrega",
        "importe_sin_iva",
        "plazo_entrega",
        "condiciones_pago",
        "numero_oferta",
    )
}


def claves(datos) -> dict:
    """Arregla las claves de un objeto de la respuesta (« descripcion», «Descripcion»,
    «description», «condicionespago»), que dan algunos modelos. Lo que no es un objeto se queda
    en {}."""
    if not isinstance(datos, dict):
        return {}
    normalizadas = [(str(clave).strip().lower().replace(" ", "_"), v) for clave, v in datos.items()]
    # Primero las claves tal como se piden; las alternativas solo rellenan lo que falte (si llegan
    # «detalle» y «descripcion», vale «descripcion»).
    arregladas = {c: v for c, v in normalizadas if c not in _SINONIMOS and c not in _SIN_GUION}
    for clave, valor in normalizadas:
        clave = _SINONIMOS.get(clave, clave)
        arregladas.setdefault(_SIN_GUION.get(clave, clave), valor)
    return arregladas


def modelo_usado(config: Config) -> str:
    """Nombre que se guarda con la lectura de una oferta (para saber qué la leyó)."""
    return config.ia_modelo


INSTRUCCIONES_OFERTA = """\
Lees ofertas de proveedores para el departamento de ingeniería de <EMPRESA>. Recibes el correo \
del proveedor (remitente, fecha, asunto y cuerpo) y los adjuntos de la oferta. Extrae sus datos; \
el ingeniero los revisará después.

El cliente (<EMPRESA>) es quien pide la oferta: su nombre, dirección, NIF y contacto («ATT:») \
no son datos del proveedor ni de la oferta, ni tampoco el membrete, el pie y los textos legales. \
Un código de 10 cifras en el asunto es la petición del cliente, no el número de oferta.

Antes de la oferta puede venir «Lo que pidió el cliente» (título y descripción de la \
necesidad). No es parte de la oferta: no saques de ahí ningún dato. Úsalo solo para elegir la \
opción que corresponde a lo pedido y para avisar de lo pedido que la oferta no incluye.

Reglas:
- Usa solo el correo y los adjuntos. Si un dato no aparece, pon null; no inventes.
- «moneda»: código ISO de tres letras (EUR, USD, PLN…). Si no consta, es ambigua (como $) o hay \
varias, pon null y avisa. No conviertas importes.
- Importes, precios y cantidades como números, sin símbolo de moneda ni separador de miles. Ojo \
con el formato europeo: «1.250,50 €» es 1250.5 y «1.250 €» es 1250; «12,5» es 12.5.
- Precios unitarios e «importe_sin_iva», siempre sin IVA. Si la oferta solo da importes con IVA, \
pon null y avisa. No calcules importes con IVA.
- «importe_sin_iva»: el total sin IVA que da la oferta; si no lo da, null (no lo sumes tú).
- «precio_unitario» es el de una unidad. Si la oferta da el precio por 100 o por 1000 unidades \
(«4,20 €/100 uds», «precio por mil»), divídelo para dejarlo por unidad y avisa de que lo has \
hecho. Si una línea solo da su total, divídelo entre la cantidad y avisa.
- Un descuento o abono que venga como línea aparte («Descuento 10 %», «Dto. pronto pago») va \
como una línea con su precio unitario en negativo; no lo repartas entre las demás.
- Textos en español, aunque la oferta venga en otro idioma, salvo referencias, códigos y \
nombres propios.
- Fechas como AAAA-MM-DD. «plazo_entrega»: el plazo del proveedor en español («25 working \
days» → «25 días laborables»). Es solo el tiempo de entrega: nunca la validez de la oferta, el \
pago ni la garantía. Si se cuenta desde algo distinto del pedido («desde la aprobación de \
planos»), déjalo en el texto y avisa. «fecha_entrega»: solo si la oferta da una fecha concreta.
- Si cada línea tiene su propio plazo o fecha («18 - 20 días», «5 Sem.»), ponlos en la línea \
(«plazo_entrega» o «fecha_entrega» de la línea; el plazo en español: «5 semanas»). El \
«plazo_entrega» y la «fecha_entrega» generales, solo si la oferta da uno para toda ella; si \
no, null.
- Si la oferta da solo un mes, sin día («entrega en diciembre», «December 2026»): \
«mes_entrega» es su número (1 a 12), «anio_mes_entrega» el año si lo dice (si no, null), \
«fecha_entrega» null y «plazo_entrega» lo que dice, en español («diciembre de 2026»). En los \
demás casos, «mes_entrega» y «anio_mes_entrega» son null. Una semana («semana 50», «KW 50») \
no es un mes: va tal cual en «plazo_entrega».
- Si la oferta trae varias opciones o precios por tramos de cantidad, extrae la que corresponde \
a lo que pidió el cliente (si no se sabe, la principal) y avisa de las demás con sus precios.
- Si el cliente pidió algo que la oferta no incluye o dice que no oferta, avísalo nombrándolo.
- «idioma»: el del texto del proveedor, en código de dos letras («es», «en», «de»…).
- «condiciones»: las nueve condiciones de la tabla, cada una con «estado» y «texto»:
  - «embalaje»; «incoterm» (Incoterm o condiciones y lugar de entrega: «FCA Barcelona»; \
«Material: en sus dependencias» o «entrega en sus instalaciones» quiere decir que se entrega en \
las instalaciones del cliente); «transporte» (portes: quién lo paga o lo organiza; \
«N/Medios» o «por nuestros medios» es el proveedor); «incluye_precio» (qué incluye el \
precio: utillaje, ensayos, certificados…); «validez» (de la oferta); «materia_prima» (solo \
una cláusula de revisión del precio según el coste del material o un recargo por aleación; no \
dónde se entrega el material ni quién lo pone); «utillaje» (su coste, propiedad o \
amortización); «tratamientos» (tratamientos térmicos o recubrimientos); «condiciones_pedido» \
(pedido mínimo, lotes, descuentos por volumen…).
  - Estados: «especificado» (la oferta dice cómo es: pon en «texto» lo que dice), «incluido» \
(está incluido en el precio), «no_incluido» (dice que no está incluido o se cobra aparte), \
«no_aplica» (dice que no aplica a esta compra) y «no_especificado» (no lo dice; «texto» null). \
Con «incluido» o «no_incluido», «texto» solo si añade algo (por ejemplo, el importe aparte).
  - No inventes ni deduzcas: si la oferta no lo dice, «no_especificado». No deduzcas el \
transporte del Incoterm. No cambies el sentido de lo que dice.
  - No repitas aquí el plazo de entrega, las condiciones de pago ni el importe: tienen su campo.
  - «texto» en español y breve, como lo diría la oferta.
- «otros»: información adicional que afecta a la compra y no encaja en ningún otro campo (por \
ejemplo, la garantía), en pocas frases; si no hay, null.
- «avisos»: datos dudosos, ilegibles o contradictorios que el ingeniero debe comprobar. En \
impersonal o tratando de tú al ingeniero («Comprueba…»), nunca en primera persona."""


def _nulo(tipo: str) -> dict:
    return {"type": [tipo, "null"]}


def _formato(nombre: str, propiedades: dict) -> dict:
    """Salida estructurada estricta (guía «Structured outputs» de OpenAI): todos los campos son
    obligatorios y los que pueden faltar admiten null; sin campos de más."""
    return {
        "type": "json_schema",
        "name": nombre,
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": list(propiedades),
            "properties": propiedades,
        },
    }


_AVISOS = {"type": "array", "items": {"type": "string"}}

# Las nueve condiciones de la oferta, de la lista única de `servicios/condiciones.py`.
_UNA_CONDICION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["estado", "texto"],
    "properties": {"estado": {"type": "string", "enum": list(ESTADOS)}, "texto": _nulo("string")},
}
_FORMATO_CONDICIONES = {
    "type": "object",
    "additionalProperties": False,
    "required": [clave for clave, _ in CONDICIONES],
    "properties": {clave: _UNA_CONDICION for clave, _ in CONDICIONES},
}


# Salida estructurada estricta (guía «Structured outputs» de OpenAI): todos los campos son
# obligatorios y los que pueden faltar admiten null; sin campos de más.
FORMATO_OFERTA = {
    "type": "json_schema",
    "name": "oferta",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "moneda", "proveedor", "numero_oferta", "lineas", "importe_sin_iva",
            "plazo_entrega", "fecha_entrega", "mes_entrega", "anio_mes_entrega",
            "condiciones_pago", "condiciones", "otros", "idioma", "avisos",
        ],
        "properties": {
            "moneda": _nulo("string"),
            "proveedor": {
                "type": "object",
                "additionalProperties": False,
                "required": ["nombre", "email"],
                "properties": {"nombre": _nulo("string"), "email": _nulo("string")},
            },
            "numero_oferta": _nulo("string"),
            "lineas": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "descripcion", "cantidad", "precio_unitario", "fecha_entrega",
                        "plazo_entrega",
                    ],
                    "properties": {
                        "descripcion": {"type": "string"},
                        "cantidad": _nulo("number"),
                        "precio_unitario": _nulo("number"),
                        "fecha_entrega": _nulo("string"),
                        # Si la línea da un plazo y no una fecha; el código lo pasa a fecha.
                        "plazo_entrega": _nulo("string"),
                    },
                },
            },
            "importe_sin_iva": _nulo("number"),
            "plazo_entrega": _nulo("string"),
            "fecha_entrega": _nulo("string"),
            # Solo si la oferta da un mes sin día; el código calcula su último viernes.
            "mes_entrega": _nulo("integer"),
            "anio_mes_entrega": _nulo("integer"),
            "condiciones_pago": _nulo("string"),
            "condiciones": _FORMATO_CONDICIONES,
            "otros": _nulo("string"),
            # Para escribir en inglés al proveedor extranjero (petición de datos).
            "idioma": _nulo("string"),
            "avisos": {"type": "array", "items": {"type": "string"}},
        },
    },
}  # fmt: skip


def leer_oferta(config: Config, partes: list[dict]) -> dict:
    """CU-004 — Datos de una oferta a partir del correo y sus adjuntos (pasos 3 y 4). Devuelve el
    JSON de la IA tal cual: quien llama comprueba cada campo."""
    tarea = {"instrucciones": INSTRUCCIONES_OFERTA, "formato": FORMATO_OFERTA}
    return _pedir_json(config, tarea, partes)


def _texto_de(datos: dict, campo: str) -> str:
    valor = datos.get(campo)
    if not isinstance(valor, str) or not valor.strip():
        # Solo las claves (no el contenido): basta para saber qué ha devuelto el modelo.
        log.warning("La respuesta de la IA no trae «%s»; claves: %s", campo, sorted(datos))
        raise ErrorIA(f"La respuesta de la IA no trae «{campo}».")
    return valor.strip()


def _avisos_de(datos: dict) -> list[str]:
    avisos = datos.get("avisos") or []
    return [str(a) for a in avisos if str(a).strip()] if isinstance(avisos, list) else []


# Las instrucciones citan la plantilla para que la IA no empiece otra vez («Se solicita…»),
# separan la regla de los avisos (impersonal) de la del correo (primera persona del plural) y
# piden reescribir las notas como un correo ordenado, sin rellenar cada pieza como un formulario
# ni repetir nada en un apartado final; con «breve» o «copia tal cual», la IA se limita a copiar
# las notas. Lleva un ejemplo de cómo.
# Las frases de la plantilla citadas aquí las comprueba test_solicitudes.py.
INSTRUCCIONES_PETICION = """\
Ayudas al departamento de ingeniería de <EMPRESA> a pedir ofertas a proveedores.
El ingeniero escribe la descripción de la necesidad como notas para sí mismo, sin orden. Tú la \
conviertes en la parte central de un correo de petición de oferta en español, con un tono técnico, \
profesional y natural, como lo escribiría un ingeniero a un proveedor industrial. No copies las \
notas ni las conviertas en una plantilla: comprende la necesidad, agrupa la información \
relacionada y reescríbela.

La aplicación pone el resto del correo alrededor de tu texto, así:
«Buenos días:
Desde el departamento de ingeniería de <EMPRESA> les solicitamos oferta para lo siguiente:
[TU TEXTO]
En su oferta, indiquen por favor el precio y el plazo de entrega.
Adjuntamos la documentación disponible. Para facilitar el seguimiento, mantengan por favor la \
referencia … en el asunto de su respuesta.
Quedamos a la espera de su respuesta.»
(La frase «Adjuntamos la documentación disponible.» solo sale si hay documentos adjuntos.)

Cómo se ordena tu texto:
- Empieza directamente por el objeto de la petición; tu texto sigue a «les solicitamos oferta \
para lo siguiente:», por lo que no empieces con «Se solicita» ni vuelvas a pedir una oferta.
- Presenta la información técnica en una lista con guiones. Cada punto debe reunir una idea o un \
grupo de datos relacionados: alcance o piezas, material y norma, documentación disponible, \
trabajo que debe valorar el proveedor, lote o fecha objetivo y volúmenes previstos. Incluye solo \
los grupos que existan en las notas y elige su orden según la necesidad concreta.
- Si varias piezas comparten un requisito, menciónalo una sola vez. Separa piezas en distintos \
puntos únicamente cuando tengan requisitos propios que convenga distinguir.
- Redacta los requisitos como frases técnicas completas y fáciles de revisar, no como campos de \
un formulario. Normalmente basta una lista breve; usa una frase fuera de la lista solo cuando \
mejore de verdad la lectura.
- No fuerces apartados, encabezados ni un número fijo de puntos.

Reglas:
- Usa solo lo que dicen la descripción y los nombres de los adjuntos. No añadas piezas, \
cantidades, materiales, fechas ni requisitos que no aparezcan. Los valores (referencias, normas, \
materiales, cifras, fechas) se mantienen exactos; lo que cambia es la redacción.
- Cada dato aparece una vez: ni lo repitas ni lo pierdas. No termines con un apartado de \
«indicaciones», «observaciones» o «resumen» que repita lo ya dicho. Si las notas repiten algo \
(por ejemplo, un título pegado dos veces), dilo una vez.
- Nombra un documento adjunto una sola vez, donde se diga para qué sirve. No lo atribuyas a una \
pieza si las notas no lo hacen. De los adjuntos solo tienes el nombre: no hace falta abrirlos \
ni avisar de que no puedes.
- Nada de palabras que digan de dónde sale el dato («indicados», «según la descripción»).
- Los datos por año van en una línea («2029: 23.459; 2030: 186.466; …») o una lista corta.
- Escribe en primera persona del plural («necesitamos», «no disponemos de», «les pedimos») y \
tratando de usted al proveedor.
- Usa vocabulario propio de compras técnicas e ingeniería («fabricación», «modelo 3D», \
«utillajes», «lote», «volumen anual», «plazo»), pero no introduzcas tecnicismos ni conclusiones \
que no estén respaldados por las notas. Evita muletillas, lenguaje comercial y tono robótico.
- La cantidad solo vale si la descripción dice expresamente cuántas unidades se piden \
(por ejemplo, «4 rodamientos») o da los volúmenes previstos. No la deduzcas de frases como «se \
han partido dos» o «los de los dos lados». Si no hay ninguna, escribe [INDICAR cantidad] y \
avisa. Con cualquier otro dato importante que falte, escribe [INDICAR …] y avisa.
- No escribas saludo, despedida, firma, asunto, la petición de precio y plazo de entrega ni la \
frase de los adjuntos: los pone la aplicación. No avises de que no los incluyes.

Ejemplo (de otra necesidad; no copies sus datos, solo la forma):
Notas del ingeniero:
«Soportes A y B útil soldadura. Soportes A y B útil soldadura.
No hay plano, valorar con el STEP.
Material los dos: S355. Galvanizado.
Primero 20 de cada para probar, si va bien unas 500/año.»
Adjunto: soportes.step
Tu texto:
«- Fabricación de los soportes A y B para un útil de soldadura, en acero S355 galvanizado.
- Primer lote para pruebas: 20 unidades de cada soporte.
- No disponemos de plano 2D; les pedimos que realicen la valoración a partir del modelo 3D \
adjunto (soportes.step).
- Volumen anual previsto si las pruebas son satisfactorias: unas 500 unidades.»

Avisos (para el ingeniero, no para el proveedor): en impersonal o tratando de tú al ingeniero \
(por ejemplo, «Se ha tomado…», «Comprueba…»), nunca en primera persona («he tomado») ni con \
«vosotros» («comprobad»)."""

FORMATO_PETICION = _formato("peticion", {"peticion": {"type": "string"}, "avisos": _AVISOS})


def redactar_peticion(config: Config, descripcion: str, nombres_adjuntos: list[str]) -> dict:
    """CU-002 — Parte central del correo de petición de oferta: {peticion, avisos}."""
    adjuntos = "\n".join(f"- {n}" for n in nombres_adjuntos) or "(ninguno)"
    contenido = f"Descripción de la necesidad:\n{descripcion}\n\nDocumentos adjuntos:\n{adjuntos}"
    tarea = {"instrucciones": INSTRUCCIONES_PETICION, "formato": FORMATO_PETICION}
    datos = _pedir_json(config, tarea, contenido)
    return {"peticion": _texto_de(datos, "peticion"), "avisos": _avisos_de(datos)}


INSTRUCCIONES_ADJUDICACION = """\
Ayudas al departamento de ingeniería de <EMPRESA> cuando se elige la oferta de un proveedor.
Redacta en español dos textos:

1. «descripcion»: la descripción de la inversión para la solicitud de compra en SAP. Un texto \
breve (de 3 a 6 líneas) con el proceso o máquina afectados, las referencias, el proyecto, si es \
proveedor único (solo si hay una sola oferta) y un resumen de por qué se ha elegido esta oferta \
frente a las demás (precio, plazo, condiciones). No escribas «SOLICITADO POR» ni «IR»: esas \
líneas las pone la aplicación. Si los datos dicen que la aplicación ya pone una línea de \
proveedor único o de pocos proveedores consultados, no la repitas ni des otro motivo.
2. «resumen»: una o dos frases (o una lista breve con guiones) con lo que se adjudica al \
proveedor, para el correo en el que se le comunica (por ejemplo: «4 rodamientos 6204-2RS de \
acero inoxidable»). Sin saludo, despedida, firma, fechas ni precios.

Reglas:
- Usa solo los datos que se te dan. No inventes importes, referencias, piezas ni motivos.
- Al citar un importe, indica su moneda. No conviertas importes de una moneda a otra.
- Lo que se compra sale de la necesidad y de las líneas de la oferta. No añadas actividades ni \
servicios del proveedor que no estén en las líneas.
- Si la entrega no es una fecha que dio el proveedor (un plazo como «3 semanas», un mes como \
«diciembre» o una semana como «KW 50»), habla de lo que dijo, no de la fecha calculada.
- No incluyas el código interno de la necesidad (un número de 10 cifras): no le sirve a quien \
lee la descripción en SAP.
- En «descripcion», no hagas referencia a documentos adjuntos (planos, fotos, la oferta u otros \
archivos; por ejemplo, «según plano adjunto» o «ver documentación adjunta»): a SAP no se suben \
los adjuntos. Describe lo que se compra solo con el texto.
- La «Comparación de la elegida con las demás» ya viene calculada: úsala tal cual, sin \
recalcularla. Si la elegida no es la más barata, no digas que lo es ni que es la opción más \
económica; justifica la elección solo con lo que den los datos (plazo, condiciones de pago, \
garantía, histórico del proveedor…).
- Los «Comentarios de ingeniería al recibir pedidos anteriores» (si los hay) los escribió \
ingeniería al recibir pedidos de esos proveedores (por ejemplo, un paquete que llegó dañado). \
Tenlos en cuenta al justificar la elección cuando sean relevantes, sin exagerarlos ni sacar \
conclusiones que no digan.
- Si los datos no explican por qué se elige esta oferta, no inventes el motivo: escribe en la \
descripción «[INDICAR motivo de la elección]» y añade un aviso.
- Si falta un dato importante para justificar la elección, añade un aviso.
- «descripcion», en impersonal (la lee quien tramita la compra en SAP); «resumen», neutro, para \
el proveedor (sin dirigirse a nadie). Nunca en primera persona del singular.
- «avisos» (para el ingeniero): en impersonal o tratando de tú (por ejemplo, «Se ha tomado…», \
«Comprueba…»), nunca en primera persona («he tomado») ni con «vosotros» («comprobad»)."""

FORMATO_ADJUDICACION = _formato(
    "adjudicacion",
    {"descripcion": {"type": "string"}, "resumen": {"type": "string"}, "avisos": _AVISOS},
)


def redactar_adjudicacion(config: Config, contexto: str) -> dict:
    """CU-005 — En una sola llamada: descripción de la inversión para SAP y resumen de lo
    adjudicado para el correo. Devuelve {descripcion, resumen, avisos}."""
    tarea = {"instrucciones": INSTRUCCIONES_ADJUDICACION, "formato": FORMATO_ADJUDICACION}
    datos = _pedir_json(config, tarea, contexto)
    return {
        "descripcion": _texto_de(datos, "descripcion"),
        "resumen": _texto_de(datos, "resumen"),
        "avisos": _avisos_de(datos),
    }


INSTRUCCIONES_PETICION_DATOS = """\
Ayudas al departamento de ingeniería de <EMPRESA> a pedir a un proveedor los datos que faltan en \
su oferta. Recibes el proveedor, la necesidad, el número de oferta y la lista de lo que falta. \
Redacta la parte central del correo, en el idioma que se indica (español o inglés): lo que se \
le pide. La lista llega en español: tradúcela si el correo va en inglés.

La aplicación pone el resto del correo alrededor de tu texto, así:
«Buenos días:
Gracias por su oferta … para «…». Para poder valorarla, necesitamos que nos indiquen también lo \
siguiente:
[TU TEXTO]
Para facilitar el seguimiento, mantengan por favor la referencia … en el asunto de su respuesta.
Un saludo, …»

Reglas:
- Una lista con guiones, un dato por línea, en el orden recibido. Pide todos y solo los de la \
lista: no añadas otros ni des por sabido ninguno.
- En cada línea, di qué se necesita en pocas palabras y de forma natural (por ejemplo, \
«- Incoterm y lugar de entrega»; «- Validez de la oferta»; «- Si el precio se revisa con la \
materia prima y cómo»). Si un dato es una condición que puede estar incluida o no (embalaje, \
transporte, utillaje, tratamientos…), pide que indiquen si está incluido en el precio y, si no, \
su coste.
- Sin saludo, despedida, firma, asunto, agradecimientos ni la referencia: los pone la aplicación.
- Trata de usted al proveedor; no escribas en impersonal. En inglés, un tono cortés y directo.
- «avisos» (para el ingeniero, en impersonal o tratando de tú, nunca en primera persona): solo \
si algo de la lista no se entiende; si no, vacío."""

FORMATO_PETICION_DATOS = _formato(
    "peticion_datos", {"peticion": {"type": "string"}, "avisos": _AVISOS}
)


def redactar_peticion_datos(
    config: Config,
    *,
    proveedor: str,
    titulo: str,
    numero_oferta: str | None,
    faltan: list[str],
    ingles: bool = False,
) -> dict:
    """CU-004 — Parte central del correo que pide los datos que faltan:
    {peticion, avisos}. Solo se envían el proveedor, la necesidad, el número de oferta y la lista.
    `ingles`: el proveedor escribe en otro idioma."""
    lista = "\n".join(f"- {f}" for f in faltan)
    contenido = (
        f"Idioma del correo: {'inglés' if ingles else 'español'}\n"
        f"Proveedor: {proveedor}\nNecesidad: {titulo}\n"
        f"Número de oferta: {numero_oferta or '(no consta)'}\n\nDatos que faltan:\n{lista}"
    )
    tarea = {"instrucciones": INSTRUCCIONES_PETICION_DATOS, "formato": FORMATO_PETICION_DATOS}
    datos = _pedir_json(config, tarea, contenido)
    return {"peticion": _texto_de(datos, "peticion"), "avisos": _avisos_de(datos)}
