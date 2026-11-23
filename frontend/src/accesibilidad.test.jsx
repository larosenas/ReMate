// Accesibilidad de las pantallas principales con axe-core. La API se simula con datos
// inventados; cada pantalla se pinta entera (cabecera y pie incluidos) y no debe tener problemas.
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import App from './App.jsx'
import { problemasDeAccesibilidad } from './pruebas/accesibilidad.js'
import { respuestaJson, simularFetch } from './pruebas/api.js'

const ANA = { id: 1, nombre_completo: 'Ana Prueba' }
const ACME = { id: 2, nombre: 'Acme', email: 'ventas@acme.test', activo: true }
const NECESIDAD = {
  id: 7,
  codigo: '2026102301',
  titulo: 'Rodamiento roto',
  proyecto: 'Línea 3',
  descripcion: 'Necesitamos 4 rodamientos.',
  estado: 'pendiente_entrega',
  estado_texto: 'Pendiente entrega',
  peticionario: ANA,
  creada_en: '2026-10-23T10:00:00+02:00',
  estado_desde: '2026-10-25T10:00:00+02:00',
  adjuntos: [],
  historial: [
    { estado_anterior: null, estado_nuevo: 'necesidad_creada', peticionario: ANA, cambiado_en: '2026-10-23T10:00:00+02:00' },
    { estado_anterior: 'pendiente_pedido_sap', estado_nuevo: 'pendiente_entrega', peticionario: ANA, cambiado_en: '2026-10-25T10:00:00+02:00' },
  ],
  // Con un cambio de peticionario, para que axe vea también esa entrada del historial.
  cambios_peticionario: [
    { peticionario_anterior: { id: 9, nombre_completo: 'Luis Prueba' }, peticionario_nuevo: ANA, cambiado_en: '2026-10-26T10:00:00+02:00' },
  ],
  proveedores_solicitados: [ACME],
  proveedor_adjudicado: ACME,
  solicitud_eml: null,
  adjudicacion_eml: null,
  oferta_adjudicada_id: null,
  // Muy lejos: si la fecha prevista ya ha pasado, confirmar la entrega pide antes el motivo del
  // retraso y la prueba de la pregunta final dependería del día en que se ejecuta.
  fecha_entrega_inicial: '2099-12-31',
  fecha_entrega_prevista: '2099-12-31',
  fecha_entrega_real: null,
  numero_pedido_sap: '4500012345',
  pedido_sap: null,
  retrasos: [],
  recordatorio_enviado_en: null,
}

function simularApi() {
  simularFetch(
    [
      ['GET', '/api/salud', () => respuestaJson({ estado: 'ok', base_de_datos: 'ok' })],
      ['GET', '/api/necesidades', () => respuestaJson([NECESIDAD])],
      ['GET', '/api/necesidades/7', () => respuestaJson(NECESIDAD)],
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([])],
      ['GET', '/api/proveedores', () => respuestaJson([ACME])],
      ['GET', '/api/proveedores?incluir_inactivos=true', () => respuestaJson([ACME])],
      ['GET', '/api/peticionarios', () => respuestaJson([{ ...ANA, email: 'ana@ejemplo.test', activo: true }])],
      [
        'GET',
        '/api/peticionarios?incluir_inactivos=true',
        () =>
          respuestaJson([
            { ...ANA, email: 'ana@ejemplo.test', activo: true },
            { id: 9, nombre_completo: 'Luis Prueba', email: 'luis@ejemplo.test', activo: false },
          ]),
      ],
      [
        'POST',
        '/api/peticionarios/9/baja',
        () =>
          respuestaJson(
            {
              error: 'necesidades_en_curso',
              mensaje: 'Lleva 1 necesidad(es) en curso.',
              detalles: { necesidades: [{ id: 7, codigo: '2026102301', titulo: 'Rodamiento roto' }] },
            },
            409,
          ),
      ],
      [
        'GET',
        '/api/proveedores/2/retrasos',
        () => respuestaJson({ proveedor: ACME, pedidos: 1, con_retraso: 0, retraso_medio: 0, retrasos: [] }),
      ],
    ],
    (metodo, ruta) => respuestaJson({ mensaje: `no simulado: ${metodo} ${ruta}` }, 500),
  )
}

async function pintar(ruta, esperar) {
  simularApi()
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  )
  await esperar()
}

describe('accesibilidad (axe-core)', () => {
  it.each([
    ['el panel', '/', () => screen.findByRole('link', { name: '2026102301' })],
    ['la nueva necesidad', '/nueva', () => screen.findByLabelText('Título')],
    ['el detalle de una necesidad', '/necesidades/7', () => screen.findByRole('heading', { level: 1, name: 'Rodamiento roto' })],
    ['proveedores y peticionarios', '/listas', () => screen.findAllByText('Acme')],
    ['el histórico de retrasos', '/proveedores/2/retrasos', () => screen.findByText(/Acme/)],
  ])('%s no tiene problemas de accesibilidad', async (_, ruta, esperar) => {
    await pintar(ruta, esperar)
    expect(await problemasDeAccesibilidad()).toEqual([])
  })

  // Estados que solo aparecen tras una acción.
  it('la pregunta antes de confirmar la entrega no tiene problemas', async () => {
    await pintar('/necesidades/7', () => screen.findByRole('button', { name: 'Confirmar la entrega' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar la entrega' }))
    fireEvent.click(screen.getByRole('button', { name: 'Confirmar que ha llegado' }))
    expect(screen.getByText(/¿Seguro que el pedido ha llegado\?/)).toBeInTheDocument()
    expect(await problemasDeAccesibilidad()).toEqual([])
  })

  it('los avisos de la IA y la comparativa tras «Analizar y comparar» no tienen problemas', async () => {
    // Los avisos no pueden ir en un <ul role="status">, que axe-core rechaza.
    const oferta = {
      id: 30,
      proveedor: ACME,
      fecha_correo: '2026-10-22T09:15:00+02:00',
      numero_oferta: 'OF-1',
      moneda: 'EUR',
      importe_sin_iva: '1000',
      plazo_entrega_texto: '3 semanas',
      fecha_entrega_estimada: null,
      condiciones_pago: null,
      otros: null,
      revisada: false,
      sin_analizar: false,
      estado_oferta: 'vigente',
      lineas: [],
      archivos: [{ id: 40, tipo: 'correo_oferta', formato: null, nombre_archivo: 'oferta.eml', tamano: 10 }],
      avisos: [],
      historial_proveedor: { pedidos: 0, con_retraso: 0, retraso_medio: null },
      destacados: { importe: null, entrega: null, retrasos: null },
    }
    const enEvaluacion = { ...NECESIDAD, estado: 'en_evaluacion', estado_texto: 'En evaluación', proveedor_adjudicado: null }
    simularFetch(
      [
        ['GET', '/api/salud', () => respuestaJson({ estado: 'ok', base_de_datos: 'ok' })],
        ['GET', '/api/necesidades/7', () => respuestaJson(enEvaluacion)],
        ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([{ ...oferta, sin_analizar: true }])],
        ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([oferta])],
        ['GET', '/api/proveedores', () => respuestaJson([ACME])],
        ['GET', '/api/peticionarios', () => respuestaJson([{ ...ANA, email: 'ana@ejemplo.test', activo: true }])],
        [
          'POST',
          '/api/necesidades/7/evaluacion',
          () =>
            respuestaJson({
              necesidad: enEvaluacion,
              avisos: ['Acme: La IA no ha leído la oferta.'],
            }),
        ],
      ],
      (metodo, ruta) => respuestaJson({ mensaje: `no simulado: ${metodo} ${ruta}` }, 500),
    )
    render(
      <MemoryRouter initialEntries={['/necesidades/7']}>
        <App />
      </MemoryRouter>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Analizar las nuevas y volver a comparar' }))
    expect(await screen.findByText('Acme: La IA no ha leído la oferta.')).toBeInTheDocument()
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(await problemasDeAccesibilidad()).toEqual([])
  })

  it('el aviso de necesidades en curso al eliminar a un peticionario no tiene problemas', async () => {
    await pintar('/listas', () => screen.findAllByText('Acme'))
    for (const casilla of screen.getAllByRole('checkbox', { name: /inactivos/i })) fireEvent.click(casilla)
    fireEvent.click(await screen.findByRole('button', { name: 'Eliminar Luis Prueba' }))
    fireEvent.change(screen.getByLabelText('Motivo'), { target: { value: 'otro' } })
    fireEvent.change(screen.getByLabelText('Escribe el motivo'), { target: { value: 'Se va' } })
    fireEvent.click(screen.getByRole('button', { name: 'Eliminar definitivamente' }))
    expect(await screen.findByLabelText('Pasar sus necesidades a')).toBeInTheDocument()
    expect(await problemasDeAccesibilidad()).toEqual([])
  })

  it('el modo admin, con la sesión iniciada y una necesidad buscada, no tiene problemas', async () => {
    simularFetch(
      [
        ['GET', '/api/admin/sesion', () => respuestaJson({ activa: true, configurado: true })],
        [
          'GET',
          '/api/admin/estado',
          () =>
            respuestaJson({
              necesidades: { pendiente_entrega: 1 },
              archivos: { cantidad: 3, bytes: 1000 },
              disco: { total: 1e11, libre: 5e10 },
              ultima_copia: null,
              ia_30_dias: { llamadas: 0, entrada: 0, salida: 0 },
              avisos_y_errores_7_dias: 0,
            }),
        ],
        [
          'GET',
          '/api/admin/registros?nivel=WARNING',
          () => respuestaJson([{ id: 1, creado_en: '2026-11-17T10:00:00+01:00', nivel: 'ERROR', origen: 'app', mensaje: 'Fallo', traza: 'Traceback' }]),
        ],
        ['GET', '/api/necesidades', () => respuestaJson([NECESIDAD])],
        ['GET', '/api/necesidades/7', () => respuestaJson(NECESIDAD)],
      ],
      (metodo, ruta) => respuestaJson({ mensaje: `no simulado: ${metodo} ${ruta}` }, 500),
    )
    render(
      <MemoryRouter initialEntries={['/admin']}>
        <App />
      </MemoryRouter>,
    )
    fireEvent.change(await screen.findByLabelText('Código de la necesidad'), { target: { value: '2026102301' } })
    fireEvent.click(screen.getByRole('button', { name: 'Buscar' }))
    expect(await screen.findByRole('button', { name: 'Borrar definitivamente' })).toBeInTheDocument()
    expect(await screen.findByText('Fallo')).toBeInTheDocument()
    expect(await problemasDeAccesibilidad()).toEqual([])
  })
})
