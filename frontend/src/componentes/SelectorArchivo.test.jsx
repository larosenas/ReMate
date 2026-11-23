// Selector de archivos con botón propio.
import { createEvent, fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import SelectorArchivo from './SelectorArchivo.jsx'

describe('SelectorArchivo', () => {
  it('solo el botón abre el diálogo; la etiqueta no', () => {
    render(<SelectorArchivo etiqueta="Correo de la oferta (.eml)" onChange={vi.fn()} />)
    const entrada = screen.getByLabelText('Correo de la oferta (.eml)', { selector: 'input' })
    const abrir = vi.spyOn(entrada, 'click')
    fireEvent.click(screen.getByText('Correo de la oferta (.eml)'))
    expect(abrir).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /elegir archivo/ }))
    expect(abrir).toHaveBeenCalledTimes(1)
  })

  it('muestra debajo de la zona el nombre del archivo elegido', () => {
    const cambio = vi.fn()
    const { container } = render(<SelectorArchivo etiqueta="Adjunto 1" etiquetaVisible={false} onChange={cambio} />)
    expect(screen.queryByRole('list', { name: 'Archivos elegidos' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Adjunto 1', { selector: 'input' }), {
      target: { files: [new File(['x'], 'oferta 123.pdf')] },
    })
    expect(screen.getByRole('list', { name: 'Archivos elegidos' })).toHaveTextContent('oferta 123.pdf')
    expect(container.querySelector('[data-zona-archivos]')).not.toHaveTextContent('oferta 123.pdf')
    expect(cambio).toHaveBeenCalledTimes(1)
  })

  it('acepta archivos arrastrados y soltados en la zona', () => {
    const cambio = vi.fn()
    const { container } = render(<SelectorArchivo etiqueta="Correo de la oferta (.eml)" onChange={cambio} />)
    const zona = container.querySelector('[data-zona-archivos]')
    expect(zona).toHaveTextContent('o arrástralo aquí')
    const archivos = [new File(['x'], 'oferta.eml'), new File(['y'], 'otra.eml')]
    fireEvent.dragOver(zona, { dataTransfer: { files: archivos, dropEffect: '' } })
    expect(zona).toHaveTextContent('Suelta aquí')
    fireEvent.drop(zona, { dataTransfer: { files: archivos } })
    // Con un solo archivo permitido, se queda con el primero.
    expect(cambio).toHaveBeenCalledTimes(1)
    expect(cambio.mock.calls[0][0].target.files.map((f) => f.name)).toEqual(['oferta.eml'])
    expect(screen.getByText('oferta.eml')).toBeInTheDocument()
  })

  it('desactivado, no acepta lo que se suelta ni invita a soltar', () => {
    const cambio = vi.fn()
    const { container } = render(<SelectorArchivo etiqueta="Pedido" disabled onChange={cambio} />)
    const zona = container.querySelector('[data-zona-archivos]')
    const dataTransfer = { files: [new File(['x'], 'pedido.pdf')], dropEffect: '' }
    fireEvent.dragOver(zona, { dataTransfer })
    expect(dataTransfer.dropEffect).toBe('none')
    expect(zona).not.toHaveTextContent('Suelta aquí')
    fireEvent.drop(zona, { dataTransfer })
    expect(cambio).not.toHaveBeenCalled()
  })

  it('pasar por encima del botón no apaga el resaltado', () => {
    const { container } = render(<SelectorArchivo etiqueta="Pedido" onChange={vi.fn()} />)
    const zona = container.querySelector('[data-zona-archivos]')
    fireEvent.dragOver(zona, { dataTransfer: { files: [], dropEffect: '' } })
    // jsdom no pasa `relatedTarget` en los eventos de arrastre: se pone a mano.
    const salir = (hacia) => {
      const evento = createEvent.dragLeave(zona)
      Object.defineProperty(evento, 'relatedTarget', { value: hacia })
      fireEvent(zona, evento)
    }
    salir(screen.getByRole('button'))
    expect(zona).toHaveTextContent('Suelta aquí')
    salir(document.body)
    expect(zona).not.toHaveTextContent('Suelta aquí')
  })

  it('un archivo soltado fuera de la zona no lo abre el navegador', () => {
    const { unmount } = render(<SelectorArchivo etiqueta="Pedido" onChange={vi.fn()} />)
    const soltar = () => {
      const evento = new Event('drop', { cancelable: true })
      evento.dataTransfer = { types: ['Files'] }
      window.dispatchEvent(evento)
      return evento.defaultPrevented
    }
    expect(soltar()).toBe(true)
    unmount()
    expect(soltar()).toBe(false)
  })

  it('con varios archivos permitidos, los toma todos', () => {
    const cambio = vi.fn()
    const { container } = render(<SelectorArchivo etiqueta="Adjuntos" multiple onChange={cambio} />)
    const archivos = [new File(['x'], 'plano.pdf'), new File(['y'], 'foto.jpg')]
    fireEvent.drop(container.querySelector('[data-zona-archivos]'), { dataTransfer: { files: archivos } })
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['plano.pdf', 'foto.jpg'])
  })
})
