// Lista de peticionarios activos para los selectores de «quién hace la acción», con el
// peticionario de la necesidad elegido por defecto. Si esa persona está desactivada (no sale en
// la lista), se elige la primera de la lista para no enviar a alguien que no se ve.
import { useEffect, useState } from 'react'
import { listar } from './api/listas.js'

export function usePeticionarios(idInicial) {
  const [peticionarios, setPeticionarios] = useState([])
  const [peticionarioId, setPeticionarioId] = useState(String(idInicial))
  const [error, setError] = useState(null)

  useEffect(() => {
    let vigente = true
    listar('/api/peticionarios')
      .then((lista) => {
        if (!vigente) return
        setPeticionarios(lista)
        setPeticionarioId((actual) =>
          lista.some((p) => String(p.id) === actual) ? actual : String(lista[0]?.id ?? ''),
        )
      })
      .catch((e) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [])

  return { peticionarios, peticionarioId, setPeticionarioId, errorPeticionarios: error }
}
