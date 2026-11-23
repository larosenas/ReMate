// Cancelar una necesidad con un motivo (obligatorio), desde cualquier estado salvo «Entregado».
import { useState } from 'react'
import { cancelarNecesidad } from '../api/necesidades.js'
import { useFocoDeVuelta } from '../foco.js'
import { usePeticionarios } from '../usePeticionarios.js'
import Campo, { claseEntrada } from './Campo.jsx'

export default function CancelarNecesidad({ necesidad, onCancelada }) {
  const [abierto, setAbierto] = useState(false)
  const [motivo, setMotivo] = useState('')
  const { peticionarios, peticionarioId, setPeticionarioId, errorPeticionarios } = usePeticionarios(
    necesidad.peticionario.id,
  )
  const [errores, setErrores] = useState({})
  const [enviando, setEnviando] = useState(false)
  const botonAbrir = useFocoDeVuelta(abierto)

  async function confirmar() {
    if (enviando) return
    if (!motivo.trim()) {
      setErrores({ motivo: 'Indica el motivo de la cancelación.' })
      return
    }
    setEnviando(true)
    try {
      onCancelada(await cancelarNecesidad(necesidad.id, { peticionario_id: Number(peticionarioId), motivo }))
    } catch (e) {
      setErrores(e.detalles?.campo === 'motivo' ? { motivo: e.message } : { general: e.message })
    } finally {
      setEnviando(false)
    }
  }

  if (!abierto) {
    return (
      // Acción poco habitual y destructiva: discreta hasta que se abre (pide motivo y confirmación).
      <div>
        <button
          ref={botonAbrir}
          type="button"
          className="text-sm font-medium text-red-700 underline-offset-4 hover:underline"
          onClick={() => setAbierto(true)}
        >
          <span aria-hidden="true">⚠ </span>Cancelar la necesidad
        </button>
      </div>
    )
  }

  return (
    <section className="grid gap-3 rounded-lg border-2 border-red-700 bg-red-50 p-4">
      <h2 className="font-semibold text-red-800">
        <span aria-hidden="true">⚠ </span>Cancelar la necesidad
      </h2>
      <p className="text-sm font-medium text-red-800">
        Se cierra el caso y se conserva todo lo registrado. No se puede deshacer.
      </p>
      <Campo etiqueta="Motivo" error={errores.motivo}>
        {(props) => (
          // Al abrir, el foco va al motivo.
          <textarea {...props} autoFocus rows={3} className={claseEntrada} value={motivo} onChange={(e) => setMotivo(e.target.value)} />
        )}
      </Campo>
      <div className="max-w-sm">
        <Campo etiqueta="Quién la cancela">
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
      </div>
      {(errores.general || errorPeticionarios) && (
        <p role="alert" className="text-sm text-red-700">
          {errores.general || errorPeticionarios}
        </p>
      )}
      <div className="flex items-center gap-4">
        <button
          type="button"
          className="rounded bg-red-700 px-4 py-2 text-sm font-semibold text-white shadow hover:bg-red-800 disabled:opacity-50"
          disabled={enviando}
          onClick={confirmar}
        >
          Confirmar la cancelación
        </button>
        <button type="button" className="text-sm text-slate-700 hover:underline" onClick={() => setAbierto(false)}>
          No cancelar
        </button>
      </div>
    </section>
  )
}
