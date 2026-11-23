// Llevar la pantalla a lo nuevo: el paso que toca, el formulario que se acaba de abrir o, al
// terminar, arriba del todo. Sin animación si la persona ha
// pedido menos movimiento en su sistema.
function comportamiento() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'
}

// Lleva el foco al título del elemento (o al propio elemento), para que con el teclado o con un
// lector de pantalla se siga desde ahí y no desde el botón que ya no existe.
export function enfocarTitulo(elemento) {
  if (!elemento) return
  const titulo = elemento.matches('h1, h2, h3, h4') ? elemento : (elemento.querySelector('h2, h3, h4') ?? elemento)
  if (!titulo.hasAttribute('tabindex')) titulo.setAttribute('tabindex', '-1')
  titulo.focus({ preventScroll: true })
}

// `enfocar`: además lleva el foco a su título. `bloque`: dónde queda (arriba o en el centro).
export function llevarA(elemento, { enfocar = false, bloque = 'start' } = {}) {
  if (!elemento) return
  elemento.scrollIntoView?.({ behavior: comportamiento(), block: bloque })
  if (enfocar) enfocarTitulo(elemento)
}

export function subirArriba() {
  window.scrollTo?.({ top: 0, behavior: comportamiento() })
}
