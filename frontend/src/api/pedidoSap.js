// CU-007 — Llamadas a la API del pedido SAP: propuesta, borrador del correo y envío.
import { enviarJson, pedirJson } from './cliente.js'

const base = (id) => `/api/necesidades/${id}/pedido-sap`

// Proveedor, correo y número de oferta propuesto (de la oferta revisada o del nombre del adjunto).
export function obtenerPropuestaPedido(id) {
  return pedirJson(`${base(id)}/propuesta`)
}

export function prepararCorreoPedido(id, { numeroOferta, numeroPedido }) {
  return enviarJson(`${base(id)}/borrador`, 'POST', { numero_oferta: numeroOferta, numero_pedido: numeroPedido || null })
}

// Guarda el pedido, genera el .eml y pasa a «Pendiente entrega».
export function enviarPedido(id, { peticionarioId, pedido, numeroOferta, numeroPedido, cuerpo }) {
  const formulario = new FormData()
  formulario.append('peticionario_id', peticionarioId)
  formulario.append('pedido', pedido)
  formulario.append('numero_oferta', numeroOferta)
  if (numeroPedido) formulario.append('numero_pedido', numeroPedido)
  formulario.append('cuerpo_correo', cuerpo)
  return pedirJson(base(id), { method: 'POST', body: formulario })
}

// Número de pedido leído del PDF de SAP («PURCHASE ORDER NO. …»), o null si no lo dice.
export function leerNumeroPedido(id, pedido) {
  const formulario = new FormData()
  formulario.append('pedido', pedido)
  return pedirJson(`${base(id)}/numero`, { method: 'POST', body: formulario })
}

export const urlPedidoEml = (id) => `/api/necesidades/${id}/pedido-sap.eml`
