// Pruebas de casos límite de la interfaz, encontrados al revisar el código.
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import App from './App.jsx'
import Adjudicar from './componentes/Adjudicar.jsx'
import ConfirmarPedidoSap from './componentes/ConfirmarPedidoSap.jsx'
import SubirOferta from './componentes/SubirOferta.jsx'
import TablaSap from './componentes/TablaSap.jsx'
import { aDecimal, fechaCorta, fechaHora } from './formatos.js'
import PaginaNecesidad from './paginas/PaginaNecesidad.jsx'
import { llamadas, respuestaJson, simularFetch } from './pruebas/api.js'

vi.mock('./api/descargar.js', () => ({ descargar: vi.fn() }))

const ANA = { id: 1, nombre_completo: 'Ana Prueba', email: 'ana@ejemplo.test', activo: true }

// `respuestas`: lista de [método, ruta, función]; la primera que coincide gana.
function simularApi(respuestas) {
  return simularFetch(respuestas)
}

const archivo = (nombre, tamano = 10) => {
  const f = new File(['x'], nombre)
  Object.defineProperty(f, 'size', { value: tamano })
  return f
}

describe('formatos', () => {
  it('lee el punto como separador de miles y limita los decimales', () => {
    expect(aDecimal('1.250')).toBe('1250')
    expect(aDecimal('12.500.000')).toBe('12500000')
    expect(aDecimal('1,250.50')).toBeNaN()
    expect(aDecimal('10,555', 2)).toBeNaN()
    expect(aDecimal('10,55', 2)).toBe('10.55')
  })

  it('muestra las fechas con hora en la hora local', () => {
    const iso = '2026-10-22T09:15:00+02:00'
    const d = new Date(iso)
    expect(fechaCorta(iso)).toBe(`${String(d.getDate()).padStart(2, '0')}.10.2026`)
    expect(fechaHora(iso)).toMatch(/^\d\d\.10\.2026 \d\d:\d\d$/)
  })
})

describe('Corregir → Nueva necesidad', () => {
  it('al pasar a «Nueva necesidad» el formulario empieza vacío', async () => {
    const NECESIDAD = {
      id: 7,
      codigo: '2026102301',
      titulo: 'Rodamiento roto',
      proyecto: 'Línea 3',
      descripcion: 'Texto',
      estado: 'necesidad_creada',
      peticionario: ANA,
      adjuntos: [],
    }
    simularApi([
      ['GET', '/api/necesidades/7', () => respuestaJson(NECESIDAD)],
      ['GET', '/api/peticionarios', () => respuestaJson([ANA])],
    ])
    render(
      <MemoryRouter initialEntries={['/necesidades/7/editar']}>
        <App />
      </MemoryRouter>,
    )
    expect(await screen.findByLabelText('Título')).toHaveValue('Rodamiento roto')
    fireEvent.click(screen.getByRole('link', { name: 'Nueva necesidad' }))
    expect(await screen.findByRole('heading', { level: 1, name: 'Nueva necesidad' })).toBeInTheDocument()
    expect(screen.getByLabelText('Título')).toHaveValue('')
  })
})

describe('SubirOferta', () => {
  const NECESIDAD = { id: 7, proveedores_solicitados: [{ id: 2, nombre: 'Acme' }] }
  const PROVEEDORES = [
    { id: 2, nombre: 'Acme' },
    { id: 3, nombre: 'Zeta' },
  ]

  function pintar(subida = vi.fn()) {
    render(<SubirOferta necesidad={NECESIDAD} proveedores={PROVEEDORES} onSubida={subida} onCancelar={vi.fn()} />)
  }

  it('no muestra como elegido un correo que no es .eml ni .msg', () => {
    simularApi([])
    pintar()
    fireEvent.change(screen.getByLabelText('Correo de la oferta (.eml o .msg)', { selector: 'input' }), {
      target: { files: [archivo('oferta.pdf')] },
    })
    expect(screen.getByText('El correo de la oferta tiene que ser un archivo .eml o .msg.')).toBeInTheDocument()
    expect(screen.queryByText('oferta.pdf')).not.toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Archivos elegidos' })).not.toBeInTheDocument()
  })

  it('un adjunto de más de 25 MB no sustituye al que ya estaba elegido', () => {
    simularApi([])
    pintar()
    const adjunto = screen.getByLabelText('Adjunto 1', { selector: 'input' })
    fireEvent.change(adjunto, { target: { files: [archivo('oferta.pdf')] } })
    fireEvent.change(adjunto, { target: { files: [archivo('enorme.pdf', 26 * 1024 * 1024)] } })
    expect(screen.getByText('oferta.pdf')).toBeInTheDocument()
    expect(screen.queryByText('enorme.pdf')).not.toBeInTheDocument()
  })

  it('pide confirmación antes de sustituir una oferta del mismo proveedor', async () => {
    const subida = vi.fn()
    let primera = true
    simularApi([
      [
        'POST',
        '/api/necesidades/7/ofertas',
        () => {
          if (primera) {
            primera = false
            return respuestaJson(
              { error: 'oferta_existente', mensaje: 'Acme ya tiene una oferta. Si la nueva la sustituye, confírmalo.', detalles: {} },
              409,
            )
          }
          return respuestaJson({ id: 31, avisos: [] }, 201)
        },
      ],
    ])
    pintar(subida)
    fireEvent.change(screen.getByLabelText('Correo de la oferta (.eml o .msg)', { selector: 'input' }), {
      target: { files: [archivo('oferta.eml')] },
    })
    // Primero se leen los adjuntos del correo; hasta entonces no se puede subir.
    await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Subir oferta' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Subir oferta' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Sí, sustituir la oferta anterior' }))
    await vi.waitFor(() => expect(subida).toHaveBeenCalled())
    const [primeraLlamada, segunda] = llamadas('POST', '/api/necesidades/7/ofertas')
    expect(primeraLlamada[1].body.get('confirmar_sustitucion')).toBeNull()
    expect(segunda[1].body.get('confirmar_sustitucion')).toBe('true')
  })

  it('«Añadir datos del proveedor» completa su oferta en lugar de sustituirla', async () => {
    const subida = vi.fn()
    let primera = true
    simularApi([
      [
        'POST',
        '/api/necesidades/7/ofertas',
        () => {
          if (primera) {
            primera = false
            return respuestaJson({ error: 'oferta_existente', mensaje: 'Acme ya tiene una oferta.', detalles: {} }, 409)
          }
          return respuestaJson({ id: 30, avisos: ['La respuesta del proveedor completa: embalaje.'] }, 200)
        },
      ],
    ])
    pintar(subida)
    fireEvent.change(screen.getByLabelText('Correo de la oferta (.eml o .msg)', { selector: 'input' }), {
      target: { files: [archivo('respuesta.msg')] },
    })
    await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Subir oferta' })).toBeEnabled())
    fireEvent.click(screen.getByRole('button', { name: 'Subir oferta' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Añadir datos del proveedor' }))
    await vi.waitFor(() => expect(subida).toHaveBeenCalledWith(expect.objectContaining({ id: 30 })))
    const segunda = llamadas('POST', '/api/necesidades/7/ofertas')[1][1].body
    expect(segunda.get('anadir_datos')).toBe('true')
    expect(segunda.get('confirmar_sustitucion')).toBeNull()
  })

  it('«Otro» da de alta el proveedor y lo deja elegido', async () => {
    simularApi([
      ['POST', '/api/proveedores', () => respuestaJson({ id: 9, nombre: 'Beta', email: 'beta@beta.example', activo: true, avisos: [] }, 201)],
    ])
    pintar()
    fireEvent.change(screen.getByLabelText('Proveedor'), { target: { value: 'otro' } })
    fireEvent.change(screen.getByLabelText('Nombre del proveedor'), { target: { value: 'Beta' } })
    fireEvent.change(screen.getByLabelText('Correo del proveedor'), { target: { value: 'beta@beta.example' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar en la lista' }))
    await vi.waitFor(() => expect(screen.getByLabelText('Proveedor')).toHaveValue('9'))
    expect(screen.getByRole('option', { name: 'Beta' })).toBeInTheDocument()
  })
})

describe('Adjudicar', () => {
  it('si falla la preparación, se puede volver a intentar', async () => {
    let intentos = 0
    simularApi([
      [
        'POST',
        '/api/necesidades/7/adjudicacion/borrador',
        () => {
          intentos += 1
          return intentos === 1
            ? respuestaJson({ error: 'x', mensaje: 'Error del servidor.', detalles: {} }, 500)
            : respuestaJson({
                texto_sap_fijo: 'SOLICITADO POR: Ana Prueba\nIR: NO\n',
                descripcion_inversion: 'Texto',
                tabla_sap: [],
                correo: { para: 'a@b.example', asunto: 'Asunto', cuerpo: 'Cuerpo' },
                bloqueos: [],
                avisos: [],
              })
        },
      ],
      ['GET', '/api/peticionarios', () => respuestaJson([ANA])],
    ])
    render(<Adjudicar necesidad={{ id: 7, peticionario: ANA }} oferta={{ id: 30, proveedor: { nombre: 'Acme' } }} onCancelar={vi.fn()} onAdjudicada={vi.fn()} />)
    expect(await screen.findByText('Error del servidor.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Volver a preparar' }))
    expect(await screen.findByText(/SOLICITADO POR: Ana Prueba/)).toBeInTheDocument()
  })

  it('pide confirmación antes de perder los cambios al volver a preparar', async () => {
    simularApi([
      [
        'POST',
        '/api/necesidades/7/adjudicacion/borrador',
        () =>
          respuestaJson({
            texto_sap_fijo: 'SOLICITADO POR: Ana Prueba\nIR: NO\n',
            descripcion_inversion: 'Texto',
            tabla_sap: [],
            correo: { para: 'a@b.example', asunto: 'Asunto', cuerpo: 'Cuerpo' },
            bloqueos: [],
            avisos: [],
          }),
      ],
      ['GET', '/api/peticionarios', () => respuestaJson([ANA])],
    ])
    render(<Adjudicar necesidad={{ id: 7, peticionario: ANA }} oferta={{ id: 30, proveedor: { nombre: 'Acme' } }} onCancelar={vi.fn()} onAdjudicada={vi.fn()} />)
    fireEvent.change(await screen.findByLabelText(/descripción de la inversión/i), { target: { value: 'Mi texto' } })
    fireEvent.click(screen.getByRole('button', { name: 'Volver a preparar' }))
    expect(screen.getByText(/Se perderán los cambios/)).toBeInTheDocument()
    expect(llamadas('POST', '/api/necesidades/7/adjudicacion/borrador')).toHaveLength(1)
  })
})

describe('Portapapeles sin HTTPS', () => {
  it('avisa si no se puede copiar', async () => {
    vi.stubGlobal('navigator', { ...navigator, clipboard: undefined })
    document.execCommand = vi.fn(() => false)
    render(<TablaSap filas={[{ short_text: 'A', quantity_requested: '1', valuation_price: '1,00', delivery_date: '01.01.2027', requisitioner: 'X' }]} />)
    fireEvent.click(screen.getByRole('button', { name: 'Copiar las filas' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('selecciona el texto y pulsa Ctrl+C')
    vi.unstubAllGlobals()
    delete document.execCommand
  })
})

describe('CU-006 en el detalle', () => {
  const BASE = {
    id: 7,
    codigo: '2026102301',
    titulo: 'Rodamientos',
    proyecto: 'Línea 3',
    descripcion: 'Texto',
    peticionario: ANA,
    creada_en: '2026-10-23T10:00:00+02:00',
    adjuntos: [],
    historial: [],
    proveedores_solicitados: [],
    solicitud_eml: null,
    adjudicacion_eml: null,
    oferta_adjudicada_id: null,
    fecha_entrega_inicial: '2026-11-15',
    motivo_cancelacion: null,
  }

  function pintar() {
    render(
      <MemoryRouter initialEntries={['/necesidades/7']}>
        <Routes>
          <Route path="/necesidades/:id" element={<PaginaNecesidad />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('en «Pendiente solicitud SAP» muestra el paso 5', async () => {
    simularApi([
      ['GET', '/api/necesidades/7', () => respuestaJson({ ...BASE, estado: 'pendiente_solicitud_sap', estado_texto: 'Pendiente solicitud SAP', fecha_entrega_prevista: null })],
      ['GET', '/api/peticionarios', () => respuestaJson([ANA])],
    ])
    pintar()
    expect(await screen.findByRole('heading', { name: '5. Meter el pedido en SAP' })).toBeInTheDocument()
  })

  it('muestra la fecha prevista y la de la oferta si son distintas', async () => {
    simularApi([
      ['GET', '/api/necesidades/7', () => respuestaJson({ ...BASE, estado: 'pendiente_pedido_sap', estado_texto: 'Pendiente pedido SAP', fecha_entrega_prevista: '2026-11-27' })],
    ])
    pintar()
    // En la columna de datos: la fecha prevista y, debajo, la de la oferta.
    expect((await screen.findByText('Entrega prevista')).parentElement).toHaveTextContent(
      'Entrega prevista27.11.2026La oferta decía 15.11.2026',
    )
  })

  it('muestra el error de la API al confirmar', async () => {
    simularApi([
      [
        'POST',
        '/api/necesidades/7/pedido-en-sap',
        () =>
          respuestaJson(
            { error: 'datos_no_validos', mensaje: 'La fecha de entrega prevista no puede ser anterior a la creación de la necesidad.', detalles: { campo: 'fecha_entrega_prevista' } },
            400,
          ),
      ],
      ['GET', '/api/peticionarios', () => respuestaJson([ANA])],
    ])
    render(<ConfirmarPedidoSap necesidad={{ ...BASE, estado: 'pendiente_solicitud_sap' }} onConfirmado={vi.fn()} />)
    await screen.findByRole('option', { name: 'Ana Prueba' })
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar que el pedido está en SAP' }))
    expect(await screen.findByText(/no puede ser anterior a la creación/)).toBeInTheDocument()
  })
})
