// CU-003 — Pruebas de la lista de proveedores/peticionarios (la API se simula con fetch).
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import TablaLista from './TablaLista.jsx'
import { llamadas, respuestaJson, simularFetch } from '../pruebas/api.js'

const ACME = { id: 1, nombre: 'Acme', email: 'ventas@acme.example', activo: true }
const BETA = { id: 2, nombre: 'Beta', email: 'beta@beta.example', activo: false }

// Responde según método y ruta; `respuestas` es una lista de [comprobación, respuesta].
function simularApi(respuestas) {
  return simularFetch(respuestas, () => respuestaJson([ACME]))
}

function pintar() {
  render(<TablaLista titulo="Proveedores" ruta="/api/proveedores" campoNombre="nombre" etiquetaNombre="Nombre" />)
}

function pintarPeticionarios() {
  render(
    <TablaLista
      titulo="Peticionarios"
      ruta="/api/peticionarios"
      campoNombre="nombre_completo"
      etiquetaNombre="Nombre y apellido"
    />,
  )
}

function rellenar(nombre, email) {
  fireEvent.change(screen.getByLabelText('Nombre'), { target: { value: nombre } })
  fireEvent.change(screen.getByLabelText('Correo'), { target: { value: email } })
  fireEvent.click(screen.getByRole('button', { name: 'Añadir' }))
}

describe('TablaLista', () => {
  it('muestra los registros que devuelve la API', async () => {
    simularApi([])
    pintar()
    expect(await screen.findByText('Acme')).toBeInTheDocument()
    expect(screen.getByText('ventas@acme.example')).toBeInTheDocument()
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/proveedores', expect.any(Object))
  })

  it('pide también los inactivos al marcar «Ver inactivos»', async () => {
    simularApi([['GET', '/api/proveedores?incluir_inactivos=true', () => respuestaJson([ACME, BETA])]])
    pintar()
    await screen.findByText('Acme')
    fireEvent.click(screen.getByLabelText('Ver inactivos'))
    expect(await screen.findByText('Beta')).toBeInTheDocument()
    expect(screen.getByText('Inactivo')).toBeInTheDocument()
  })

  it('no llama a la API si faltan datos en el alta', async () => {
    simularApi([])
    pintar()
    await screen.findByText('Acme')
    rellenar('', '')
    expect(screen.getByText('Nombre es obligatorio.')).toBeInTheDocument()
    expect(screen.getByText('El correo es obligatorio.')).toBeInTheDocument()
    expect(llamadas('POST')).toHaveLength(0)
  })

  it('da de alta un registro y muestra los avisos', async () => {
    simularApi([
      [
        'POST',
        '/api/proveedores',
        () => respuestaJson({ id: 3, nombre: 'Gamma', email: 'g@g.example', activo: true, avisos: ['Ya existe otro con un nombre parecido.'] }, 201),
      ],
    ])
    pintar()
    await screen.findByText('Acme')
    rellenar('Gamma', 'g@g.example')
    expect(await screen.findByText('Ya existe otro con un nombre parecido.')).toBeInTheDocument()
    const [, opciones] = llamadas('POST')[0]
    expect(JSON.parse(opciones.body)).toEqual({ nombre: 'Gamma', email: 'g@g.example' })
  })

  it('marca el campo cuando la API rechaza el correo', async () => {
    simularApi([
      [
        'POST',
        '/api/proveedores',
        () => respuestaJson({ error: 'datos_no_validos', mensaje: 'El correo no es válido.', detalles: { campo: 'email' } }, 400),
      ],
    ])
    pintar()
    await screen.findByText('Acme')
    rellenar('Gamma', 'a@3.3')
    expect(await screen.findByText('El correo no es válido.')).toBeInTheDocument()
  })

  it('ofrece reactivar cuando el correo pertenece a un registro inactivo', async () => {
    simularApi([
      [
        'POST',
        '/api/proveedores',
        () =>
          respuestaJson(
            { error: 'correo_duplicado', mensaje: 'Ese correo ya está registrado.', detalles: { existente: BETA } },
            409,
          ),
      ],
      ['PATCH', '/api/proveedores/2', () => respuestaJson({ ...BETA, activo: true })],
    ])
    pintar()
    await screen.findByText('Acme')
    rellenar('Beta nueva', 'beta@beta.example')
    fireEvent.click(await screen.findByRole('button', { name: 'Reactivarlo' }))
    await vi.waitFor(() => expect(llamadas('PATCH')).toHaveLength(1))
    expect(JSON.parse(llamadas('PATCH')[0][1].body)).toEqual({ activo: true })
  })

  it('desactiva un registro', async () => {
    simularApi([['PATCH', '/api/proveedores/1', () => respuestaJson({ ...ACME, activo: false })]])
    pintar()
    const fila = (await screen.findByText('Acme')).closest('tr')
    fireEvent.click(within(fila).getByRole('button', { name: 'Desactivar Acme' }))
    await vi.waitFor(() => expect(llamadas('PATCH')).toHaveLength(1))
    expect(JSON.parse(llamadas('PATCH')[0][1].body)).toEqual({ activo: false })
  })

  it('edita el nombre y el correo', async () => {
    simularApi([['PATCH', '/api/proveedores/1', () => respuestaJson({ ...ACME, nombre: 'Acme SL' })]])
    pintar()
    const fila = (await screen.findByText('Acme')).closest('tr')
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar Acme' }))
    fireEvent.change(screen.getByLabelText('Editar nombre'), { target: { value: 'Acme SL' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    await vi.waitFor(() => expect(llamadas('PATCH')).toHaveLength(1))
    expect(JSON.parse(llamadas('PATCH')[0][1].body)).toEqual({ nombre: 'Acme SL', email: 'ventas@acme.example' })
  })

  it('muestra «Cargando…» hasta que responde la API', async () => {
    simularApi([])
    pintar()
    expect(screen.getByText('Cargando…')).toBeInTheDocument()
    expect(await screen.findByText('Acme')).toBeInTheDocument()
    expect(screen.queryByText('Cargando…')).not.toBeInTheDocument()
  })

  it('avisa si no puede cargar la lista', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    pintar()
    expect(await screen.findByRole('alert')).toHaveTextContent('No se puede conectar con el servidor de ReMate.')
    expect(screen.queryByText('No hay registros.')).not.toBeInTheDocument()
  })

  it('muestra quién tiene ya el correo aunque esté activo (A2)', async () => {
    simularApi([
      [
        'POST',
        '/api/proveedores',
        () =>
          respuestaJson(
            { error: 'correo_duplicado', mensaje: 'Ese correo ya está registrado.', detalles: { existente: ACME } },
            409,
          ),
      ],
    ])
    pintar()
    await screen.findByText('Acme')
    rellenar('Otro', 'ventas@acme.example')
    expect(await screen.findByText(/El correo ya es de «Acme»/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reactivarlo' })).not.toBeInTheDocument()
  })

  it('avisa antes de guardar un nombre repetido y guarda al confirmar (A3)', async () => {
    simularApi([
      ['POST', '/api/proveedores', () => respuestaJson({ id: 4, nombre: 'ACME', email: 'otro@acme.example', activo: true, avisos: [] }, 201)],
    ])
    pintar()
    await screen.findByText('Acme')
    rellenar('ACME', 'otro@acme.example')
    expect(screen.getByRole('status')).toHaveTextContent('Ya existe «Acme»')
    expect(llamadas('POST')).toHaveLength(0)
    fireEvent.click(screen.getByRole('button', { name: 'Añadir' }))
    await vi.waitFor(() => expect(llamadas('POST')).toHaveLength(1))
  })

  it('muestra en la propia fila el error al editar', async () => {
    simularApi([
      [
        'PATCH',
        '/api/proveedores/1',
        () => respuestaJson({ error: 'datos_no_validos', mensaje: 'El correo no es válido.', detalles: { campo: 'email' } }, 400),
      ],
    ])
    pintar()
    const fila = (await screen.findByText('Acme')).closest('tr')
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar Acme' }))
    fireEvent.change(screen.getByLabelText('Editar correo'), { target: { value: 'a@3.3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    const filaEdicion = screen.getByLabelText('Editar correo').closest('tr')
    expect(await within(filaEdicion).findByText('El correo no es válido.')).toBeInTheDocument()
    expect(screen.getByLabelText('Correo')).toHaveAttribute('aria-invalid', 'false')
  })

  it('cancela la edición sin llamar a la API', async () => {
    simularApi([])
    pintar()
    const fila = (await screen.findByText('Acme')).closest('tr')
    fireEvent.click(within(fila).getByRole('button', { name: 'Editar Acme' }))
    fireEvent.keyDown(screen.getByLabelText('Editar nombre'), { key: 'Escape' })
    expect(screen.queryByLabelText('Editar nombre')).not.toBeInTheDocument()
    expect(llamadas('PATCH')).toHaveLength(0)
  })

  it('envía nombre_completo en la lista de peticionarios', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((ruta, opciones = {}) =>
      opciones.method === 'POST'
        ? respuestaJson({ id: 9, nombre_completo: 'Ana Pérez', email: 'ana@empresa.example', activo: true, avisos: [] }, 201)
        : respuestaJson([]),
    )
    pintarPeticionarios()
    expect(await screen.findByText('No hay registros.')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Nombre y apellido'), { target: { value: 'Ana Pérez' } })
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'ana@empresa.example' } })
    fireEvent.click(screen.getByRole('button', { name: 'Añadir' }))
    await vi.waitFor(() => expect(llamadas('POST')).toHaveLength(1))
    expect(JSON.parse(llamadas('POST')[0][1].body)).toEqual({ nombre_completo: 'Ana Pérez', email: 'ana@empresa.example' })
    // Tras el alta se vuelve a pedir la lista.
    await vi.waitFor(() => expect(llamadas('GET')).toHaveLength(2))
  })

  it('al desactivar ofrece eliminarlo; pide el motivo y, con «Otro», que se escriba', async () => {
    let lista = [ACME]
    simularApi([
      ['GET', '/api/proveedores', () => respuestaJson(lista)],
      [
        'PATCH',
        '/api/proveedores/1',
        () => {
          lista = []
          return respuestaJson({ ...ACME, activo: false })
        },
      ],
      ['POST', '/api/proveedores/1/baja', () => Promise.resolve(new Response(null, { status: 204 }))],
    ])
    render(
      <TablaLista titulo="Proveedores" ruta="/api/proveedores" campoNombre="nombre" etiquetaNombre="Nombre" motivosBaja={['Registro duplicado']} />,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Desactivar Acme' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminarlo definitivamente' }))
    expect(screen.getByText('Eliminar «Acme» definitivamente')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
    expect(screen.getByText('Elige el motivo.')).toBeInTheDocument()
    expect([...screen.getByLabelText('Motivo').options].map((o) => o.textContent)).toEqual(['Elige el motivo…', 'Registro duplicado', 'Otro…'])
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'otro' } })
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
    expect(screen.getByText('Escribe el motivo.', { selector: '[role="alert"]' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Escribe el motivo'), { target: { value: 'Se ha fusionado con Beta' } })
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))

    expect(await screen.findByText('«Acme» eliminado.')).toBeInTheDocument()
    const llamada = globalThis.fetch.mock.calls.find(([r, o = {}]) => o.method === 'POST' && r === '/api/proveedores/1/baja')
    expect(JSON.parse(llamada[1].body)).toEqual({ motivo: 'Otro: Se ha fusionado con Beta' })
  })

  // Si la persona elegida ya no vale, el error va en su selector y la lista
  // se recarga; sin nadie a quien pasarlas, se explica qué hacer.
  async function abrirBajaDeAna({ candidatos, segundaRespuesta }) {
    const ANA = { id: 5, nombre_completo: 'Ana Prueba', email: 'ana@ejemplo.test', activo: false }
    let intentos = 0
    let cargas = 0
    simularFetch([
      ['GET', '/api/peticionarios?incluir_inactivos=true', () => respuestaJson([ANA, ...candidatos()])],
      [
        'GET',
        '/api/peticionarios',
        () => {
          cargas += 1
          return respuestaJson(candidatos())
        },
      ],
      [
        'POST',
        '/api/peticionarios/5/baja',
        () =>
          intentos++
            ? segundaRespuesta()
            : respuestaJson(
                {
                  error: 'necesidades_en_curso',
                  mensaje: 'Lleva 1 necesidad(es) en curso.',
                  detalles: { necesidades: [{ id: 7, codigo: '2026102301', titulo: 'Rodamiento roto' }] },
                },
                409,
              ),
      ],
    ])
    render(
      <TablaLista
        titulo="Peticionarios"
        ruta="/api/peticionarios"
        campoNombre="nombre_completo"
        etiquetaNombre="Nombre y apellido"
        motivosBaja={['Ya no trabaja en la empresa']}
      />,
    )
    fireEvent.click(await screen.findByRole('checkbox', { name: /inactivos/i }))
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar Ana Prueba' }))
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'Ya no trabaja en la empresa' } })
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
    await screen.findByText(/lleva 1 necesidad en curso/)
    return () => cargas
  }

  it('si la persona elegida ya no vale, el error va en «Pasar sus necesidades a» y la lista se recarga', async () => {
    const LUIS = { id: 6, nombre_completo: 'Luis Prueba', email: 'luis@ejemplo.test', activo: true }
    const PEDRO = { id: 8, nombre_completo: 'Pedro Prueba', email: 'pedro@ejemplo.test', activo: true }
    let activos = [LUIS, PEDRO]
    const cargas = await abrirBajaDeAna({
      candidatos: () => activos,
      segundaRespuesta: () => {
        activos = [PEDRO] // otra persona ha desactivado a Luis mientras tanto
        return respuestaJson(
          {
            error: 'datos_no_validos',
            mensaje: 'Elige un peticionario activo para sus necesidades.',
            detalles: { campo: 'reasignar_a' },
          },
          400,
        )
      },
    })
    fireEvent.change(screen.getByLabelText('Pasar sus necesidades a'), { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
    expect(await screen.findByText('Elige un peticionario activo para sus necesidades.')).toBeInTheDocument()
    const selector = screen.getByLabelText('Pasar sus necesidades a')
    expect(selector).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByLabelText('Motivo')).toHaveAttribute('aria-invalid', 'false')
    // Una carga al abrir la tabla, otra con el aviso 409 y otra tras el 400.
    await vi.waitFor(() => expect(cargas()).toBe(3))
    await vi.waitFor(() =>
      expect([...selector.options].map((o) => o.textContent)).toEqual(['Elige un peticionario…', 'Pedro Prueba']),
    )
    expect(selector).toHaveValue('')
  })

  it('sin otro peticionario activo, explica qué hacer', async () => {
    await abrirBajaDeAna({ candidatos: () => [], segundaRespuesta: () => respuestaJson({}, 500) })
    expect(screen.getByText(/No hay otro peticionario activo a quien pasárselas/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Pasar sus necesidades a')).not.toBeInTheDocument()
  })

  it('un peticionario con necesidades en curso: avisa y obliga a elegir a quién pasarlas', async () => {
    const ANA = { id: 5, nombre_completo: 'Ana Prueba', email: 'ana@ejemplo.test', activo: false }
    const LUIS = { id: 6, nombre_completo: 'Luis Prueba', email: 'luis@ejemplo.test', activo: true }
    let intentos = 0
    simularFetch([
      ['GET', '/api/peticionarios?incluir_inactivos=true', () => respuestaJson([ANA, LUIS])],
      ['GET', '/api/peticionarios', () => respuestaJson([LUIS])],
      [
        'POST',
        '/api/peticionarios/5/baja',
        // La primera vez avisa de sus necesidades en curso; la segunda (ya con a quién pasarlas), elimina.
        () =>
          intentos++
            ? Promise.resolve(new Response(null, { status: 204 }))
            : respuestaJson(
                {
                  error: 'necesidades_en_curso',
                  mensaje: 'Lleva 1 necesidad(es) en curso: elige a quién pasárselas.',
                  detalles: { necesidades: [{ id: 7, codigo: '2026102301', titulo: 'Rodamiento roto' }] },
                },
                409,
              ),
      ],
    ])
    render(
      <TablaLista
        titulo="Peticionarios"
        ruta="/api/peticionarios"
        campoNombre="nombre_completo"
        etiquetaNombre="Nombre y apellido"
        motivosBaja={['Ya no trabaja en la empresa']}
      />,
    )
    fireEvent.click(await screen.findByRole('checkbox', { name: /inactivos/i }))
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar Ana Prueba' }))
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'Ya no trabaja en la empresa' } })
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))

    expect(await screen.findByText(/lleva 1 necesidad en curso/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: '2026102301' })).toHaveAttribute('href', '/necesidades/7')
    // Sin elegir a nadie no se elimina; solo se puede elegir a peticionarios activos que no sean ella.
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
    expect(screen.getByText('Elige a quién pasar sus necesidades.')).toBeInTheDocument()
    const selector = screen.getByLabelText('Pasar sus necesidades a')
    expect([...selector.options].map((o) => o.textContent)).toEqual(['Elige un peticionario…', 'Luis Prueba'])
    fireEvent.change(selector, { target: { value: '6' } })
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))

    expect(await screen.findByText('«Ana Prueba» eliminado.')).toBeInTheDocument()
    const bajas = globalThis.fetch.mock.calls.filter(([r, o = {}]) => o.method === 'POST' && r === '/api/peticionarios/5/baja')
    expect(JSON.parse(bajas.at(-1)[1].body)).toEqual({ motivo: 'Ya no trabaja en la empresa', reasignar_a: 6 })
  })

  it('al editar, el error de la API queda enlazado a su campo', async () => {
    simularApi([
      [
        'PATCH',
        '/api/proveedores/1',
        () => respuestaJson({ error: 'datos_no_validos', mensaje: 'El correo «x» no es válido.', detalles: { campo: 'email' } }, 400),
      ],
    ])
    pintar()
    fireEvent.click(await screen.findByRole('button', { name: 'Editar Acme' }))
    fireEvent.change(screen.getByLabelText('Editar correo'), { target: { value: 'x@x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar' }))
    expect(await screen.findByText('El correo «x» no es válido.')).toBeInTheDocument()
    expect(screen.getByLabelText('Editar correo')).toHaveAccessibleDescription('El correo «x» no es válido.')
  })

  it('los inactivos tienen «Eliminar»; los activos, no', async () => {
    simularApi([['GET', '/api/proveedores?incluir_inactivos=true', () => respuestaJson([ACME, BETA])]])
    pintar()
    fireEvent.click(await screen.findByLabelText('Ver inactivos'))
    expect(await screen.findByRole('button', { name: 'Eliminar Beta' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Eliminar Acme' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar Beta' }))
    expect(screen.getByText('Eliminar «Beta» definitivamente')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Cancelar' }))
    expect(screen.queryByText('Eliminar «Beta» definitivamente')).not.toBeInTheDocument()
  })
})
