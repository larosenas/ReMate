// CU-008 — Paso 7: registrar retrasos (con motivo y una fecha posterior a la prevista) y
// confirmar la entrega. Si llega más tarde de lo previsto, se pide el motivo del retraso.
import { useEffect, useRef, useState } from 'react'
import { confirmarEntrega, registrarRetraso } from '../api/necesidades.js'
import { fechaCorta, fechaHora, hoyIso } from '../formatos.js'
import { usePeticionarios } from '../usePeticionarios.js'
import Campo, { claseEntrada, claseBoton, claseBotonSecundario } from './Campo.jsx'

// El pedido llegó el día previsto o antes: el retraso avisado no cuenta (CU-010).
export function SinEfecto() {
  return <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs whitespace-nowrap text-slate-700">No se cumplió: llegó a tiempo</span>
}

// Lista de retrasos; también se usa en el paso ya cerrado.
export function ListaRetrasos({ retrasos }) {
  if (retrasos.length === 0) return <p className="text-sm text-slate-600">Sin retrasos.</p>
  return (
    <ul className="grid gap-2 text-sm">
      {retrasos.map((r) => (
        <li key={r.registrado_en} className="rounded border border-slate-200 p-3">
          <p>
            <span className="font-medium">
              {fechaCorta(r.fecha_anterior)} → {fechaCorta(r.fecha_nueva)}
            </span>{' '}
            · {r.motivo}
            {r.sin_efecto && <SinEfecto />}
          </p>
          <p className="text-xs text-slate-600">
            {r.peticionario.nombre_completo} · {fechaHora(r.registrado_en)}
          </p>
        </li>
      ))}
    </ul>
  )
}

export default function SeccionEntrega({ necesidad, onActualizada }) {
  // null, 'retraso' o 'entrega': el formulario abierto.
  const [accion, setAccion] = useState(null)
  const [fechaNueva, setFechaNueva] = useState('')
  const [motivo, setMotivo] = useState('')
  const [fechaReal, setFechaReal] = useState(hoyIso())
  // Opcional; sale en la comparativa de las ofertas futuras del proveedor y lo tiene en cuenta la IA.
  const [comentario, setComentario] = useState('')
  const { peticionarios, peticionarioId, setPeticionarioId, errorPeticionarios } = usePeticionarios(
    necesidad.peticionario.id,
  )
  const [errores, setErrores] = useState({})
  const [ocupado, setOcupado] = useState(false)
  // Confirmar la entrega cierra la necesidad: se pregunta antes, para evitar un clic por error.
  // Al preguntar, el foco va a «No».
  const [preguntando, setPreguntando] = useState(false)
  const botonNo = useRef(null)
  // Al responder «No» (o si falla la API tras «Sí»), el foco vuelve a «Confirmar que ha llegado».
  const botonConfirmar = useRef(null)
  const preguntaba = useRef(false)
  useEffect(() => {
    if (preguntando) botonNo.current?.focus()
    else if (preguntaba.current) botonConfirmar.current?.focus()
    preguntaba.current = preguntando
  }, [preguntando])
  const prevista = necesidad.fecha_entrega_prevista
  // Fechas «AAAA-MM-DD»: se comparan como texto.
  const llegaTarde = accion === 'entrega' && fechaReal > prevista

  // Al cerrar un formulario, el foco vuelve al botón que lo abrió (si no, se iría a <body>).
  const botonEntrega = useRef(null)
  const botonRetraso = useRef(null)
  const ultimo = useRef(null)
  useEffect(() => {
    // Solo tras cerrar un formulario (no al cargar la página).
    if (accion !== null || !ultimo.current) return
    ;(ultimo.current === 'retraso' ? botonRetraso : botonEntrega).current?.focus({ preventScroll: true })
  }, [accion])

  function abrir(nueva) {
    if (nueva) ultimo.current = nueva
    setAccion(nueva)
    setPreguntando(false)
    setMotivo('')
    setComentario('')
    // Cada retraso empieza con la fecha vacía: la anterior ya es la prevista y no valdría.
    setFechaNueva('')
    setErrores({})
  }

  async function enviar(llamada, datos, campos) {
    if (ocupado) return
    setErrores({})
    setOcupado(true)
    try {
      await onActualizada(await llamada(necesidad.id, { peticionario_id: Number(peticionarioId), ...datos }))
      abrir(null)
    } catch (e) {
      const campo = e.detalles?.campo
      setErrores(campos.includes(campo) ? { [campo]: e.message } : { general: e.message })
      setPreguntando(false)
    } finally {
      setOcupado(false)
    }
  }

  function guardarRetraso() {
    const nuevos = {}
    if (!fechaNueva) nuevos.fecha_nueva = 'Indica la nueva fecha de entrega.'
    else if (fechaNueva <= prevista) nuevos.fecha_nueva = `La nueva fecha tiene que ser posterior a la prevista (${fechaCorta(prevista)}).`
    if (!motivo.trim()) nuevos.motivo = 'Indica el motivo del retraso.'
    if (Object.keys(nuevos).length) return setErrores(nuevos)
    enviar(registrarRetraso, { fecha_nueva: fechaNueva, motivo }, ['fecha_nueva', 'motivo'])
  }

  function guardarEntrega() {
    const nuevos = {}
    if (!fechaReal) nuevos.fecha_entrega_real = 'Indica la fecha de entrega.'
    if (llegaTarde && !motivo.trim()) nuevos.motivo_retraso = 'Indica el motivo del retraso.'
    if (Object.keys(nuevos).length) return setErrores(nuevos)
    setErrores({})
    if (!preguntando) return setPreguntando(true)
    enviar(
      confirmarEntrega,
      { fecha_entrega_real: fechaReal, motivo_retraso: llegaTarde ? motivo : null, comentario: comentario.trim() || null },
      ['fecha_entrega_real', 'motivo_retraso', 'comentario'],
    )
  }

  const quien = (etiqueta) => (
    <Campo etiqueta={etiqueta}>
      {(props) => (
        <select {...props} className={claseEntrada} value={peticionarioId} onChange={(e) => setPeticionarioId(e.target.value)}>
          {peticionarios.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nombre_completo}
            </option>
          ))}
        </select>
      )}
    </Campo>
  )

  return (
    <section className="grid gap-4 rounded-lg border border-t-4 border-slate-200 border-t-marca-acento bg-white p-5 sm:p-6">
      <h2 className="text-2xl font-normal">7. Entrega</h2>
      <p className="text-sm text-slate-700">
        Si el proveedor avisa de que no llega a tiempo, registra el retraso con su motivo. Cuando llegue el pedido,
        confirma la entrega.
      </p>
      <div>
        <h3 className="mb-2 font-medium">Retrasos</h3>
        <ListaRetrasos retrasos={necesidad.retrasos} />
      </div>

      {accion === null && (
        <div className="flex flex-wrap gap-3">
          <button ref={botonEntrega} type="button" className={claseBoton} onClick={() => abrir('entrega')}>
            Confirmar la entrega
          </button>
          <button ref={botonRetraso} type="button" className={claseBotonSecundario} onClick={() => abrir('retraso')}>
            Registrar un retraso
          </button>
        </div>
      )}

      {accion === 'retraso' && (
        <div className="grid gap-4 rounded border border-slate-200 bg-slate-50 p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo etiqueta="Nueva fecha de entrega" error={errores.fecha_nueva}>
              {(props) => <input {...props} autoFocus type="date" className={claseEntrada} value={fechaNueva} onChange={(e) => setFechaNueva(e.target.value)} />}
            </Campo>
            {quien('Quién lo registra')}
          </div>
          <Campo etiqueta="Motivo del retraso" error={errores.motivo}>
            {(props) => <textarea {...props} rows={2} className={claseEntrada} value={motivo} onChange={(e) => setMotivo(e.target.value)} />}
          </Campo>
          <div className="flex flex-wrap items-center gap-4">
            <button type="button" className={claseBoton} disabled={ocupado} onClick={guardarRetraso}>
              Guardar el retraso
            </button>
            <button type="button" className="text-sm text-slate-700 hover:underline" onClick={() => abrir(null)}>
              Cancelar
            </button>
          </div>
        </div>
      )}

      {accion === 'entrega' && (
        <div className="grid gap-4 rounded border border-slate-200 bg-slate-50 p-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo etiqueta="Fecha en que llegó" error={errores.fecha_entrega_real}>
              {(props) => (
                <input {...props} autoFocus type="date" max={hoyIso()} className={claseEntrada} value={fechaReal} onChange={(e) => setFechaReal(e.target.value)} />
              )}
            </Campo>
            {quien('Quién lo confirma')}
          </div>
          {llegaTarde && (
            <Campo etiqueta={`Motivo del retraso (estaba prevista el ${fechaCorta(prevista)})`} error={errores.motivo_retraso}>
              {(props) => <textarea {...props} rows={2} className={claseEntrada} value={motivo} onChange={(e) => setMotivo(e.target.value)} />}
            </Campo>
          )}
          <Campo
            etiqueta="Comentarios (opcional)"
            ayuda="Por ejemplo, si el paquete llegó dañado o faltaba algo. Se verá al comparar ofertas de este proveedor más adelante."
            error={errores.comentario}
          >
            {(props) => (
              <textarea {...props} rows={2} maxLength={1000} className={claseEntrada} value={comentario} onChange={(e) => setComentario(e.target.value)} />
            )}
          </Campo>
          {preguntando ? (
            <div role="group" aria-labelledby="pregunta-entrega" className="grid gap-3 rounded border border-amber-300 bg-amber-50 p-3 text-sm">
              <p id="pregunta-entrega" className="font-medium text-amber-900">
                ¿Seguro que el pedido ha llegado? La necesidad pasará a «Entregado» y ya no se podrán registrar
                retrasos ni cancelarla.
              </p>
              <div className="flex flex-wrap items-center gap-4">
                <button type="button" className={claseBoton} disabled={ocupado} onClick={guardarEntrega}>
                  Sí, ha llegado
                </button>
                <button ref={botonNo} type="button" className={claseBotonSecundario} onClick={() => setPreguntando(false)}>
                  No
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-4">
              <button ref={botonConfirmar} type="button" className={claseBoton} disabled={ocupado} onClick={guardarEntrega}>
                Confirmar que ha llegado
              </button>
              <button type="button" className="text-sm text-slate-700 hover:underline" onClick={() => abrir(null)}>
                Cancelar
              </button>
            </div>
          )}
        </div>
      )}

      {(errores.general || errorPeticionarios) && (
        <p role="alert" className="text-sm text-red-700">
          {errores.general || errorPeticionarios}
        </p>
      )}
    </section>
  )
}
