// CU-004: moneda de cada oferta, sin conversiones (ADR 0010). Desplegables con el símbolo al lado de
// cada precio; todos comparten la moneda de la oferta.
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { simularFetch, respuestaJson, cuerpoDe } from '../pruebas/api.js'
import SelectorMoneda from './SelectorMoneda.jsx'
import EditorOferta from './EditorOferta.jsx'
import SeccionOfertas from './SeccionOfertas.jsx'
import { problemasDeAccesibilidad } from '../pruebas/accesibilidad.js'

const OFERTA = {
  id: 5,
  importe_sin_iva: '10',
  fecha_entrega_estimada: '2026-12-01',
  lineas: [{ descripcion: 'Rodamiento', cantidad: '1', precio_unitario: '10', fecha_entrega: null }],
}
const RUTA = '/api/necesidades/7/ofertas/5'

const editor = (oferta, guardada = vi.fn()) =>
  render(<main><EditorOferta necesidadId={7} oferta={oferta} onGuardada={guardada} onCerrar={vi.fn()} /></main>)

describe('CU-004 monedas', () => {
  it.each([undefined, null])('sin moneda leída (%s), propone EUR y la guarda', async (moneda) => {
    simularFetch([['PATCH', RUTA, () => respuestaJson({ id: 5, moneda: 'EUR' })]])
    const guardada = vi.fn()
    editor({ ...OFERTA, moneda }, guardada)
    expect(screen.getByRole('combobox', { name: 'Moneda del importe sin IVA' })).toHaveValue('EUR')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y dar por revisada' }))
    await waitFor(() => expect(guardada).toHaveBeenCalled())
    expect(cuerpoDe('PATCH', RUTA)).toMatchObject({ moneda: 'EUR' })
  })

  it('un desplegable al lado de cada precio; al cambiar uno cambian todos', async () => {
    simularFetch([['PATCH', RUTA, () => respuestaJson({ id: 5, moneda: 'USD' })]])
    const guardada = vi.fn()
    editor({ ...OFERTA, moneda: 'EUR' }, guardada)
    const selectores = () => [
      screen.getByRole('combobox', { name: 'Moneda del importe sin IVA' }),
      screen.getByRole('combobox', { name: 'Moneda del precio unitario de la línea 1' }),
    ]
    expect(selectores().map((s) => s.value)).toEqual(['EUR', 'EUR'])
    fireEvent.change(selectores()[0], { target: { value: 'USD' } })
    expect(selectores().map((s) => s.value)).toEqual(['USD', 'USD'])
    expect(await problemasDeAccesibilidad()).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y dar por revisada' }))
    await waitFor(() => expect(guardada).toHaveBeenCalled())
    expect(cuerpoDe('PATCH', RUTA)).toMatchObject({ moneda: 'USD', importe_sin_iva: '10' })
  })

  it('muestra símbolos y, si la IA leyó otra moneda, su código', () => {
    render(<SelectorMoneda etiqueta="Moneda" value="SEK" onChange={vi.fn()} />)
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toEqual(['€', '$', '£', 'zł', 'CHF', '¥', 'SEK'])
    expect(screen.getByRole('combobox', { name: 'Moneda' })).toHaveValue('SEK')
  })

  it('una moneda fuera de la lista se puede volver a elegir tras cambiarla', () => {
    const oferta = { id: 5, moneda: 'SEK', importe_sin_iva: '10', fecha_entrega_estimada: '2026-12-01', lineas: [] }
    render(<main><EditorOferta necesidadId={7} oferta={oferta} onGuardada={vi.fn()} onCerrar={vi.fn()} /></main>)
    const selector = () => screen.getByRole('combobox', { name: 'Moneda del importe sin IVA' })
    fireEvent.change(selector(), { target: { value: 'EUR' } })
    expect([...selector().options].map((o) => o.value)).toContain('SEK')
  })

  it('avisa en la comparativa si las ofertas vienen en monedas distintas, sin convertir', async () => {
    const usd = { id: 30, moneda: 'USD', proveedor: { id: 2, nombre: 'Acme' }, importe_sin_iva: '125', revisada: true, lineas: [], archivos: [], avisos: [] }
    const eur = { ...usd, id: 31, moneda: 'EUR', proveedor: { id: 3, nombre: 'Zeta' } }
    simularFetch([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([usd, eur])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([usd, eur])],
      ['GET', '/api/proveedores', () => respuestaJson([])],
      ['GET', '/api/peticionarios', () => respuestaJson([])],
    ])
    render(<SeccionOfertas necesidad={{ id: 7, estado: 'en_evaluacion', peticionario: { id: 1, nombre_completo: 'Ana Prueba' }, proveedores_solicitados: [] }} onActualizada={vi.fn()} />)
    expect(await screen.findByText(/monedas distintas \(EUR, USD\)/)).toBeInTheDocument()
    const tabla = within(screen.getByRole('region', { name: 'Tabla de la comparativa' }))
    expect(tabla.getAllByText('125,00 $').length).toBeGreaterThan(0)
    expect(tabla.getAllByText('125,00 €').length).toBeGreaterThan(0)
  })
})
