// CU-004 — Pruebas de la sección de ofertas (la API se simula con fetch).
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { aDecimal, diasMedios, fechaCorta, importe, porcentajeConRetraso } from '../formatos.js'
import { tipoPorExtension } from '../tiposArchivo.js'
import SeccionOfertas from './SeccionOfertas.jsx'
import { llamada, llamadas, respuestaJson, simularFetch } from '../pruebas/api.js'
import { problemasDeAccesibilidad } from '../pruebas/accesibilidad.js'

const ANA = { id: 1, nombre_completo: 'Ana Prueba' }
const NECESIDAD = {
  id: 7,
  estado: 'en_cotizacion',
  peticionario: ANA,
  proveedores_solicitados: [{ id: 2, nombre: 'Acme', email: 'ventas@acme.test' }],
}
const OFERTA = {
  moneda: 'EUR',
  id: 30,
  proveedor: { id: 2, nombre: 'Acme', email: 'ventas@acme.test' },
  fecha_correo: '2026-10-22T09:15:00+02:00',
  numero_oferta: null,
  importe_sin_iva: null,
  plazo_entrega_texto: null,
  fecha_entrega_estimada: null,
  condiciones_pago: null,
  otros: null,
  revisada: false,
  estado_oferta: 'vigente',
  lineas: [],
  archivos: [{ id: 40, tipo: 'correo_oferta', formato: null, nombre_archivo: 'oferta.eml', tamano: 10 }],
  avisos: ['Falta: importe sin IVA, fecha de entrega.'],
}

function simularApi(extra = []) {
  const respuestas = [
    ...extra,
    ['POST', '/api/necesidades/7/ofertas/correo', () => respuestaJson(SIN_ADJUNTOS)],
    ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([])],
    ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([])],
    ['GET', '/api/proveedores', () => respuestaJson([{ id: 2, nombre: 'Acme' }, { id: 3, nombre: 'Zeta' }])],
    ['GET', '/api/peticionarios', () => respuestaJson([{ ...ANA, activo: true }])],
  ]
  return simularFetch(respuestas)
}

const archivo = (nombre) => new File(['x'], nombre)
const SIN_ADJUNTOS = { remitente: 'ventas@acme.test', proveedor: null, aviso_proveedor: null, adjuntos: [] }

// Al elegir el correo, se leen sus adjuntos; hasta entonces no se puede subir.
async function esperarLectura() {
  await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Subir oferta' })).toBeEnabled())
}

describe('formatos', () => {
  it('lee importes con coma decimal y puntos de miles', () => {
    expect(aDecimal('1.250,50')).toBe('1250.50')
    expect(aDecimal('2,5')).toBe('2.5')
    expect(aDecimal('1250.5')).toBe('1250.5')
    expect(aDecimal('')).toBeNull()
    expect(aDecimal('doce')).toBeNaN()
  })

  it('un retraso medio que redondea a 0 no se muestra como «0 días»', () => {
    expect(diasMedios(0, true)).toBe('menos de 0,1 días')
    expect(diasMedios(0)).toBe('0 días')
    expect(diasMedios(1)).toBe('1 día')
    expect(diasMedios(2.4, true)).toBe('2,4 días')
    // Como el backend: 1 de 8 pedidos son 12,5 %, que se redondea a 13.
    expect(porcentajeConRetraso({ pedidos: 8, con_retraso: 1 })).toBe(13)
  })

  it('muestra importes y fechas en español', () => {
    expect(importe('1250.5')).toBe('1.250,50')
    expect(importe(null)).toBe('—')
    expect(fechaCorta('2026-11-19')).toBe('19.11.2026')
  })

  it('propone el tipo de adjunto por la extensión', () => {
    expect(tipoPorExtension('oferta.PDF')).toBe('pdf')
    expect(tipoPorExtension('precios.xlsx')).toBe('excel')
    expect(tipoPorExtension('foto.jpg')).toBe('imagen')
    expect(tipoPorExtension('raro.xyz')).toBe('otro')
  })
})

describe('SeccionOfertas', () => {
  it('sube una oferta con el correo y un adjunto con su tipo, sin leerla todavía con la IA', async () => {
    let lista = []
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson(lista)],
      [
        'POST',
        '/api/necesidades/7/ofertas',
        () => {
          lista = [{ ...OFERTA, sin_analizar: true }]
          return respuestaJson({ ...lista[0], avisos: ['Zeta no estaba entre los proveedores solicitados.', ...OFERTA.avisos] }, 201)
        },
      ],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Añadir oferta' }))

    const zonaCorreo = screen.getByLabelText('Correo de la oferta (.eml o .msg)')
    fireEvent.change(zonaCorreo, { target: { files: [archivo('oferta.pdf')] } })
    expect(screen.getByText('El correo de la oferta tiene que ser un archivo .eml o .msg.')).toBeInTheDocument()
    expect(llamada('POST', '/api/necesidades/7/ofertas/correo')).toBeUndefined()
    fireEvent.change(zonaCorreo, { target: { files: [archivo('oferta.eml')] } })
    await esperarLectura()

    fireEvent.change(screen.getByLabelText('Adjunto 1'), { target: { files: [archivo('oferta 123.pdf')] } })
    expect(screen.getByLabelText('Tipo del adjunto 1')).toHaveValue('pdf')
    fireEvent.click(screen.getByRole('button', { name: 'Añadir otro adjunto' }))
    expect(screen.getByLabelText('Adjunto 2')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Subir oferta' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Zeta no estaba entre los proveedores solicitados.')
    const cuerpo = llamada('POST', '/api/necesidades/7/ofertas')[1].body
    expect(cuerpo.get('correo').name).toBe('oferta.eml')
    expect(cuerpo.getAll('adjuntos').map((a) => a.name)).toEqual(['oferta 123.pdf'])
    expect(cuerpo.getAll('tipos_adjunto')).toEqual(['pdf'])
    expect(cuerpo.get('proveedor_id')).toBeNull()
    // Solo se guarda: queda «Sin analizar», sin abrir la revisión ni avisar de lo que falta.
    expect(await screen.findByText('Sin analizar')).toBeInTheDocument()
    expect(screen.queryByLabelText('Importe total sin IVA')).not.toBeInTheDocument()
    expect(screen.queryByText(/Falta:/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Reanalizar con IA la oferta de Acme' })).not.toBeInTheDocument()
  })

  it('propone los adjuntos del correo y el proveedor reconocido por el dominio', async () => {
    const leido = {
      remitente: 'luis@ventas.acme.test',
      proveedor: { id: 2, nombre: 'Acme', email: 'ventas@acme.test' },
      aviso_proveedor: null,
      adjuntos: [
        { indice: 0, nombre: 'oferta 123.pdf', tamano: 100 },
        { indice: 1, nombre: 'precios.xlsx', tamano: 50 },
        { indice: 2, nombre: 'condiciones.pdf', tamano: 70 },
      ],
    }
    simularApi([
      ['POST', '/api/necesidades/7/ofertas/correo', () => respuestaJson(leido)],
      ['POST', '/api/necesidades/7/ofertas', () => respuestaJson({ ...OFERTA, avisos: [] }, 201)],
    ])
    // Dentro de <main>, como en la página: axe pide que todo esté en una zona de la página.
    render(
      <main>
        <SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />
      </main>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Añadir oferta' }))
    // Un .msg de Outlook (arrastrado desde Outlook) se acepta y se lee igual.
    fireEvent.change(screen.getByLabelText('Correo de la oferta (.eml o .msg)'), { target: { files: [archivo('oferta.msg')] } })
    expect(screen.getByText('Leyendo los adjuntos del correo…')).toBeInTheDocument()
    await esperarLectura()

    expect(screen.getByLabelText('Proveedor')).toHaveValue('2')
    expect(screen.getByLabelText('Tipo de oferta 123.pdf')).toHaveValue('pdf')
    expect(screen.getByLabelText('Tipo de precios.xlsx')).toHaveValue('excel')
    fireEvent.change(screen.getByLabelText('Tipo de precios.xlsx'), { target: { value: 'otro' } })
    fireEvent.click(screen.getByRole('button', { name: 'Quitar condiciones.pdf' }))
    expect(screen.queryByText('condiciones.pdf')).not.toBeInTheDocument()
    expect(await problemasDeAccesibilidad(document.body)).toEqual([])

    fireEvent.click(screen.getByRole('button', { name: 'Subir oferta' }))
    await vi.waitFor(() => expect(llamada('POST', '/api/necesidades/7/ofertas')).toBeDefined())
    const cuerpo = llamada('POST', '/api/necesidades/7/ofertas')[1].body
    expect(cuerpo.getAll('adjuntos_correo')).toEqual(['0', '1'])
    expect(cuerpo.getAll('tipos_adjunto_correo')).toEqual(['pdf', 'otro'])
    expect(cuerpo.get('proveedor_id')).toBe('2')
    expect(cuerpo.get('correo').name).toBe('oferta.msg')
  })

  it('si no reconoce al proveedor, lo dice y deja elegirlo; un correo que no vale se quita', async () => {
    let respuesta = { ...SIN_ADJUNTOS, aviso_proveedor: 'Hay varios proveedores con el dominio del remitente (x@zeta.test). Elígelo de la lista.' }
    simularApi([
      [
        'POST',
        '/api/necesidades/7/ofertas/correo',
        () =>
          respuesta === null
            ? respuestaJson({ error: 'archivo_no_aceptado', mensaje: 'El archivo no parece un correo .eml válido.', detalles: { campo: 'correo' } }, 422)
            : respuestaJson(respuesta),
      ],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Añadir oferta' }))
    const zonaCorreo = screen.getByLabelText('Correo de la oferta (.eml o .msg)')
    fireEvent.change(zonaCorreo, { target: { files: [archivo('oferta.eml')] } })
    expect(await screen.findByText(/Hay varios proveedores/)).toBeInTheDocument()
    expect(screen.getByLabelText('Proveedor')).toHaveValue('')

    respuesta = null
    fireEvent.change(screen.getByLabelText('Correo de la oferta (.eml o .msg)'), { target: { files: [archivo('roto.eml')] } })
    expect(await screen.findByText('El archivo no parece un correo .eml válido.')).toBeInTheDocument()
    expect(screen.queryByText(/Hay varios proveedores/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Quitar el correo' })).not.toBeInTheDocument()
  })

  it('descarta la lectura pendiente si después se elige un archivo que no es un correo', async () => {
    let terminarLectura
    simularApi([
      [
        'POST',
        '/api/necesidades/7/ofertas/correo',
        () =>
          new Promise((resolve) => {
            terminarLectura = () =>
              resolve(
                respuestaJson({
                  ...SIN_ADJUNTOS,
                  proveedor: { id: 2, nombre: 'Acme', email: 'ventas@acme.test' },
                  adjuntos: [{ indice: 0, nombre: 'oferta.pdf', tamano: 100 }],
                }),
              )
          }),
      ],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Añadir oferta' }))
    const zonaCorreo = screen.getByLabelText('Correo de la oferta (.eml o .msg)')

    fireEvent.change(zonaCorreo, { target: { files: [archivo('oferta.eml')] } })
    await vi.waitFor(() => expect(terminarLectura).toBeTypeOf('function'))
    fireEvent.change(zonaCorreo, { target: { files: [archivo('oferta.pdf')] } })
    terminarLectura()

    expect(await screen.findByText('El correo de la oferta tiene que ser un archivo .eml o .msg.')).toBeInTheDocument()
    await vi.waitFor(() => expect(screen.queryByText('oferta.pdf (del correo)')).not.toBeInTheDocument())
    expect(screen.getByLabelText('Proveedor')).toHaveValue('')
  })

  it('si no se puede leer el correo, se sube igual con los adjuntos a mano', async () => {
    simularApi([['POST', '/api/necesidades/7/ofertas/correo', () => respuestaJson({ mensaje: 'Error' }, 500)]])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Añadir oferta' }))
    fireEvent.change(screen.getByLabelText('Correo de la oferta (.eml o .msg)'), { target: { files: [archivo('oferta.eml')] } })
    expect(await screen.findByText(/No se han podido leer los adjuntos/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Quitar el correo' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Subir oferta' })).toBeEnabled()
  })

  it('permite quitar el correo y los adjuntos elegidos antes de subir', async () => {
    simularApi()
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Añadir oferta' }))
    fireEvent.change(screen.getByLabelText('Correo de la oferta (.eml o .msg)'), { target: { files: [archivo('oferta.eml')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el correo' }))
    expect(screen.queryByRole('button', { name: 'Quitar el correo' })).not.toBeInTheDocument()

    fireEvent.change(screen.getByLabelText('Adjunto 1'), { target: { files: [archivo('oferta.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: 'Quitar el adjunto 1' }))
    // Queda una fila vacía para elegir otro archivo.
    expect(screen.getByLabelText('Tipo del adjunto 1')).toHaveValue('otro')
    expect(screen.queryByRole('button', { name: 'Quitar el adjunto 1' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Subir oferta' }))
    expect(screen.getByText('Sube el correo de la oferta (.eml o .msg).')).toBeInTheDocument()
  })

  it('no sube nada sin el correo', async () => {
    simularApi()
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Añadir oferta' }))
    fireEvent.click(screen.getByRole('button', { name: 'Subir oferta' }))
    expect(screen.getByText('Sube el correo de la oferta (.eml o .msg).')).toBeInTheDocument()
    expect(llamada('POST', '/api/necesidades/7/ofertas')).toBeUndefined()
  })

  it('revisa la oferta con importes en formato español', async () => {
    const revisada = { ...OFERTA, importe_sin_iva: '1250.50', fecha_entrega_estimada: '2026-11-19', revisada: true, avisos: [] }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([OFERTA])],
      ['PATCH', '/api/necesidades/7/ofertas/30', () => respuestaJson(revisada)],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar la oferta de Acme' }))
    fireEvent.change(screen.getByLabelText('Importe total sin IVA'), { target: { value: '1.250,50' } })
    fireEvent.change(screen.getByLabelText(/Plazo de entrega/), { target: { value: '4 semanas' } })
    fireEvent.click(screen.getByRole('button', { name: 'Añadir línea' }))
    fireEvent.change(screen.getByLabelText('Descripción de la línea 1'), { target: { value: 'Rodamiento' } })
    fireEvent.change(screen.getByLabelText('Cantidad de la línea 1'), { target: { value: '2,5' } })
    fireEvent.change(screen.getByLabelText('Precio unitario de la línea 1'), { target: { value: '500,20' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y dar por revisada' }))

    await vi.waitFor(() => expect(llamada('PATCH', '/api/necesidades/7/ofertas/30')).toBeDefined())
    const cuerpo = JSON.parse(llamada('PATCH', '/api/necesidades/7/ofertas/30')[1].body)
    expect(cuerpo).toMatchObject({
      importe_sin_iva: '1250.50',
      plazo_entrega_texto: '4 semanas',
      fecha_entrega_estimada: null,
      revisada: true,
      lineas: [{ descripcion: 'Rodamiento', cantidad: '2.5', precio_unitario: '500.20', fecha_entrega: null }],
    })
  })

  it('«Pedir datos que faltan» solo sale si falta algo y abre el correo propuesto', async () => {
    const completa = { ...OFERTA, id: 31, proveedor: { id: 3, nombre: 'Zeta', email: 'z@zeta.test' }, datos_que_faltan: [] }
    const incompleta = { ...OFERTA, datos_que_faltan: ['Embalaje'] }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([incompleta, completa])],
      ['POST', '/api/necesidades/7/ofertas/30/peticion-datos/borrador', () => respuestaJson({ para: 'ventas@acme.test', asunto: 'A', cuerpo: 'Hola', faltan: ['Embalaje'], avisos: [], con_ia: true })],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    const boton = await screen.findByRole('button', { name: 'Pedir los datos que faltan a Acme' })
    expect(screen.queryByRole('button', { name: 'Pedir los datos que faltan a Zeta' })).not.toBeInTheDocument()
    fireEvent.click(boton)
    expect(boton).toHaveAttribute('aria-expanded', 'true')
    expect(await screen.findByLabelText(/Cuerpo del correo/)).toHaveValue('Hola')
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(screen.queryByLabelText(/Cuerpo del correo/)).not.toBeInTheDocument()
  })

  it('corrige las condiciones de la oferta, cada una con su estado y su texto', async () => {
    const conCondiciones = {
      ...OFERTA,
      otros: 'Garantía de 12 meses',
      condiciones: [
        { clave: 'embalaje', nombre: 'Embalaje', estado: 'no_especificado', texto: null },
        { clave: 'incoterm', nombre: 'Incoterm / condiciones de entrega', estado: 'especificado', texto: 'FCA Barcelona' },
      ],
    }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([conCondiciones])],
      ['PATCH', '/api/necesidades/7/ofertas/30', () => respuestaJson(conCondiciones)],
    ])
    render(
      <main>
        <SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />
      </main>,
    )
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar la oferta de Acme' }))
    expect(screen.getByRole('group', { name: 'Otras condiciones' })).toBeInTheDocument()
    expect(screen.getByLabelText('Qué dice la oferta: Incoterm / condiciones de entrega')).toHaveValue('FCA Barcelona')
    expect(screen.getByLabelText('Información adicional (garantía…)')).toHaveValue('Garantía de 12 meses')
    fireEvent.change(screen.getByLabelText('Estado: Embalaje'), { target: { value: 'no_incluido' } })
    fireEvent.change(screen.getByLabelText('Qué dice la oferta: Embalaje'), { target: { value: ' 35 € por palé ' } })
    expect(await problemasDeAccesibilidad()).toEqual([])
    fireEvent.click(screen.getByRole('button', { name: 'Guardar sin revisar' }))

    await vi.waitFor(() => expect(llamada('PATCH', '/api/necesidades/7/ofertas/30')).toBeDefined())
    const cuerpo = JSON.parse(llamada('PATCH', '/api/necesidades/7/ofertas/30')[1].body)
    expect(cuerpo.condiciones).toEqual({
      embalaje: { estado: 'no_incluido', texto: '35 € por palé' },
      incoterm: { estado: 'especificado', texto: 'FCA Barcelona' },
    })
  })

  it('al guardar y dar por revisada, solo se cierra el editor y la pantalla vuelve a esa oferta', async () => {
    const completa = {
      ...OFERTA,
      importe_sin_iva: '100',
      fecha_entrega_estimada: '2026-11-19',
      lineas: [{ descripcion: 'Rodamiento', cantidad: '1', precio_unitario: '100', fecha_entrega: null }],
      avisos: [],
    }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([completa])],
      ['PATCH', '/api/necesidades/7/ofertas/30', () => respuestaJson({ ...completa, revisada: true })],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar la oferta de Acme' }))
    // Al cerrarse el editor, sin esto lo que había debajo (la comparativa) subía a la vista.
    const bajar = vi.spyOn(Element.prototype, 'scrollIntoView')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar y dar por revisada' }))
    await vi.waitFor(() => expect(screen.queryByRole('button', { name: 'Guardar y dar por revisada' })).not.toBeInTheDocument())
    const revisar = screen.getByRole('button', { name: 'Revisar la oferta de Acme' })
    expect(bajar).toHaveBeenCalledTimes(1)
    expect(bajar.mock.calls[0][0]).toEqual({ behavior: 'smooth', block: 'nearest' })
    expect(bajar.mock.contexts[0]).toBe(revisar.closest('li'))
    expect(revisar).toHaveFocus()
    bajar.mockRestore()
  })

  it('no guarda un importe que no es un número', async () => {
    // jsdom no implementa scrollIntoView: se simula para comprobar que la pantalla sube al error.
    const subir = vi.fn()
    Element.prototype.scrollIntoView = subir
    simularApi([['GET', '/api/necesidades/7/ofertas', () => respuestaJson([OFERTA])]])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar la oferta de Acme' }))
    fireEvent.change(screen.getByLabelText('Importe total sin IVA'), { target: { value: 'mil' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar sin revisar' }))
    expect(screen.getByText(/El importe sin IVA no es un número válido/)).toBeInTheDocument()
    // La pantalla sube hasta el campo con el error y el foco va a él.
    expect(subir).toHaveBeenCalled()
    expect(subir.mock.calls[0][0]).toEqual({ behavior: 'smooth', block: 'center' })
    expect(subir.mock.contexts[0]).toBe(screen.getByLabelText('Importe total sin IVA'))
    expect(screen.getByLabelText('Importe total sin IVA')).toHaveFocus()
    delete Element.prototype.scrollIntoView
    expect(llamada('PATCH', '/api/necesidades/7/ofertas/30')).toBeUndefined()
  })

  it('borra una oferta tras confirmar', async () => {
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([OFERTA])],
      ['DELETE', '/api/necesidades/7/ofertas/30', () => respuestaJson(null, 204)],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Borrar la oferta de Acme' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sí, borrar la oferta de Acme' }))
    await vi.waitFor(() => expect(llamada('DELETE', '/api/necesidades/7/ofertas/30')).toBeDefined())
  })

  it('al borrar una oferta desaparecen los avisos de la última subida', async () => {
    let lista = [OFERTA]
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson(lista)],
      [
        'POST',
        '/api/necesidades/7/ofertas/30/analisis',
        () => respuestaJson({ ...OFERTA, avisos: ['La IA avisa: La oferta es válida 30 días.'] }),
      ],
      [
        'DELETE',
        '/api/necesidades/7/ofertas/30',
        () => {
          lista = []
          return respuestaJson(null, 204)
        },
      ],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Reanalizar con IA la oferta de Acme' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sí, reanalizar la oferta de Acme' }))
    expect(await screen.findByRole('status')).toHaveTextContent('La oferta es válida 30 días.')
    fireEvent.click(screen.getByRole('button', { name: 'Borrar la oferta de Acme' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sí, borrar la oferta de Acme' }))
    expect(await screen.findByText('Todavía no hay ofertas.')).toBeInTheDocument()
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('con «menos movimiento» en el sistema, sube al error sin animación', async () => {
    const subir = vi.fn()
    Element.prototype.scrollIntoView = subir
    window.matchMedia = vi.fn(() => ({ matches: true }))
    simularApi([['GET', '/api/necesidades/7/ofertas', () => respuestaJson([OFERTA])]])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar la oferta de Acme' }))
    fireEvent.change(screen.getByLabelText('Importe total sin IVA'), { target: { value: 'mil' } })
    fireEvent.click(screen.getByRole('button', { name: 'Guardar sin revisar' }))
    expect(subir.mock.calls[0][0].behavior).toBe('auto')
    delete window.matchMedia
    delete Element.prototype.scrollIntoView
  })

  it('el plazo de cada línea se ve y se guarda con ella (CU-004)', async () => {
    const linea = { descripcion: 'Inserto', cantidad: '1', precio_unitario: '243', fecha_entrega: '2026-11-26', plazo_entrega_texto: '5 Sem.', fecha_calculada: true }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([{ ...OFERTA, lineas: [linea] }])],
      ['PATCH', '/api/necesidades/7/ofertas/30', () => respuestaJson({ ...OFERTA, lineas: [linea] })],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar la oferta de Acme' }))
    expect(screen.getByLabelText('Entrega de la línea 1')).toHaveValue('2026-11-26')
    expect(screen.getByLabelText('Plazo de la línea 1')).toHaveValue('5 Sem.')
    fireEvent.click(screen.getByRole('button', { name: 'Guardar sin revisar' }))
    await vi.waitFor(() => expect(llamada('PATCH', '/api/necesidades/7/ofertas/30')).toBeDefined())
    const cuerpo = JSON.parse(llamada('PATCH', '/api/necesidades/7/ofertas/30')[1].body)
    expect(cuerpo.lineas).toEqual([
      { descripcion: 'Inserto', cantidad: '1', precio_unitario: '243', fecha_entrega: '2026-11-26', plazo_entrega_texto: '5 Sem.' },
    ])
  })

  it('un error de la API en una línea dice qué línea y qué dato revisar', async () => {
    const conLinea = { ...OFERTA, lineas: [{ descripcion: 'Rodamiento', cantidad: '4', precio_unitario: '10', fecha_entrega: null }] }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([conLinea])],
      [
        'PATCH',
        '/api/necesidades/7/ofertas/30',
        () =>
          respuestaJson(
            {
              error: 'datos_no_validos',
              mensaje: 'Faltan datos o no tienen el formato correcto.',
              detalles: { campos: ['lineas.0.cantidad'] },
            },
            400,
          ),
      ],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar la oferta de Acme' }))
    fireEvent.click(screen.getByRole('button', { name: 'Guardar sin revisar' }))
    expect(await screen.findByText(/Revisa la cantidad de la línea 1/)).toBeInTheDocument()
  })

  it('no deja borrar la oferta que está leyendo la IA', async () => {
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([OFERTA])],
      ['POST', '/api/necesidades/7/ofertas/30/analisis', () => new Promise(() => {})],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Reanalizar con IA la oferta de Acme' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sí, reanalizar la oferta de Acme' }))
    expect(await screen.findByText('Leyendo con la IA…')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Borrar la oferta de Acme' })).toBeDisabled()
  })

  it('pregunta antes de cerrar el editor con cambios sin guardar', async () => {
    simularApi([['GET', '/api/necesidades/7/ofertas', () => respuestaJson([OFERTA])]])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    // Sin cambios, se cierra sin preguntar.
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar la oferta de Acme' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(screen.queryByLabelText('Importe total sin IVA')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Revisar la oferta de Acme' }))
    fireEvent.change(screen.getByLabelText('Importe total sin IVA'), { target: { value: '100' } })
    fireEvent.click(screen.getByRole('button', { name: 'Cerrar' }))
    expect(screen.getByText('Hay cambios sin guardar en esta oferta. ¿Cerrarla sin guardarlos?')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'No, seguir revisando' })).toHaveFocus()
    fireEvent.click(screen.getByRole('button', { name: 'No, seguir revisando' }))
    expect(screen.getByLabelText('Importe total sin IVA')).toHaveValue('100')

    // También al pulsar otra vez «Revisar».
    fireEvent.click(screen.getByRole('button', { name: 'Revisar la oferta de Acme' }))
    fireEvent.click(screen.getByRole('button', { name: 'Sí, cerrar sin guardar' }))
    expect(screen.queryByLabelText('Importe total sin IVA')).not.toBeInTheDocument()
  })

  it('al subir una oferta, un adjunto demasiado grande se señala en los adjuntos', async () => {
    simularApi([
      [
        'POST',
        '/api/necesidades/7/ofertas',
        () =>
          respuestaJson(
            { error: 'archivo_demasiado_grande', mensaje: 'El archivo «oferta.pdf» supera el máximo de 25 MB.', detalles: { archivo: 'oferta.pdf' } },
            413,
          ),
      ],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Añadir oferta' }))
    fireEvent.change(screen.getByLabelText('Correo de la oferta (.eml o .msg)'), { target: { files: [archivo('oferta.eml')] } })
    fireEvent.change(screen.getByLabelText('Adjunto 1'), { target: { files: [archivo('oferta.pdf')] } })
    await esperarLectura()
    fireEvent.click(screen.getByRole('button', { name: 'Subir oferta' }))
    const mensaje = await screen.findByText('El archivo «oferta.pdf» supera el máximo de 25 MB.')
    expect(mensaje.closest('fieldset')).toHaveAccessibleDescription('El archivo «oferta.pdf» supera el máximo de 25 MB.')
  })

  it('«Analizar y comparar» lee todas las ofertas, pasa a evaluación y muestra la comparativa', async () => {
    const actualizada = vi.fn()
    const leida = { ...OFERTA, importe_sin_iva: '1000', fecha_entrega_estimada: '2026-11-19' }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([{ ...OFERTA, sin_analizar: true }])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([leida])],
      [
        'POST',
        '/api/necesidades/7/evaluacion',
        () =>
          respuestaJson({
            necesidad: { ...NECESIDAD, estado: 'en_evaluacion' },
            avisos: ['Acme: La IA avisa: La oferta es válida 30 días.'],
          }),
      ],
    ])
    const { rerender } = render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={actualizada} />)
    await screen.findByRole('option', { name: 'Ana Prueba' })
    expect(screen.queryByRole('button', { name: 'Pasar a evaluación' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Analizar y comparar' }))
    await vi.waitFor(() => expect(actualizada).toHaveBeenCalledWith(expect.objectContaining({ estado: 'en_evaluacion' })))
    expect(JSON.parse(llamada('POST', '/api/necesidades/7/evaluacion')[1].body)).toEqual({ peticionario_id: 1 })
    expect(await screen.findByText('Acme: La IA avisa: La oferta es válida 30 días.')).toBeInTheDocument()
    // Quien la usa cambia el estado: la comparativa sale sin pulsar nada, y ya sin resumen de
    // ventajas e inconvenientes.
    rerender(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={actualizada} />)
    expect(await screen.findByRole('table')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Actualizar comparación' })).not.toBeInTheDocument()
  })

  it('en «En evaluación», analiza las ofertas que llegan después sin pedir quién', async () => {
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([{ ...OFERTA, sin_analizar: true }])],
      [
        'POST',
        '/api/necesidades/7/evaluacion',
        () => respuestaJson({ necesidad: { ...NECESIDAD, estado: 'en_evaluacion' }, avisos: [] }),
      ],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    expect(await screen.findByText(/Hay 1 oferta sin analizar/)).toBeInTheDocument()
    expect(screen.queryByLabelText('Quién pasa a evaluación')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Analizar las nuevas y volver a comparar' }))
    await vi.waitFor(() => expect(llamada('POST', '/api/necesidades/7/evaluacion')).toBeDefined())
    expect(JSON.parse(llamada('POST', '/api/necesidades/7/evaluacion')[1].body)).toEqual({ peticionario_id: null })
  })

  it('al terminar «Analizar las nuevas…», el foco va a la comparativa y se anuncia', async () => {
    let analizada = false
    const leida = { ...OFERTA, importe_sin_iva: '1000' }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([{ ...OFERTA, sin_analizar: !analizada }])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson(analizada ? [leida] : [])],
      [
        'POST',
        '/api/necesidades/7/evaluacion',
        () => {
          analizada = true
          return respuestaJson({ necesidad: { ...NECESIDAD, estado: 'en_evaluacion' }, avisos: [] })
        },
      ],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    const boton = await screen.findByRole('button', { name: 'Analizar las nuevas y volver a comparar' })
    boton.focus()
    fireEvent.click(boton)
    expect(await screen.findByRole('status')).toHaveTextContent('Análisis terminado')
    await vi.waitFor(() => expect(screen.queryByRole('button', { name: /Analizar las nuevas/ })).not.toBeInTheDocument())
    expect(document.activeElement).toBe(screen.getByRole('heading', { name: 'Comparativa de las ofertas' }))
  })

  it('si «Analizar y comparar» falla, vuelve a cargar la necesidad y las ofertas', async () => {
    const actualizada = vi.fn()
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([{ ...OFERTA, sin_analizar: true }])],
      ['POST', '/api/necesidades/7/evaluacion', () => respuestaJson({ error: 'error_interno', mensaje: 'Error interno.' }, 500)],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={actualizada} />)
    await screen.findByRole('option', { name: 'Ana Prueba' })
    const antes = llamadas('GET', '/api/necesidades/7/ofertas').length
    fireEvent.click(screen.getByRole('button', { name: 'Analizar y comparar' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Error interno.')
    // El servidor puede haberla pasado ya a «En evaluación»: sin datos, la página la vuelve a pedir.
    expect(actualizada).toHaveBeenCalledWith()
    await vi.waitFor(() => expect(llamadas('GET', '/api/necesidades/7/ofertas').length).toBe(antes + 1))
  })

  it('mientras se analiza no se puede borrar ni cambiar quién', async () => {
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([{ ...OFERTA, sin_analizar: true }])],
      ['POST', '/api/necesidades/7/evaluacion', () => new Promise(() => {})],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    await screen.findByRole('option', { name: 'Ana Prueba' })
    fireEvent.click(screen.getByRole('button', { name: 'Analizar y comparar' }))
    expect(await screen.findByRole('button', { name: 'Analizando con la IA…' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Borrar la oferta de Acme' })).toBeDisabled()
    expect(screen.getByLabelText('Quién pasa a evaluación')).toBeDisabled()
  })

  it('en la comparativa, una oferta sin revisar se marca y no se puede elegir', async () => {
    const leida = { ...OFERTA, importe_sin_iva: '1000', fecha_entrega_estimada: '2026-11-19' }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([leida])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([leida])],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    const tabla = await screen.findByRole('table')
    expect(within(tabla).getByRole('columnheader', { name: /Acme/ })).toHaveTextContent('Sin revisar')
    expect(screen.getByText(/revisa antes todas/)).toHaveTextContent('Falta: Acme.')
    expect(screen.queryByRole('button', { name: 'Elegir la oferta de Acme' })).not.toBeInTheDocument()
  })

  it('no se puede elegir ninguna oferta hasta revisarlas todas', async () => {
    const revisada = { ...OFERTA, importe_sin_iva: '1000', fecha_entrega_estimada: '2026-11-19', revisada: true }
    const zeta = { ...OFERTA, id: 31, proveedor: { id: 3, nombre: 'Zeta', email: 'ofertas@zeta.test' }, importe_sin_iva: '900' }
    // Una tercera oferta sin datos (la IA no la leyó) tampoco está revisada: también falta.
    const beta = { ...OFERTA, id: 32, proveedor: { id: 4, nombre: 'Beta', email: 'beta@beta.test' }, sin_analizar: true }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([revisada, zeta, beta])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([zeta, revisada])],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    expect(await screen.findByText(/revisa antes todas/)).toHaveTextContent('Falta: Zeta, Beta.')
    expect(screen.queryByRole('button', { name: /^Elegir la oferta/ })).not.toBeInTheDocument()
  })

  it('la oferta elegida dice «Elegida» y se anuncia como pulsada', async () => {
    const revisada = { ...OFERTA, importe_sin_iva: '1000', fecha_entrega_estimada: '2026-11-19', revisada: true }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([revisada])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([revisada])],
      ['POST', '/api/necesidades/7/adjudicacion/borrador', () => new Promise(() => {})],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Elegir la oferta de Acme' }))
    const elegida = await screen.findByRole('button', { name: 'Elegida la oferta de Acme' })
    expect(elegida).toHaveTextContent('Elegida')
    expect(elegida).toHaveAttribute('aria-pressed', 'true')
  })

  it('muestra la comparativa en «En evaluación» con los importes por separado', async () => {
    const revisada = { ...OFERTA, importe_sin_iva: '1000', fecha_entrega_estimada: '2026-11-19', revisada: true }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([revisada])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([revisada])],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    // Proveedores en columnas y datos en filas.
    const tabla = await screen.findByRole('table')
    expect(within(tabla).getByRole('columnheader', { name: /Acme/ })).toHaveTextContent('Revisada')
    const fila = (nombre) => within(tabla).getByRole('rowheader', { name: nombre }).closest('tr')
    expect(fila('Importe sin IVA')).toHaveTextContent('1.000,00')
    // Ingeniero: todos los importes son sin IVA.
    expect(within(tabla).queryByRole('rowheader', { name: /con IVA/i })).not.toBeInTheDocument()
    expect(fila('Entrega')).toHaveTextContent('19.11.2026')
    // CU-010: sin datos del histórico, «Sin pedidos anteriores».
    expect(fila('Retrasos del proveedor')).toHaveTextContent('Sin pedidos anteriores')
    expect(within(tabla).getByRole('button', { name: 'Elegir la oferta de Acme' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Analizar y comparar' })).not.toBeInTheDocument()
  })

  it('reanaliza una oferta con la IA tras confirmarlo y abre la revisión con los datos nuevos', async () => {
    let lista = [{ ...OFERTA, numero_oferta: 'A MANO' }]
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson(lista)],
      [
        'POST',
        '/api/necesidades/7/ofertas/30/analisis',
        () => {
          lista = [{ ...OFERTA, numero_oferta: 'OF-55' }]
          return respuestaJson({ ...lista[0], avisos: ['La IA avisa: Hay dos alternativas.'] })
        },
      ],
    ])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Reanalizar con IA la oferta de Acme' }))
    expect(llamada('POST', '/api/necesidades/7/ofertas/30/analisis')).toBeUndefined()
    fireEvent.click(screen.getByRole('button', { name: 'Sí, reanalizar la oferta de Acme' }))
    expect(await screen.findByRole('status')).toHaveTextContent('Hay dos alternativas.')
    expect(await screen.findByDisplayValue('OF-55')).toBeInTheDocument()
  })

  it('al revisar, los avisos de lo que falta se actualizan mientras se escribe', async () => {
    simularApi([['GET', '/api/necesidades/7/ofertas', () => respuestaJson([OFERTA])]])
    render(<SeccionOfertas necesidad={NECESIDAD} onActualizada={vi.fn()} />)
    fireEvent.click(await screen.findByRole('button', { name: 'Revisar la oferta de Acme' }))
    // Solo se ve el aviso del editor, no el de la oferta guardada.
    expect(screen.getAllByText(/Falta:/)).toHaveLength(1)
    expect(screen.getByText(/Falta:/)).toHaveTextContent('Falta: importe sin IVA, fecha de entrega.')
    expect(screen.queryByLabelText(/con IVA/)).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Importe total sin IVA'), { target: { value: '150' } })
    expect(screen.getByText(/Falta:/)).toHaveTextContent('Falta: fecha de entrega.')
    fireEvent.change(screen.getByLabelText('Plazo de entrega (tal como lo da el proveedor)'), { target: { value: '4 semanas' } })
    expect(screen.queryByText(/Falta:/)).not.toBeInTheDocument()
  })

  it('marca en verde el mejor y en rojo el peor valor, con su texto', async () => {
    const acme = {
      ...OFERTA,
      importe_sin_iva: '1000',
      fecha_entrega_estimada: '2026-11-19',
      revisada: true,
      destacados: { importe: 'peor', entrega: 'mejor', retrasos: null },
      // Dos de las nueve condiciones (la API da siempre las nueve).
      condiciones: [
        { clave: 'incoterm', nombre: 'Incoterm / condiciones de entrega', estado: 'especificado', texto: 'FCA Barcelona' },
        { clave: 'transporte', nombre: 'Transporte', estado: 'no_especificado', texto: null },
      ],
      otros: 'Garantía de 12 meses',
    }
    const beta = {
      ...acme,
      id: 31,
      proveedor: { id: 3, nombre: 'Beta', email: 'beta@beta.test' },
      importe_sin_iva: '900',
      fecha_entrega_estimada: '2026-11-30',
      destacados: { importe: 'mejor', entrega: 'peor', retrasos: null },
      condiciones: [
        { clave: 'incoterm', nombre: 'Incoterm / condiciones de entrega', estado: 'no_especificado', texto: null },
        { clave: 'transporte', nombre: 'Transporte', estado: 'no_incluido', texto: 'Portes a cargo del cliente' },
      ],
      otros: null,
    }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([acme, beta])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([beta, acme])],
    ])
    // Dentro de <main>, como en la página (si no, axe-core pide una región).
    render(
      <main>
        <SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />
      </main>,
    )
    const tabla = await screen.findByRole('table')
    // «Retrasos» va justo después de «Entrega».
    expect(within(tabla).getAllByRole('rowheader').map((th) => th.textContent)).toEqual([
      'Importe sin IVA',
      'Entrega',
      'Retrasos del proveedor',
      'Comentarios de entregas anteriores',
      'Condiciones de pago',
      'Incoterm / condiciones de entrega',
      'Transporte',
      'Información adicional',
      'Elegir',
    ])
    const celdas = (nombre) => within(within(tabla).getByRole('rowheader', { name: nombre }).closest('tr')).getAllByRole('cell')
    // Las condiciones van en su apartado y no se destacan.
    expect(within(tabla).getByRole('columnheader', { name: 'Otras condiciones' })).toBeInTheDocument()
    expect(celdas('Incoterm / condiciones de entrega').map((c) => c.textContent)).toEqual(['No especificado', 'FCA Barcelona'])
    expect(celdas('Transporte').map((c) => c.textContent)).toEqual(['No incluido: Portes a cargo del cliente', 'No especificado'])
    for (const celda of celdas('Transporte')) expect(celda).not.toHaveClass('bg-green-50')
    expect(celdas('Información adicional').map((c) => c.textContent)).toEqual(['—', 'Garantía de 12 meses'])
    const [importeBeta, importeAcme] = celdas('Importe sin IVA')
    expect(importeBeta).toHaveTextContent('900,00 €Mejor')
    expect(importeBeta).toHaveClass('bg-green-50')
    expect(importeAcme).toHaveTextContent('1.000,00 €Peor')
    expect(importeAcme).toHaveClass('bg-red-50')
    const [entregaBeta, entregaAcme] = celdas('Entrega')
    expect(entregaBeta).toHaveTextContent('Peor')
    expect(entregaAcme).toHaveTextContent('Mejor')
    for (const celda of celdas('Retrasos del proveedor')) expect(celda).not.toHaveTextContent(/Mejor|Peor/)
    expect(screen.getByText(/En verde, el mejor valor; en rojo, el peor \(el precio, solo si todas las ofertas están en la misma moneda\)/)).toBeInTheDocument()
    // Todas las celdas de una columna llevan el mismo margen, marcadas o no.
    for (const celda of [...celdas('Importe sin IVA'), ...celdas('Condiciones de pago')]) expect(celda).toHaveClass('pl-2')
    expect(await problemasDeAccesibilidad()).toEqual([])
  })

  it('marca también los retrasos, sin perder el enlace al histórico', async () => {
    const sinMarcas = { importe: null, entrega: null }
    const acme = {
      ...OFERTA,
      importe_sin_iva: '1000',
      revisada: true,
      historial_proveedor: { pedidos: 4, con_retraso: 0, dias_retraso: 0, retraso_medio: 0 },
      destacados: { ...sinMarcas, retrasos: 'mejor' },
    }
    const beta = {
      ...acme,
      id: 31,
      proveedor: { id: 3, nombre: 'Beta', email: 'beta@beta.test' },
      historial_proveedor: { pedidos: 2, con_retraso: 1, dias_retraso: 6, retraso_medio: 3 },
      destacados: { ...sinMarcas, retrasos: 'peor' },
    }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([acme, beta])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([acme, beta])],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    const tabla = await screen.findByRole('table')
    const fila = within(tabla).getByRole('rowheader', { name: 'Retrasos del proveedor' }).closest('tr')
    const [retrasosAcme, retrasosBeta] = within(fila).getAllByRole('cell')
    expect(retrasosAcme).toHaveTextContent('Mejor')
    expect(retrasosAcme).toHaveClass('bg-green-50')
    expect(within(retrasosAcme).getByRole('link')).toHaveAttribute('href', '/proveedores/2/retrasos')
    expect(retrasosBeta).toHaveTextContent('Peor')
    expect(retrasosBeta).toHaveClass('bg-red-50')
    // El color de la marca sustituye al ámbar de «con retraso».
    expect(retrasosBeta).not.toHaveClass('text-amber-900')
    expect(within(retrasosBeta).getByRole('link')).toHaveAttribute('href', '/proveedores/3/retrasos')
  })

  it('con todas revisadas pero nada marcado no habla de colores', async () => {
    const unica = { ...OFERTA, importe_sin_iva: '1000', revisada: true, destacados: { importe: null, entrega: null, retrasos: null } }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([unica])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([unica])],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    await screen.findByRole('table')
    expect(screen.queryByText(/En verde/)).not.toBeInTheDocument()
    expect(screen.getByText('La aplicación no elige proveedor.')).toBeInTheDocument()
  })

  it('sin todas revisadas no hay marcas y se explica cuándo salen', async () => {
    const leida = { ...OFERTA, importe_sin_iva: '1000', destacados: { importe: null, entrega: null, retrasos: null } }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([leida])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([leida])],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    const tabla = await screen.findByRole('table')
    expect(within(tabla).queryByText(/^(Mejor|Peor)$/)).not.toBeInTheDocument()
    expect(screen.getByText(/se marcan cuando estén revisadas todas las ofertas/)).toBeInTheDocument()
  })

  it('la comparativa muestra el histórico de retrasos de cada proveedor', async () => {
    const revisada = {
      ...OFERTA,
      importe_sin_iva: '1000',
      fecha_entrega_estimada: '2026-11-19',
      revisada: true,
      historial_proveedor: { pedidos: 5, con_retraso: 2, retraso_medio: 2.4 },
    }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([revisada])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([revisada])],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    // Lo que cuenta es el retraso medio, junto con la proporción.
    const enlace = await screen.findByRole('link', {
      name: /^Retraso medio: 2,4 días por pedido\. 2 de 5 pedidos con retraso \(40 %\) ?\(se abre en otra pestaña\)$/,
    })
    expect(enlace).toHaveAttribute('href', '/proveedores/2/retrasos')
    // En otra pestaña, para no perder la adjudicación que se esté preparando.
    expect(enlace).toHaveAttribute('target', '_blank')
  })

  it('la comparativa muestra los comentarios de las entregas anteriores del proveedor', async () => {
    const comentarios = [
      { necesidad_id: 3, codigo: '2026101001', titulo: 'A', fecha: '2026-10-20', texto: 'Embalaje roto.' },
      { necesidad_id: 2, codigo: '2026100101', titulo: 'B', fecha: '2026-10-01', texto: 'Llegó mojado.' },
      { necesidad_id: 1, codigo: '2026090101', titulo: 'C', fecha: '2026-09-01', texto: 'Faltaba una pieza.' },
    ]
    const revisada = {
      ...OFERTA,
      importe_sin_iva: '1000',
      revisada: true,
      historial_proveedor: { pedidos: 3, con_retraso: 0, retraso_medio: 0, comentarios },
    }
    simularApi([
      ['GET', '/api/necesidades/7/ofertas', () => respuestaJson([revisada])],
      ['GET', '/api/necesidades/7/comparativa', () => respuestaJson([revisada])],
    ])
    render(<SeccionOfertas necesidad={{ ...NECESIDAD, estado: 'en_evaluacion' }} onActualizada={vi.fn()} />)
    const fila = (await screen.findByRole('rowheader', { name: 'Comentarios de entregas anteriores' })).closest('tr')
    // Los dos más recientes a la vista; el resto, en su histórico.
    expect(fila).toHaveTextContent('20.10.2026: Embalaje roto.')
    expect(fila).toHaveTextContent('01.10.2026: Llegó mojado.')
    expect(fila).not.toHaveTextContent('Faltaba una pieza.')
    expect(within(fila).getByRole('link', { name: /Ver los 3 comentarios/ })).toHaveAttribute('href', '/proveedores/2/retrasos')
    // Probador: los saltos de línea del comentario se respetan.
    expect(within(fila).getByText('Embalaje roto.').closest('li')).toHaveClass('whitespace-pre-line')
  })
})
