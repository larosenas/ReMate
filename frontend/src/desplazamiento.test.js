// Desplazamiento y foco.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { enfocarTitulo, llevarA } from './desplazamiento.js'

function seccion() {
  const elemento = document.createElement('section')
  elemento.innerHTML = '<h2>3. Ofertas</h2><button>Añadir oferta</button>'
  document.body.append(elemento)
  return elemento
}

afterEach(() => {
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
})

describe('llevarA', () => {
  it('sin animación si el sistema pide menos movimiento', () => {
    vi.stubGlobal('matchMedia', (consulta) => ({ matches: consulta.includes('reduce') }))
    const elemento = seccion()
    const bajar = vi.spyOn(elemento, 'scrollIntoView')
    llevarA(elemento)
    expect(bajar).toHaveBeenCalledWith({ behavior: 'auto', block: 'start' })
  })

  it('con animación si no', () => {
    vi.stubGlobal('matchMedia', () => ({ matches: false }))
    const elemento = seccion()
    const bajar = vi.spyOn(elemento, 'scrollIntoView')
    llevarA(elemento, { enfocar: true })
    expect(bajar).toHaveBeenCalledWith({ behavior: 'smooth', block: 'start' })
    expect(document.activeElement).toHaveTextContent('3. Ofertas')
  })
})

describe('enfocarTitulo', () => {
  it('lleva el foco al título, que se puede enfocar sin entrar en el orden del tabulador', () => {
    const elemento = seccion()
    enfocarTitulo(elemento)
    const titulo = elemento.querySelector('h2')
    expect(titulo).toHaveFocus()
    expect(titulo).toHaveAttribute('tabindex', '-1')
  })
})
