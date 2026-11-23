// Simulación de la API en las pruebas del frontend: `fetch` simulado con respuestas por método y
// ruta, y ayudas para comprobar qué se ha llamado.
import { vi } from 'vitest'

export function respuestaJson(datos, estado = 200) {
  return Promise.resolve(new Response(estado === 204 ? null : JSON.stringify(datos), { status: estado }))
}

const noSimulado = (metodo, ruta) => respuestaJson({ mensaje: `no simulado: ${metodo} ${ruta}` }, 500)

// `respuestas`: [[método, ruta, () => respuesta], …]; vale la primera que coincide. Si ninguna
// coincide, `porDefecto(método, ruta)` (por defecto, un error 500 que dice qué faltaba simular).
export function simularFetch(respuestas, porDefecto = noSimulado) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((ruta, opciones = {}) => {
    const metodo = opciones.method ?? 'GET'
    const encontrada = respuestas.find(([m, r]) => m === metodo && r === ruta)
    return encontrada ? encontrada[2]() : porDefecto(metodo, ruta)
  })
}

// Llamadas a `fetch` con ese método (y esa ruta, si se indica).
export function llamadas(metodo, ruta) {
  return globalThis.fetch.mock.calls.filter(([r, o = {}]) => (o.method ?? 'GET') === metodo && (ruta === undefined || r === ruta))
}

export function llamada(metodo, ruta) {
  return llamadas(metodo, ruta)[0]
}

// Cuerpo JSON de la primera llamada con ese método y ruta (undefined si no la hubo).
export function cuerpoDe(metodo, ruta) {
  const encontrada = llamada(metodo, ruta)
  return encontrada && JSON.parse(encontrada[1].body)
}
