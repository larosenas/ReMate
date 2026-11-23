// Comprobación de accesibilidad con axe-core (el motor de las herramientas de los navegadores) sobre
// lo que pinta una prueba. Complementa a eslint-plugin-jsx-a11y-x, que solo ve el JSX.
import axe from 'axe-core'

// jsdom no calcula estilos ni colores: el contraste se revisa a mano con la guía de estilo.
const REGLAS_SIN_JSDOM = { 'color-contrast': { enabled: false } }

// Devuelve los problemas de `contenedor` como texto legible («regla: descripción (elementos)»).
export async function problemasDeAccesibilidad(contenedor = document.body) {
  const { violations } = await axe.run(contenedor, { rules: REGLAS_SIN_JSDOM })
  return violations.map(
    (v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(' ')).join(', ')})`,
  )
}
