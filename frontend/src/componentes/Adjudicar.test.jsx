// CU-005 — Pruebas de la adjudicación y de la información para SAP (la API se simula).
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { descargar } from '../api/descargar.js'
import { filasComoTexto } from '../sap.js'
import Adjudicar from './Adjudicar.jsx'
import InformacionSap from './InformacionSap.jsx'
import { cuerpoDe, respuestaJson, simularFetch } from '../pruebas/api.js'

vi.mock('../api/descargar.js', () => ({ descargar: vi.fn() }))

const ANA = { id: 1, nombre_completo: 'Ana Prueba' }
const NECESIDAD = { id: 7, estado: 'en_evaluacion', peticionario: ANA, adjudicacion_eml: null }
const OFERTA = { id: 30, moneda: 'EUR', proveedor: { id: 2, nombre: 'FICMEC' } }
const FILAS = [
  {
    short_text: 'Rodamiento 6204-2RS inox',
    quantity_requested: '2,5',
    valuation_price: '20,50',
    delivery_date: '15.11.2026',
    requisitioner: 'FICMEC',
  },
]
const BORRADOR = {
  texto_sap_fijo: 'SOLICITADO POR: Ana Prueba\nIR: NO\n',
  descripcion_inversion: 'Cambio de rodamientos.',
  tabla_sap: FILAS,
  correo: { para: 'ofertas@ficmec.test', asunto: '2026102301 | Línea 3 | Rodamientos', cuerpo: 'Buenos días…' },
  bloqueos: [],
  avisos: ['Falta justificar el plazo.'],
}

function simularApi(extra = []) {
  const respuestas = [
    ...extra,
    ['POST', '/api/necesidades/7/adjudicacion/borrador', () => respuestaJson(BORRADOR)],
    ['GET', '/api/peticionarios', () => respuestaJson([{ ...ANA, activo: true }])],
  ]
  return simularFetch(respuestas)
}

describe('Adjudicar', () => {
  it('muestra el texto fijo, la tabla y el correo, y adjudica', async () => {
    const adjudicada = vi.fn()
    simularApi([['POST', '/api/necesidades/7/adjudicacion', () => respuestaJson({ ...NECESIDAD, estado: 'pendiente_solicitud_sap' })]])
    render(<Adjudicar necesidad={NECESIDAD} oferta={OFERTA} onCancelar={vi.fn()} onAdjudicada={adjudicada} />)

    // Al elegir la oferta, la pantalla baja hasta aquí y el foco va al título.
    expect(document.activeElement).toHaveTextContent('Adjudicar a FICMEC')
    expect(await screen.findByText(/SOLICITADO POR: Ana Prueba/)).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Falta justificar el plazo.')
    expect(screen.getByText('20,50')).toBeInTheDocument()
    expect(screen.getByText(/ofertas@ficmec.test/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText(/descripción de la inversión/i), { target: { value: 'Rodamientos de la línea 3.' } })
    await screen.findByRole('option', { name: 'Ana Prueba' })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la adjudicación' }))

    await vi.waitFor(() => expect(adjudicada).toHaveBeenCalled())
    expect(cuerpoDe('POST', '/api/necesidades/7/adjudicacion')).toEqual({
      peticionario_id: 1,
      oferta_id: 30,
      descripcion_inversion: 'Rodamientos de la línea 3.',
      cuerpo_correo: 'Buenos días…',
    })
    expect(descargar).toHaveBeenCalledWith('/api/necesidades/7/adjudicacion.eml')
  })

  it('los errores de la API van a su campo o, si no lo dicen, arriba', async () => {
    let respuesta = () =>
      respuestaJson({ error: 'datos_no_validos', mensaje: 'La descripción es demasiado larga.', detalles: { campo: 'descripcion_inversion' } }, 400)
    simularApi([['POST', '/api/necesidades/7/adjudicacion', () => respuesta()]])
    const adjudicada = vi.fn()
    render(<Adjudicar necesidad={NECESIDAD} oferta={OFERTA} onCancelar={vi.fn()} onAdjudicada={adjudicada} />)
    await screen.findByText(/SOLICITADO POR: Ana Prueba/)
    fireEvent.change(screen.getByLabelText(/descripción de la inversión/i), { target: { value: 'Rodamientos.' } })
    await screen.findByRole('option', { name: 'Ana Prueba' })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la adjudicación' }))
    expect(await screen.findByText('La descripción es demasiado larga.')).toBeInTheDocument()
    expect(screen.getByLabelText(/descripción de la inversión/i)).toHaveAttribute('aria-invalid', 'true')

    respuesta = () => respuestaJson({ error: 'transicion_no_permitida', mensaje: 'La necesidad ya está adjudicada.' }, 409)
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la adjudicación' }))
    expect(await screen.findByText('La necesidad ya está adjudicada.')).toBeInTheDocument()
    expect(adjudicada).not.toHaveBeenCalled()
    expect(descargar).not.toHaveBeenCalledWith('/api/necesidades/7/adjudicacion.eml')
  })

  it('no adjudica sin descripción de la inversión', async () => {
    simularApi()
    render(<Adjudicar necesidad={NECESIDAD} oferta={OFERTA} onCancelar={vi.fn()} onAdjudicada={vi.fn()} />)
    fireEvent.change(await screen.findByLabelText(/descripción de la inversión/i), { target: { value: '  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la adjudicación' }))
    expect(screen.getByText('Escribe la descripción de la inversión.')).toBeInTheDocument()
    expect(cuerpoDe('POST', '/api/necesidades/7/adjudicacion')).toBeUndefined()
  })
})

describe('Adjudicar: texto para SAP', () => {
  it('pone las líneas fijas y la descripción en la misma caja y copia el texto completo', async () => {
    const copiar = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: copiar } })
    simularApi()
    render(<Adjudicar necesidad={NECESIDAD} oferta={OFERTA} onCancelar={vi.fn()} onAdjudicada={vi.fn()} />)
    const caja = await screen.findByLabelText(/descripción de la inversión/i)
    expect(caja.parentElement).toHaveTextContent('SOLICITADO POR: Ana Prueba')
    fireEvent.change(caja, { target: { value: '  Rodamientos de la línea 3.\n' } })
    fireEvent.click(screen.getByRole('button', { name: 'Copiar el texto' }))
    await vi.waitFor(() => expect(copiar).toHaveBeenCalledWith('SOLICITADO POR: Ana Prueba\nIR: NO\nRodamientos de la línea 3.'))
    expect(await screen.findByRole('button', { name: 'Texto copiado' })).toBeInTheDocument()
    vi.unstubAllGlobals()
  })
})

describe('Adjudicar: avisos y volver a preparar', () => {
  it('separa lo que bloquea de lo informativo y no deja confirmar si hay bloqueos', async () => {
    simularApi([
      [
        'POST',
        '/api/necesidades/7/adjudicacion/borrador',
        () => respuestaJson({ ...BORRADOR, tabla_sap: [], bloqueos: ['La oferta no tiene partidas.'] }),
      ],
    ])
    render(<Adjudicar necesidad={NECESIDAD} oferta={OFERTA} onCancelar={vi.fn()} onAdjudicada={vi.fn()} />)
    expect(await screen.findByRole('alert')).toHaveTextContent('La oferta no tiene partidas.')
    expect(screen.getByRole('status')).toHaveTextContent('Falta justificar el plazo.')
    expect(screen.getByRole('button', { name: 'Confirmar la adjudicación' })).toBeDisabled()
  })

  it('vuelve a pedir el borrador a la IA', async () => {
    simularApi()
    render(<Adjudicar necesidad={NECESIDAD} oferta={OFERTA} onCancelar={vi.fn()} onAdjudicada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Volver a preparar' }))
    await screen.findByRole('button', { name: 'Volver a preparar' })
    await vi.waitFor(() =>
      expect(globalThis.fetch.mock.calls.filter(([r]) => r === '/api/necesidades/7/adjudicacion/borrador')).toHaveLength(2),
    )
  })
})

describe('InformacionSap', () => {
  it('muestra el texto y la tabla y los copia', async () => {
    const copiar = vi.fn().mockResolvedValue()
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText: copiar } })
    simularApi([
      [
        'GET',
        '/api/necesidades/7/sap',
        () =>
          respuestaJson({
            proveedor: 'FICMEC',
            texto_sap: 'SOLICITADO POR: Ana Prueba\nIR: NO\nCambio de rodamientos.',
            tabla_sap: FILAS,
            fecha_entrega_inicial: '2026-11-15',
          }),
      ],
    ])
    render(<InformacionSap necesidad={{ ...NECESIDAD, adjudicacion_eml: { id: 1 } }} />)
    expect(await screen.findByText(/Entrega inicial: 15.11.2026/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Copiar el texto' }))
    await vi.waitFor(() => expect(copiar).toHaveBeenCalledWith('SOLICITADO POR: Ana Prueba\nIR: NO\nCambio de rodamientos.'))
    fireEvent.click(screen.getByRole('button', { name: 'Copiar las filas' }))
    await vi.waitFor(() => expect(copiar).toHaveBeenLastCalledWith('Rodamiento 6204-2RS inox\t2,5\t20,50\t15.11.2026\tFICMEC'))
    expect(screen.getByRole('link', { name: 'Descargar el .eml de adjudicación' })).toHaveAttribute('href', '/api/necesidades/7/adjudicacion.eml')
    vi.unstubAllGlobals()
  })

  it('copia varias filas separadas por saltos de línea', () => {
    expect(filasComoTexto([FILAS[0], { ...FILAS[0], short_text: 'Montaje' }]).split('\n')).toHaveLength(2)
  })

  it('un tabulador o un salto de línea dentro de un campo no crea filas ni columnas de más', () => {
    const texto = filasComoTexto([{ ...FILAS[0], short_text: 'Rodamiento\t6204\r\n2RS  inox' }])
    expect(texto.split('\n')).toHaveLength(1)
    expect(texto.split('\t')).toHaveLength(5)
    expect(texto.split('\t')[0]).toBe('Rodamiento 6204 2RS inox')
  })

  it('si se corrige la oferta mientras se adjudica, pide volver a prepararla', async () => {
    simularApi()
    const { rerender } = render(<Adjudicar necesidad={NECESIDAD} oferta={OFERTA} onCancelar={vi.fn()} onAdjudicada={vi.fn()} />)
    await screen.findByText(/SOLICITADO POR: Ana Prueba/)
    await screen.findByRole('option', { name: 'Ana Prueba' })
    expect(screen.getByRole('button', { name: 'Confirmar la adjudicación' })).toBeEnabled()
    // La comparativa se recarga con la oferta corregida (otro objeto, mismo id).
    rerender(<Adjudicar necesidad={NECESIDAD} oferta={{ ...OFERTA, importe_sin_iva: '99' }} onCancelar={vi.fn()} onAdjudicada={vi.fn()} />)
    expect(screen.getByText(/La oferta ha cambiado/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Confirmar la adjudicación' })).toBeDisabled()
  })
})
