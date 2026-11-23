"""CU-004 — Condiciones de la oferta: una tabla fija en lugar de un texto libre.

Cada oferta dice (o no) lo mismo sobre
nueve condiciones, para poder compararlas en columnas. Cada una tiene un estado y un texto. Se
guardan en `ofertas.condiciones` (JSONB) como {clave: {"estado": …, "texto": …}}; una oferta
sin condiciones las tiene todas «No especificado». `otros` se queda para la
información adicional que no encaja aquí. Estas condiciones no se destacan en la comparativa:
no hay un valor que sea siempre mejor.

Este es el único sitio con la lista: la usan la IA (esquema de la respuesta), la API (en el
orden de aquí, con su nombre) y la adjudicación.
"""

CONDICIONES = (
    ("embalaje", "Embalaje"),
    ("incoterm", "Incoterm / condiciones de entrega"),
    ("transporte", "Transporte"),
    ("incluye_precio", "Qué incluye el precio"),
    ("validez", "Validez de la oferta"),
    ("materia_prima", "Revisión del precio de materia prima"),
    ("utillaje", "Utillaje"),
    ("tratamientos", "Tratamientos térmicos / recubrimientos"),
    ("condiciones_pedido", "Condiciones de pedido"),
)
ESTADOS = {
    "especificado": "Especificado",
    "incluido": "Incluido",
    "no_incluido": "No incluido",
    "no_aplica": "No aplica",
    "no_especificado": "No especificado",
}
SIN_ESPECIFICAR = "no_especificado"
MAXIMO_TEXTO = 500


def _una(valor) -> dict:
    valor = valor if isinstance(valor, dict) else {}
    estado = valor.get("estado")
    estado = estado if estado in ESTADOS else SIN_ESPECIFICAR
    texto = valor.get("texto")
    texto = " ".join(texto.split())[:MAXIMO_TEXTO] if isinstance(texto, str) else ""
    # «Especificado» sin decir qué no dice nada.
    if estado == "especificado" and not texto:
        estado = SIN_ESPECIFICAR
    return {"estado": estado, "texto": texto or None}


def normalizar(valor) -> dict:
    """Las nueve condiciones, con un estado válido y el texto limpio, venga de la IA, de la API o
    de una oferta antigua (None). Lo que no se reconoce queda «No especificado»."""
    valor = valor if isinstance(valor, dict) else {}
    return {clave: _una(valor.get(clave)) for clave, _ in CONDICIONES}


def en_orden(valor) -> list[dict]:
    """Para la API y la pantalla: [{clave, nombre, estado, texto}] en el orden de la tabla."""
    todas = normalizar(valor)
    return [{"clave": c, "nombre": nombre, **todas[c]} for c, nombre in CONDICIONES]


def como_texto(una: dict) -> str:
    """Cómo se lee una condición: el texto si está especificada; si no, su estado y el texto."""
    if una["estado"] == "especificado":
        return una["texto"]
    estado = ESTADOS[una["estado"]]
    return f"{estado}: {una['texto']}" if una["texto"] else estado


def resumen(valor) -> str:
    """Las condiciones que dicen algo, en una línea por condición, para la IA de la adjudicación.
    Las «No especificado» se omiten."""
    lineas = [
        f"{c['nombre']}: {como_texto(c)}" for c in en_orden(valor) if c["estado"] != SIN_ESPECIFICAR
    ]
    return "\n".join(lineas)
