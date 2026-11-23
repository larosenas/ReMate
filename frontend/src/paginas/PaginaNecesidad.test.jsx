// CU-002 — Pruebas del detalle de la necesidad y de «Solicitar ofertas» (la API se simula).
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import { descargar } from '../api/descargar.js'
import PaginaNecesidad from './PaginaNecesidad.jsx'
import { cuerpoDe, llamada, respuestaJson, simularFetch } from '../pruebas/api.js'

vi.mock('../api/descargar.js', () => ({ descargar: vi.fn() }))

const ANA = { id: 1, nombre_completo: 'Ana Prueba' }
const NECESIDAD = {
  id: 7,
  codigo: '2026102301',
  titulo: 'Rodamiento roto',
  proyecto: 'Línea 3',
  descripcion: 'Necesitamos 4 rodamientos.',
  estado: 'necesidad_creada',
  estado_texto: 'Necesidad creada',
  peticionario: ANA,
  creada_en: '2026-10-23T10:00:00+02:00',
  adjuntos: [{ id: 11, nombre_archivo: 'plano.pdf', tipo_mime: 'application/pdf', tamano: 10 }],
  historial: [{ estado_anterior: null, estado_nuevo: 'necesidad_creada', peticionario: ANA, cambiado_en: '2026-10-23T10:00:00+02:00' }],
  proveedores_solicitados: [],
  solicitud_eml: null,
  retrasos: [],
  fecha_entrega_real: null,
}
const PROVEEDORES = [
  { id: 2, nombre: 'Acme', email: 'ventas@acme.test', activo: true },
  { id: 3, nombre: 'Zeta', email: 'ofertas@zeta.test', activo: true },
]
const BORRADOR = {
  asunto: '2026102301 | Línea 3 | Rodamiento roto',
  cuerpo: 'Buenos días:\n\n- 4 rodamientos\n\nUn saludo,\nAna Prueba\nIndustrias Ficticias\n',
  avisos: ['Indica el material.'],
  con_ia: true,
}

function simularApi(extra = []) {
  // Las respuestas de `extra` tienen prioridad sobre las de por defecto.
  const respuestas = [
    ...extra,
    ['GET', '/api/necesidades/7', () => respuestaJson(NECESIDAD)],
    ['GET', '/api/proveedores', () => respuestaJson(PROVEEDORES)],
    ['GET', '/api/peticionarios', () => respuestaJson([{ ...ANA, email: 'ana@ejemplo.test', activo: true }])],
  ]
  return simularFetch(respuestas)
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

describe('PaginaNecesidad', () => {
  it('muestra los datos, los adjuntos y el historial', async () => {
    simularApi()
    pintar()
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('Rodamiento roto')
    expect(screen.getAllByText('2026102301').length).toBeGreaterThan(0)
    expect(screen.getByRole('link', { name: 'plano.pdf' })).toHaveAttribute('href', '/api/necesidades/7/adjuntos/11')
    const historial = screen.getByRole('heading', { name: 'Historial' }).closest('section')
    expect(within(historial).getByRole('listitem')).toHaveTextContent('Necesidad creada')
    expect(within(historial).getByRole('listitem')).toHaveTextContent('Ana Prueba')
    // Paso que toca, para los lectores de pantalla (la pista de los 7 pasos es visual).
    expect(screen.getByText('Paso 2 de 7: Solicitud de ofertas')).toBeInTheDocument()
  })

  it('el historial incluye el paso a otro peticionario al dar de baja al anterior', async () => {
    const LUIS = { id: 4, nombre_completo: 'Luis Prueba' }
    simularApi([
      [
        'GET',
        '/api/necesidades/7',
        () =>
          respuestaJson({
            ...NECESIDAD,
            peticionario: LUIS,
            cambios_peticionario: [
              { peticionario_anterior: ANA, peticionario_nuevo: LUIS, cambiado_en: '2026-10-29T09:00:00+01:00' },
            ],
          }),
      ],
    ])
    pintar()
    const historial = (await screen.findByRole('heading', { name: 'Historial' })).closest('section')
    const pasos = within(historial).getAllByRole('listitem')
    expect(pasos).toHaveLength(2)
    expect(pasos[0]).toHaveTextContent('Necesidad creada')
    expect(pasos[1]).toHaveTextContent('Cambio de peticionario: de Ana Prueba a Luis Prueba')
    expect(pasos[1]).toHaveTextContent('por la baja de Ana Prueba')
  })

  it('pliega los pasos ya hechos y deja el historial a la vista', async () => {
    const EN_COTIZACION = {
      ...NECESIDAD,
      estado: 'en_cotizacion',
      estado_texto: 'En cotización',
      proveedores_solicitados: [{ id: 2, nombre: 'Acme', email: 'ventas@acme.test' }],
      solicitud_eml: { id: 12, nombre_archivo: 'x.eml', tipo_mime: 'message/rfc822', tamano: 1 },
    }
    simularApi([
      ['GET', '/api/necesidades/7', () => respuestaJson(EN_COTIZACION)],
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([])],
    ])
    pintar()
    const necesidad = (await screen.findByText('1. Necesidad')).closest('details')
    expect(necesidad).not.toHaveAttribute('open')
    expect(screen.getByText('2. Solicitud de ofertas').closest('details')).not.toHaveAttribute('open')
    // El historial va siempre a la vista, en la columna lateral.
    expect(screen.getByRole('heading', { name: 'Historial' })).toBeVisible()
    // El resumen se ve sin desplegar.
    expect(screen.getByText('Acme')).toBeInTheDocument()
    fireEvent.click(screen.getByText('1. Necesidad'))
    expect(necesidad).toHaveAttribute('open')
  })

  it('en «Necesidad creada» la necesidad se ve desplegada', async () => {
    simularApi()
    pintar()
    expect((await screen.findByText('1. Necesidad')).closest('details')).toHaveAttribute('open')
  })

  it('«Atrás» lleva a corregir los datos de la necesidad', async () => {
    simularApi()
    pintar()
    expect(await screen.findByRole('link', { name: 'Atrás' })).toHaveAttribute('href', '/necesidades/7/editar')
  })

  it('con 2 proveedores dice cómo irá en SAP y con 3 ya no pide el motivo', async () => {
    const tres = [...PROVEEDORES, { id: 4, nombre: 'Beta', email: 'beta@beta.test', activo: true }]
    simularApi([['GET', '/api/proveedores', () => respuestaJson(tres)]])
    pintar()
    fireEvent.click(await screen.findByRole('checkbox', { name: /Acme/ }))
    fireEvent.click(screen.getByRole('checkbox', { name: /Zeta/ }))
    expect(screen.getByText(/Irá en el texto para SAP: «Solo 2 proveedores consultados por …\.»/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('checkbox', { name: /Beta/ }))
    expect(screen.queryByLabelText('Motivo de pedir oferta a menos de 3 proveedores')).not.toBeInTheDocument()
  })

  it('no prepara el correo sin proveedores', async () => {
    simularApi()
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Preparar correo' }))
    expect(screen.getByText('Elige al menos un proveedor.')).toBeInTheDocument()
  })

  it('prepara el borrador, permite editarlo y genera el .eml', async () => {
    const GENERADA = {
      ...NECESIDAD,
      estado: 'en_cotizacion',
      estado_texto: 'En cotización',
      proveedores_solicitados: [{ id: 3, nombre: 'Zeta', email: 'ofertas@zeta.test' }],
      solicitud_eml: { id: 12, nombre_archivo: '2026102301 solicitud de oferta.eml', tipo_mime: 'message/rfc822', tamano: 99 },
    }
    simularApi([
      ['POST', '/api/necesidades/7/solicitud/borrador', () => respuestaJson(BORRADOR)],
      ['POST', '/api/necesidades/7/solicitud', () => respuestaJson(GENERADA)],
    ])
    pintar()
    fireEvent.click(await screen.findByRole('checkbox', { name: /Zeta/ }))
    // Se quita el plano: no irá en el correo, pero sigue en la necesidad.
    fireEvent.click(screen.getByRole('checkbox', { name: 'plano.pdf' }))
    // Con menos de 3 proveedores hay que dar el motivo, que irá en el texto para SAP.
    fireEvent.click(screen.getByRole('button', { name: 'Preparar correo' }))
    const motivo = screen.getByLabelText('Motivo de pedir oferta a menos de 3 proveedores')
    expect(motivo).toHaveAccessibleDescription(/Con menos de 3 proveedores, indica el motivo\./)
    expect(llamada('POST', '/api/necesidades/7/solicitud/borrador')).toBeUndefined()
    fireEvent.change(motivo, { target: { value: 'ser el fabricante del equipo.' } })
    expect(motivo).toHaveAccessibleDescription('Irá en el texto para SAP: «Proveedor único por ser el fabricante del equipo.»')
    fireEvent.click(screen.getByRole('button', { name: 'Preparar correo' }))

    expect(await screen.findByRole('status')).toHaveTextContent('Indica el material.')
    expect(screen.getByText(BORRADOR.asunto)).toBeInTheDocument()
    expect(cuerpoDe('POST', '/api/necesidades/7/solicitud/borrador')).toEqual({ adjunto_ids: [] })
    const cuerpo = screen.getByLabelText(/Cuerpo del correo/)
    fireEvent.change(cuerpo, { target: { value: 'Texto revisado' } })
    fireEvent.click(screen.getByRole('button', { name: 'Generar solicitud' }))

    expect(await screen.findByRole('link', { name: 'Descargar el .eml' })).toHaveAttribute('href', '/api/necesidades/7/solicitud.eml')
    expect(cuerpoDe('POST', '/api/necesidades/7/solicitud')).toEqual({
      peticionario_id: 1,
      proveedor_ids: [3],
      adjunto_ids: [],
      cuerpo: 'Texto revisado',
      motivo_pocos_proveedores: 'ser el fabricante del equipo.',
    })
    expect(descargar).toHaveBeenCalledWith('/api/necesidades/7/solicitud.eml')
    expect(screen.queryByRole('button', { name: 'Preparar correo' })).not.toBeInTheDocument()
    expect(screen.getByText('En cotización', { selector: 'span' })).toBeInTheDocument()
    // Pasa al paso siguiente: el foco va a su título.
    await vi.waitFor(() => expect(document.activeElement).toHaveTextContent('3. Ofertas'))
  })

  it('al entrar, la pantalla baja hasta el paso que toca', async () => {
    const bajar = vi.spyOn(Element.prototype, 'scrollIntoView')
    simularApi()
    pintar()
    await screen.findByRole('heading', { name: '2. Solicitar ofertas' })
    await vi.waitFor(() => expect(bajar).toHaveBeenCalled())
    expect(bajar.mock.contexts[0]).toHaveTextContent('2. Solicitar ofertas')
    // Al entrar no se mueve el foco: el lector de pantalla empieza por el principio.
    expect(document.activeElement).toBe(document.body)
  })

  it('«Otro proveedor» lo guarda en la lista y lo deja marcado', async () => {
    const NUEVO = { id: 4, nombre: 'Beta', email: 'beta@beta.test', activo: true, avisos: [] }
    let lista = PROVEEDORES
    simularApi([
      ['GET', '/api/proveedores', () => respuestaJson(lista)],
      [
        'POST',
        '/api/proveedores',
        () => {
          lista = [PROVEEDORES[0], NUEVO, PROVEEDORES[1]]
          return respuestaJson(NUEVO, 201)
        },
      ],
    ])
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Otro proveedor…' }))
    fireEvent.change(screen.getByLabelText('Nombre del proveedor'), { target: { value: 'Beta' } })
    fireEvent.change(screen.getByLabelText('Correo del proveedor'), { target: { value: 'beta@beta.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar en la lista' }))
    expect(await screen.findByRole('checkbox', { name: /Beta/ })).toBeChecked()
  })

  it('«Otro proveedor»: cada error va junto a su campo', async () => {
    simularApi([
      [
        'POST',
        '/api/proveedores',
        () =>
          respuestaJson(
            { error: 'datos_no_validos', mensaje: 'El correo «x» no es válido.', detalles: { campo: 'email' } },
            400,
          ),
      ],
    ])
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Otro proveedor…' }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar en la lista' }))
    expect(screen.getByLabelText('Nombre del proveedor')).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Correo del proveedor')).toHaveAttribute('aria-invalid', 'true')
    fireEvent.change(screen.getByLabelText('Nombre del proveedor'), { target: { value: 'Beta' } })
    fireEvent.change(screen.getByLabelText('Correo del proveedor'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar en la lista' }))
    expect(await screen.findByText('El correo «x» no es válido.')).toBeInTheDocument()
    expect(screen.getByLabelText('Nombre del proveedor')).toHaveAttribute('aria-invalid', 'false')
    expect(screen.getByLabelText('Correo del proveedor')).toHaveAccessibleDescription('El correo «x» no es válido.')
  })

  it('«Otro proveedor» con el correo de uno que ya está en la lista: lo marca y lo explica', async () => {
    simularApi([
      [
        'POST',
        '/api/proveedores',
        () =>
          respuestaJson(
            { error: 'correo_duplicado', mensaje: 'Ya existe un registro con el correo ofertas@zeta.test.', detalles: { existente: PROVEEDORES[1] } },
            409,
          ),
      ],
    ])
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Otro proveedor…' }))
    fireEvent.change(screen.getByLabelText('Nombre del proveedor'), { target: { value: 'Zeta S.L.' } })
    fireEvent.change(screen.getByLabelText('Correo del proveedor'), { target: { value: 'ofertas@zeta.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar en la lista' }))
    expect(await screen.findByText(/Se ha marcado «Zeta»/)).toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: /Zeta/ })).toBeChecked()
  })

  it('si la API rechaza un adjunto en «Solicitar ofertas», el error va en «Añadir adjuntos»', async () => {
    simularApi([
      [
        'POST',
        '/api/necesidades/7/adjuntos',
        () => respuestaJson({ error: 'archivo_demasiado_grande', mensaje: 'El archivo «plano.dwg» supera el máximo de 25 MB.', detalles: { archivo: 'plano.dwg' } }, 413),
      ],
    ])
    pintar()
    const zona = await screen.findByLabelText('Añadir adjuntos a la necesidad')
    fireEvent.change(zona, { target: { files: [new File(['x'], 'plano.dwg')] } })
    expect(await screen.findByText('El archivo «plano.dwg» supera el máximo de 25 MB.')).toBeInTheDocument()
    expect(screen.getByLabelText('Añadir adjuntos a la necesidad')).toHaveAttribute('aria-invalid', 'true')
  })

  it('muestra el .eml ya generado en «En cotización»', async () => {
    const EN_COTIZACION = {
      ...NECESIDAD,
      estado: 'en_cotizacion',
      estado_texto: 'En cotización',
      proveedores_solicitados: [{ id: 2, nombre: 'Acme', email: 'ventas@acme.test' }],
      solicitud_eml: { id: 12, nombre_archivo: 'x.eml', tipo_mime: 'message/rfc822', tamano: 1 },
    }
    simularApi([['GET', '/api/necesidades/7', () => respuestaJson(EN_COTIZACION)]])
    pintar()
    const seccion = (await screen.findByText('2. Solicitud de ofertas')).closest('details')
    expect(seccion).toHaveTextContent('Proveedores en copia oculta: Acme.')
    expect(within(seccion).getByRole('link', { name: 'Descargar el .eml' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Preparar correo' })).not.toBeInTheDocument()
  })

  it('tras adjudicar, el paso 3 sigue para consultar las ofertas y marca la adjudicada', async () => {
    const ADJUDICADA = {
      ...NECESIDAD,
      estado: 'pendiente_pedido_sap',
      estado_texto: 'Pendiente pedido SAP',
      proveedores_solicitados: [{ id: 2, nombre: 'Acme', email: 'ventas@acme.test' }],
      solicitud_eml: { id: 12, nombre_archivo: 'x.eml', tipo_mime: 'message/rfc822', tamano: 1 },
      oferta_adjudicada_id: 31,
    }
    const oferta = (id, nombre, sinIva) => ({
      id,
      proveedor: { id, nombre, email: 'x@x.test' },
      numero_oferta: `OF-${id}`,
      moneda: 'EUR',
      importe_sin_iva: sinIva,
      fecha_entrega_estimada: '2026-11-19',
      condiciones_pago: null,
    })
    simularApi([
      ['GET', '/api/necesidades/7', () => respuestaJson(ADJUDICADA)],
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([oferta(31, 'Acme', '100'), oferta(30, 'Zeta', '120')])],
    ])
    pintar()
    const seccion = (await screen.findByText('3. Ofertas')).closest('details')
    const filaAcme = (await within(seccion).findByText('Acme')).closest('tr')
    expect(filaAcme).toHaveTextContent('Adjudicada')
    expect(within(seccion).getByText('Zeta').closest('tr')).not.toHaveTextContent('Adjudicada')
    expect(screen.queryByRole('button', { name: 'Añadir oferta' })).not.toBeInTheDocument()
  })

  it('con el pedido enviado, el paso 6 muestra el pedido y el .eml para descargar', async () => {
    const ENVIADO = {
      ...NECESIDAD,
      estado: 'pendiente_entrega',
      estado_texto: 'Pendiente entrega',
      solicitud_eml: { id: 12, nombre_archivo: 'x.eml', tipo_mime: 'message/rfc822', tamano: 1 },
      numero_pedido_sap: '4500012345',
      pedido_sap: { id: 50, nombre_archivo: 'Pedido 4500012345.pdf', tipo_mime: 'application/pdf', tamano: 4 },
      pedido_sap_eml: { id: 51, nombre_archivo: '2026102301 pedido SAP.eml', tipo_mime: 'message/rfc822', tamano: 9 },
    }
    simularApi([
      ['GET', '/api/necesidades/7', () => respuestaJson(ENVIADO)],
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([])],
    ])
    pintar()
    const seccion = (await screen.findByText('6. Pedido al proveedor')).closest('details')
    expect(seccion).toHaveTextContent('Número de pedido: 4500012345.')
    expect(within(seccion).getByRole('link', { name: 'Pedido 4500012345.pdf' })).toHaveAttribute('href', '/api/necesidades/7/adjuntos/50')
    expect(within(seccion).getByRole('link', { name: 'Descargar el .eml del pedido' })).toHaveAttribute(
      'href',
      '/api/necesidades/7/pedido-sap.eml',
    )
    expect(screen.queryByRole('button', { name: 'Preparar correo' })).not.toBeInTheDocument()
    // CU-009: aún sin recordatorio.
    expect(screen.getByText('Recordatorio de entrega').nextSibling).toHaveTextContent('Se enviará una semana antes')
  })

  it('entregada: el paso 7 muestra la fecha real y los retrasos, y ya no se puede cancelar', async () => {
    const ENTREGADA = {
      ...NECESIDAD,
      estado: 'entregado',
      estado_texto: 'Entregado',
      fecha_entrega_real: '2026-11-24',
      retrasos: [
        { fecha_anterior: '2026-11-20', fecha_nueva: '2026-11-24', motivo: 'Transportista', peticionario: ANA, registrado_en: '2026-11-24T10:00:00+01:00' },
      ],
    }
    simularApi([['GET', '/api/necesidades/7', () => respuestaJson(ENTREGADA)]])
    pintar()
    const seccion = (await screen.findByText('7. Entrega')).closest('details')
    expect(seccion).toHaveTextContent('Entregado el 24.11.2026')
    expect(seccion).toHaveTextContent('20.11.2026 → 24.11.2026')
    expect(seccion).toHaveTextContent('Transportista')
    expect(screen.queryByRole('button', { name: /Cancelar la necesidad/ })).not.toBeInTheDocument()
  })

  it('«Necesidades» vuelve al panel con los filtros con los que se llegó', async () => {
    simularApi()
    render(
      <MemoryRouter initialEntries={[{ pathname: '/necesidades/7', state: { filtros: '?estado=en_curso' } }]}>
        <Routes>
          <Route path="/necesidades/:id" element={<PaginaNecesidad />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByRole('link', { name: 'Necesidades' })).toHaveAttribute('href', '/?estado=en_curso')
  })

  it('una dirección con un id que no es un número no llama a la API', () => {
    simularApi()
    render(
      <MemoryRouter initialEntries={['/necesidades/..%2Fproveedores%2F3']}>
        <Routes>
          <Route path="/necesidades/:id" element={<PaginaNecesidad />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(screen.getByText('Esta pantalla no existe.')).toBeInTheDocument()
    expect(globalThis.fetch).not.toHaveBeenCalled()
  })

  it('cancelar: el foco va al motivo y, con «No cancelar», vuelve al botón', async () => {
    simularApi()
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: /Cancelar la necesidad/ }))
    expect(screen.getByLabelText('Motivo')).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'No cancelar' }))
    await vi.waitFor(() => expect(screen.getByRole('button', { name: /Cancelar la necesidad/ })).toHaveFocus())
  })

  it('avisa si la necesidad no existe', async () => {
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      respuestaJson({ error: 'no_encontrado', mensaje: 'La necesidad no existe.', detalles: {} }, 404),
    )
    pintar()
    expect(await screen.findByRole('alert')).toHaveTextContent('La necesidad no existe.')
  })

  it('cancela la necesidad con un motivo', async () => {
    const CANCELADA = { ...NECESIDAD, estado: 'cancelada', estado_texto: 'Cancelada', motivo_cancelacion: 'Se ha reparado.' }
    simularApi([['POST', '/api/necesidades/7/cancelar', () => respuestaJson(CANCELADA)]])
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Cancelar la necesidad' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la cancelación' }))
    expect(screen.getByText('Indica el motivo de la cancelación.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'Se ha reparado.' } })
    // Espera a la lista de peticionarios del formulario de cancelación (la de «Solicitar ofertas» ya estaba).
    await vi.waitFor(() => expect(screen.getAllByRole('option', { name: 'Ana Prueba' })).toHaveLength(2))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la cancelación' }))
    expect((await screen.findByText(/Motivo de la cancelación/)).parentElement).toHaveTextContent('Se ha reparado.')
    expect(cuerpoDe('POST', '/api/necesidades/7/cancelar')).toEqual({ peticionario_id: 1, motivo: 'Se ha reparado.' })
    expect(screen.queryByRole('button', { name: 'Cancelar la necesidad' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Preparar correo' })).not.toBeInTheDocument()
    // El botón pulsado ya no existe: el foco va al título.
    await vi.waitFor(() => expect(screen.getByRole('heading', { level: 1 })).toHaveFocus())
  })
})
