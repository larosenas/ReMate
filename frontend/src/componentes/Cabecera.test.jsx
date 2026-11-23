import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import Cabecera from './Cabecera.jsx'

describe('Cabecera', () => {
  it('muestra el nombre de la aplicación y los enlaces', () => {
    render(
      <MemoryRouter initialEntries={['/listas']}>
        <Cabecera
          enlaces={[
            { href: '/', texto: 'Panel' },
            { href: '/listas', texto: 'Proveedores y peticionarios' },
          ]}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole('link', { name: 'ReMate, ir al panel' })).toHaveAttribute('href', '/')
    const enlace = screen.getByRole('link', { name: 'Proveedores y peticionarios' })
    expect(enlace).toHaveAttribute('href', '/listas')
    expect(enlace).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('link', { name: 'Panel' })).not.toHaveAttribute('aria-current')
  })

  it('el logotipo es texto, sin imágenes que puedan no cargar', () => {
    render(
      <MemoryRouter>
        <Cabecera />
      </MemoryRouter>,
    )
    const logotipo = screen.getByRole('link', { name: 'ReMate, ir al panel' })
    expect(logotipo).toHaveTextContent('ReMate')
    expect(logotipo.querySelector('img')).toBeNull()
  })
})
