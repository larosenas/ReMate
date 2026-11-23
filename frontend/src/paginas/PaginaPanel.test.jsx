// Panel: lista de necesidades con enlace a su detalle y filtros por peticionario y fecha.
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import PaginaPanel from './PaginaPanel.jsx'
import { respuestaJson } from '../pruebas/api.js'

function pintar() {
  render(
    <MemoryRouter>
      <PaginaPanel />
    </MemoryRouter>,
  )
}

describe('PaginaPanel', () => {
  it('lista las necesidades con enlace al detalle', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((ruta) =>
      ruta === '/api/necesidades'
        ? respuestaJson([
            {
              id: 7,
              codigo: '2026102301',
              titulo: 'Rodamiento roto',
              proyecto: 'Línea 3',
              estado: 'en_cotizacion',
              estado_texto: 'En cotización',
              peticionario: { id: 1, nombre_completo: 'Ana Prueba' },
              creada_en: '2026-10-23T10:00:00+02:00',
              estado_desde: '2026-10-24T09:30:00+02:00',
            },
          ])
        : respuestaJson({ estado: 'ok', base_de_datos: 'ok' }),
    )
    pintar()
    expect(await screen.findByRole('link', { name: '2026102301' })).toHaveAttribute('href', '/necesidades/7')
    // Tabla (escritorio) y tarjeta (móvil): las dos muestran el estado.
    expect(screen.getAllByText('En cotización', { selector: 'span' })).toHaveLength(2)
    // Fecha en que pasó al estado actual.
    expect(screen.getAllByText('desde 24.10.2026')).toHaveLength(2)
  })

  it('indica cuando no hay necesidades', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation((ruta) =>
      ruta === '/api/necesidades' ? respuestaJson([]) : respuestaJson({ estado: 'ok', base_de_datos: 'ok' }),
    )
    pintar()
    expect(await screen.findByText('Todavía no hay necesidades.')).toBeInTheDocument()
  })

  it('filtra por peticionario y por fecha de creación; por defecto salen todas', async () => {
    const ana = { id: 1, nombre_completo: 'Ana Prueba' }
    const luis = { id: 2, nombre_completo: 'Luis Prueba' }
    const necesidad = (id, codigo, peticionario, creada) => ({
      id,
      codigo,
      titulo: `Necesidad ${codigo}`,
      proyecto: 'Línea 3',
      estado: 'en_cotizacion',
      estado_texto: 'En cotización',
      peticionario,
      creada_en: `${creada}T10:00:00+01:00`,
      fecha_entrega_prevista: null,
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation((ruta) =>
      ruta === '/api/necesidades'
        ? respuestaJson([
            necesidad(3, '2026110301', luis, '2026-11-03'),
            necesidad(2, '2026102602', ana, '2026-10-26'),
            necesidad(1, '2026101501', ana, '2026-10-15'),
          ])
        : respuestaJson({ estado: 'ok', base_de_datos: 'ok' }),
    )
    pintar()
    // Los enlaces de la tabla (su nombre es solo el código); las tarjetas del móvil se nombran con todo su texto.
    const codigos = () => screen.queryAllByRole('link', { name: /^\d{10}$/ }).map((a) => a.textContent)
    expect(await screen.findByRole('link', { name: '2026110301' })).toBeInTheDocument()
    expect(codigos()).toEqual(['2026110301', '2026102602', '2026101501'])
    // Solo salen los peticionarios que tienen necesidades, de la A a la Z.
    const selector = screen.getByLabelText('Peticionario')
    expect([...selector.options].map((o) => o.textContent)).toEqual(['Todos', 'Ana Prueba', 'Luis Prueba'])

    fireEvent.change(selector, { target: { value: '1' } })
    expect(codigos()).toEqual(['2026102602', '2026101501'])
    expect(screen.getByText('2 de 3 con estos filtros, 2 en curso.')).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Creada desde'), { target: { value: '2026-10-20' } })
    expect(codigos()).toEqual(['2026102602'])
    fireEvent.change(screen.getByLabelText('Creada hasta'), { target: { value: '2026-10-25' } })
    expect(codigos()).toEqual([])
    expect(screen.getByText(/Ninguna necesidad cumple estos filtros/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtros' }))
    expect(codigos()).toEqual(['2026110301', '2026102602', '2026101501'])
    expect(screen.getByLabelText('Peticionario')).toHaveValue('')
  })

  it('filtra por estado («en curso»), proveedor adjudicado y texto sin tildes ni mayúsculas', async () => {
    const ana = { id: 1, nombre_completo: 'Ana Prueba' }
    const acme = { id: 5, nombre: 'Acme', email: 'a@acme.test' }
    const necesidad = (id, codigo, titulo, estado, proveedor) => ({
      id,
      codigo,
      titulo,
      proyecto: 'Línea 3',
      estado,
      estado_texto: estado,
      peticionario: ana,
      creada_en: '2026-10-26T10:00:00+01:00',
      fecha_entrega_prevista: null,
      proveedor_adjudicado: proveedor,
    })
    vi.spyOn(globalThis, 'fetch').mockImplementation((ruta) =>
      ruta === '/api/necesidades'
        ? respuestaJson([
            necesidad(3, '2026102603', 'Cilindro hidráulico', 'pendiente_entrega', acme),
            necesidad(2, '2026102602', 'Rodamientos y grasa', 'entregado', acme),
            necesidad(1, '2026102601', 'Soporte del motor', 'en_cotizacion', null),
          ])
        : respuestaJson({ estado: 'ok', base_de_datos: 'ok' }),
    )
    pintar()
    const codigos = () => screen.queryAllByRole('link', { name: /^\d{10}$/ }).map((a) => a.textContent)
    expect(await screen.findByRole('link', { name: '2026102603' })).toBeInTheDocument()
    // Solo los proveedores adjudicados (sin repetir).
    expect([...screen.getByLabelText('Proveedor').options].map((o) => o.textContent)).toEqual(['Todos', 'Acme'])

    fireEvent.change(screen.getByLabelText('Estado'), { target: { value: 'en_curso' } })
    expect(codigos()).toEqual(['2026102603', '2026102601'])
    fireEvent.change(screen.getByLabelText('Proveedor'), { target: { value: '5' } })
    expect(codigos()).toEqual(['2026102603'])
    fireEvent.click(screen.getByRole('button', { name: 'Quitar filtros' }))

    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: 'HIDRAULICO' } })
    expect(codigos()).toEqual(['2026102603'])
    fireEvent.change(screen.getByLabelText('Buscar'), { target: { value: '2602' } })
    expect(codigos()).toEqual(['2026102602'])
  })
})
