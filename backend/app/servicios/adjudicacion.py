"""CU-005 — Seleccionar proveedor y generar la información para SAP.

Reglas (docs/casos-de-uso/CU-005-seleccionar-proveedor-e-informacion-sap.md), con formatos
estrictos:
- Las líneas fijas del texto (`SOLICITADO POR:` e `IR: NO`) las pone la aplicación.
- La descripción de la inversión y el resumen del correo los redacta la IA; si falla, los propone
  el código con los datos (ADR 0011). El ingeniero los revisa antes de confirmar.
- El código avisa siempre si la elegida no es la más barata o la que antes entrega.
- Quantity requested: coma decimal y sin ceros sobrantes (`2,5`; `2`).
- Valuation Price: precio unitario sin IVA, coma decimal, sin separador de miles (`1250,50`).
- Delivery Date: `DD.MM.AAAA`. Si la oferta da un plazo («3 semanas») y no una fecha, se cuenta
  desde el día del pedido, no desde el correo de la oferta.
- Short Text: si la línea solo trae una referencia («R12345»), se completa con el título.
- Requisitioner: el nombre del proveedor en la lista de la aplicación, nunca el de la oferta.
- Al confirmar: oferta adjudicada, texto para SAP, fecha de entrega inicial, .eml solo al
  proveedor elegido y estado «Pendiente solicitud SAP».
"""

import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app import fechas
from app.config import Config
from app.integraciones import archivos, eml, ia
from app.modelos.necesidades import Adjunto, CambioEstado, Necesidad
from app.modelos.ofertas import Oferta
from app.servicios import comparativa, condiciones, historico
from app.servicios import ofertas as servicio_ofertas
from app.servicios.listas import DatosNoValidos, peticionario_activo
from app.servicios.necesidades import asunto_correos, firma, necesidad_en

AVISO_SIN_IA = (
    "No se ha podido usar la IA: la descripción y el correo son una propuesta con los datos de la "
    "necesidad y de la oferta. Complétalos o vuelve a intentarlo."
)
AVISO_SIN_LINEAS = (
    "La oferta no tiene partidas (descripción, cantidad y precio unitario): añádelas en "
    "«Revisar» para poder generar la tabla para SAP."
)


# --- Formatos de SAP --------------------------------------------------------------------------


def _sin_ceros(valor: Decimal) -> str:
    texto = f"{valor:f}"
    return texto.rstrip("0").rstrip(".") if "." in texto else texto


def formato_cantidad(valor: Decimal) -> str:
    """2.5 → «2,5»; 2.000 → «2»."""
    return _sin_ceros(valor).replace(".", ",")


def formato_precio(valor: Decimal) -> str:
    """1250.5 → «1250,50»; 1000 → «1000,00»; 12.3456 → «12,3456». Sin separador de miles."""
    texto = _sin_ceros(valor)
    entero, _, decimales = texto.partition(".")
    return f"{entero},{decimales.ljust(2, '0')}"


def formato_fecha(dia: date | None) -> str:
    return dia.strftime("%d.%m.%Y") if dia else ""


def _hoy() -> date:
    """Aparte para poder fijar «hoy» en las pruebas. En hora de España (`app/fechas.py`)."""
    return fechas.hoy()


def _de_las_lineas(oferta: Oferta) -> bool:
    """La fecha de la oferta salió de sus líneas al leerla (la más tardía, porque la oferta no
    daba una para toda ella): es la de una línea o su plazo es el de una línea (CU-004).
    Si no, manda la fecha de la oferta."""
    fecha = oferta.fecha_entrega_estimada
    if fecha is None:
        return False
    plazo = oferta.plazo_entrega_texto
    return any(
        li.fecha_entrega == fecha or (plazo and li.plazo_entrega_texto == plazo)
        for li in oferta.lineas
    )


def _plazos(oferta: Oferta, dia: date) -> list[tuple[date | None, str | None]]:
    """(fecha si el pedido se hace el día `dia`, plazo del que sale o None si es una fecha fija)
    de la oferta y, si su fecha salió de las líneas, de cada línea."""
    desde = servicio_ofertas.dia_del_correo(oferta)
    plazo = oferta.plazo_entrega_texto
    de_las_lineas = _de_las_lineas(oferta)
    # El plazo de la oferta cuenta si su fecha es ese plazo o si la fecha salió de una línea con
    # fecha fija y la oferta da también un plazo.
    if servicio_ofertas.fecha_calculada(oferta) or (
        de_las_lineas and servicio_ofertas.fecha_desde_plazo(plazo, desde)
    ):
        fechas = [(servicio_ofertas.fecha_desde_plazo(plazo, dia), plazo)]
    else:
        fechas = [(oferta.fecha_entrega_estimada, None)]
    if de_las_lineas:
        for linea in oferta.lineas:
            calculada = servicio_ofertas.linea_calculada(linea, oferta)
            fechas.append(
                (
                    servicio_ofertas.entrega_de_linea(linea, oferta, dia),
                    linea.plazo_entrega_texto if calculada else None,
                )
            )
    return [(f, p) for f, p in fechas if f is not None]


def entrega_si_se_pide(oferta: Oferta, dia: date) -> date | None:
    """Fecha de entrega si el pedido se hace el día `dia`: con un plazo relativo, contado desde
    ese día; si el proveedor dio una fecha, esa. Si la fecha de la oferta salió de sus líneas, la
    más tardía de todas, porque el pedido no está completo hasta que llega todo."""
    return max((f for f, _ in _plazos(oferta, dia)), default=None)


def plazo_relativo(necesidad: Necesidad) -> str | None:
    """El plazo de la oferta adjudicada («3 semanas») si su entrega es un plazo y no una fecha
    concreta: el de la oferta o el de la línea que más tarda."""
    oferta = necesidad.oferta_adjudicada
    if oferta is None:
        return None
    plazos = _plazos(oferta, _hoy())
    if not plazos:
        return None
    return max(plazos, key=lambda p: p[0])[1]


def fecha_propuesta(necesidad: Necesidad) -> date | None:
    """Fecha de entrega que se propone al meter el pedido en SAP (CU-006): con un plazo
    relativo, contada desde hoy; si no, la que se guardó al adjudicar."""
    if plazo_relativo(necesidad):
        return entrega_si_se_pide(necesidad.oferta_adjudicada, _hoy())
    return necesidad.fecha_entrega_inicial


def texto_corto(descripcion: str, titulo: str) -> str:
    """Una línea que solo trae una referencia («R12345»: una palabra con alguna cifra) no dice
    qué es: se completa con el título de la necesidad, o se usa el título si ya la lleva (como
    palabra entera: «R1234» no está en «Útil R12345»)."""
    referencia = descripcion.strip()
    if " " in referencia or not re.search(r"\d", referencia):
        return descripcion
    if re.search(rf"(?<!\w){re.escape(referencia)}(?!\w)", titulo, re.IGNORECASE):
        return titulo
    return f"{referencia} – {titulo}"


def lineas_sap(oferta: Oferta, titulo: str, entrega: date | None, dia: date) -> list[dict]:
    """Una fila por línea de la oferta, con las columnas y los formatos de SAP. `entrega`: la
    fecha de la oferta, para las líneas que no traen la suya. `dia`: el del pedido, desde el que
    se cuenta el plazo de cada línea."""
    return [
        {
            "short_text": texto_corto(linea.descripcion, titulo),
            "quantity_requested": formato_cantidad(linea.cantidad),
            "valuation_price": formato_precio(linea.precio_unitario),
            "delivery_date": formato_fecha(
                servicio_ofertas.entrega_de_linea(linea, oferta, dia) or entrega
            ),
            "requisitioner": oferta.proveedor.nombre,
        }
        for linea in oferta.lineas
    ]


def pocos_proveedores(necesidad: Necesidad) -> str | None:
    """Línea para SAP si se pidieron ofertas a menos de 3 proveedores:
    «Proveedor único por …» con uno y «Solo 2 proveedores consultados por …» con dos.
    Sin motivo guardado no la lleva."""
    motivo = necesidad.motivo_pocos_proveedores
    if not motivo:
        return None
    cuantos = len(necesidad.solicitados)
    if cuantos <= 1:
        return f"Proveedor único por {motivo}."
    return f"Solo {cuantos} proveedores consultados por {motivo}."


def texto_sap(necesidad: Necesidad, descripcion: str) -> str:
    lineas = [f"SOLICITADO POR: {necesidad.peticionario.nombre_completo}", "IR: NO"]
    if linea := pocos_proveedores(necesidad):
        lineas.append(linea)
    return "\n".join([*lineas, descripcion.strip()])


# --- Correo al adjudicatario -----------------------------------------------------------------


def cuerpo_adjudicacion(
    necesidad: Necesidad, oferta: Oferta, resumen: str, empresa: str = ""
) -> str:
    numero = f" {oferta.numero_oferta}" if oferta.numero_oferta else ""
    # Al proveedor no se le dice una fecha que no ha dado: si dio un plazo o solo un mes, se
    # repite lo que dijo.
    if servicio_ofertas.fecha_no_dada(oferta):
        entrega = f"Plazo de entrega según su oferta: {oferta.plazo_entrega_texto}."
    else:
        entrega = f"Fecha de entrega según su oferta: {oferta.fecha_entrega_estimada:%d/%m/%Y}."
    return (
        "Buenos días:\n\n"
        f"Les comunicamos que su oferta{numero} para la necesidad "
        f"«{necesidad.codigo} {necesidad.titulo}» ha sido seleccionada.\n\n"
        f"{resumen.strip()}\n\n"
        "Pueden comenzar con los trabajos. En los próximos días les enviaremos el pedido "
        "oficial de SAP.\n\n"
        f"{entrega}\n\n"
        f"{firma(necesidad, empresa)}"
    )


# --- Contexto para la IA y propuesta sin IA ------------------------------------------------------


def _entrega_para_ia(oferta: Oferta) -> str:
    if oferta.fecha_entrega_estimada is None:
        return oferta.plazo_entrega_texto or "—"
    if servicio_ofertas.fecha_calculada(oferta):
        return (
            f"{oferta.plazo_entrega_texto} (plazo del proveedor, sin fecha concreta; contado desde "
            f"su oferta sería el {formato_fecha(oferta.fecha_entrega_estimada)})"
        )
    if servicio_ofertas.fecha_de_mes(oferta):
        return (
            f"{oferta.plazo_entrega_texto} (el proveedor dio solo el mes; se toma el último "
            f"viernes, el {formato_fecha(oferta.fecha_entrega_estimada)})"
        )
    if servicio_ofertas.fecha_de_semana(oferta):
        return (
            f"{oferta.plazo_entrega_texto} (el proveedor dio la semana; se toma su viernes, el "
            f"{formato_fecha(oferta.fecha_entrega_estimada)})"
        )
    return formato_fecha(oferta.fecha_entrega_estimada)


def resumen_oferta(oferta: Oferta) -> str:
    lineas = "\n".join(
        f"  - {linea.descripcion}: {formato_cantidad(linea.cantidad)} × "
        f"{formato_precio(linea.precio_unitario)} sin IVA"
        for linea in oferta.lineas
    )
    return (
        f"Proveedor: {oferta.proveedor.nombre}\n"
        f"Moneda de los importes y precios: {oferta.moneda or 'sin confirmar'}\n"
        f"Importe sin IVA: {'—' if oferta.importe_sin_iva is None else oferta.importe_sin_iva}\n"
        f"Entrega: {_entrega_para_ia(oferta)}\n"
        f"Condiciones de pago: {oferta.condiciones_pago or '—'}\n"
        f"Otras condiciones:\n{condiciones.resumen(oferta.condiciones) or '  (no especifica)'}\n"
        f"Información adicional: {oferta.otros or '—'}\n"
        f"Líneas:\n{lineas or '  (sin líneas)'}"
    )


def frente_a_las_demas(elegida: Oferta, comparadas: list[Oferta]) -> tuple[list[str], list[str]]:
    """Compara la elegida con las demás revisadas en precio (sin IVA, misma moneda: ADR 0010) y
    entrega. Devuelve (hechos para la IA, avisos para el ingeniero). Lo calcula el código: es una
    cuenta exacta, y la IA no siempre avisa si se elige una más cara. Usa las
    mismas reglas que el mejor y peor valor de la comparativa."""
    if len(comparadas) < 2:
        return [], []
    hechos, avisos = [], []
    con_importe = [o for o in comparadas if o.importe_sin_iva is not None]
    importes = comparativa.importes_comparables(comparadas)
    if importes is None:
        hechos.append("Precio: las ofertas están en monedas distintas; no se comparan importes.")
    elif elegida.importe_sin_iva is not None and len(con_importe) >= 2:
        barata = min(con_importe, key=lambda o: o.importe_sin_iva)
        if comparativa.es_la_mejor(elegida.id, importes):
            hechos.append("Precio: es la oferta más barata (sin IVA).")
        else:
            diferencia = elegida.importe_sin_iva - barata.importe_sin_iva
            texto = (
                f"{barata.proveedor.nombre} ofrece {formato_precio(barata.importe_sin_iva)} "
                f"{barata.moneda} sin IVA ({formato_precio(diferencia)} {barata.moneda} menos)"
            )
            hechos.append(f"Precio: no es la oferta más barata; {texto}.")
            avisos.append(
                f"No es la oferta más barata: {texto}. Explica en la descripción por qué se elige."
            )
    con_fecha = [o for o in comparadas if o.fecha_entrega_estimada]
    if elegida.fecha_entrega_estimada and len(con_fecha) >= 2:
        pronta = min(con_fecha, key=lambda o: o.fecha_entrega_estimada)
        entregas = {o.id: o.fecha_entrega_estimada for o in comparadas}
        if comparativa.es_la_mejor(elegida.id, entregas):
            hechos.append("Entrega: es la que antes entrega.")
        else:
            texto = (
                f"{pronta.proveedor.nombre} entrega el "
                f"{pronta.fecha_entrega_estimada:%d/%m/%Y} (la elegida, el "
                f"{elegida.fecha_entrega_estimada:%d/%m/%Y})"
            )
            hechos.append(f"Entrega: no es la que antes entrega; {texto}.")
            avisos.append(f"No es la que antes entrega: {texto}.")
    return hechos, avisos


COMENTARIOS_POR_PROVEEDOR = 5


def comentarios_para_ia(ofertas: list[Oferta], resumenes: dict[int, dict]) -> str:
    """Comentarios de la entrega de pedidos anteriores de los proveedores de estas ofertas (los
    más recientes de cada uno), para que la IA los tenga en cuenta al justificar la elección."""
    lineas = []
    for proveedor in {o.proveedor_id: o.proveedor for o in ofertas}.values():
        comentarios = resumenes.get(proveedor.id, {}).get("comentarios", [])
        for c in comentarios[:COMENTARIOS_POR_PROVEEDOR]:
            lineas.append(
                f"- {proveedor.nombre}, entrega del {formato_fecha(c['fecha'])} "
                f"(«{c['titulo']}»): {c['texto']}"
            )
    return "\n".join(lineas)


def _contexto(
    necesidad: Necesidad,
    elegida: Oferta,
    comparadas: list[Oferta],
    resumenes: dict[int, dict] | None = None,
) -> str:
    otras = [o for o in comparadas if o.id != elegida.id]
    resto = "\n\n".join(resumen_oferta(o) for o in otras) or "(no hay otras ofertas revisadas)"
    hechos, _ = frente_a_las_demas(elegida, comparadas)
    comparacion = "\n".join(hechos) or "(es la única oferta revisada)"
    linea = pocos_proveedores(necesidad)
    ya_puesta = f"\n\nLa aplicación ya pone en la descripción para SAP: «{linea}»" if linea else ""
    # Lo que escribió ingeniería al recibir pedidos anteriores de estos proveedores.
    comentarios = comentarios_para_ia([elegida, *otras], resumenes or {})
    anteriores = (
        f"\n\nComentarios de ingeniería al recibir pedidos anteriores de estos proveedores:\n"
        f"{comentarios}"
        if comentarios
        else ""
    )
    # Sin el código de la necesidad: no le sirve a quien lee la descripción en SAP.
    return (
        f"Necesidad: {necesidad.titulo}\n"
        f"Proyecto: {necesidad.proyecto}\n"
        f"Descripción del ingeniero:\n{necesidad.descripcion}\n\n"
        f"Oferta elegida:\n{resumen_oferta(elegida)}\n\n"
        f"Comparación de la elegida con las demás (calculada por la aplicación):\n{comparacion}\n\n"
        f"Otras ofertas revisadas ({len(otras)}):\n{resto}"
        f"{anteriores}"
        f"{ya_puesta}"
    )


def _resumen_adjudicado(oferta: Oferta, titulo: str) -> str:
    """Lo que se adjudica, para el correo al proveedor: las líneas de la oferta (sin precios)."""
    if not oferta.lineas:
        return titulo
    return "\n".join(
        f"- {formato_cantidad(linea.cantidad)} × {linea.descripcion}" for linea in oferta.lineas
    )


def _descripcion_inversion(
    necesidad: Necesidad, elegida: Oferta, comparadas: list[Oferta]
) -> tuple[str, list[str]]:
    """Texto inicial editable para SAP y avisos sobre el criterio que solo conoce el ingeniero."""
    lineas = [
        necesidad.titulo.strip(),
        f"Proyecto: {necesidad.proyecto.strip()}.",
        necesidad.descripcion.strip(),
    ]
    avisos = []
    if len(comparadas) == 1:
        # Con el motivo de pedir a menos de 3, la parte fija ya dice que es proveedor único.
        if not pocos_proveedores(necesidad):
            lineas.append(f"Proveedor único consultado: {elegida.proveedor.nombre}.")
        return "\n".join(dict.fromkeys(lineas)), avisos

    criterios = []
    monedas = {o.moneda for o in comparadas if o.moneda}
    con_importe = [o for o in comparadas if o.importe_sin_iva is not None]
    if len(monedas) == 1 and len(con_importe) >= 2:
        menor = min(o.importe_sin_iva for o in con_importe)
        if elegida.importe_sin_iva == menor:
            criterios.append("menor importe sin IVA")
    con_fecha = [o for o in comparadas if o.fecha_entrega_estimada]
    if len(con_fecha) >= 2:
        primera = min(o.fecha_entrega_estimada for o in con_fecha)
        if elegida.fecha_entrega_estimada == primera:
            criterios.append("entrega más próxima")
    lineas.append(f"Proveedor seleccionado: {elegida.proveedor.nombre}.")
    if criterios:
        lineas.append("Criterios objetivos: " + " y ".join(criterios) + ".")
    else:
        avisos.append(
            "Completa en la descripción el motivo de elegir esta oferta; no se puede deducir "
            "solo del precio y la fecha de entrega."
        )
    return "\n".join(dict.fromkeys(lineas)), avisos


def sin_codigo(texto: str, codigo: str) -> str:
    """Quita de la descripción propuesta el código de la necesidad, si la IA lo escribe o la
    descripción del ingeniero lo lleva («Necesidad 2026102602: …», «(2026102602)» o suelto)."""
    if codigo not in texto:
        return texto
    texto = re.sub(rf"(?i)\bnecesidad\s*(?:n\.?º\s*)?{codigo}\s*[:.,-]?\s*", "", texto)
    texto = re.sub(rf"\s*\(\s*{codigo}\s*\)", "", texto)
    # «Ref. 2026102602.» → «Ref.»: el signo que lo seguía sobra. Solo alrededor del código, para
    # no tocar otros signos del texto (los puntos suspensivos, por ejemplo).
    texto = re.sub(rf"([.,;:])\s*{codigo}\s*[.,;:]?", r"\1", texto)
    texto = re.sub(rf"[ \t]*{codigo}", "", texto)
    texto = re.sub(r"[ \t]+([.,;:])", r"\1", texto)  # espacios que quedan antes de un signo
    texto = re.sub(r"[ \t]{2,}", " ", texto).strip()
    return texto[:1].upper() + texto[1:]


# --- Acciones --------------------------------------------------------------------------------


def _necesidad_y_oferta(sesion: Session, necesidad_id: int, oferta_id: int, bloquear=False):
    necesidad = necesidad_en(sesion, necesidad_id, "en_evaluacion", bloquear)
    if necesidad is None:
        return None, None
    oferta = sesion.get(Oferta, oferta_id) if oferta_id else None
    if (
        oferta is None
        or oferta.necesidad_id != necesidad_id
        or oferta.estado_oferta != "vigente"
        or not oferta.revisada
        or not oferta.moneda
        or oferta.importe_sin_iva is None
        or oferta.fecha_entrega_estimada is None
    ):
        raise DatosNoValidos("oferta_id", "Elige una oferta vigente y revisada de la comparativa.")
    # Se elige con todas las ofertas revisadas: así se compara con datos comprobados, no con lo
    # que leyó la IA.
    sin_revisar = [
        o.proveedor.nombre
        for o in servicio_ofertas.vigentes(sesion, necesidad_id)
        if not o.revisada
    ]
    if sin_revisar:
        raise DatosNoValidos(
            "oferta_id",
            f"Revisa todas las ofertas antes de elegir una. Falta: {', '.join(sin_revisar)}.",
        )
    return necesidad, oferta


def borrador(sesion: Session, config: Config, necesidad_id: int, oferta_id: int) -> dict | None:
    """Prepara la información para SAP y el correo al adjudicatario (sin guardar nada). La IA
    redacta la descripción y el resumen; si falla, se proponen con los datos (ADR 0011)."""
    necesidad, oferta = _necesidad_y_oferta(sesion, necesidad_id, oferta_id)
    if necesidad is None:
        return None
    # `bloqueos` impiden adjudicar; `avisos` son informativos.
    bloqueos = [] if oferta.lineas else [AVISO_SIN_LINEAS]
    # Solo las revisadas: la descripción para SAP no se justifica con datos sin revisar.
    revisadas = servicio_ofertas.comparativa(sesion, necesidad_id, solo_revisadas=True)
    resumenes = historico.resumenes(sesion, list({o.proveedor_id for o in [oferta, *revisadas]}))
    try:
        redactado = ia.redactar_adjudicacion(
            config, _contexto(necesidad, oferta, revisadas, resumenes)
        )
        descripcion, resumen, avisos = (
            redactado["descripcion"],
            redactado["resumen"],
            redactado["avisos"],
        )
    except ia.ErrorIA as error:
        descripcion, avisos = _descripcion_inversion(necesidad, oferta, revisadas)
        resumen = _resumen_adjudicado(oferta, necesidad.titulo)
        avisos.insert(0, ia.aviso_sin_ia(error, AVISO_SIN_IA))
    # Siempre, redacte la IA o no: elegir una más cara o que llega después tiene que verse.
    avisos = frente_a_las_demas(oferta, revisadas)[1] + avisos
    # El código interno no le sirve a quien lee la descripción en SAP.
    descripcion = "\n".join(
        sin_codigo(linea, necesidad.codigo) for linea in descripcion.split("\n")
    )
    return {
        "texto_sap_fijo": texto_sap(necesidad, ""),
        "moneda": oferta.moneda,
        "descripcion_inversion": descripcion,
        "tabla_sap": lineas_sap(
            oferta, necesidad.titulo, entrega_si_se_pide(oferta, _hoy()), _hoy()
        ),
        "correo": {
            "para": ", ".join(servicio_ofertas.destinatarios(oferta)),
            "asunto": asunto_correos(necesidad),
            "cuerpo": cuerpo_adjudicacion(necesidad, oferta, resumen, config.empresa_nombre),
        },
        "bloqueos": bloqueos,
        "avisos": avisos,
    }


def adjudicar(
    sesion: Session,
    raiz_archivos: Path,
    necesidad_id: int,
    *,
    peticionario_id: int | None,
    oferta_id: int | None,
    descripcion_inversion: str | None,
    cuerpo_correo: str | None,
) -> Necesidad | None:
    """Guarda la adjudicación, genera el .eml y pasa a «Pendiente solicitud SAP»."""
    necesidad, oferta = _necesidad_y_oferta(sesion, necesidad_id, oferta_id, bloquear=True)
    if necesidad is None:
        return None
    if not oferta.lineas:
        raise DatosNoValidos("oferta_id", AVISO_SIN_LINEAS)
    if not (descripcion_inversion or "").strip():
        raise DatosNoValidos("descripcion_inversion", "Escribe la descripción de la inversión.")
    if not (cuerpo_correo or "").strip():
        raise DatosNoValidos("cuerpo_correo", "El cuerpo del correo está vacío.")
    peticionario = peticionario_activo(sesion, peticionario_id, "Elige quién adjudica.")

    contenido = eml.componer(
        asunto_correos(necesidad),
        cuerpo_correo.strip() + "\n",
        para=servicio_ofertas.destinatarios(oferta),
    )
    nombre = f"{necesidad.codigo} adjudicacion.eml"
    ruta = archivos.guardar(raiz_archivos, necesidad.codigo, nombre, contenido)
    try:
        necesidad.adjuntos.append(
            Adjunto(
                tipo="adjudicacion",
                nombre_archivo=nombre,
                ruta=ruta,
                tipo_mime="message/rfc822",
                tamano=len(contenido),
            )
        )
        necesidad.oferta_adjudicada = oferta
        necesidad.texto_sap = texto_sap(necesidad, descripcion_inversion)
        necesidad.fecha_entrega_inicial = entrega_si_se_pide(oferta, _hoy())
        necesidad.historial.append(
            CambioEstado(
                estado_anterior=necesidad.estado,
                estado_nuevo="pendiente_solicitud_sap",
                peticionario=peticionario,
            )
        )
        necesidad.estado = "pendiente_solicitud_sap"
        sesion.commit()
    except Exception:
        sesion.rollback()
        archivos.borrar(raiz_archivos, ruta)
        raise
    return necesidad


def _dia_del_pedido(necesidad: Necesidad) -> date:
    """Día en que se confirmó el pedido en SAP (paso 5); si aún no, hoy. Desde él se cuentan los
    plazos de las líneas."""
    for cambio in reversed(necesidad.historial):
        if cambio.estado_nuevo == "pendiente_entrega" and cambio.cambiado_en:
            return cambio.cambiado_en.astimezone(fechas.ZONA).date()
    return _hoy()


def informacion_sap(necesidad: Necesidad) -> dict | None:
    """Texto y tabla para copiar en SAP, una vez adjudicada. None si aún no hay adjudicación."""
    oferta = necesidad.oferta_adjudicada
    if oferta is None:
        return None
    # La misma fecha que se propone (o se confirmó) al meter el pedido en SAP: con un plazo sin
    # fecha, contado desde hoy.
    entrega = necesidad.fecha_entrega_prevista or fecha_propuesta(necesidad)
    return {
        "proveedor": oferta.proveedor.nombre,
        "moneda": oferta.moneda,
        "texto_sap": necesidad.texto_sap,
        "tabla_sap": lineas_sap(oferta, necesidad.titulo, entrega, _dia_del_pedido(necesidad)),
        "fecha_entrega_inicial": necesidad.fecha_entrega_inicial,
    }
