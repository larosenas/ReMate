// Al cerrar un formulario que sustituye al botón que lo abrió, el foco vuelve a ese botón: si no,
// se iría a <body> y con el teclado habría que empezar desde el principio de la página.
import { useEffect, useRef } from 'react'

export function useFocoDeVuelta(abierto) {
  const boton = useRef(null)
  const antes = useRef(abierto)
  useEffect(() => {
    if (antes.current && !abierto) boton.current?.focus()
    antes.current = abierto
  }, [abierto])
  return boton
}
