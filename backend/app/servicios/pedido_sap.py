"""CU-007 — Adjuntar el pedido oficial de SAP y generar el .eml al proveedor adjudicatario.

Reglas (docs/casos-de-uso/CU-007-enviar-pedido-sap.md):
- Solo desde «Pendiente pedido SAP»; al generar el .eml pasa a «Pendiente entrega».
- Número de oferta obligatorio: se propone el de la oferta revisada y, si no hay, el del nombre
  del adjunto de la oferta. El confirmado se guarda en la oferta adjudicada.
- Número de pedido de SAP opcional; si se indica, va en el cuerpo. Al elegir el PDF del pedido
  se lee de él («PURCHASE ORDER NO. …», `integraciones/pedido_pdf.py`) para proponerlo. El
  asunto es el de todos los correos de la necesidad, sin el número.
- El .eml va solo al proveedor adjudicatario, con el pedido adjunto; lo envía el ingeniero.
"""

import re
from pathlib import Path, PurePath

from sqlalchemy.orm import Session

from app.integraciones import archivos, eml, pedido_pdf
from app.modelos.necesidades import Adjunto, CambioEstado, Necesidad
from app.servicios.listas import DatosNoValidos, peticionario_activo
from app.servicios.necesidades import ArchivoSubido, asunto_correos, firma, necesidad_en
from app.servicios.ofertas import destinatarios

ESTADO = "pendiente_pedido_sap"
# «OF-2026-0417», «HN-1182», «TZ 81»: unas letras y un número. O un número de 3 cifras o más.
_CON_LETRAS = re.compile(r"(?<![A-Za-z])[A-Za-z]{1,5}[-_ ]?\d[\d./_-]*")
_SOLO_NUMERO = re.compile(r"(?<![\d])\d{3,}(?:[./_-]\d+)*")


def _necesidad(sesion: Session, necesidad_id: int, bloquear: bool = False) -> Necesidad | None:
    return necesidad_en(sesion, necesidad_id, ESTADO, bloquear)


def numero_en_nombre(nombre: str, excluir: str = "") -> str | None:
    """Número de oferta en el nombre de un archivo: «Oferta HN-1182.pdf» → «HN-1182».
    Se queda con el candidato más largo; no cuenta el código de la necesidad."""
    base = PurePath(nombre).stem
    candidatos = [
        c.strip("-_. /") for patron in (_CON_LETRAS, _SOLO_NUMERO) for c in patron.findall(base)
    ]
    # Con letras basta con 2 cifras («TZ-81»); un número suelto, 3 o más.
    validos = [
        c
        for c in candidatos
        if c != excluir and sum(ch.isdigit() for ch in c) >= (2 if c[0].isalpha() else 3)
    ]
    return max(validos, key=len) if validos else None


def numero_del_pdf(sesion: Session, necesidad_id: int, pedido: ArchivoSubido) -> dict | None:
    """Número de pedido leído del PDF de SAP, para proponerlo (no se guarda nada). None si la
    necesidad no existe; `numero_pedido` es None si el PDF no lo dice."""
    if _necesidad(sesion, necesidad_id) is None:
        return None
    archivos.comprobar_tamano(pedido.nombre, len(pedido.datos))
    return {"numero_pedido": pedido_pdf.numero_de_pedido(pedido.datos)}


def propuesta(sesion: Session, necesidad_id: int) -> dict | None:
    """Proveedor, correo y número de oferta propuesto, con su origen («oferta» o «archivo»)."""
    necesidad = _necesidad(sesion, necesidad_id)
    if necesidad is None:
        return None
    oferta = necesidad.oferta_adjudicada
    numero, origen = oferta.numero_oferta, "oferta" if oferta.numero_oferta else None
    if not numero:
        for adjunto in oferta.archivos:
            if adjunto.tipo == "adjunto_oferta":
                numero = numero_en_nombre(adjunto.nombre_archivo, necesidad.codigo)
                if numero:
                    origen = "archivo"
                    break
    return {
        "proveedor": oferta.proveedor.nombre,
        "para": ", ".join(destinatarios(oferta)),
        "numero_oferta": numero,
        "origen_numero_oferta": origen,
        "fecha_entrega_prevista": necesidad.fecha_entrega_prevista,
    }


def cuerpo(
    necesidad: Necesidad, numero_oferta: str, numero_pedido: str | None, empresa: str = ""
) -> str:
    # «Les adjuntamos el pedido XXXXXXXX correspondiente a su oferta…».
    pedido = numero_pedido or "oficial de SAP"
    entrega = necesidad.fecha_entrega_prevista
    linea_entrega = (
        f"Fecha de entrega prevista: {entrega.strftime('%d/%m/%Y')}. Si no pueden cumplirla, "
        "avísennos lo antes posible.\n\n"
        if entrega
        else ""
    )
    return (
        "Buenos días:\n\n"
        f"Les adjuntamos el pedido {pedido} correspondiente a su oferta "
        f"{numero_oferta}, para la necesidad «{necesidad.codigo} {necesidad.titulo}».\n\n"
        f"{linea_entrega}"
        "Por favor, indiquen el número de pedido en el albarán y en la factura.\n\n"
        f"{firma(necesidad, empresa)}"
    )


def _numeros(numero_oferta: str | None, numero_pedido: str | None) -> tuple[str, str | None]:
    numero_oferta = " ".join((numero_oferta or "").split())
    numero_pedido = " ".join((numero_pedido or "").split()) or None
    if not numero_oferta:
        raise DatosNoValidos("numero_oferta", "Indica el número de oferta del proveedor.")
    if len(numero_oferta) > 100:
        raise DatosNoValidos("numero_oferta", "El número de oferta es demasiado largo.")
    if numero_pedido and len(numero_pedido) > 50:
        raise DatosNoValidos("numero_pedido", "El número de pedido es demasiado largo.")
    return numero_oferta, numero_pedido


def borrador(
    sesion: Session,
    necesidad_id: int,
    numero_oferta: str | None,
    numero_pedido: str | None,
    empresa: str = "",
) -> dict | None:
    """Correo propuesto con los números indicados (no guarda nada)."""
    necesidad = _necesidad(sesion, necesidad_id)
    if necesidad is None:
        return None
    numero_oferta, numero_pedido = _numeros(numero_oferta, numero_pedido)
    return {
        "para": ", ".join(destinatarios(necesidad.oferta_adjudicada)),
        "asunto": asunto_correos(necesidad),
        "cuerpo": cuerpo(necesidad, numero_oferta, numero_pedido, empresa),
    }


def enviar(
    sesion: Session,
    raiz_archivos: Path,
    necesidad_id: int,
    *,
    peticionario_id: int | None,
    pedido: ArchivoSubido | None,
    numero_oferta: str | None,
    numero_pedido: str | None,
    cuerpo_correo: str | None,
) -> Necesidad | None:
    """Guarda el pedido, genera el .eml con el pedido adjunto y pasa a «Pendiente entrega»."""
    necesidad = _necesidad(sesion, necesidad_id, bloquear=True)
    if necesidad is None:
        return None
    if pedido is None:
        raise DatosNoValidos("pedido", "Sube el pedido oficial de SAP.")
    archivos.comprobar_tamano(pedido.nombre, len(pedido.datos))
    numero_oferta, numero_pedido = _numeros(numero_oferta, numero_pedido)
    if not (cuerpo_correo or "").strip():
        raise DatosNoValidos("cuerpo_correo", "El cuerpo del correo está vacío.")
    peticionario = peticionario_activo(sesion, peticionario_id, "Elige quién envía el pedido.")

    oferta = necesidad.oferta_adjudicada
    tipo_mime = pedido.tipo_mime or "application/octet-stream"
    contenido = eml.componer(
        asunto_correos(necesidad),
        cuerpo_correo.strip() + "\n",
        para=destinatarios(oferta),
        adjuntos=[eml.ArchivoAdjunto(pedido.nombre, tipo_mime, pedido.datos)],
    )
    nombre_eml = f"{necesidad.codigo} pedido SAP.eml"
    guardados = []
    try:
        for tipo, nombre, mime, datos in (
            ("pedido_sap", pedido.nombre, tipo_mime, pedido.datos),
            ("envio_pedido", nombre_eml, "message/rfc822", contenido),
        ):
            ruta = archivos.guardar(raiz_archivos, necesidad.codigo, nombre, datos)
            guardados.append(ruta)
            necesidad.adjuntos.append(
                Adjunto(
                    tipo=tipo,
                    nombre_archivo=nombre[:255],
                    ruta=ruta,
                    tipo_mime=mime,
                    tamano=len(datos),
                )
            )
        oferta.numero_oferta = numero_oferta
        necesidad.numero_pedido_sap = numero_pedido
        necesidad.historial.append(
            CambioEstado(
                estado_anterior=necesidad.estado,
                estado_nuevo="pendiente_entrega",
                peticionario=peticionario,
            )
        )
        necesidad.estado = "pendiente_entrega"
        sesion.commit()
    except Exception:
        sesion.rollback()
        for ruta in guardados:
            archivos.borrar(raiz_archivos, ruta)
        raise
    return necesidad
