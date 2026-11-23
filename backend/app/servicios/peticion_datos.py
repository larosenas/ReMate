"""CU-004 — Pedir al proveedor los datos que faltan en su oferta.

Lo redacta la IA, se piden todos los datos que falten
(también las condiciones de la tabla en «No especificado»; «No aplica» y «No incluido» cuentan
como respondidas) y el correo **no se guarda**: se revisa en pantalla y se descarga como `.eml`
(con `X-Unsent`, como los demás). Va al proveedor y, si la oferta la envió otra persona de su
empresa, también a ella (`destinatarios`), con el asunto común de la necesidad.

A la IA solo se le envían el nombre del proveedor, el título de la necesidad, el número de la
oferta y la lista de lo que falta. Si falla, el código propone la lista tal cual y avisa.

Si el proveedor escribe en otro idioma (lo dice la IA al leer su oferta), el correo va en inglés.
Sin la IA, va en español: la
lista de lo que falta solo está en español.
"""

import logging

from sqlalchemy.orm import Session

from app.config import Config
from app.integraciones import eml, ia
from app.modelos.ofertas import Oferta
from app.servicios import ofertas as servicio_ofertas
from app.servicios.listas import DatosNoValidos
from app.servicios.necesidades import asunto_correos, firma
from app.servicios.ofertas import que_falta

log = logging.getLogger(__name__)

AVISO_SIN_IA = (
    "No se ha podido usar la IA: se ha puesto la lista de lo que falta. Revísala antes de "
    "descargar el correo."
)
NADA_QUE_PEDIR = "A esta oferta no le falta ningún dato que pedir."


def componer_cuerpo(oferta: Oferta, peticion: str, ingles: bool = False, empresa: str = "") -> str:
    necesidad = oferta.necesidad
    numero = f" {oferta.numero_oferta}" if oferta.numero_oferta else ""
    if ingles:
        return (
            "Good morning,\n\n"
            f"Thank you for your quotation{numero} for “{necesidad.titulo}”. To be able to "
            "evaluate it, we also need the following information:\n\n"
            f"{peticion.strip()}\n\n"
            f"To help us follow up, please keep the reference {necesidad.codigo} in the subject "
            "of your reply.\n\n"
            f"{firma(necesidad, empresa, 'Best regards,')}"
        )
    return (
        "Buenos días:\n\n"
        f"Gracias por su oferta{numero} para «{necesidad.titulo}». Para poder valorarla, "
        "necesitamos que nos indiquen también lo siguiente:\n\n"
        f"{peticion.strip()}\n\n"
        f"Para facilitar el seguimiento, mantengan por favor la referencia {necesidad.codigo} "
        "en el asunto de su respuesta.\n\n"
        f"{firma(necesidad, empresa)}"
    )


def _oferta_con_algo_que_pedir(sesion: Session, necesidad_id: int, oferta_id: int):
    oferta = servicio_ofertas.oferta_vigente(sesion, necesidad_id, oferta_id)
    if oferta is None:
        return None, []
    faltan = que_falta(oferta)
    if not faltan:
        raise DatosNoValidos("oferta_id", NADA_QUE_PEDIR)
    return oferta, faltan


def borrador(sesion: Session, config: Config, necesidad_id: int, oferta_id: int) -> dict | None:
    """Correo propuesto: {para, asunto, cuerpo, faltan, avisos, con_ia}. No guarda nada."""
    oferta, faltan = _oferta_con_algo_que_pedir(sesion, necesidad_id, oferta_id)
    if oferta is None:
        return None
    ingles = servicio_ofertas.idioma(oferta) not in servicio_ofertas.IDIOMAS_EN_ESPANOL
    try:
        redactado = ia.redactar_peticion_datos(
            config,
            proveedor=oferta.proveedor.nombre,
            titulo=oferta.necesidad.titulo,
            numero_oferta=oferta.numero_oferta,
            faltan=faltan,
            ingles=ingles,
        )
        peticion, avisos, con_ia = redactado["peticion"], redactado["avisos"], True
    except ia.ErrorIA as error:
        peticion, avisos, con_ia = "", [ia.aviso_sin_ia(error, AVISO_SIN_IA)], False
    if not peticion.strip():
        # Sin la IA, o si no devuelve texto: la lista tal cual, para no perder ningún dato (y en
        # español, que es como está la lista).
        peticion, ingles = "\n".join(f"- {f}" for f in faltan), False
    if ingles:
        avisos = [*avisos, "El proveedor escribe en otro idioma: el correo va en inglés."]
    return {
        "para": ", ".join(servicio_ofertas.destinatarios(oferta)),
        "asunto": asunto_correos(oferta.necesidad),
        "cuerpo": componer_cuerpo(oferta, peticion, ingles, config.empresa_nombre),
        "faltan": faltan,
        "avisos": avisos,
        "con_ia": con_ia,
    }


def generar(
    sesion: Session, necesidad_id: int, oferta_id: int, cuerpo: str | None
) -> tuple[str, bytes] | None:
    """El `.eml` con el cuerpo revisado: (nombre del archivo, contenido). No se guarda."""
    if not (cuerpo or "").strip():
        raise DatosNoValidos("cuerpo", "El cuerpo del correo está vacío.")
    oferta, _ = _oferta_con_algo_que_pedir(sesion, necesidad_id, oferta_id)
    if oferta is None:
        return None
    contenido = eml.componer(
        asunto_correos(oferta.necesidad),
        cuerpo.strip() + "\n",
        para=servicio_ofertas.destinatarios(oferta),
    )
    log.info(
        "Petición de datos que faltan generada (oferta %s, necesidad %s)",
        oferta.id,
        oferta.necesidad.codigo,
    )
    return f"{oferta.necesidad.codigo} datos que faltan.eml", contenido
