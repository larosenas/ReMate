// CU-003 — Eliminar (baja definitiva) un proveedor o peticionario ya desactivado, con un motivo
// de la lista o «Otro» escrito por el usuario. Deja de salir en las listas, pero sigue en las
// necesidades antiguas. Si es un peticionario con necesidades en curso, la API lo avisa y hay que
// elegir a quién pasárselas.
import { useId, useState } from 'react'
import { eliminar, listar } from '../api/listas.js'
import { claseEntrada } from './Campo.jsx'

const OTRO = 'otro'

export default function BajaDefinitiva({ ruta, registro, nombre, motivos, onEliminado, onCancelar }) {
  const id = useId()
  const [motivo, setMotivo] = useState('')
  const [otro, setOtro] = useState('')
  const [error, setError] = useState(null)
  // Campo del último error de la API (`detalles.campo`), si lo dijo.
  const [campoApi, setCampoApi] = useState(null)
  const [enviando, setEnviando] = useState(false)
  // Necesidades en curso del peticionario, los peticionarios activos y el elegido para llevarlas.
  const [enCurso, setEnCurso] = useState(null)
  const [candidatos, setCandidatos] = useState([])
  const [reasignarA, setReasignarA] = useState('')

  // El error se asocia al campo que hay que corregir (para los lectores de pantalla).
  // Si la API dice el campo, manda ella; si no, se deduce de lo que falta.
  const campoLocal = enCurso && !reasignarA ? 'reasignar' : motivo === OTRO ? 'otro' : 'motivo'
  const campoConError = error && (campoApi === 'reasignar_a' ? 'reasignar' : campoApi === 'motivo' ? (motivo === OTRO ? 'otro' : 'motivo') : campoLocal)

  async function cargarCandidatos() {
    const activos = await listar(ruta)
    setCandidatos(activos.filter((p) => p.id !== registro.id))
  }

  async function confirmar() {
    if (enviando) return
    if (!motivo) return setError('Elige el motivo.')
    if (motivo === OTRO && !otro.trim()) return setError('Escribe el motivo.')
    if (enCurso && !reasignarA) return setError('Elige a quién pasar sus necesidades.')
    setError(null)
    setCampoApi(null)
    setEnviando(true)
    try {
      await eliminar(ruta, registro.id, motivo === OTRO ? `Otro: ${otro.trim()}` : motivo, enCurso ? Number(reasignarA) : null)
      onEliminado(registro)
    } catch (e) {
      if (e.codigo === 'necesidades_en_curso') {
        try {
          await cargarCandidatos()
          setEnCurso(e.detalles?.necesidades ?? [])
        } catch (e2) {
          setError(e2.message)
        }
      } else {
        setError(e.message)
        setCampoApi(e.detalles?.campo ?? null)
        // La persona elegida ya no vale (por ejemplo, otra la acaba de desactivar): se recarga la lista.
        if (e.detalles?.campo === 'reasignar_a') {
          setReasignarA('')
          await cargarCandidatos().catch(() => {})
        }
      }
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div role="group" aria-labelledby={`${id}-titulo`} className="mt-3 grid gap-3 rounded-lg border border-red-200 bg-red-50/60 p-4 text-sm">
      <p id={`${id}-titulo`} className="font-medium text-red-800">
        Eliminar «{nombre}» definitivamente
      </p>
      <p className="text-slate-700">
        Dejará de salir en las listas, también en «Ver inactivos». Seguirá en las necesidades antiguas. No se puede deshacer
        desde la aplicación.
      </p>
      <div className="grid gap-1">
        <label htmlFor={`${id}-motivo`} className="font-medium">
          Motivo
        </label>
        {/* Al abrir, el foco va al motivo. */}
        <select
          id={`${id}-motivo`}
          autoFocus
          aria-invalid={campoConError === 'motivo'}
          aria-describedby={campoConError === 'motivo' ? `${id}-error` : undefined}
          className={`${claseEntrada} bg-white`}
          value={motivo}
          onChange={(e) => setMotivo(e.target.value)}
        >
          <option value="">Elige el motivo…</option>
          {motivos.map((m) => (
            <option key={m} value={m}>
              {m}
            </option>
          ))}
          <option value={OTRO}>Otro…</option>
        </select>
      </div>
      {motivo === OTRO && (
        <div className="grid gap-1">
          <label htmlFor={`${id}-otro`} className="font-medium">
            Escribe el motivo
          </label>
          <textarea
            id={`${id}-otro`}
            autoFocus
            aria-invalid={campoConError === 'otro'}
            aria-describedby={campoConError === 'otro' ? `${id}-error` : undefined}
            rows={2}
            maxLength={490}
            className={`${claseEntrada} bg-white`}
            value={otro}
            onChange={(e) => setOtro(e.target.value)}
          />
        </div>
      )}
      {enCurso && (
        <div className="grid gap-2 rounded border border-amber-300 bg-amber-50 p-3">
          <p role="alert" className="font-medium text-amber-900">
            «{nombre}» lleva {enCurso.length === 1 ? '1 necesidad en curso' : `${enCurso.length} necesidades en curso`}. Antes de
            eliminarlo, elige quién las lleva a partir de ahora.
          </p>
          <ul className="list-disc pl-5 text-slate-700">
            {enCurso.map((n) => (
              <li key={n.id}>
                <a href={`/necesidades/${n.id}`} target="_blank" rel="noreferrer" className="text-marca-acento hover:underline">
                  {n.codigo}
                </a>{' '}
                {n.titulo}
              </li>
            ))}
          </ul>
          {candidatos.length === 0 ? (
            <p className="text-slate-700">
              No hay otro peticionario activo a quien pasárselas. Añade uno o reactiva uno en esta misma lista y vuelve a
              intentarlo.
            </p>
          ) : (
            <>
              <label htmlFor={`${id}-reasignar`} className="font-medium">
                Pasar sus necesidades a
              </label>
              <select
                id={`${id}-reasignar`}
                autoFocus
                aria-invalid={campoConError === 'reasignar'}
                aria-describedby={campoConError === 'reasignar' ? `${id}-error` : undefined}
                className={`${claseEntrada} bg-white`}
                value={reasignarA}
                onChange={(e) => setReasignarA(e.target.value)}
              >
                <option value="">Elige un peticionario…</option>
                {candidatos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nombre_completo}
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
      )}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-red-700">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-4">
        <button
          type="button"
          className="rounded bg-red-700 px-4 py-2 font-medium text-white hover:bg-red-800 disabled:opacity-50"
          disabled={enviando}
          onClick={confirmar}
        >
          Eliminar definitivamente
        </button>
        <button type="button" className="text-slate-700 hover:underline disabled:opacity-50" disabled={enviando} onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </div>
  )
}
