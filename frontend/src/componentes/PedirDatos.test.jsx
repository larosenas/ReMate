// CU-004 — Pedir al proveedor los datos que faltan (la API se simula con fetch).
import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { descargar } from '../api/descargar.js'
import { llamada, respuestaJson, simularFetch } from '../pruebas/api.js'
import { problemasDeAccesibilidad } from '../pruebas/accesibilidad.js'
import PedirDatos from './PedirDatos.jsx'

vi.mock('../api/descargar.js', () => ({ descargar: vi.fn() }))

const OFERTA = { id: 30, proveedor: { id: 2, nombre: 'Acme' } }
const BORRADOR = {
  para: 'ventas@acme.test, luis@acme.test',
  asunto: '2026111101 | Línea 3 | Rodamiento roto',
  cuerpo: 'Buenos días:\n\n- Embalaje\n\nUn saludo,\nAna Prueba\nIndustrias Ficticias\n',
  faltan: ['Embalaje'],
  avisos: [],
  con_ia: true,
}
const RUTA = '/api/necesidades/7/ofertas/30/peticion-datos'

function eml() {
  return Promise.resolve(
    new Response('Subject: x\r\n\r\nHola', {
      status: 200,
      headers: { 'Content-Disposition': "attachment; filename*=UTF-8''2026111101%20datos%20que%20faltan.eml" },
    }),
  )
}

function pintar(onCerrar = vi.fn()) {
  render(
    <main>
      <PedirDatos necesidadId={7} oferta={OFERTA} onCerrar={onCerrar} />
    </main>,
  )
  return onCerrar
}

describe('PedirDatos', () => {
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => 'blob:eml')
    URL.revokeObjectURL = vi.fn()
  })
  afterEach(() => vi.clearAllMocks())

  it('muestra el correo propuesto y descarga el .eml con el cuerpo revisado', async () => {
    simularFetch([
      ['POST', `${RUTA}/borrador`, () => respuestaJson(BORRADOR)],
      ['POST', RUTA, eml],
    ])
    pintar()
    const cuerpo = await screen.findByLabelText(/Cuerpo del correo/)
    expect(cuerpo).toHaveValue(BORRADOR.cuerpo)
    expect(screen.getByText(BORRADOR.para)).toBeInTheDocument()
    expect(screen.getByText(BORRADOR.asunto)).toBeInTheDocument()
    expect(await problemasDeAccesibilidad()).toEqual([])
    fireEvent.change(cuerpo, { target: { value: 'Texto revisado' } })
    fireEvent.click(screen.getByRole('button', { name: 'Descargar el .eml' }))

    expect(await screen.findByText(/Correo descargado/)).toBeInTheDocument()
    expect(JSON.parse(llamada('POST', RUTA)[1].body)).toEqual({ cuerpo: 'Texto revisado' })
    expect(descargar).toHaveBeenCalledWith('blob:eml', '2026111101 datos que faltan.eml')
  })

  it('sin la IA, enseña su aviso', async () => {
    simularFetch([['POST', `${RUTA}/borrador`, () => respuestaJson({ ...BORRADOR, con_ia: false, avisos: ['No se ha podido usar la IA.'] })]])
    pintar()
    expect(await screen.findByText('No se ha podido usar la IA.')).toBeInTheDocument()
    expect(await problemasDeAccesibilidad()).toEqual([])
  })

  it('no descarga un correo vacío y dice si el borrador falla', async () => {
    simularFetch([['POST', `${RUTA}/borrador`, () => respuestaJson(BORRADOR)]])
    const onCerrar = pintar()
    fireEvent.change(await screen.findByLabelText(/Cuerpo del correo/), { target: { value: '  ' } })
    fireEvent.click(screen.getByRole('button', { name: 'Descargar el .eml' }))
    expect(screen.getByText('El cuerpo del correo está vacío.')).toBeInTheDocument()
    expect(llamada('POST', RUTA)).toBeUndefined()
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(onCerrar).toHaveBeenCalled()
  })

  it('si no se puede preparar, lo dice', async () => {
    simularFetch([
      ['POST', `${RUTA}/borrador`, () => respuestaJson({ error: 'datos_no_validos', mensaje: 'A esta oferta no le falta ningún dato que pedir.', detalles: {} }, 400)],
    ])
    pintar()
    expect(await screen.findByRole('alert')).toHaveTextContent('A esta oferta no le falta ningún dato que pedir.')
    expect(screen.queryByRole('button', { name: 'Descargar el .eml' })).not.toBeInTheDocument()
  })
})
