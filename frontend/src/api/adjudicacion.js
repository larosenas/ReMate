// CU-005 — Llamadas a la API de la adjudicación y de la información para SAP.
import { enviarJson, pedirJson } from './cliente.js'

export function prepararAdjudicacion(id, ofertaId) {
  return enviarJson(`/api/necesidades/${id}/adjudicacion/borrador`, 'POST', { oferta_id: ofertaId })
}

// `datos`: peticionario_id, oferta_id, descripcion_inversion y cuerpo_correo.
export function adjudicar(id, datos) {
  return enviarJson(`/api/necesidades/${id}/adjudicacion`, 'POST', datos)
}

export function obtenerInformacionSap(id) {
  return pedirJson(`/api/necesidades/${id}/sap`)
}

export const urlAdjudicacionEml = (id) => `/api/necesidades/${id}/adjudicacion.eml`
