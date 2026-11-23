// CU-008 — Pruebas de «7. Entrega»: retrasos y confirmación (la API se simula).
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { hoyIso } from '../formatos.js'
import SeccionEntrega from './SeccionEntrega.jsx'
import { cuerpoDe, respuestaJson, simularFetch } from '../pruebas/api.js'

const ANA = { id: 1, nombre_completo: 'Ana Prueba' }
const NECESIDAD = {
  id: 7,
  estado: 'pendiente_entrega',
  peticionario: ANA,
  fecha_entrega_prevista: '2026-11-20',
  retrasos: [
    {
      fecha_anterior: '2026-11-13',
      fecha_nueva: '2026-11-20',
      motivo: 'Falta material',
      peticionario: ANA,
      registrado_en: '2026-11-10T09:00:00+01:00',
    },
  ],
}

function simularApi(extra = []) {
  const respuestas = [...extra, ['GET', '/api/peticionarios', () => respuestaJson([{ ...ANA, activo: true }])]]
  return simularFetch(respuestas)
}

describe('SeccionEntrega', () => {
  it('muestra los retrasos y registra uno nuevo con fecha posterior y motivo', async () => {
    const actualizada = vi.fn()
    simularApi([['POST', '/api/necesidades/7/retrasos', () => respuestaJson({ ...NECESIDAD })]])
    render(<SeccionEntrega necesidad={NECESIDAD} onActualizada={actualizada} />)
    expect(screen.getByText('13.11.2026 → 20.11.2026')).toBeInTheDocument()
    expect(screen.getByText(/Falta material/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Registrar un retraso' }))
    fireEvent.change(screen.getByLabelText('Nueva fecha de entrega'), { target: { value: '2026-11-18' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar el retraso' }))
    expect(screen.getByText('La nueva fecha tiene que ser posterior a la prevista (20.11.2026).')).toBeInTheDocument()
    expect(screen.getByText('Indica el motivo del retraso.')).toBeInTheDocument()
    expect(cuerpoDe('POST', '/api/necesidades/7/retrasos')).toBeUndefined()

    fireEvent.change(screen.getByLabelText('Nueva fecha de entrega'), { target: { value: '2026-11-27' } })
    fireEvent.change(screen.getByLabelText('Motivo del retraso'), { target: { value: 'Transporte' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar el retraso' }))
    await vi.waitFor(() => expect(actualizada).toHaveBeenCalled())
    expect(cuerpoDe('POST', '/api/necesidades/7/retrasos')).toEqual({
      peticionario_id: 1,
      fecha_nueva: '2026-11-27',
      motivo: 'Transporte',
    })
  })

  it('confirma la entrega con la fecha de hoy propuesta', async () => {
    const actualizada = vi.fn()
    // Con la entrega prevista muy lejos, hoy no llega tarde.
    const aTiempo = { ...NECESIDAD, fecha_entrega_prevista: '2099-12-31' }
    simularApi([['POST', '/api/necesidades/7/entrega', () => respuestaJson({ ...aTiempo, estado: 'entregado' })]])
    render(<SeccionEntrega necesidad={aTiempo} onActualizada={actualizada} />)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la entrega' }))
    expect(screen.getByLabelText('Fecha en que llegó')).toHaveValue(hoyIso())
    expect(screen.queryByLabelText(/Motivo del retraso/)).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar que ha llegado' }))
    // Antes de cerrar la necesidad pregunta si es seguro; con «No» no se envía nada.
    expect(screen.getByText(/¿Seguro que el pedido ha llegado?/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'No' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'No' }))
    // El foco vuelve al botón que hizo la pregunta.
    expect(screen.getByRole('button', { name: 'Confirmar que ha llegado' })).toHaveFocus()
    expect(globalThis.fetch.mock.calls.some(([r]) => r === '/api/necesidades/7/entrega')).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar que ha llegado' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sí, ha llegado' }))
    await vi.waitFor(() => expect(actualizada).toHaveBeenCalledWith(expect.objectContaining({ estado: 'entregado' })))
    expect(cuerpoDe('POST', '/api/necesidades/7/entrega')).toEqual({
      peticionario_id: 1,
      fecha_entrega_real: hoyIso(),
      motivo_retraso: null,
      comentario: null,
    })
  })

  it('si llega más tarde de lo previsto, pide el motivo del retraso', async () => {
    simularApi([['POST', '/api/necesidades/7/entrega', () => respuestaJson({ ...NECESIDAD, estado: 'entregado' })]])
    render(<SeccionEntrega necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la entrega' }))
    fireEvent.change(screen.getByLabelText('Fecha en que llegó'), { target: { value: '2026-11-24' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar que ha llegado' }))
    expect(screen.getByText('Indica el motivo del retraso.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Motivo del retraso (estaba prevista el 20.11.2026)'), {
      target: { value: 'Transportista' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar que ha llegado' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sí, ha llegado' }))
    await vi.waitFor(() =>
      expect(cuerpoDe('POST', '/api/necesidades/7/entrega')).toEqual({
        peticionario_id: 1,
        fecha_entrega_real: '2026-11-24',
        motivo_retraso: 'Transportista',
        comentario: null,
      }),
    )
  })

  it('formatea la fecha de hoy para los campos de fecha', () => {
    expect(hoyIso(new Date(2026, 0, 5))).toBe('2026-01-05')
  })

  it('cada retraso empieza con la fecha vacía y el foco va y vuelve', async () => {
    simularApi()
    render(<SeccionEntrega necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    const abrir = screen.getByRole('button', { name: 'Registrar un retraso' })
    fireEvent.click(abrir)
    expect(screen.getByLabelText('Nueva fecha de entrega')).toHaveFocus()
    fireEvent.change(screen.getByLabelText('Nueva fecha de entrega'), { target: { value: '2026-12-10' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    // Al cerrar, el foco vuelve al botón que lo abrió.
    await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Registrar un retraso' })).toHaveFocus())
    fireEvent.click(screen.getByRole('button', { name: 'Registrar un retraso' }))
    expect(screen.getByLabelText('Nueva fecha de entrega')).toHaveValue('')
  })

  it('envía el comentario opcional de la entrega', async () => {
    // Con la entrega prevista muy lejos, hoy no llega tarde.
    const aTiempo = { ...NECESIDAD, fecha_entrega_prevista: '2099-12-31' }
    simularApi([['POST', '/api/necesidades/7/entrega', () => respuestaJson({ ...aTiempo, estado: 'entregado' })]])
    render(<SeccionEntrega necesidad={aTiempo} onActualizada={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la entrega' }))
    const campo = screen.getByLabelText('Comentarios (opcional)')
    expect(campo).toHaveAccessibleDescription(/Por ejemplo, si el paquete llegó dañado/)
    fireEvent.change(campo, { target: { value: '  El paquete llegó destrozado.  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar que ha llegado' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sí, ha llegado' }))
    await vi.waitFor(() =>
      expect(cuerpoDe('POST', '/api/necesidades/7/entrega')).toEqual({
        peticionario_id: 1,
        fecha_entrega_real: hoyIso(),
        motivo_retraso: null,
        comentario: 'El paquete llegó destrozado.',
      }),
    )
  })

  it('al cancelar se vacía el comentario', () => {
    simularApi()
    render(<SeccionEntrega necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la entrega' }))
    fireEvent.change(screen.getByLabelText('Comentarios (opcional)'), { target: { value: 'Llegó roto' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la entrega' }))
    expect(screen.getByLabelText('Comentarios (opcional)')).toHaveValue('')
  })
})
