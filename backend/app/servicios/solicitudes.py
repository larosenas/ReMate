"""CU-002 — Solicitar ofertas a proveedores.

Reglas (docs/casos-de-uso/CU-002-solicitar-ofertas.md):
- Solo desde «Necesidad creada»; al generar la solicitud pasa a «En cotización».
- La IA redacta solo la parte central (qué se pide); asunto, saludo, referencia y firma los
  pone la aplicación. Si la IA falla, se usa la descripción tal cual y, si no dice cuántas
  unidades se piden, se avisa. No se exige a los proveedores ningún formato de
  oferta, pero siempre se les pide el precio y el plazo de entrega.
- Un único .eml con todos los proveedores en CCO, asunto `AAAAMMDDNN | Proyecto | Título` (el
  mismo en todos los correos de la necesidad, `asunto_correos`) y los adjuntos elegidos. La
  aplicación no envía el correo.
- Quitar un adjunto en este paso no lo borra de la necesidad.
- Se pide oferta a 3 proveedores como mínimo; con menos, hay que dar el motivo, que va al texto
  para SAP.
"""

import re
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Config
from app.integraciones import archivos, eml, ia
from app.modelos.listas import Proveedor
from app.modelos.necesidades import Adjunto, CambioEstado, Necesidad, ProveedorSolicitado
from app.servicios.listas import DatosNoValidos, peticionario_activo
from app.servicios.necesidades import asunto_correos, firma, necesidad_en

AVISO_SIN_IA = (
    "No se ha podido usar la IA: se ha puesto la descripción tal cual. Revísala antes de generar "
    "la solicitud."
)
# Si no redacta la IA, que es quien lo avisaba (CU-002): sin una cifra, el proveedor no sabe
# cuántas unidades ofertar.
AVISO_SIN_CANTIDAD = (
    "La descripción no dice cuántas unidades se piden: añádelo en el correo antes de generarlo."
)
MINIMO_PROVEEDORES = 3
_CANTIDAD = re.compile(
    r"\d|\b(dos|tres|cuatro|cinco|seis|siete|ocho|nueve|diez|once|doce|quince|veinte|"
    r"treinta|cincuenta|cien|mil|docena)\b",
    re.IGNORECASE,
)


def componer_cuerpo(
    necesidad: Necesidad, peticion: str, con_adjuntos: bool, empresa: str = ""
) -> str:
    """Plantilla del correo (CU-002) con la parte central ya redactada.

    No se pide a los proveedores un formato de oferta: cada uno usa el suyo. Se les pide
    siempre el precio y el plazo de entrega y mantener la referencia en el asunto.
    """
    adjuntos = "Adjuntamos la documentación disponible. " if con_adjuntos else ""
    de_empresa = f" de {empresa.strip()}" if empresa.strip() else ""
    return (
        "Buenos días:\n\n"
        f"Desde el departamento de ingeniería{de_empresa} les solicitamos oferta para lo siguiente:"
        f"\n\n{peticion.strip()}\n\n"
        "En su oferta, indiquen por favor el precio y el plazo de entrega.\n\n"
        f"{adjuntos}Para facilitar el seguimiento, mantengan por favor la referencia "
        f"{necesidad.codigo} en el asunto de su respuesta.\n\n"
        "Quedamos a la espera de su respuesta.\n\n"
        f"{firma(necesidad, empresa)}"
    )


def _necesidad_en_creada(
    sesion: Session, necesidad_id: int, bloquear: bool = False
) -> Necesidad | None:
    # Al generar la solicitud se bloquea la fila: un doble clic no la genera dos veces.
    return necesidad_en(sesion, necesidad_id, "necesidad_creada", bloquear)


def _adjuntos_elegidos(necesidad: Necesidad, adjunto_ids: list[int]) -> list[Adjunto]:
    propios = {a.id: a for a in necesidad.adjuntos if a.tipo == "necesidad"}
    if any(i not in propios for i in adjunto_ids):
        raise DatosNoValidos("adjunto_ids", "Algún adjunto no pertenece a esta necesidad.")
    return [propios[i] for i in dict.fromkeys(adjunto_ids)]


def borrador(
    sesion: Session, config: Config, necesidad_id: int, adjunto_ids: list[int]
) -> dict | None:
    """Prepara el correo: {asunto, cuerpo, avisos, con_ia}. None si la necesidad no existe."""
    necesidad = _necesidad_en_creada(sesion, necesidad_id)
    if necesidad is None:
        return None
    elegidos = _adjuntos_elegidos(necesidad, adjunto_ids)
    try:
        redactado = ia.redactar_peticion(
            config, necesidad.descripcion, [a.nombre_archivo for a in elegidos]
        )
        peticion, avisos, con_ia = redactado["peticion"], redactado["avisos"], True
    except ia.ErrorIA as error:
        peticion, con_ia = necesidad.descripcion, False
        avisos = [ia.aviso_sin_ia(error, AVISO_SIN_IA)]
        if not _CANTIDAD.search(necesidad.descripcion):
            avisos.append(AVISO_SIN_CANTIDAD)
    return {
        "asunto": asunto_correos(necesidad),
        "cuerpo": componer_cuerpo(
            necesidad, peticion, con_adjuntos=bool(elegidos), empresa=config.empresa_nombre
        ),
        "avisos": avisos,
        "con_ia": con_ia,
    }


def generar(
    sesion: Session,
    raiz_archivos: Path,
    necesidad_id: int,
    *,
    peticionario_id: int | None,
    proveedor_ids: list[int],
    adjunto_ids: list[int],
    cuerpo: str | None,
    motivo_pocos_proveedores: str | None = None,
) -> Necesidad | None:
    """Genera el .eml, guarda los proveedores solicitados y pasa a «En cotización».
    `motivo_pocos_proveedores`: obligatorio con menos de 3 proveedores; con 3 o más, no se
    guarda."""
    necesidad = _necesidad_en_creada(sesion, necesidad_id, bloquear=True)
    if necesidad is None:
        return None
    if not (cuerpo or "").strip():
        raise DatosNoValidos("cuerpo", "El cuerpo del correo está vacío.")
    peticionario = peticionario_activo(sesion, peticionario_id, "Elige quién hace la solicitud.")
    proveedores = [sesion.get(Proveedor, i) for i in dict.fromkeys(proveedor_ids)]
    if not proveedores:
        raise DatosNoValidos("proveedor_ids", "Elige al menos un proveedor.")
    if any(p is None or not p.activo for p in proveedores):
        raise DatosNoValidos("proveedor_ids", "Algún proveedor no existe o está desactivado.")
    # Sin el punto final: en SAP sigue a «Proveedor único por …» y la aplicación pone el suyo.
    motivo = (motivo_pocos_proveedores or "").strip().rstrip(".").strip()
    if len(proveedores) < MINIMO_PROVEEDORES and not motivo:
        raise DatosNoValidos(
            "motivo_pocos_proveedores",
            f"Con menos de {MINIMO_PROVEEDORES} proveedores, indica el motivo.",
        )
    elegidos = _adjuntos_elegidos(necesidad, adjunto_ids)
    for adjunto in elegidos:
        if not archivos.ruta_absoluta(raiz_archivos, adjunto.ruta).is_file():
            raise DatosNoValidos(
                "adjunto_ids", f"El adjunto «{adjunto.nombre_archivo}» no está en el servidor."
            )

    contenido = eml.componer(
        asunto_correos(necesidad),
        cuerpo.strip() + "\n",
        cco=[p.email for p in proveedores],
        adjuntos=[
            eml.ArchivoAdjunto(
                a.nombre_archivo,
                a.tipo_mime,
                archivos.ruta_absoluta(raiz_archivos, a.ruta).read_bytes(),
            )
            for a in elegidos
        ],
    )
    nombre = f"{necesidad.codigo} solicitud de oferta.eml"
    ruta = archivos.guardar(raiz_archivos, necesidad.codigo, nombre, contenido)
    try:
        necesidad.adjuntos.append(
            Adjunto(
                tipo="solicitud",
                nombre_archivo=nombre,
                ruta=ruta,
                tipo_mime="message/rfc822",
                tamano=len(contenido),
            )
        )
        necesidad.solicitados.extend(ProveedorSolicitado(proveedor=p) for p in proveedores)
        necesidad.motivo_pocos_proveedores = (
            " ".join(motivo.split()) if len(proveedores) < MINIMO_PROVEEDORES else None
        )
        necesidad.historial.append(
            CambioEstado(
                estado_anterior=necesidad.estado,
                estado_nuevo="en_cotizacion",
                peticionario=peticionario,
            )
        )
        necesidad.estado = "en_cotizacion"
        sesion.commit()
    except Exception:
        sesion.rollback()
        archivos.borrar(raiz_archivos, ruta)
        raise
    return necesidad
