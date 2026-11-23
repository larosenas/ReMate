import { useEffect } from 'react'
import { obtenerSalud } from '../api/cliente.js'

// Diagnóstico al abrir la aplicación, disponible en F12 → Consola, sin contenido visual.
export default function EstadoServidor() {
  useEffect(() => {
    let activo = true
    obtenerSalud()
      .then((datos) => {
        if (activo) console.info(`[ReMate] Servidor: ${datos.estado} · Base de datos: ${datos.base_de_datos}`)
      })
      .catch((error) => {
        if (activo) console.error(`[ReMate] ${error.message}`)
      })
    return () => {
      activo = false
    }
  }, [])

  return null
}
