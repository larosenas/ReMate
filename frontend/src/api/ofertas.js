// CU-004 — Llamadas a la API de ofertas.
import { enviarJson, pedirArchivo, pedirJson } from './cliente.js'

const base = (id) => `/api/necesidades/${id}/ofertas`

export function listarOfertas(id) {
  return pedirJson(base(id))
}

// `adjuntos`: lista de { archivo: File, tipo: 'pdf' | 'excel' | 'word' | 'imagen' | 'otro' }.
// Sin `proveedorId`, el backend busca el proveedor por el remitente del correo.
// `confirmarSustitucion`: si el proveedor ya tiene oferta, la nueva la sustituye (CU-004 4c).
// `adjuntosCorreo`: los adjuntos del propio correo que se guardan, { indice, tipo } (los da
// `leerCorreo`).
// `anadirDatos`: el correo es la respuesta del proveedor y completa su oferta.
export function subirOferta(id, { proveedorId, correo, adjuntos = [], adjuntosCorreo = [], confirmarSustitucion = false, anadirDatos = false }) {
  const formulario = new FormData()
  if (proveedorId) formulario.append('proveedor_id', proveedorId)
  if (confirmarSustitucion) formulario.append('confirmar_sustitucion', 'true')
  if (anadirDatos) formulario.append('anadir_datos', 'true')
  formulario.append('correo', correo)
  adjuntos.forEach(({ archivo, tipo }) => {
    formulario.append('adjuntos', archivo)
    formulario.append('tipos_adjunto', tipo)
  })
  adjuntosCorreo.forEach(({ indice, tipo }) => {
    formulario.append('adjuntos_correo', String(indice))
    formulario.append('tipos_adjunto_correo', tipo)
  })
  return pedirJson(base(id), { method: 'POST', body: formulario })
}

// Paso previo a subir: lee el correo sin guardar nada. Devuelve sus adjuntos
// ({ indice, nombre, tamano }) y el proveedor que reconoce (o `aviso_proveedor`).
export function leerCorreo(id, correo) {
  const formulario = new FormData()
  formulario.append('correo', correo)
  return pedirJson(`${base(id)}/correo`, { method: 'POST', body: formulario })
}

export function corregirOferta(id, ofertaId, cambios) {
  return enviarJson(`${base(id)}/${ofertaId}`, 'PATCH', cambios)
}

// «Reanalizar con IA»: los datos de la IA sustituyen a los de la oferta, que queda sin revisar.
export function reanalizarOferta(id, ofertaId) {
  return pedirJson(`${base(id)}/${ofertaId}/analisis`, { method: 'POST' })
}

export function borrarOferta(id, ofertaId) {
  return pedirJson(`${base(id)}/${ofertaId}`, { method: 'DELETE' })
}

// «Analizar y comparar»: en «En cotización» pasa a evaluación (`peticionarioId`);
// la IA lee a la vez las ofertas sin analizar. Devuelve { necesidad, avisos }; la comparativa se
// pide aparte.
export function analizarYComparar(id, peticionarioId) {
  return enviarJson(`/api/necesidades/${id}/evaluacion`, 'POST', { peticionario_id: peticionarioId })
}

// Cada oferta lleva `destacados` ({ importe, entrega, retrasos }: 'mejor', 'peor' o null), que
// calcula el backend solo con todas las ofertas revisadas.
export function obtenerComparativa(id) {
  return pedirJson(`/api/necesidades/${id}/comparativa`)
}

// Petición de los datos que faltan: el borrador (lo redacta la IA) y el .eml con el
// cuerpo revisado, que no se guarda en el servidor.
export function borradorPeticionDatos(id, ofertaId) {
  return pedirJson(`${base(id)}/${ofertaId}/peticion-datos/borrador`, { method: 'POST' })
}

export function generarPeticionDatos(id, ofertaId, cuerpo) {
  return pedirArchivo(`${base(id)}/${ofertaId}/peticion-datos`, { cuerpo })
}
