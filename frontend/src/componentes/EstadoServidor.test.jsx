// El diagnóstico de la API queda en la consola y no ocupa espacio en la interfaz.
import { act, render, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import EstadoServidor from './EstadoServidor.jsx'
import { respuestaJson } from '../pruebas/api.js'

describe('EstadoServidor', () => {
  it('registra que el servidor y la base de datos funcionan sin mostrar contenido', async () => {
    const informar = vi.spyOn(console, 'info').mockImplementation(() => {})
    vi.spyOn(globalThis, 'fetch').mockReturnValue(respuestaJson({ estado: 'ok', base_de_datos: 'ok' }))
    const { container } = render(<EstadoServidor />)
    expect(container).toBeEmptyDOMElement()
    await waitFor(() => expect(informar).toHaveBeenCalledWith('[ReMate] Servidor: ok · Base de datos: ok'))
    expect(container).toBeEmptyDOMElement()
    expect(globalThis.fetch).toHaveBeenCalledWith('/api/salud', expect.any(Object))
  })

  it('avisa cuando no puede conectar con el servidor', async () => {
    const avisar = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(globalThis, 'fetch').mockRejectedValue(new TypeError('Failed to fetch'))
    const { container } = render(<EstadoServidor />)
    await waitFor(() => expect(avisar).toHaveBeenCalledWith('[ReMate] No se puede conectar con el servidor de ReMate.'))
    expect(container).toBeEmptyDOMElement()
  })

  it('registra el fallo cuando la base de datos no responde', async () => {
    const avisar = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(globalThis, 'fetch').mockReturnValue(
      respuestaJson({ estado: 'error', base_de_datos: 'sin conexión' }, 503),
    )
    const { container } = render(<EstadoServidor />)
    await waitFor(() => expect(avisar).toHaveBeenCalledWith('[ReMate] Error del servidor (503).'))
    expect(container).toBeEmptyDOMElement()
  })

  it('no registra una respuesta que llega después de desmontarse', async () => {
    const informar = vi.spyOn(console, 'info').mockImplementation(() => {})
    let responder
    vi.spyOn(globalThis, 'fetch').mockReturnValue(new Promise((resolve) => { responder = resolve }))
    const { unmount } = render(<EstadoServidor />)
    unmount()
    await act(async () => {
      responder(await respuestaJson({ estado: 'ok', base_de_datos: 'ok' }))
    })
    expect(informar).not.toHaveBeenCalled()
  })
})
