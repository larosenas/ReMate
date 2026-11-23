// CU-006 — Pruebas de «Meter el pedido en SAP» (la API se simula).
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import ConfirmarPedidoSap from './ConfirmarPedidoSap.jsx'
import { respuestaJson } from '../pruebas/api.js'

const ANA = { id: 1, nombre_completo: 'Ana Prueba' }
const NECESIDAD = { id: 7, estado: 'pendiente_solicitud_sap', peticionario: ANA, fecha_entrega_inicial: '2026-11-15' }

function simularApi() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation((ruta, opciones = {}) =>
    opciones.method === 'POST'
      ? respuestaJson({ ...NECESIDAD, estado: 'pendiente_pedido_sap', fecha_entrega_prevista: '2026-11-27' })
      : respuestaJson([{ ...ANA, activo: true }]),
  )
}

describe('ConfirmarPedidoSap', () => {
  it('propone la fecha inicial y confirma con la fecha elegida', async () => {
    const confirmado = vi.fn()
    simularApi()
    render(<ConfirmarPedidoSap necesidad={NECESIDAD} onConfirmado={confirmado} />)
    const fecha = screen.getByLabelText('Fecha de entrega prevista')
    expect(fecha).toHaveValue('2026-11-15')
    fireEvent.change(fecha, { target: { value: '2026-11-27' } })
    await screen.findByRole('option', { name: 'Ana Prueba' })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar que el pedido está en SAP' }))
    await vi.waitFor(() => expect(confirmado).toHaveBeenCalled())
    const [, opciones] = globalThis.fetch.mock.calls.find(([, o = {}]) => o.method === 'POST')
    expect(JSON.parse(opciones.body)).toEqual({ peticionario_id: 1, fecha_entrega_prevista: '2026-11-27' })
  })

  it('con un plazo sin fecha («3 semanas»), propone el plazo contado desde hoy', () => {
    simularApi()
    const necesidad = { ...NECESIDAD, plazo_entrega_relativo: '3 semanas', fecha_entrega_propuesta: '2026-11-23' }
    render(<ConfirmarPedidoSap necesidad={necesidad} onConfirmado={vi.fn()} />)
    const fecha = screen.getByLabelText('Fecha de entrega prevista')
    expect(fecha).toHaveValue('2026-11-23')
    // La aclaración va ligada al campo: el lector de pantalla la lee al llegar a él.
    expect(fecha).toHaveAccessibleDescription(/El proveedor dio un plazo, no una fecha \(«3 semanas»\)/)
  })

  it('no confirma sin fecha', async () => {
    simularApi()
    render(<ConfirmarPedidoSap necesidad={{ ...NECESIDAD, fecha_entrega_inicial: null }} onConfirmado={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar que el pedido está en SAP' }))
    expect(screen.getByText('Indica la fecha de entrega prevista.')).toBeInTheDocument()
  })
})
