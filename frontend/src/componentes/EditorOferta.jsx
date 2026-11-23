// CU-004 — Revisar y corregir los datos de una oferta (los propone la IA o se escriben a mano) y
// marcarla como revisada. Los importes se escriben con coma decimal («1.250,50»).
import { useEffect, useRef, useState } from 'react'
import { corregirOferta } from '../api/ofertas.js'
import { llevarA } from '../desplazamiento.js'
import { aDecimal, importe, paraEditar } from '../formatos.js'
import { ESTADOS_CONDICION } from '../condiciones.js'
import Campo, { claseEntrada, claseBoton, claseBotonSecundario } from './Campo.jsx'
import SelectorMoneda from './SelectorMoneda.jsx'

const DATOS_LINEA = {
  descripcion: 'la descripción',
  cantidad: 'la cantidad',
  precio_unitario: 'el precio unitario',
  fecha_entrega: 'la fecha',
  plazo_entrega_texto: 'el plazo',
}

// La API señala los errores de las líneas como «lineas.0.cantidad» en `detalles.campos`: se dice
// qué línea y qué dato hay que revisar.
function errorDeLinea(detalles) {
  const ruta = (detalles?.campos ?? []).find((c) => /^lineas\.\d+\./.test(c))
  if (!ruta) return null
  const [, numero, dato] = ruta.split('.')
  return `Revisa ${DATOS_LINEA[dato] ?? 'los datos'} de la línea ${Number(numero) + 1}: no tiene un formato válido o es demasiado grande.`
}

const LINEA_VACIA = { descripcion: '', cantidad: '', precio_unitario: '', fecha_entrega: '', plazo_entrega_texto: '' }
const ETIQUETAS = {
  importe_sin_iva: 'importe sin IVA',
}

function inicial(oferta) {
  return {
    // EUR por defecto: casi todas las ofertas llegan en euros.
    moneda: oferta.moneda ?? 'EUR',
    numero_oferta: oferta.numero_oferta ?? '',
    importe_sin_iva: paraEditar(oferta.importe_sin_iva),
    plazo_entrega_texto: oferta.plazo_entrega_texto ?? '',
    fecha_entrega_estimada: oferta.fecha_entrega_estimada ?? '',
    condiciones_pago: oferta.condiciones_pago ?? '',
    otros: oferta.otros ?? '',
    // Las nueve condiciones: { clave: { estado, texto } }.
    condiciones: Object.fromEntries((oferta.condiciones ?? []).map((c) => [c.clave, { estado: c.estado, texto: c.texto ?? '' }])),
  }
}

// Los mismos avisos que da el backend (datos que faltan o no cuadran), al momento mientras se
// escribe. La fecha no falta si hay un plazo: al guardar, el backend la calcula con él.
function avisosEnVivo(datos, lineas) {
  const numero = (texto, decimales) => {
    const valor = aDecimal(texto, decimales)
    return valor === null || Number.isNaN(valor) ? null : Number(valor)
  }
  const sinIva = numero(datos.importe_sin_iva, 2)
  const avisos = []
  const faltan = [
    sinIva === null && 'importe sin IVA',
    !datos.fecha_entrega_estimada && !datos.plazo_entrega_texto.trim() && 'fecha de entrega',
  ].filter(Boolean)
  if (faltan.length) avisos.push(`Falta: ${faltan.join(', ')}.`)
  const validas = lineas
    .map((l) => [numero(l.cantidad, 3), numero(l.precio_unitario, 4)])
    .filter(([cantidad, precio]) => cantidad !== null && precio !== null)
  if (validas.length && sinIva !== null) {
    const suma = validas.reduce((total, [cantidad, precio]) => total + cantidad * precio, 0)
    if (Math.abs(suma - sinIva) > 0.01)
      avisos.push(`La suma de las líneas (${importe(suma)}) no coincide con el importe sin IVA (${importe(sinIva)}).`)
  }
  return avisos
}

export default function EditorOferta({ necesidadId, oferta, onGuardada, onCerrar, onCambios }) {
  const [datos, setDatos] = useState(() => inicial(oferta))
  const [lineas, setLineas] = useState(() =>
    oferta.lineas.map((l) => ({
      descripcion: l.descripcion,
      cantidad: paraEditar(l.cantidad),
      precio_unitario: paraEditar(l.precio_unitario),
      fecha_entrega: l.fecha_entrega ?? '',
      // El plazo de la línea («5 Sem.»): se guarda con ella para contarlo desde el pedido.
      plazo_entrega_texto: l.plazo_entrega_texto ?? '',
    })),
  )
  const [errores, setErrores] = useState({})
  const [guardando, setGuardando] = useState(false)
  // Avisa a quien lo abre de si hay cambios sin guardar, para preguntar antes de cerrarlo. Se
  // compara con lo que había al abrirlo.
  const [original] = useState(() => JSON.stringify([datos, lineas]))
  const cambiado = JSON.stringify([datos, lineas]) !== original
  useEffect(() => {
    onCambios?.(cambiado)
  }, [cambiado, onCambios])
  // Cada intento de guardar con errores sube la pantalla hasta el primero.
  const [intentosConError, setIntentosConError] = useState(0)
  const raiz = useRef(null)
  useEffect(() => {
    if (!intentosConError) return
    const primero = raiz.current?.querySelector('[aria-invalid="true"], [role="alert"]')
    llevarA(primero, { bloque: 'center' })
    if (primero?.matches('[aria-invalid="true"]')) primero.focus({ preventScroll: true })
  }, [intentosConError])

  const cambiar = (campo) => (e) => setDatos({ ...datos, [campo]: e.target.value })
  const cambiarCondicion = (clave, cambio) =>
    setDatos({ ...datos, condiciones: { ...datos.condiciones, [clave]: { ...datos.condiciones[clave], ...cambio } } })

  function cambiarLinea(i, cambio) {
    setLineas(lineas.map((l, j) => (j === i ? { ...l, ...cambio } : l)))
  }

  // Convierte lo escrito al formato de la API; devuelve null y marca errores si algo no vale.
  function preparar() {
    const nuevosErrores = {}
    const cuerpo = { ...datos, fecha_entrega_estimada: datos.fecha_entrega_estimada || null }
    cuerpo.condiciones = Object.fromEntries(
      Object.entries(datos.condiciones).map(([clave, c]) => [clave, { estado: c.estado, texto: c.texto.trim() || null }]),
    )
    for (const campo of ['importe_sin_iva']) {
      // Importes con 2 decimales como mucho (como la API).
      const valor = aDecimal(datos[campo], 2)
      if (Number.isNaN(valor)) nuevosErrores[campo] = `El ${ETIQUETAS[campo]} no es un número válido (como mucho 2 decimales).`
      cuerpo[campo] = valor
    }
    const convertidas = lineas
      .filter((l) => l.descripcion.trim() || l.cantidad || l.precio_unitario)
      .map((l) => ({
        descripcion: l.descripcion,
        cantidad: aDecimal(l.cantidad, 3),
        precio_unitario: aDecimal(l.precio_unitario, 4),
        fecha_entrega: l.fecha_entrega || null,
        plazo_entrega_texto: l.plazo_entrega_texto.trim() || null,
      }))
    if (convertidas.some((l) => !l.descripcion.trim() || !l.cantidad || Number.isNaN(l.cantidad) || l.precio_unitario === null || Number.isNaN(l.precio_unitario)))
      nuevosErrores.lineas =
        'Cada línea necesita descripción, cantidad (hasta 3 decimales) y precio unitario (hasta 4 decimales).'
    cuerpo.lineas = convertidas
    setErrores(nuevosErrores)
    return Object.keys(nuevosErrores).length ? null : cuerpo
  }

  async function guardar(revisada) {
    const cuerpo = preparar()
    if (!cuerpo) return setIntentosConError((n) => n + 1)
    // Al guardar sin revisar, una oferta que ya estaba revisada deja de contar hasta revisarla.
    cuerpo.revisada = revisada
    setGuardando(true)
    try {
      const guardada = await corregirOferta(necesidadId, oferta.id, cuerpo)
      onGuardada(guardada, revisada)
    } catch (error) {
      const campo = error.detalles?.campo
      const linea = errorDeLinea(error.detalles)
      setErrores(linea ? { lineas: linea } : campo && campo !== 'lineas' ? { [campo]: error.message } : { general: error.message })
      setIntentosConError((n) => n + 1)
    } finally {
      setGuardando(false)
    }
  }

  const avisos = avisosEnVivo(datos, lineas)
  // Al lado de cada precio; cambiar uno cambia todos, porque es la moneda de la oferta.
  const moneda = (etiqueta) => (
    <SelectorMoneda etiqueta={etiqueta} value={datos.moneda} original={oferta.moneda} onChange={(valor) => setDatos({ ...datos, moneda: valor })} disabled={guardando} />
  )

  return (
    <div ref={raiz} className="grid gap-4 rounded border border-slate-200 bg-slate-50 p-4">
      {avisos.length > 0 && (
        <ul className="text-sm text-amber-900">
          {avisos.map((a) => (
            <li key={a}>⚠ {a}</li>
          ))}
        </ul>
      )}
      <div className="grid gap-4 sm:grid-cols-3">
        <Campo etiqueta="Número de oferta" error={errores.numero_oferta}>
          {(props) => <input {...props} className={claseEntrada} maxLength={100} value={datos.numero_oferta} onChange={cambiar('numero_oferta')} />}
        </Campo>
        <Campo etiqueta="Importe total sin IVA" error={errores.importe_sin_iva}>
          {(props) => (
            <div className="flex gap-1">
              <input {...props} inputMode="decimal" className={`${claseEntrada} min-w-0`} value={datos.importe_sin_iva} onChange={cambiar('importe_sin_iva')} />
              {moneda('Moneda del importe sin IVA')}
            </div>
          )}
        </Campo>
        <Campo etiqueta="Plazo de entrega (tal como lo da el proveedor)" error={errores.plazo_entrega_texto}>
          {(props) => <input {...props} className={claseEntrada} maxLength={200} value={datos.plazo_entrega_texto} onChange={cambiar('plazo_entrega_texto')} />}
        </Campo>
        <Campo etiqueta="Fecha de entrega estimada" error={errores.fecha_entrega_estimada}>
          {(props) => (
            <input {...props} type="date" className={claseEntrada} value={datos.fecha_entrega_estimada} onChange={cambiar('fecha_entrega_estimada')} />
          )}
        </Campo>
        <Campo etiqueta="Condiciones de pago">
          {(props) => <input {...props} className={claseEntrada} value={datos.condiciones_pago} onChange={cambiar('condiciones_pago')} />}
        </Campo>
      </div>
      {errores.moneda && (
        <p role="alert" className="-mt-2 text-sm text-red-700">
          {errores.moneda}
        </p>
      )}
      <p className="-mt-2 text-xs text-slate-600">
        Si dejas la fecha vacía y escribes un plazo como «4 semanas», la fecha se calcula desde el envío del correo para comparar; al hacer el pedido, el plazo se cuenta desde ese día. Lo mismo con el plazo de cada línea.
      </p>
      {(oferta.condiciones ?? []).length > 0 && (
        <fieldset>
          <legend className="mb-2 text-sm font-medium">Otras condiciones</legend>
          <div className="grid gap-2">
            {oferta.condiciones.map(({ clave, nombre }) => (
              <div key={clave} className="grid gap-2 text-sm sm:grid-cols-[14rem_10rem_1fr] sm:items-center">
                <span className="font-medium">{nombre}</span>
                <select
                  aria-label={`Estado: ${nombre}`}
                  className={claseEntrada}
                  value={datos.condiciones[clave].estado}
                  onChange={(e) => cambiarCondicion(clave, { estado: e.target.value })}
                >
                  {ESTADOS_CONDICION.map(([valor, texto]) => (
                    <option key={valor} value={valor}>
                      {texto}
                    </option>
                  ))}
                </select>
                <input
                  aria-label={`Qué dice la oferta: ${nombre}`}
                  className={claseEntrada}
                  maxLength={500}
                  value={datos.condiciones[clave].texto}
                  onChange={(e) => cambiarCondicion(clave, { texto: e.target.value })}
                />
              </div>
            ))}
          </div>
        </fieldset>
      )}
      <Campo etiqueta="Información adicional (garantía…)">
        {(props) => <textarea {...props} rows={2} className={claseEntrada} value={datos.otros} onChange={cambiar('otros')} />}
      </Campo>

      <fieldset>
        <legend className="mb-2 text-sm font-medium">Líneas de la oferta (precios unitarios sin IVA)</legend>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left">
              <th className="font-medium">Descripción</th>
              <th className="w-24 font-medium">Cantidad</th>
              <th className="w-44 font-medium">Precio unitario</th>
              <th className="w-40 font-medium">Entrega</th>
              <th className="w-16">
                <span className="sr-only">Acciones</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {lineas.map((linea, i) => (
              <tr key={i}>
                <td className="py-1 pr-2">
                  <input aria-label={`Descripción de la línea ${i + 1}`} className={claseEntrada} value={linea.descripcion} onChange={(e) => cambiarLinea(i, { descripcion: e.target.value })} />
                </td>
                <td className="pr-2">
                  <input aria-label={`Cantidad de la línea ${i + 1}`} inputMode="decimal" className={claseEntrada} value={linea.cantidad} onChange={(e) => cambiarLinea(i, { cantidad: e.target.value })} />
                </td>
                <td className="pr-2">
                  <div className="flex gap-1">
                    <input aria-label={`Precio unitario de la línea ${i + 1}`} inputMode="decimal" className={`${claseEntrada} min-w-0`} value={linea.precio_unitario} onChange={(e) => cambiarLinea(i, { precio_unitario: e.target.value })} />
                    {moneda(`Moneda del precio unitario de la línea ${i + 1}`)}
                  </div>
                </td>
                <td className="pr-2">
                  <input aria-label={`Entrega de la línea ${i + 1}`} type="date" className={claseEntrada} value={linea.fecha_entrega} onChange={(e) => cambiarLinea(i, { fecha_entrega: e.target.value })} />
                  <input
                    aria-label={`Plazo de la línea ${i + 1}`}
                    placeholder="Plazo (opcional)"
                    maxLength={200}
                    className={`${claseEntrada} mt-1 text-xs`}
                    value={linea.plazo_entrega_texto}
                    onChange={(e) => cambiarLinea(i, { plazo_entrega_texto: e.target.value })}
                  />
                </td>
                <td>
                  <button type="button" className="text-slate-700 hover:underline" aria-label={`Quitar la línea ${i + 1}`} onClick={() => setLineas(lineas.filter((_, j) => j !== i))}>
                    Quitar
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <button type="button" className="mt-2 text-sm text-marca-acento hover:underline" onClick={() => setLineas([...lineas, { ...LINEA_VACIA }])}>
          Añadir línea
        </button>
        {errores.lineas && (
          <p role="alert" className="mt-1 text-sm text-red-700">
            {errores.lineas}
          </p>
        )}
      </fieldset>

      {errores.general && (
        <p role="alert" className="text-sm text-red-700">
          {errores.general}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-4">
        <button type="button" className={claseBoton} disabled={guardando} onClick={() => guardar(true)}>
          Guardar y dar por revisada
        </button>
        <button type="button" className={claseBotonSecundario} disabled={guardando} onClick={() => guardar(false)}>
          Guardar sin revisar
        </button>
        <button type="button" className="text-sm text-slate-700 hover:underline" onClick={onCerrar}>
          Cerrar
        </button>
      </div>
    </div>
  )
}
