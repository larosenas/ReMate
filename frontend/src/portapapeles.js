import { useState } from 'react'

// Copiar texto al portapapeles. `navigator.clipboard` solo existe con HTTPS o en localhost; por
// HTTP se usa el método antiguo (`execCommand`). Devuelve false si no se ha podido copiar, para
// que la pantalla pida copiarlo a mano.
async function copiarTexto(texto) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(texto)
      return true
    }
    const area = document.createElement('textarea')
    area.value = texto
    area.setAttribute('readonly', '')
    area.style.position = 'fixed'
    area.style.opacity = '0'
    document.body.append(area)
    area.select()
    const copiado = document.execCommand?.('copy') ?? false
    area.remove()
    return Boolean(copiado)
  } catch {
    return false
  }
}

export const MENSAJE_SIN_COPIAR = 'No se ha podido copiar: selecciona el texto y pulsa Ctrl+C.'

// Botón «Copiar»: `copiado` es null, 'ok' (vuelve a null al cabo de 3 s) o 'error' (se queda,
// para que la pantalla pida copiarlo a mano).
export function useCopiar() {
  const [copiado, setCopiado] = useState(null)
  async function copiar(texto) {
    const bien = await copiarTexto(texto)
    setCopiado(bien ? 'ok' : 'error')
    if (bien) setTimeout(() => setCopiado(null), 3000)
  }
  return [copiado, copiar]
}
