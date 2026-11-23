// CU-010 — Pruebas de la página de retrasos de un proveedor (la API se simula).
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import PaginaRetrasosProveedor from './PaginaRetrasosProveedor.jsx'
import { respuestaJson } from '../pruebas/api.js'

function pintar(datos) {
  vi.spyOn(globalThis, 'fetch').mockImplementation(() => respuestaJson(datos))
  render(
    <MemoryRouter initialEntries={['/proveedores/4/retrasos']}>
      <Routes>
        <Route path="/proveedores/:id/retrasos" element={<PaginaRetrasosProveedor />} />
      </Routes>
    </MemoryRouter>,
  )
}

const PROVEEDOR = { id: 4, nombre: 'FICMEC', email: 'ofertas@ficmec.test', activo: true }

describe('PaginaRetrasosProveedor', () => {
  it('muestra las cifras y cada retraso con enlace a su necesidad', async () => {
    pintar({
      proveedor: PROVEEDOR,
      pedidos: 2,
      con_retraso: 1,
      retraso_medio: 5,
      retrasos: [
        {
          necesidad: { id: 9, codigo: '2026102605', titulo: 'Sensor inductivo' },
          fecha_anterior: '2026-11-27',
          fecha_nueva: '2026-11-30',
          dias: 3,
          motivo: 'Transporte',
          peticionario: 'Ana Prueba',
          registrado_en: '2026-11-25T10:00:00+01:00',
        },
      ],
    })
    expect(await screen.findByRole('heading', { name: 'Retrasos de FICMEC' })).toBeInTheDocument()
    expect(screen.getByText('Pedidos adjudicados').nextSibling).toHaveTextContent('2')
    // Lo que cuenta es el retraso medio, junto con la proporción.
    expect(screen.getByText('Retraso medio por pedido').nextSibling).toHaveTextContent('5 días')
    expect(screen.getByText('Pedidos con retraso').nextSibling).toHaveTextContent('1 de 2 (50 %)')
    const fila = screen.getByRole('link', { name: '2026102605' }).closest('tr')
    expect(screen.getByRole('link', { name: '2026102605' })).toHaveAttribute('href', '/necesidades/9')
    expect(within(fila).getByText('Transporte')).toBeInTheDocument()
    expect(fila).toHaveTextContent('27.11.2026')
    expect(fila).toHaveTextContent('30.11.2026')
  })

  it('marca los retrasos avisados que no se cumplieron', async () => {
    pintar({
      proveedor: PROVEEDOR,
      pedidos: 1,
      con_retraso: 0,
      retraso_medio: 0,
      retrasos: [
        {
          necesidad: { id: 9, codigo: '2026102605', titulo: 'Sensor inductivo' },
          fecha_anterior: '2026-11-20',
          fecha_nueva: '2026-11-27',
          dias: 7,
          motivo: 'Material',
          peticionario: 'Ana Prueba',
          registrado_en: '2026-11-15T10:00:00+01:00',
          sin_efecto: true,
        },
      ],
    })
    const fila = (await screen.findByRole('link', { name: '2026102605' })).closest('tr')
    expect(fila).toHaveTextContent('No se cumplió: llegó a tiempo')
  })

  it('explica cuando no hay pedidos', async () => {
    pintar({ proveedor: PROVEEDOR, pedidos: 0, con_retraso: 0, retraso_medio: null, retrasos: [] })
    expect(await screen.findByText('Todavía no se le ha adjudicado ningún pedido.')).toBeInTheDocument()
  })

  it('muestra los comentarios de las entregas', async () => {
    pintar({
      proveedor: PROVEEDOR,
      pedidos: 1,
      con_retraso: 0,
      retraso_medio: 0,
      retrasos: [],
      comentarios: [{ necesidad_id: 9, codigo: '2026102605', titulo: 'Sensor', fecha: '2026-11-19', texto: 'Llegó destrozado.' }],
    })
    const seccion = (await screen.findByRole('heading', { name: 'Comentarios de las entregas' })).closest('section')
    expect(within(seccion).getByRole('link', { name: '2026102605' })).toHaveAttribute('href', '/necesidades/9')
    expect(seccion).toHaveTextContent('Sensor · entregado el 19.11.2026')
    expect(seccion).toHaveTextContent('Llegó destrozado.')
  })
})
