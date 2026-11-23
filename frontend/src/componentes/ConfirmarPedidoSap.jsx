// CU-006 — Confirmar que el pedido está en SAP y la fecha de entrega prevista. Se propone la de la
// oferta o, si el proveedor dio un plazo («3 semanas»), ese plazo contado desde hoy.
// Cambiarla aquí no cuenta como retraso.
import { useId, useState } from 'react'
import { confirmarPedidoEnSap } from '../api/necesidades.js'
import { usePeticionarios } from '../usePeticionarios.js'
import Campo, { claseEntrada, claseBoton } from './Campo.jsx'

export default function ConfirmarPedidoSap({ necesidad, onConfirmado }) {
  const [fecha, setFecha] = useState(necesidad.fecha_entrega_propuesta ?? necesidad.fecha_entrega_inicial ?? '')
  const { peticionarios, peticionarioId, setPeticionarioId, errorPeticionarios } = usePeticionarios(
    necesidad.peticionario.id,
  )
  const [errores, setErrores] = useState({})
  const [enviando, setEnviando] = useState(false)
  const idPlazo = useId()
  const plazo = necesidad.plazo_entrega_relativo

  async function confirmar() {
    if (enviando) return
    if (!fecha) {
      setErrores({ fecha: 'Indica la fecha de entrega prevista.' })
      return
    }
    setEnviando(true)
    try {
      onConfirmado(await confirmarPedidoEnSap(necesidad.id, { peticionario_id: Number(peticionarioId), fecha_entrega_prevista: fecha }))
    } catch (e) {
      setErrores(e.detalles?.campo === 'fecha_entrega_prevista' ? { fecha: e.message } : { general: e.message })
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section className="grid gap-4 rounded-lg border border-t-4 border-slate-200 border-t-marca-acento bg-white p-5 sm:p-6">
      <h2 className="text-2xl font-normal">5. Meter el pedido en SAP</h2>
      <p className="text-sm text-slate-700">
        Mete en SAP el texto y la tabla de «4. Adjudicación e información para SAP» y confirma aquí la fecha de entrega
        prevista. Si al meter el pedido ha cambiado la fecha, cámbiala: no cuenta como retraso.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Campo etiqueta="Fecha de entrega prevista" error={errores.fecha}>
          {(props) => (
            <input
              {...props}
              aria-describedby={[props['aria-describedby'], plazo && idPlazo].filter(Boolean).join(' ') || undefined}
              type="date"
              className={claseEntrada}
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
            />
          )}
        </Campo>
        <Campo etiqueta="Quién lo confirma">
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
        {plazo && (
          <p id={idPlazo} className="text-sm text-slate-600 sm:col-span-2">
            El proveedor dio un plazo, no una fecha («{plazo}»): la fecha propuesta cuenta ese plazo desde hoy.
          </p>
        )}
      </div>
      {(errores.general || errorPeticionarios) && (
        <p role="alert" className="text-sm text-red-700">
          {errores.general || errorPeticionarios}
        </p>
      )}
      <div>
        <button
          type="button"
          className={claseBoton}
          disabled={enviando}
          onClick={confirmar}
        >
          Confirmar que el pedido está en SAP
        </button>
      </div>
    </section>
  )
}
