// ADR 0015 — Pruebas del modo admin (la API se simula). El enlace del pie, en App.test.jsx.
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import PaginaAdmin from './PaginaAdmin.jsx'
import { cuerpoDe, llamadas, respuestaJson, simularFetch } from '../pruebas/api.js'

const ESTADO = {
  necesidades: { necesidad_creada: 1, entregado: 3 },
  archivos: { cantidad: 12, bytes: 4_500_000 },
  disco: { total: 100_000_000_000, libre: 40_000_000_000 },
  ultima_copia: { carpeta: 'remate-20261117-020000', completa: true },
  ia_30_dias: { llamadas: 5, entrada: 12000, salida: 3000 },
  avisos_y_errores_7_dias: 2,
}
const NECESIDAD = {
  id: 7,
  codigo: '2026111701',
  titulo: 'Rodamientos',
  estado: 'pendiente_entrega',
  historial: [{ estado_anterior: 'pendiente_pedido_sap', estado_nuevo: 'pendiente_entrega' }],
  fecha_entrega_prevista: '2026-11-20',
  fecha_entrega_real: null,
  numero_pedido_sap: '4500012345',
  comentario_entrega: null,
}

function pintar(respuestas, ruta = '/admin') {
  simularFetch([
    ['GET', '/api/admin/estado', () => respuestaJson(ESTADO)],
    ['GET', '/api/admin/registros?nivel=WARNING', () => respuestaJson([])],
    ...respuestas,
  ])
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <Routes>
        <Route path="/" element={<p>Panel</p>} />
        <Route path="/admin" element={<PaginaAdmin />} />
      </Routes>
    </MemoryRouter>,
  )
}

const conSesion = () => ['GET', '/api/admin/sesion', () => respuestaJson({ activa: true, configurado: true })]

describe('Modo admin', () => {
  it('pide la contraseña, dice si no vale y entra', async () => {
    let activa = false
    pintar([
      ['GET', '/api/admin/sesion', () => respuestaJson({ activa, configurado: true })],
      [
        'POST',
        '/api/admin/sesion',
        () => {
          const { clave } = JSON.parse(globalThis.fetch.mock.calls.at(-1)[1].body)
          if (clave !== 'buena') return respuestaJson({ error: 'clave_incorrecta', mensaje: 'La contraseña no es correcta.' }, 401)
          activa = true
          return respuestaJson({ activa: true, configurado: true })
        },
      ],
    ])
    const clave = await screen.findByLabelText('Contraseña del modo admin')
    fireEvent.change(clave, { target: { value: 'mala' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByText('La contraseña no es correcta.')).toBeInTheDocument()
    fireEvent.change(clave, { target: { value: 'buena' } })
    fireEvent.click(screen.getByRole('button', { name: 'Entrar' }))
    expect(await screen.findByRole('heading', { name: 'Estado del servidor' })).toBeInTheDocument()
    expect(await screen.findByText('remate-20261117-020000')).toBeInTheDocument()
    expect(screen.getByText(/5 llamadas/)).toBeInTheDocument()
  })

  it('sin configurar lo dice', async () => {
    pintar([['GET', '/api/admin/sesion', () => respuestaJson({ activa: false, configurado: false })]])
    expect(await screen.findByText(/falta ADMIN_CLAVE_HASH/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Contraseña del modo admin')).not.toBeInTheDocument()
  })

  it('busca una necesidad, deshace su último paso y la borra escribiendo su código', async () => {
    const deshecha = { ...NECESIDAD, estado: 'pendiente_pedido_sap', historial: [{ estado_anterior: 'pendiente_solicitud_sap', estado_nuevo: 'pendiente_pedido_sap' }] }
    pintar([
      conSesion(),
      ['GET', '/api/necesidades', () => respuestaJson([{ id: 7, codigo: '2026111701' }])],
      ['GET', '/api/necesidades/7', () => respuestaJson(NECESIDAD)],
      ['POST', '/api/admin/necesidades/7/deshacer', () => respuestaJson(deshecha)],
      ['POST', '/api/admin/necesidades/7/borrado', () => respuestaJson({ codigo: '2026111701', archivos: 4, no_borrados: 0 })],
    ])
    fireEvent.change(await screen.findByLabelText('Código de la necesidad'), { target: { value: '2026111701' } })
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Deshacer «Pendiente pedido SAP» → «Pendiente entrega»' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sí, deshacer' }))
    expect(await screen.findByText('Paso deshecho: ahora está en «Pendiente pedido SAP».')).toBeInTheDocument()
    // Con el estado que tenía: si otro lo ha deshecho a la vez, el servidor no deshace otro paso.
    expect(cuerpoDe('POST', '/api/admin/necesidades/7/deshacer')).toEqual({ estado: 'pendiente_entrega' })

    const borrar = screen.getByRole('button', { name: 'Borrar definitivamente' })
    expect(borrar).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Escribe 2026111701 para confirmar'), { target: { value: '2026111701' } })
    fireEvent.click(borrar)
    expect(await screen.findByText('Necesidad 2026111701 borrada, con 4 archivo(s).')).toBeInTheDocument()
    expect(cuerpoDe('POST', '/api/admin/necesidades/7/borrado')).toEqual({ codigo: '2026111701' })
  })

  it('corrige solo los datos que cambian', async () => {
    pintar([
      conSesion(),
      ['GET', '/api/necesidades', () => respuestaJson([{ id: 7, codigo: '2026111701' }])],
      ['GET', '/api/necesidades/7', () => respuestaJson(NECESIDAD)],
      ['PATCH', '/api/admin/necesidades/7', () => respuestaJson({ ...NECESIDAD, numero_pedido_sap: '4500099999' })],
    ])
    fireEvent.change(await screen.findByLabelText('Código de la necesidad'), { target: { value: '2026111701' } })
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    fireEvent.change(await screen.findByLabelText('Número de pedido SAP'), { target: { value: '4500099999' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar las correcciones' }))
    expect(await screen.findByText('Datos corregidos.')).toBeInTheDocument()
    expect(cuerpoDe('PATCH', '/api/admin/necesidades/7')).toEqual({ numero_pedido_sap: '4500099999' })
  })

  it('las tareas se prueban sin confirmar y se ejecutan confirmando', async () => {
    pintar([
      conSesion(),
      ['POST', '/api/admin/tareas/caducidad', () => respuestaJson({ tarea: 'caducidad', prueba: true, resumen: { archivos: 3, bytes: 900, logs: 10, no_borrados: 0 } })],
    ])
    const fila = (await screen.findByText('Caducidad de archivos y registros')).closest('li')
    fireEvent.click(within(fila).getByRole('button', { name: 'Probar' }))
    expect(await screen.findByText('Caducidad de archivos y registros (prueba)')).toBeInTheDocument()
    expect(screen.getByText('archivos: 3')).toBeInTheDocument()
    fireEvent.click(within(fila).getByRole('button', { name: 'Ejecutar' }))
    expect(llamadas('POST', '/api/admin/tareas/caducidad')).toHaveLength(1)
    expect(within(fila).getByRole('button', { name: 'Sí, ejecutar' })).toBeInTheDocument()
  })

  it('si la sesión caduca vuelve a pedir la contraseña', async () => {
    pintar([
      conSesion(),
      ['POST', '/api/admin/tareas/avisos', () => respuestaJson({ error: 'sin_sesion_admin', mensaje: 'Entra en el modo admin.' }, 401)],
    ])
    const fila = (await screen.findByText('Avisos del pedido SAP')).closest('li')
    fireEvent.click(within(fila).getByRole('button', { name: 'Probar' }))
    expect(await screen.findByText('La sesión ha caducado: vuelve a entrar.')).toBeInTheDocument()
    expect(screen.getByLabelText('Contraseña del modo admin')).toBeInTheDocument()
    vi.restoreAllMocks()
  })

  it('el error de una corrección se marca en su campo', async () => {
    pintar([
      conSesion(),
      ['GET', '/api/necesidades', () => respuestaJson([{ id: 7, codigo: '2026111701' }])],
      ['GET', '/api/necesidades/7', () => respuestaJson(NECESIDAD)],
      [
        'PATCH',
        '/api/admin/necesidades/7',
        () => respuestaJson({ error: 'datos_no_validos', mensaje: 'Indica la fecha de entrega prevista.', detalles: { campo: 'fecha_entrega_prevista' } }, 400),
      ],
    ])
    fireEvent.change(await screen.findByLabelText('Código de la necesidad'), { target: { value: '2026111701' } })
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    const prevista = await screen.findByLabelText('Fecha de entrega prevista')
    fireEvent.change(prevista, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar las correcciones' }))
    expect(await screen.findByText('Indica la fecha de entrega prevista.')).toBeInTheDocument()
    expect(prevista).toHaveAttribute('aria-invalid', 'true')
  })

  it('distingue COPIAS_DIR sin configurar y una carpeta que no se puede leer', async () => {
    simularFetch([
      conSesion(),
      ['GET', '/api/admin/estado', () => respuestaJson({ ...ESTADO, ultima_copia: { carpeta: null, completa: false, accesible: false } })],
      ['GET', '/api/admin/registros?nivel=WARNING', () => respuestaJson([])],
    ])
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <Routes>
          <Route path="/admin" element={<PaginaAdmin />} />
        </Routes>
      </MemoryRouter>,
    )
    expect(await screen.findByText('No se puede leer la carpeta de COPIAS_DIR')).toBeInTheDocument()
  })

  it('al cambiar el filtro de los registros desaparece el error anterior', async () => {
    pintar([
      conSesion(),
      ['GET', '/api/admin/registros?nivel=ERROR', () => respuestaJson([{ id: 1, creado_en: '2026-11-17T10:00:00Z', nivel: 'ERROR', origen: 'app', mensaje: 'Un error', traza: null }])],
    ])
    simularFetch([
      conSesion(),
      ['GET', '/api/admin/estado', () => respuestaJson(ESTADO)],
      ['GET', '/api/admin/registros?nivel=WARNING', () => respuestaJson({ mensaje: 'Fallo temporal' }, 500)],
      ['GET', '/api/admin/registros?nivel=ERROR', () => respuestaJson([{ id: 1, creado_en: '2026-11-17T10:00:00Z', nivel: 'ERROR', origen: 'app', mensaje: 'Un error', traza: null }])],
    ])
    expect(await screen.findByText('Fallo temporal')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Mostrar'), { target: { value: 'ERROR' } })
    expect(await screen.findByText('Un error')).toBeInTheDocument()
    expect(screen.queryByText('Fallo temporal')).not.toBeInTheDocument()
  })
})
