// Entrega de una oferta: la fecha que dio el proveedor o su plazo (ejemplo real).
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EntregaOferta from './EntregaOferta.jsx'

describe('EntregaOferta', () => {
  it('con una fecha del proveedor, la fecha', () => {
    render(<p><EntregaOferta oferta={{ fecha_entrega_estimada: '2026-11-15', fecha_calculada: false, plazo_entrega_texto: null }} /></p>)
    expect(screen.getByText('15.11.2026')).toBeInTheDocument()
  })

  it('con un plazo, el plazo y la fecha desde su oferta como orientación', () => {
    render(<p><EntregaOferta oferta={{ fecha_entrega_estimada: '2026-11-04', fecha_calculada: true, plazo_entrega_texto: '3 SEMANAS' }} /></p>)
    expect(screen.getByText('3 SEMANAS')).toBeInTheDocument()
    expect(screen.getByText('≈ 04.11.2026 desde su oferta')).toBeInTheDocument()
  })

  it('con solo un mes, el mes y su último viernes', () => {
    render(
      <p>
        <EntregaOferta oferta={{ fecha_entrega_estimada: '2026-12-25', fecha_calculada: false, fecha_de_mes: true, plazo_entrega_texto: 'diciembre' }} />
      </p>,
    )
    expect(screen.getByText('diciembre')).toBeInTheDocument()
    expect(screen.getByText('25.12.2026 (último viernes del mes)')).toBeInTheDocument()
  })
})
