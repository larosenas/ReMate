// CU-001 — Pruebas de la pantalla «Nueva necesidad» (la API se simula con fetch).
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import PaginaNuevaNecesidad from './PaginaNuevaNecesidad.jsx'
import { llamadas, respuestaJson, simularFetch } from '../pruebas/api.js'

const ANA = { id: 1, nombre_completo: 'Ana Prueba', email: 'ana@ejemplo.test', activo: true }
const CREADA = {
  id: 7,
  codigo: '2026102301',
  titulo: 'Rodamiento roto',
  estado: 'necesidad_creada',
  estado_texto: 'Necesidad creada',
}

// `respuestas` es una lista de [método, ruta, función que devuelve la respuesta].
function simularApi(respuestas = []) {
  return simularFetch(respuestas, () => respuestaJson([ANA]))
}

async function rellenar() {
  await screen.findByRole('option', { name: 'Ana Prueba' })
  fireEvent.change(screen.getByLabelText('Título'), { target: { value: 'Rodamiento roto' } })
  fireEvent.change(screen.getByLabelText('Proyecto'), { target: { value: '2026' } })
  fireEvent.change(screen.getByLabelText('Peticionario'), { target: { value: '1' } })
  fireEvent.change(screen.getByLabelText('Descripción de la necesidad'), { target: { value: 'Cambiar el 6204.' } })
}

function pintar() {
  render(
    <MemoryRouter>
      <PaginaNuevaNecesidad />
    </MemoryRouter>,
  )
}

function archivo(nombre, tamano) {
  const f = new File(['x'], nombre)
  Object.defineProperty(f, 'size', { value: tamano })
  return f
}

describe('PaginaNuevaNecesidad', () => {
  it('crea la necesidad y muestra el código y el título', async () => {
    simularApi([['POST', '/api/necesidades', () => respuestaJson(CREADA, 201)]])
    pintar()
    await rellenar()
    fireEvent.change(screen.getByLabelText(/Adjuntos/, { selector: 'input' }), { target: { files: [archivo('foto.jpg', 1000)] } })
    fireEvent.click(screen.getByRole('button', { name: 'Crear' }))
    expect(await screen.findByRole('status')).toHaveTextContent('2026102301 Rodamiento roto')
    expect(screen.getByRole('link', { name: 'Solicitar ofertas (paso 2)' })).toHaveAttribute('href', '/necesidades/7')
    const cuerpo = llamadas('POST', '/api/necesidades')[0][1].body
    expect(cuerpo.get('titulo')).toBe('Rodamiento roto')
    expect(cuerpo.get('proyecto')).toBe('2026')
    expect(cuerpo.get('peticionario_id')).toBe('1')
    expect(cuerpo.getAll('adjuntos')).toHaveLength(1)
  })

  it('no envía nada si faltan campos obligatorios', async () => {
    simularApi()
    pintar()
    await screen.findByRole('option', { name: 'Ana Prueba' })
    fireEvent.click(screen.getByRole('button', { name: 'Crear' }))
    expect(screen.getByText('El título es obligatorio.')).toBeInTheDocument()
    expect(screen.getByText('Elige un peticionario de la lista.')).toBeInTheDocument()
    expect(llamadas('POST', '/api/necesidades')).toHaveLength(0)
  })

  it('rechaza un adjunto de más de 25 MB sin perder lo escrito', async () => {
    simularApi()
    pintar()
    await rellenar()
    fireEvent.change(screen.getByLabelText(/Adjuntos/, { selector: 'input' }), {
      target: { files: [archivo('enorme.zip', 26 * 1024 * 1024), archivo('plano.pdf', 2000)] },
    })
    expect(screen.getByText(/No se ha añadido «enorme.zip»/)).toBeInTheDocument()
    expect(screen.getByText('plano.pdf')).toBeInTheDocument()
    expect(screen.getByLabelText('Título')).toHaveValue('Rodamiento roto')
  })

  it('marca el campo que rechaza la API', async () => {
    simularApi([
      [
        'POST',
        '/api/necesidades',
        () => respuestaJson({ error: 'datos_no_validos', mensaje: 'El título es obligatorio.', detalles: { campo: 'titulo' } }, 400),
      ],
    ])
    pintar()
    await rellenar()
    fireEvent.click(screen.getByRole('button', { name: 'Crear' }))
    expect(await screen.findByText('El título es obligatorio.')).toBeInTheDocument()
    expect(screen.getByLabelText('Título')).toHaveAttribute('aria-invalid', 'true')
  })

  it('«Otro» guarda el peticionario nuevo y lo deja elegido', async () => {
    const BEA = { id: 2, nombre_completo: 'Bea Nueva', email: 'bea@ejemplo.test', activo: true, avisos: [] }
    let lista = [ANA]
    simularApi([
      ['GET', '/api/peticionarios', () => respuestaJson(lista)],
      [
        'POST',
        '/api/peticionarios',
        () => {
          lista = [ANA, BEA]
          return respuestaJson(BEA, 201)
        },
      ],
    ])
    pintar()
    await screen.findByRole('option', { name: 'Ana Prueba' })
    fireEvent.change(screen.getByLabelText('Peticionario'), { target: { value: 'otro' } })
    fireEvent.change(screen.getByLabelText('Nombre y apellido'), { target: { value: 'Bea Nueva' } })
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'bea@ejemplo.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar en la lista' }))
    expect(await screen.findByRole('option', { name: 'Bea Nueva' })).toBeInTheDocument()
    expect(screen.getByLabelText('Peticionario')).toHaveValue('2')
    expect(screen.queryByLabelText('Nombre y apellido')).not.toBeInTheDocument()
  })

  it('«Otro» con un correo ya registrado propone usar el existente', async () => {
    simularApi([
      [
        'POST',
        '/api/peticionarios',
        () =>
          respuestaJson(
            { error: 'correo_duplicado', mensaje: 'Ya existe un registro con el correo ana@ejemplo.test.', detalles: { existente: ANA } },
            409,
          ),
      ],
    ])
    pintar()
    await screen.findByRole('option', { name: 'Ana Prueba' })
    fireEvent.change(screen.getByLabelText('Peticionario'), { target: { value: 'otro' } })
    fireEvent.change(screen.getByLabelText('Nombre y apellido'), { target: { value: 'Ana P.' } })
    fireEvent.change(screen.getByLabelText('Correo'), { target: { value: 'ana@ejemplo.test' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar en la lista' }))
    fireEvent.click(await screen.findByRole('button', { name: 'Usar «Ana Prueba»' }))
    await vi.waitFor(() => expect(screen.getByLabelText('Peticionario')).toHaveValue('1'))
  })

  describe('corregir los datos («Atrás» desde el paso 2)', () => {
    const NECESIDAD = {
      ...CREADA,
      proyecto: 'Línea 3',
      descripcion: 'Descripción mal escrita',
      peticionario: { id: 1, nombre_completo: 'Ana Prueba' },
      adjuntos: [{ id: 11, nombre_archivo: 'plano.pdf', tipo_mime: 'application/pdf', tamano: 10 }],
    }

    function pintarEdicion() {
      render(
        <MemoryRouter initialEntries={['/necesidades/7/editar']}>
          <Routes>
            <Route path="/necesidades/:id/editar" element={<PaginaNuevaNecesidad />} />
            <Route path="/necesidades/:id" element={<p>Detalle de la necesidad</p>} />
          </Routes>
        </MemoryRouter>,
      )
    }

    it('carga los datos, guarda los cambios y vuelve al detalle', async () => {
      simularApi([
        ['GET', '/api/necesidades/7', () => respuestaJson(NECESIDAD)],
        ['PUT', '/api/necesidades/7', () => respuestaJson({ ...NECESIDAD, descripcion: 'Bien escrita' })],
      ])
      pintarEdicion()
      expect(await screen.findByRole('heading', { name: 'Corregir la necesidad 2026102301' })).toBeInTheDocument()
      await screen.findByRole('option', { name: 'Ana Prueba' })
      expect(screen.getByLabelText('Título')).toHaveValue('Rodamiento roto')
      expect(screen.getByText(/plano.pdf/)).toBeInTheDocument()
      fireEvent.change(screen.getByLabelText('Descripción de la necesidad'), { target: { value: 'Bien escrita' } })
      fireEvent.click(screen.getByRole('button', { name: 'Guardar y volver' }))
      expect(await screen.findByText('Detalle de la necesidad')).toBeInTheDocument()
      const [, opciones] = llamadas('PUT', '/api/necesidades/7')[0]
      expect(JSON.parse(opciones.body)).toEqual({
        titulo: 'Rodamiento roto',
        proyecto: 'Línea 3',
        peticionario_id: 1,
        descripcion: 'Bien escrita',
      })
      expect(llamadas('POST', '/api/necesidades')).toHaveLength(0)
    })

    it('si su peticionario está desactivado, obliga a elegir otro', async () => {
      simularApi([
        ['GET', '/api/necesidades/7', () => respuestaJson({ ...NECESIDAD, peticionario: { id: 99, nombre_completo: 'De Baja' } })],
      ])
      pintarEdicion()
      await screen.findByRole('option', { name: 'Ana Prueba' })
      await vi.waitFor(() => expect(screen.getByLabelText('Título')).toHaveValue('Rodamiento roto'))
      fireEvent.click(screen.getByRole('button', { name: 'Guardar y volver' }))
      expect(await screen.findByText('Elige un peticionario de la lista.')).toBeInTheDocument()
      expect(llamadas('PUT', '/api/necesidades/7')).toHaveLength(0)
    })

    it('no deja corregir si ya se han pedido ofertas', async () => {
      simularApi([['GET', '/api/necesidades/7', () => respuestaJson({ ...NECESIDAD, estado: 'en_cotizacion' })]])
      pintarEdicion()
      expect(await screen.findByRole('alert')).toHaveTextContent('Los datos ya no se pueden cambiar')
    })
  })
})
