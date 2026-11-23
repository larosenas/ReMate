// Navegación con React Router (ADR 0005).
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it, vi } from 'vitest'
import App from './App.jsx'

function pintar(ruta) {
  render(
    <MemoryRouter initialEntries={[ruta]}>
      <App />
    </MemoryRouter>,
  )
}

describe('App', () => {
  it('muestra la pantalla de listas en /listas, también con barra final', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]'))
    pintar('/listas/')
    expect(screen.getByRole('heading', { level: 1, name: 'Proveedores y peticionarios' })).toBeInTheDocument()
  })

  it('cambia de pantalla al pulsar un enlace de la cabecera sin recargar', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]'))
    pintar('/listas')
    fireEvent.click(screen.getByRole('link', { name: 'Nueva necesidad' }))
    expect(screen.getByRole('heading', { level: 1, name: 'Nueva necesidad' })).toBeInTheDocument()
  })

  it('el pie lleva la autoría', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]'))
    pintar('/listas')
    expect(screen.getByRole('contentinfo')).toHaveTextContent('ReMate, desarrollado por Laro Señas')
  })

  it('el enlace «admin» del pie abre el modo admin (ADR 0015)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ activa: false, configurado: true })))
    pintar('/listas')
    fireEvent.click(within(screen.getByRole('contentinfo')).getByRole('link', { name: 'admin' }))
    expect(await screen.findByRole('heading', { name: 'Modo admin' })).toBeInTheDocument()
  })

  it('el título solo lleva al panel, aunque se pulse tres veces', () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('[]'))
    pintar('/listas')
    const titulo = screen.getByRole('link', { name: 'ReMate, ir al panel' })
    fireEvent.click(titulo)
    fireEvent.click(titulo)
    fireEvent.click(titulo)
    expect(screen.queryByRole('heading', { name: 'Modo admin' })).not.toBeInTheDocument()
  })

  it('avisa cuando la pantalla no existe', () => {
    pintar('/no-existe')
    expect(screen.getByText('Esta pantalla todavía no existe.')).toBeInTheDocument()
  })
})
