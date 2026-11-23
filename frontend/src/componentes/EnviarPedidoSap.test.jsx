// CU-007 — Pruebas de «6. Enviar el pedido SAP al proveedor» (la API se simula).
import { act, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { descargar } from '../api/descargar.js'
import EnviarPedidoSap from './EnviarPedidoSap.jsx'
import { llamada, respuestaJson, simularFetch } from '../pruebas/api.js'

vi.mock('../api/descargar.js', () => ({ descargar: vi.fn() }))

const ANA = { id: 1, nombre_completo: 'Ana Prueba' }
const NECESIDAD = { id: 7, estado: 'pendiente_pedido_sap', peticionario: ANA }
const PROPUESTA = {
  proveedor: 'FICMEC',
  para: 'ofertas@ficmec.test',
  numero_oferta: 'OF-77',
  origen_numero_oferta: 'oferta',
  fecha_entrega_prevista: '2026-11-20',
}
const CORREO = {
  para: 'ofertas@ficmec.test',
  asunto: '2026102301 | Línea 3 | Rodamientos',
  cuerpo: 'Buenos días:\n\nLes adjuntamos el pedido.\n',
}

function simularApi(extra = []) {
  const respuestas = [
    ...extra,
    ['GET', '/api/necesidades/7/pedido-sap/propuesta', () => respuestaJson(PROPUESTA)],
    ['POST', '/api/necesidades/7/pedido-sap/borrador', () => respuestaJson(CORREO)],
    ['GET', '/api/peticionarios', () => respuestaJson([{ ...ANA, activo: true }])],
  ]
  return simularFetch(respuestas)
}

const elegirPedido = (nombre = 'Pedido 4500012345.pdf') =>
  fireEvent.change(screen.getByLabelText('Pedido oficial de SAP'), {
    target: { files: [new File(['%PDF'], nombre)] },
  })

describe('EnviarPedidoSap', () => {
  it('dice si se ha avisado a los avisados del pedido SAP', async () => {
    simularApi()
    const { rerender } = render(<EnviarPedidoSap necesidad={NECESIDAD} onEnviado={vi.fn()} />)
    expect(await screen.findByDisplayValue('OF-77')).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent('Todavía no se ha podido avisar a los avisados del pedido SAP')
    rerender(<EnviarPedidoSap necesidad={{ ...NECESIDAD, aviso_pedido_sap_en: '2026-11-17T09:30:00Z' }} onEnviado={vi.fn()} />)
    expect(screen.getByText(/Se ha avisado a los avisados del pedido SAP \(último aviso: 17\.11\.2026/)).toBeInTheDocument()
    expect(screen.queryByText(/Todavía no se ha podido avisar/)).not.toBeInTheDocument()
    // Justo al confirmar el paso 5, lo que diga la API (por ejemplo, una dirección rechazada).
    const rechazo = 'El servidor de correo ha rechazado alguna dirección de la lista «Avisados del pedido SAP».'
    rerender(
      <EnviarPedidoSap
        necesidad={{ ...NECESIDAD, aviso_pedido_sap_en: '2026-11-17T09:30:00Z', avisos: [rechazo] }}
        onEnviado={vi.fn()}
      />,
    )
    expect(screen.getByRole('status')).toHaveTextContent(rechazo)
  })

  it('prepara el correo con el número propuesto, deja retocarlo y genera el .eml', async () => {
    const enviado = vi.fn()
    simularApi([['POST', '/api/necesidades/7/pedido-sap', () => respuestaJson({ ...NECESIDAD, estado: 'pendiente_entrega' })]])
    render(<EnviarPedidoSap necesidad={NECESIDAD} onEnviado={enviado} />)
    expect(await screen.findByDisplayValue('OF-77')).toBeInTheDocument()
    expect(screen.getByText('Es el número de la oferta revisada.')).toBeInTheDocument()

    // Sin pedido no se prepara.
    fireEvent.click(screen.getByRole('button', { name: 'Preparar correo' }))
    expect(await screen.findByText('Sube el pedido oficial de SAP.')).toBeInTheDocument()

    elegirPedido()
    fireEvent.change(screen.getByLabelText('Número de pedido de SAP (opcional)'), { target: { value: '4500012345' } })
    fireEvent.click(screen.getByRole('button', { name: 'Preparar correo' }))
    expect(await screen.findByText(CORREO.asunto)).toBeInTheDocument()
    expect(JSON.parse(llamada('POST', '/api/necesidades/7/pedido-sap/borrador')[1].body)).toEqual({
      numero_oferta: 'OF-77',
      numero_pedido: '4500012345',
    })

    fireEvent.change(screen.getByLabelText('Cuerpo del correo'), { target: { value: 'Texto retocado.' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generar el .eml' }))
    await vi.waitFor(() => expect(enviado).toHaveBeenCalledWith(expect.objectContaining({ estado: 'pendiente_entrega' })))
    const formulario = llamada('POST', '/api/necesidades/7/pedido-sap')[1].body
    expect(formulario.get('pedido').name).toBe('Pedido 4500012345.pdf')
    expect(formulario.get('numero_oferta')).toBe('OF-77')
    expect(formulario.get('numero_pedido')).toBe('4500012345')
    expect(formulario.get('cuerpo_correo')).toBe('Texto retocado.')
    expect(formulario.get('peticionario_id')).toBe('1')
    expect(descargar).toHaveBeenCalledWith('/api/necesidades/7/pedido-sap.eml')
  })

  it('si la API rechaza el pedido al generar el .eml, vuelve al primer paso con el error en el pedido', async () => {
    simularApi([
      [
        'POST',
        '/api/necesidades/7/pedido-sap',
        () => respuestaJson({ error: 'datos_no_validos', mensaje: 'El pedido tiene que ser un PDF.', detalles: { campo: 'pedido' } }, 400),
      ],
    ])
    const enviado = vi.fn()
    render(<EnviarPedidoSap necesidad={NECESIDAD} onEnviado={enviado} />)
    await screen.findByDisplayValue('OF-77')
    elegirPedido()
    fireEvent.click(screen.getByRole('button', { name: 'Preparar correo' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Generar el .eml' }))
    expect(await screen.findByText('El pedido tiene que ser un PDF.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Preparar correo' })).toBeInTheDocument()
    expect(enviado).not.toHaveBeenCalled()
    expect(descargar).not.toHaveBeenCalledWith('/api/necesidades/7/pedido-sap.eml')
  })

  it('un error de la API sin campo (otra persona ya lo envió) se muestra arriba y no descarga nada', async () => {
    simularApi([
      [
        'POST',
        '/api/necesidades/7/pedido-sap',
        () => respuestaJson({ error: 'transicion_no_permitida', mensaje: 'La necesidad no está en «Pendiente pedido SAP».' }, 409),
      ],
    ])
    render(<EnviarPedidoSap necesidad={NECESIDAD} onEnviado={vi.fn()} />)
    await screen.findByDisplayValue('OF-77')
    elegirPedido()
    fireEvent.click(screen.getByRole('button', { name: 'Preparar correo' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Generar el .eml' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('La necesidad no está en «Pendiente pedido SAP».')
  })

  it('sin número propuesto, pide escribirlo; «Cambiar los datos» vuelve al primer paso', async () => {
    simularApi([
      ['GET', '/api/necesidades/7/pedido-sap/propuesta', () => respuestaJson({ ...PROPUESTA, numero_oferta: null, origen_numero_oferta: null })],
    ])
    render(<EnviarPedidoSap necesidad={NECESIDAD} onEnviado={vi.fn()} />)
    expect(await screen.findByText('No se ha encontrado: escríbelo.')).toBeInTheDocument()
    elegirPedido()
    fireEvent.click(screen.getByRole('button', { name: 'Preparar correo' }))
    expect(await screen.findByText('Indica el número de oferta del proveedor.')).toBeInTheDocument()
    expect(llamada('POST', '/api/necesidades/7/pedido-sap/borrador')).toBeUndefined()

    fireEvent.change(screen.getByLabelText('Número de oferta del proveedor'), { target: { value: 'IND-5521' } })
    fireEvent.click(screen.getByRole('button', { name: 'Preparar correo' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Cambiar los datos' }))
    expect(screen.getByDisplayValue('IND-5521')).toBeInTheDocument()
    // El pedido elegido sigue a la vista.
    expect(screen.getByText('Pedido 4500012345.pdf')).toBeInTheDocument()
  })
})

describe('EnviarPedidoSap: número de pedido leído del PDF', () => {
  const NUMERO = '/api/necesidades/7/pedido-sap/numero'

  it('propone el número del PDF y dice de dónde sale', async () => {
    simularApi([['POST', NUMERO, () => respuestaJson({ numero_pedido: '4510000001' })]])
    render(<EnviarPedidoSap necesidad={NECESIDAD} onEnviado={vi.fn()} />)
    await screen.findByText(/Es el número de la oferta revisada/)
    elegirPedido()
    expect(await screen.findByDisplayValue('4510000001')).toBeInTheDocument()
    expect(screen.getByText('Leído del PDF del pedido: compruébalo.')).toBeInTheDocument()
    expect(llamada('POST', NUMERO)[1].body.get('pedido').name).toBe('Pedido 4500012345.pdf')
    // Si se cambia a mano, ya no se dice que sale del PDF.
    fireEvent.change(screen.getByLabelText('Número de pedido de SAP (opcional)'), { target: { value: '4510000009' } })
    expect(screen.queryByText('Leído del PDF del pedido: compruébalo.')).not.toBeInTheDocument()
  })

  it('no pisa un número escrito a mano', async () => {
    simularApi([['POST', NUMERO, () => respuestaJson({ numero_pedido: '4510000001' })]])
    render(<EnviarPedidoSap necesidad={NECESIDAD} onEnviado={vi.fn()} />)
    await screen.findByText(/Es el número de la oferta revisada/)
    fireEvent.change(screen.getByLabelText('Número de pedido de SAP (opcional)'), { target: { value: '123' } })
    elegirPedido()
    await vi.waitFor(() => expect(llamada('POST', NUMERO)).toBeDefined())
    expect(screen.getByLabelText('Número de pedido de SAP (opcional)')).toHaveValue('123')
  })

  it('si el PDF no lo dice, el campo se queda vacío', async () => {
    simularApi([['POST', NUMERO, () => respuestaJson({ numero_pedido: null })]])
    render(<EnviarPedidoSap necesidad={NECESIDAD} onEnviado={vi.fn()} />)
    await screen.findByText(/Es el número de la oferta revisada/)
    elegirPedido()
    await vi.waitFor(() => expect(llamada('POST', NUMERO)).toBeDefined())
    expect(screen.getByLabelText('Número de pedido de SAP (opcional)')).toHaveValue('')
    expect(screen.queryByText(/Leído del PDF/)).not.toBeInTheDocument()
  })

  it('ignora el número del PDF anterior si su respuesta llega tarde', async () => {
    let responderPrimero
    let peticion = 0
    simularApi([
      [
        'POST',
        NUMERO,
        () => {
          peticion += 1
          if (peticion === 1) return new Promise((resolve) => { responderPrimero = resolve })
          return respuestaJson({ numero_pedido: '2222222222' })
        },
      ],
    ])
    render(<EnviarPedidoSap necesidad={NECESIDAD} onEnviado={vi.fn()} />)
    await screen.findByText(/Es el número de la oferta revisada/)
    elegirPedido('pedido-1.pdf')
    elegirPedido('pedido-2.pdf')
    expect(await screen.findByDisplayValue('2222222222')).toBeInTheDocument()

    await act(async () => {
      responderPrimero(await respuestaJson({ numero_pedido: '1111111111' }))
    })
    expect(screen.getByLabelText('Número de pedido de SAP (opcional)')).toHaveValue('2222222222')
  })
})
