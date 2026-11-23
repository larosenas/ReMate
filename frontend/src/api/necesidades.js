// CU-001 y CU-002 — Llamadas a la API de necesidades.
import { enviarJson, pedirJson } from './cliente.js'

function formularioCon(datos, adjuntos) {
  const formulario = new FormData()
  Object.entries(datos).forEach(([clave, valor]) => formulario.append(clave, valor))
  adjuntos.forEach((archivo) => formulario.append('adjuntos', archivo))
  return formulario
}

// `datos` lleva titulo, proyecto, peticionario_id y descripcion; `adjuntos` es una lista de File.
// Se envía como multipart/form-data (el navegador pone la cabecera con el separador).
export function crearNecesidad(datos, adjuntos = []) {
  return pedirJson('/api/necesidades', { method: 'POST', body: formularioCon(datos, adjuntos) })
}

export function listarNecesidades() {
  return pedirJson('/api/necesidades')
}

export function obtenerNecesidad(id) {
  return pedirJson(`/api/necesidades/${id}`)
}

// Corrige los datos del paso 1 («Atrás» desde «Solicitar ofertas»); solo en «Necesidad creada».
export function actualizarNecesidad(id, datos) {
  return enviarJson(`/api/necesidades/${id}`, 'PUT', datos)
}

// `datos`: peticionario_id y motivo (obligatorio).
export function cancelarNecesidad(id, datos) {
  return enviarJson(`/api/necesidades/${id}/cancelar`, 'POST', datos)
}

// CU-006: `datos` lleva peticionario_id y fecha_entrega_prevista (AAAA-MM-DD).
export function confirmarPedidoEnSap(id, datos) {
  return enviarJson(`/api/necesidades/${id}/pedido-en-sap`, 'POST', datos)
}

// CU-008: `datos` = { peticionario_id, fecha_nueva, motivo }.
export function registrarRetraso(id, datos) {
  return enviarJson(`/api/necesidades/${id}/retrasos`, 'POST', datos)
}

// CU-008: `datos` = { peticionario_id, fecha_entrega_real, motivo_retraso? }.
export function confirmarEntrega(id, datos) {
  return enviarJson(`/api/necesidades/${id}/entrega`, 'POST', datos)
}

export function anadirAdjuntos(id, adjuntos) {
  return pedirJson(`/api/necesidades/${id}/adjuntos`, { method: 'POST', body: formularioCon({}, adjuntos) })
}

export function prepararSolicitud(id, adjuntoIds) {
  return enviarJson(`/api/necesidades/${id}/solicitud/borrador`, 'POST', { adjunto_ids: adjuntoIds })
}

// `datos`: peticionario_id, proveedor_ids, adjunto_ids y cuerpo.
export function generarSolicitud(id, datos) {
  return enviarJson(`/api/necesidades/${id}/solicitud`, 'POST', datos)
}

export const urlAdjunto = (id, adjuntoId) => `/api/necesidades/${id}/adjuntos/${adjuntoId}`
export const urlSolicitudEml = (id) => `/api/necesidades/${id}/solicitud.eml`
