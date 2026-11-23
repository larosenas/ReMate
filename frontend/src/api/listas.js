// CU-003 — Llamadas a la API de las listas de proveedores y peticionarios.
import { enviarJson, pedirJson } from './cliente.js'

export function listar(ruta, incluirInactivos = false) {
  return pedirJson(incluirInactivos ? `${ruta}?incluir_inactivos=true` : ruta)
}

export function crear(ruta, datos) {
  return enviarJson(ruta, 'POST', datos)
}

export function actualizar(ruta, id, cambios) {
  return enviarJson(`${ruta}/${id}`, 'PATCH', cambios)
}

// CU-010: histórico de retrasos de un proveedor.
export function obtenerRetrasosProveedor(id) {
  return pedirJson(`/api/proveedores/${id}/retrasos`)
}

// Baja definitiva de un registro ya desactivado, con su motivo. Un peticionario con necesidades
// en curso necesita `reasignarA`: el peticionario activo al que pasan.
export function eliminar(ruta, id, motivo, reasignarA = null) {
  return enviarJson(`${ruta}/${id}/baja`, 'POST', reasignarA ? { motivo, reasignar_a: reasignarA } : { motivo })
}
