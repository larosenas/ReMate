// Cliente de la API de ReMate. Todas las llamadas van a rutas relativas /api/...
// (en desarrollo las redirige Vite; en producción las sirve el propio Flask).

class ErrorApi extends Error {
  // `codigo` y `detalles` vienen del formato común de errores de la API
  // ({ error, mensaje, detalles }; ver docs/diseno/api.md).
  constructor(mensaje, estado, codigo = null, detalles = {}) {
    super(mensaje)
    this.name = 'ErrorApi'
    this.estado = estado
    this.codigo = codigo
    this.detalles = detalles
  }
}

export async function pedirJson(ruta, opciones = {}) {
  let respuesta
  try {
    respuesta = await fetch(ruta, {
      ...opciones,
      headers: { Accept: 'application/json', ...opciones.headers },
    })
  } catch {
    throw new ErrorApi('No se puede conectar con el servidor de ReMate.', 0)
  }
  const datos = await respuesta.json().catch(() => null)
  if (!respuesta.ok) {
    throw new ErrorApi(
      datos?.mensaje ?? `Error del servidor (${respuesta.status}).`,
      respuesta.status,
      datos?.error ?? null,
      datos?.detalles ?? {},
    )
  }
  return datos
}

// Un archivo que la API genera al momento y no guarda: devuelve { blob, nombre }. Los
// errores llegan en JSON, como en el resto de la API.
export async function pedirArchivo(ruta, cuerpo) {
  let respuesta
  try {
    respuesta = await fetch(ruta, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cuerpo),
    })
  } catch {
    throw new ErrorApi('No se puede conectar con el servidor de ReMate.', 0)
  }
  if (!respuesta.ok) {
    const datos = await respuesta.json().catch(() => null)
    throw new ErrorApi(datos?.mensaje ?? `Error del servidor (${respuesta.status}).`, respuesta.status, datos?.error ?? null, datos?.detalles ?? {})
  }
  const disposicion = respuesta.headers.get('Content-Disposition') ?? ''
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(disposicion)
  const simple = /filename="?([^";]+)"?/i.exec(disposicion)
  const nombre = utf8 ? decodeURIComponent(utf8[1]) : (simple?.[1] ?? '')
  return { blob: await respuesta.blob(), nombre }
}

export function enviarJson(ruta, metodo, cuerpo) {
  return pedirJson(ruta, {
    method: metodo,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(cuerpo),
  })
}

export function obtenerSalud() {
  return pedirJson('/api/salud')
}
