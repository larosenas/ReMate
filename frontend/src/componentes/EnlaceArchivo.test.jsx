// ADR 0014 — Enlace de descarga o aviso de archivo eliminado por antigüedad.
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EnlaceArchivo from './EnlaceArchivo.jsx'

describe('EnlaceArchivo', () => {
  it('enlaza el archivo mientras está en el servidor', () => {
    render(
      <EnlaceArchivo archivo={{ id: 1, caducado: false }} href="/api/necesidades/7/adjuntos/1">
        plano.step
      </EnlaceArchivo>,
    )
    expect(screen.getByRole('link', { name: 'plano.step' })).toHaveAttribute('href', '/api/necesidades/7/adjuntos/1')
  })

  it('sin enlace y con el aviso si se eliminó por antigüedad', () => {
    render(
      <EnlaceArchivo archivo={{ id: 1, caducado: true }} href="/api/necesidades/7/adjuntos/1">
        plano.step
      </EnlaceArchivo>,
    )
    expect(screen.queryByRole('link')).not.toBeInTheDocument()
    expect(screen.getByText(/plano\.step \(eliminado por antigüedad: búscalo en Outlook o en SAP\)/)).toBeInTheDocument()
  })
})
