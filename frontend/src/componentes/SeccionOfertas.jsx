// CU-004 — Ofertas de la necesidad («En cotización» y «En evaluación»): añadirlas (solo se
// guardan), «Analizar y comparar» (la IA las lee todas a la vez y pasa a evaluación),
// revisarlas, reanalizarlas con la IA, borrarlas y comparativa con el mejor y el peor valor
// (sin el resumen de ventajas e inconvenientes, que se quitó ese día).
import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { listar } from '../api/listas.js'
import { analizarYComparar, borrarOferta, listarOfertas, obtenerComparativa, reanalizarOferta } from '../api/ofertas.js'
import { llevarA } from '../desplazamiento.js'
import { diasMedios, fechaCorta, importeEn, porcentajeConRetraso } from '../formatos.js'
import { textoCondicion } from '../condiciones.js'
import { useFocoDeVuelta } from '../foco.js'
import { usePeticionarios } from '../usePeticionarios.js'
import EditorOferta from './EditorOferta.jsx'
import PedirDatos from './PedirDatos.jsx'
import Adjudicar from './Adjudicar.jsx'
import EntregaOferta from './EntregaOferta.jsx'
import SubirOferta from './SubirOferta.jsx'
import { claseBoton, claseBotonSecundario } from './Campo.jsx'

// CU-010: histórico de retrasos del proveedor en la comparativa. Lo que cuenta es el retraso medio
// por pedido, junto con la proporción de pedidos con retraso.
function historial(datos) {
  if (!datos?.pedidos) return 'Sin pedidos anteriores'
  if (!datos.con_retraso) return `Sin retrasos (${datos.pedidos} ${datos.pedidos === 1 ? 'pedido' : 'pedidos'})`
  return `Retraso medio: ${diasMedios(datos.retraso_medio, true)} por pedido. ${datos.con_retraso} de ${datos.pedidos} pedidos con retraso (${porcentajeConRetraso(datos)} %)`
}

function retrasos(o) {
  if (!o.historial_proveedor?.pedidos) return historial(o.historial_proveedor)
  // En otra pestaña: así no se pierde la adjudicación que se esté preparando.
  return (
    <a className="hover:underline" href={`/proveedores/${o.proveedor.id}/retrasos`} target="_blank" rel="noopener noreferrer">
      {historial(o.historial_proveedor)}
      <span className="sr-only"> (se abre en otra pestaña)</span>
    </a>
  )
}

// Comentarios de la entrega de pedidos anteriores del proveedor (los dos más recientes; el resto,
// en su histórico). No se destacan: son para leerlos.
const COMENTARIOS_A_LA_VISTA = 2

function comentarios(o) {
  const lista = o.historial_proveedor?.comentarios ?? []
  if (!lista.length) return '—'
  return (
    <ul className="grid gap-1">
      {lista.slice(0, COMENTARIOS_A_LA_VISTA).map((c) => (
        <li key={c.necesidad_id} className="whitespace-pre-line">
          <span className="text-slate-500 tabular-nums">{fechaCorta(c.fecha)}:</span> {c.texto}
        </li>
      ))}
      {lista.length > COMENTARIOS_A_LA_VISTA && (
        <li>
          <a className="hover:underline" href={`/proveedores/${o.proveedor.id}/retrasos`} target="_blank" rel="noopener noreferrer">
            Ver los {lista.length} comentarios
            <span className="sr-only"> (se abre en otra pestaña)</span>
          </a>
        </li>
      )}
    </ul>
  )
}

// Filas de la comparativa: los proveedores van en columnas y los datos en filas. Los
// importes no van a la derecha: en cada columna hay datos de todo tipo.
// Moneda de cada oferta, sin conversiones (ADR 0010). «Retrasos» va justo después de «Entrega».
// Cada fila: [nombre, valor, clase, dato de `destacados`].
const FILAS_COMPARATIVA = [
  ['Importe sin IVA', (o) => importeEn(o.importe_sin_iva, o.moneda), () => 'tabular-nums', 'importe'],
  ['Entrega', (o) => <EntregaOferta oferta={o} />, () => 'tabular-nums', 'entrega'],
  ['Retrasos del proveedor', retrasos, (o) => (o.historial_proveedor?.con_retraso ? 'text-amber-900' : 'text-slate-600'), 'retrasos'],
  ['Comentarios de entregas anteriores', comentarios, () => 'text-slate-700'],
  ['Condiciones de pago', (o) => o.condiciones_pago ?? '—'],
]
// Después de las condiciones de la tabla: lo que no encaja en ninguna.
const FILA_INFORMACION = ['Información adicional', (o) => o.otros ?? '—']

// Mejor (verde) y peor (rojo) valor, calculados por el backend solo con todas las ofertas revisadas.
// El color va siempre con su texto: no basta con el color (WCAG 1.4.1).
const DESTACADO = {
  mejor: { clase: 'bg-green-50 text-green-900', texto: 'Mejor' },
  peor: { clase: 'bg-red-50 text-red-900', texto: 'Peor' },
}

// Todas las celdas de datos llevan el mismo margen a la izquierda que las marcadas, para que el texto
// de una columna quede alineado.
const claseCeldaDeDatos = 'py-2 pr-4 pl-2'

// Una fila por condición, en el orden y con el nombre que da la API; no se destacan:
// ningún valor es siempre mejor. La primera lleva el título del apartado.
function filasDeCondiciones(comparativa) {
  const lista = comparativa[0]?.condiciones ?? []
  return lista.map(({ clave, nombre }, i) => [
    nombre,
    (o) => textoCondicion(o.condiciones?.find((c) => c.clave === clave)),
    undefined,
    undefined,
    i === 0 ? 'Otras condiciones' : null,
  ])
}

const hayDestacados = (comparativa) => comparativa.some((o) => Object.values(o.destacados ?? {}).some(Boolean))

function Celda({ oferta, valor, clase, campo }) {
  const marca = DESTACADO[campo && oferta.destacados?.[campo]]
  return (
    <td className={`${claseCeldaDeDatos} ${marca ? `${marca.clase} tabular-nums` : clase(oferta)}`}>
      {valor(oferta)}
      {marca && <span className="mt-0.5 block text-xs font-medium">{marca.texto}</span>}
    </td>
  )
}

// Nombre de cada fila: fijo a la izquierda al desplazar la tabla en horizontal (móvil).
const claseCabeceraDeFila = 'sticky left-0 z-10 bg-white py-2 pr-4'

// Los avisos de datos (falta el importe…) se ven en la propia oferta; arriba, los de la subida.
const avisosDeLaSubida = (oferta) => oferta.avisos.filter((a) => !a.startsWith('Falta:'))

function EtiquetaRevision({ revisada, className = '' }) {
  return (
    <span className={`rounded px-2 py-0.5 text-xs ${revisada ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-900'} ${className}`}>
      {revisada ? 'Revisada' : 'Sin revisar'}
    </span>
  )
}

export default function SeccionOfertas({ necesidad, onActualizada }) {
  // null mientras carga, para no decir «Todavía no hay ofertas» antes de saberlo.
  const [ofertas, setOfertas] = useState(null)
  const [comparativa, setComparativa] = useState([])
  const [proveedores, setProveedores] = useState([])
  const { peticionarios, peticionarioId, setPeticionarioId, errorPeticionarios } = usePeticionarios(
    necesidad.peticionario.id,
  )
  // Evita el doble envío en «Sí» de borrar.
  const [ocupado, setOcupado] = useState(false)
  // «Analizar y comparar»: la IA lee todas las ofertas a la vez (puede tardar unos minutos).
  const [analizando, setAnalizando] = useState(false)
  // Al terminar se anuncia y, en «En evaluación», el foco va a la comparativa: el botón que lo
  // tenía desaparece.
  const [terminado, setTerminado] = useState('')
  const tituloComparativa = useRef(null)
  const botonNo = useRef(null)
  const [subiendo, setSubiendo] = useState(false)
  const [editando, setEditando] = useState(null)
  // Oferta a cuyo proveedor se le están pidiendo los datos que faltan.
  const [pidiendo, setPidiendo] = useState(null)
  // Cambios sin guardar en el editor abierto: antes de cerrarlo o de abrir otro, se pregunta.
  // `cierre`: a qué oferta se iba a pasar (null = cerrar) mientras se pregunta.
  const [sinGuardar, setSinGuardar] = useState(false)
  const [cierre, setCierre] = useState(undefined)
  const botonSeguir = useRef(null)
  useEffect(() => {
    if (cierre !== undefined) botonSeguir.current?.focus()
  }, [cierre])
  useEffect(() => {
    // Al recargar o cerrar la pestaña con cambios sin guardar, el navegador pregunta.
    if (!sinGuardar) return
    const avisar = (e) => e.preventDefault()
    window.addEventListener('beforeunload', avisar)
    return () => window.removeEventListener('beforeunload', avisar)
  }, [sinGuardar])

  function abrirEditor(siguiente) {
    setCierre(undefined)
    setSinGuardar(false)
    setEditando(siguiente)
  }

  // Cerrar el editor o pasar a otra oferta; si hay cambios sin guardar, primero se pregunta.
  function cambiarEditor(siguiente) {
    if (editando !== null && sinGuardar && siguiente !== editando) return setCierre(siguiente)
    abrirEditor(siguiente)
  }
  const [borrando, setBorrando] = useState(null)
  // «Reanalizar con IA»: pide confirmación (sustituye los datos) y muestra que está leyendo.
  const [reanalizando, setReanalizando] = useState(null)
  // Al responder «No», el foco vuelve al «Reanalizar con IA» de esa oferta.
  const [volverA, setVolverA] = useState(null)
  // Foco: al abrir «Añadir oferta», al formulario; al cerrarlo, de vuelta al botón.
  const botonAnadir = useFocoDeVuelta(subiendo)
  const enfocar = useCallback((nodo) => nodo?.focus(), [])
  const [leyendo, setLeyendo] = useState(null)
  // Cambia tras leer con la IA, para que el editor abierto se rellene con los datos nuevos.
  const [lecturas, setLecturas] = useState(0)
  // CU-005: oferta elegida en la comparativa para adjudicarla.
  const [elegida, setElegida] = useState(null)
  // Avisos de la última subida o lectura con IA (sustituye a otra oferta, la IA avisa…).
  const [avisosSubida, setAvisosSubida] = useState([])
  const [error, setError] = useState(null)
  const [recargas, setRecargas] = useState(0)
  const recargar = () => setRecargas((n) => n + 1)

  useEffect(() => {
    let vigente = true
    Promise.all([listarOfertas(necesidad.id), obtenerComparativa(necesidad.id)])
      .then(([lista, comparadas]) => {
        if (!vigente) return
        setOfertas(lista)
        setComparativa(comparadas)
        setError(null)
        // La oferta elegida para adjudicar se actualiza, o se suelta si ya no está en la comparativa
        // o ha dejado de estar revisada.
        setElegida((actual) =>
          actual && lista.every((o) => o.revisada) ? (comparadas.find((o) => o.id === actual.id) ?? null) : null,
        )
      })
      .catch((e) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [necesidad.id, recargas])

  useEffect(() => {
    let vigente = true
    listar('/api/proveedores')
      .then((lista) => vigente && setProveedores(lista))
      .catch((e) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [])

  function leida(oferta) {
    setAvisosSubida(avisosDeLaSubida(oferta))
    abrirEditor(oferta.id)
    // Los datos nuevos entran ya en la lista para que el editor se abra con ellos, sin esperar a recargar.
    setOfertas((lista) => lista?.map((o) => (o.id === oferta.id ? oferta : o)) ?? lista)
    setLecturas((n) => n + 1)
    recargar()
  }

  function subida(oferta) {
    // Solo se guarda: la IA la lee después, con las demás, al «Analizar y comparar».
    setSubiendo(false)
    setAvisosSubida(avisosDeLaSubida(oferta))
    recargar()
  }

  async function reanalizar(id) {
    if (leyendo) return
    setError(null)
    setReanalizando(null)
    setLeyendo(id)
    try {
      leida(await reanalizarOferta(necesidad.id, id))
    } catch (e) {
      setError(e.message)
    } finally {
      setLeyendo(null)
    }
  }

  // Al guardar se cierra el editor y la pantalla vuelve a la fila de esa oferta, con el foco en su
  // «Revisar»: si no, lo que había debajo (la comparativa) subía a la vista.
  const filas = useRef(new Map())
  const volverAFila = useRef(null)
  useEffect(() => {
    if (editando !== null || volverAFila.current === null) return
    const fila = filas.current.get(volverAFila.current)
    volverAFila.current = null
    llevarA(fila, { bloque: 'nearest' })
    fila?.querySelector('button[aria-label^="Revisar la oferta"]')?.focus({ preventScroll: true })
  }, [editando])

  function guardada(oferta) {
    volverAFila.current = oferta.id
    abrirEditor(null)
    setAvisosSubida([])
    recargar()
  }

  useEffect(() => {
    // Al pedir confirmación para borrar, el foco va a «No» (el botón «Borrar» desaparece).
    if (borrando) botonNo.current?.focus()
  }, [borrando])

  async function borrar(id) {
    if (ocupado) return
    setError(null)
    setOcupado(true)
    try {
      await borrarOferta(necesidad.id, id)
      setBorrando(null)
      // Los avisos de la última subida ya no tienen sentido si se borra una oferta.
      setAvisosSubida([])
      if (editando === id) abrirEditor(null)
      recargar()
    } catch (e) {
      setError(e.message)
    } finally {
      setOcupado(false)
    }
  }

  async function analizar() {
    if (analizando) return
    setError(null)
    setAvisosSubida([])
    setTerminado('')
    setAnalizando(true)
    // En «En cotización», al cambiar de estado la página ya lleva el foco al paso.
    const enEvaluacion = necesidad.estado === 'en_evaluacion'
    try {
      const quien = enEvaluacion ? null : Number(peticionarioId)
      const resultado = await analizarYComparar(necesidad.id, quien)
      setAvisosSubida(resultado.avisos)
      setTerminado('Análisis terminado: la comparativa está al día.')
      if (enEvaluacion) tituloComparativa.current?.focus()
      recargar()
      await onActualizada(resultado.necesidad)
    } catch (e) {
      setError(e.message)
      // El servidor puede haber pasado ya la necesidad a «En evaluación» antes de fallar.
      recargar()
      await onActualizada()
    } finally {
      setAnalizando(false)
    }
  }

  const sinAnalizar = (ofertas ?? []).filter((o) => o.sin_analizar).length
  // Para elegir hay que revisar todas las ofertas, no solo la elegida.
  const porRevisar = (ofertas ?? []).filter((o) => !o.revisada).map((o) => o.proveedor.nombre)
  const monedas = [...new Set(comparativa.map((o) => o.moneda).filter(Boolean))].sort()

  return (
    <section className="rounded-lg border border-t-4 border-slate-200 border-t-marca-acento bg-white p-5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <h2 className="text-2xl font-normal">3. Ofertas</h2>
        {!subiendo && (
          <button ref={botonAnadir} type="button" className={claseBoton} onClick={() => setSubiendo(true)}>
            Añadir oferta
          </button>
        )}
      </div>

      {subiendo && (
        <div ref={enfocar} tabIndex={-1} role="group" aria-label="Añadir oferta" className="mb-4 focus:outline-none">
          <SubirOferta necesidad={necesidad} proveedores={proveedores} onSubida={subida} onCancelar={() => setSubiendo(false)} />
        </div>
      )}

      {avisosSubida.length > 0 && (
        <div role="status" className="mb-4 rounded bg-amber-50 px-4 py-2 text-sm text-amber-900">
          <ul>
            {avisosSubida.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
      {terminado && (
        <p role="status" className="sr-only">
          {terminado}
        </p>
      )}

      {ofertas === null && <p className="text-sm text-slate-600">Cargando…</p>}
      {ofertas?.length === 0 && !subiendo && <p className="text-sm text-slate-600">Todavía no hay ofertas.</p>}
      <ul className="grid gap-3">
        {(ofertas ?? []).map((o) => (
          <li
            key={o.id}
            ref={(nodo) => {
              filas.current.set(o.id, nodo)
              return () => filas.current.delete(o.id)
            }}
            className="rounded border border-slate-200 p-4"
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="font-medium">
                  {o.proveedor.nombre}
                  {o.numero_oferta && <span className="ml-2 font-normal text-slate-600">Oferta {o.numero_oferta}</span>}
                </p>
                <dl className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:flex">
                  {[
                    ['Importe sin IVA', importeEn(o.importe_sin_iva, o.moneda)],
                    ['Entrega', <EntregaOferta oferta={o} />],
                  ].map(([etiqueta, valor]) => (
                    <div key={etiqueta}>
                      <dt className="text-xs text-slate-500">{etiqueta}</dt>
                      <dd className="tabular-nums">{valor}</dd>
                    </div>
                  ))}
                </dl>
                <p className="mt-2 text-xs break-words text-slate-500">
                  Correo del {fechaCorta(o.fecha_correo)}. Archivos: {o.archivos.map((a) => a.nombre_archivo).join(', ')}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm whitespace-nowrap">
                {o.sin_analizar ? (
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-700">Sin analizar</span>
                ) : (
                  <EtiquetaRevision revisada={o.revisada} />
                )}
                {/* Botón grande: hay que revisar todas para elegir; relleno mientras falta. */}
                <button
                  type="button"
                  className={o.revisada ? claseBotonSecundario : claseBoton}
                  aria-label={`Revisar la oferta de ${o.proveedor.nombre}`}
                  onClick={() => cambiarEditor(editando === o.id ? null : o.id)}
                >
                  Revisar
                </button>
                {o.sin_analizar ? null : leyendo === o.id ? (
                  <span className="text-slate-600">Leyendo con la IA…</span>
                ) : reanalizando === o.id ? (
                  <span>
                    ¿Sustituir los datos por los que lea la IA?{' '}
                    <button
                      type="button"
                      autoFocus
                      className="text-marca-acento hover:underline"
                      aria-label={`Sí, reanalizar la oferta de ${o.proveedor.nombre}`}
                      onClick={() => reanalizar(o.id)}
                    >
                      Sí
                    </button>{' '}
                    <button
                      type="button"
                      className="text-slate-700 hover:underline"
                      onClick={() => {
                        setVolverA(o.id)
                        setReanalizando(null)
                      }}
                    >
                      No
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="text-marca-acento hover:underline disabled:opacity-50"
                    aria-label={`Reanalizar con IA la oferta de ${o.proveedor.nombre}`}
                    autoFocus={volverA === o.id}
                    disabled={leyendo !== null || analizando}
                    onClick={() => setReanalizando(o.id)}
                  >
                    Reanalizar con IA
                  </button>
                )}
                {o.datos_que_faltan?.length > 0 && (
                  <button
                    type="button"
                    className="text-marca-acento hover:underline"
                    aria-label={`Pedir los datos que faltan a ${o.proveedor.nombre}`}
                    aria-expanded={pidiendo === o.id}
                    onClick={() => setPidiendo(pidiendo === o.id ? null : o.id)}
                  >
                    Pedir datos que faltan
                  </button>
                )}
                {borrando === o.id ? (
                  <span>
                    ¿Borrar?{' '}
                    <button
                      type="button"
                      className="text-marca-acento hover:underline disabled:opacity-50"
                      aria-label={`Sí, borrar la oferta de ${o.proveedor.nombre}`}
                      disabled={ocupado}
                      onClick={() => borrar(o.id)}
                    >
                      Sí
                    </button>{' '}
                    <button ref={botonNo} type="button" className="text-slate-700 hover:underline" onClick={() => setBorrando(null)}>
                      No
                    </button>
                  </span>
                ) : (
                  <button
                    type="button"
                    className="text-slate-700 hover:underline disabled:opacity-50"
                    aria-label={`Borrar la oferta de ${o.proveedor.nombre}`}
                    // Mientras la IA la lee no se puede borrar (daría un error confuso al terminar).
                    disabled={leyendo === o.id || analizando}
                    onClick={() => setBorrando(o.id)}
                  >
                    Borrar
                  </button>
                )}
              </div>
            </div>
            {/* Mientras se revisa, los avisos los da el editor al momento. Sin analizar, que falten
                los datos es lo normal: no se avisa. */}
            {o.avisos.length > 0 && editando !== o.id && !o.sin_analizar && (
              <ul className="mt-2 text-sm text-amber-900">
                {o.avisos.map((a) => (
                  <li key={a}>⚠ {a}</li>
                ))}
              </ul>
            )}
            {pidiendo === o.id && (
              <div className="mt-3">
                <PedirDatos necesidadId={necesidad.id} oferta={o} onCerrar={() => setPidiendo(null)} />
              </div>
            )}
            {editando === o.id && (
              <div className="mt-3">
                {cierre !== undefined && (
                  <div role="group" aria-labelledby="pregunta-cierre" className="mb-3 grid gap-2 rounded border border-amber-300 bg-amber-50 p-3 text-sm">
                    <p id="pregunta-cierre" className="font-medium text-amber-900">
                      Hay cambios sin guardar en esta oferta. ¿Cerrarla sin guardarlos?
                    </p>
                    <div className="flex flex-wrap items-center gap-4">
                      <button type="button" className="text-marca-acento hover:underline" onClick={() => abrirEditor(cierre)}>
                        Sí, cerrar sin guardar
                      </button>
                      <button ref={botonSeguir} type="button" className="text-slate-700 hover:underline" onClick={() => setCierre(undefined)}>
                        No, seguir revisando
                      </button>
                    </div>
                  </div>
                )}
                <EditorOferta
                  key={lecturas}
                  necesidadId={necesidad.id}
                  oferta={o}
                  onGuardada={guardada}
                  onCerrar={() => cambiarEditor(null)}
                  onCambios={setSinGuardar}
                />
              </div>
            )}
          </li>
        ))}
      </ul>

      {ofertas?.length > 0 && (necesidad.estado === 'en_cotizacion' || sinAnalizar > 0) && (
        <div className="mt-6 grid gap-3 border-t border-slate-200 pt-4">
          <p className="text-sm text-slate-600">
            {necesidad.estado === 'en_cotizacion'
              ? 'Cuando estén todas las ofertas, la IA las lee a la vez, la necesidad pasa a «En evaluación» y sale la comparativa.'
              : sinAnalizar === 1
                ? 'Hay 1 oferta sin analizar: la IA la lee y se vuelve a comparar.'
                : `Hay ${sinAnalizar} ofertas sin analizar: la IA las lee y se vuelve a comparar.`}{' '}
            Puede tardar unos minutos.
          </p>
          <div className="flex flex-wrap items-end gap-4">
            {necesidad.estado === 'en_cotizacion' && (
              <label className="text-sm">
                <span className="mb-1 block font-medium">Quién pasa a evaluación</span>
                <select
                  className="rounded border border-slate-300 px-3 py-2 text-sm focus:border-marca-acento focus:outline-none disabled:opacity-50"
                  value={peticionarioId}
                  disabled={analizando}
                  onChange={(e) => setPeticionarioId(e.target.value)}
                >
                  {peticionarios.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre_completo}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button type="button" className={claseBoton} disabled={analizando || leyendo !== null} onClick={analizar}>
              {analizando
                ? 'Analizando con la IA…'
                : necesidad.estado === 'en_cotizacion'
                  ? 'Analizar y comparar'
                  : 'Analizar las nuevas y volver a comparar'}
            </button>
          </div>
        </div>
      )}

      {necesidad.estado === 'en_evaluacion' && (
        <div className="mt-6 border-t border-slate-200 pt-4">
          <h3 ref={tituloComparativa} tabIndex={-1} className="mb-2 text-lg font-medium focus:outline-none">
            Comparativa de las ofertas
          </h3>
          {comparativa.length === 0 ? (
            <p className="text-sm text-slate-600">Ninguna oferta tiene datos todavía: analízalas con la IA o escribe sus datos en «Revisar».</p>
          ) : (
            <>
              {porRevisar.length > 0 && (
                <p className="mb-2 rounded bg-amber-50 px-4 py-2 text-sm text-amber-900">
                  Los datos «Sin revisar» son los que ha leído la IA. Para elegir una oferta, revisa antes todas («Revisar», arriba). Falta:{' '}
                  {porRevisar.join(', ')}.
                </p>
              )}
              {monedas.length > 1 && (
                <p className="mb-2 rounded bg-amber-50 px-4 py-2 text-sm text-amber-900">
                  Las ofertas están en monedas distintas ({monedas.join(', ')}): ReMate no convierte importes. Pásalos a la misma moneda antes de compararlos.
                </p>
              )}
              {/* Proveedores en columnas y datos en filas; en pantallas estrechas se desplaza en horizontal,
                  con el nombre de cada fila siempre a la vista, y también con el teclado (tabIndex). */}
              {/* Una zona que se desplaza tiene que poder recibir el foco (regla de axe-core
                  «scrollable-region-focusable»), aunque no sea un control. */}
              {/* eslint-disable-next-line jsx-a11y-x/no-noninteractive-tabindex */}
              <div role="region" aria-label="Tabla de la comparativa" tabIndex={0} className="-mx-1 overflow-x-auto px-1 print:overflow-visible">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left align-bottom">
                      <th scope="col" className={claseCabeceraDeFila}>
                        <span className="sr-only">Dato</span>
                      </th>
                      {comparativa.map((o) => (
                        <th key={o.id} scope="col" className={`min-w-40 ${claseCeldaDeDatos} font-medium print:min-w-0`}>
                          {o.proveedor.nombre}
                          <EtiquetaRevision revisada={o.revisada} className="mt-1 block w-fit font-normal" />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {[...FILAS_COMPARATIVA, ...filasDeCondiciones(comparativa), FILA_INFORMACION].map(([etiqueta, valor, clase = () => '', campo, grupo]) => (
                      <Fragment key={etiqueta}>
                        {grupo && (
                          <tr>
                            <th scope="colgroup" colSpan={comparativa.length + 1} className="pt-4 pb-1 text-left text-sm font-medium text-slate-700">
                              {grupo}
                            </th>
                          </tr>
                        )}
                        <tr className="border-b border-slate-100 align-top">
                          <th scope="row" className={`${claseCabeceraDeFila} text-left font-medium whitespace-nowrap`}>
                            {etiqueta}
                          </th>
                          {comparativa.map((o) => (
                            <Celda key={o.id} oferta={o} valor={valor} clase={clase} campo={campo} />
                          ))}
                        </tr>
                      </Fragment>
                    ))}
                    {porRevisar.length === 0 && (
                      <tr>
                        <th scope="row" className={claseCabeceraDeFila}>
                          <span className="sr-only">Elegir</span>
                        </th>
                        {comparativa.map((o) => (
                          <td key={o.id} className={claseCeldaDeDatos}>
                            {/* Botón grande, como «Revisar»; la elegida dice «Elegida». */}
                            <button
                              type="button"
                              className={`${claseBoton} print:hidden`}
                              aria-label={`${elegida?.id === o.id ? 'Elegida' : 'Elegir'} la oferta de ${o.proveedor.nombre}`}
                              aria-pressed={elegida?.id === o.id}
                              disabled={elegida?.id === o.id}
                              onClick={() => setElegida(o)}
                            >
                              {elegida?.id === o.id ? 'Elegida' : 'Elegir'}
                            </button>
                          </td>
                        ))}
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              {/* La leyenda de colores solo si hay algo marcado. */}
              <p className="mt-2 text-xs text-slate-600">
                {porRevisar.length > 0
                  ? 'El mejor y el peor precio, plazo de entrega y retrasos se marcan cuando estén revisadas todas las ofertas.'
                  : hayDestacados(comparativa)
                    ? 'En verde, el mejor valor; en rojo, el peor (el precio, solo si todas las ofertas están en la misma moneda). La aplicación no elige proveedor.'
                    : 'La aplicación no elige proveedor.'}
              </p>
            </>
          )}
          {elegida && (
            <Adjudicar
              key={elegida.id}
              necesidad={necesidad}
              oferta={elegida}
              onCancelar={() => setElegida(null)}
              onAdjudicada={onActualizada}
            />
          )}
        </div>
      )}

      {(error || errorPeticionarios) && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {error || errorPeticionarios}
        </p>
      )}
    </section>
  )
}
