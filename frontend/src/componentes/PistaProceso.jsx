// Los 7 pasos del proceso de compra y en cuál está la necesidad. Versión completa (detalle de la
// necesidad) y compacta (panel): rojo = hecho, negro = el que toca, gris = pendiente.
import { PASOS, pasosHechos } from '../estados.js'

function claseTramo(numero, hechos, cerrada) {
  if (numero <= hechos) return cerrada ? 'bg-slate-400' : 'bg-marca-acento'
  if (numero === hechos + 1 && !cerrada) return 'bg-marca-oscuro'
  return 'bg-slate-200'
}

// `estado`: estado actual; si está cancelada, `estadoPrevio` es el que tenía al cancelarla.
export default function PistaProceso({ estado, estadoPrevio = null, compacta = false }) {
  const cancelada = estado === 'cancelada'
  const hechos = pasosHechos(cancelada ? estadoPrevio : estado)
  const entregada = estado === 'entregado'
  const enCurso = cancelada || entregada ? null : PASOS[hechos]

  if (compacta) {
    return (
      <span className="flex gap-0.5" aria-hidden="true">
        {PASOS.map((p) => (
          <span key={p.numero} className={`h-1.5 w-3 rounded-full ${claseTramo(p.numero, hechos, cancelada)}`} />
        ))}
      </span>
    )
  }

  const resumen = cancelada
    ? `Cancelada después del paso ${hechos} de 7`
    : entregada
      ? 'Proceso terminado: pedido entregado'
      : `Paso ${enCurso.numero} de 7: ${enCurso.nombre}`
  return (
    <div>
      <ol className="grid grid-cols-7 gap-1" aria-hidden="true">
        {PASOS.map((p) => {
          const actual = p.numero === enCurso?.numero
          return (
            <li key={p.numero} className="min-w-0">
              <span className={`block h-2 rounded-full ${claseTramo(p.numero, hechos, cancelada)}`} />
              <span
                className={`mt-2 hidden truncate text-xs sm:block ${actual ? 'font-medium text-marca-texto' : 'text-slate-500'}`}
                title={p.nombre}
              >
                <span className="tabular-nums">{p.numero}</span> {p.nombre}
              </span>
            </li>
          )
        })}
      </ol>
      {/* En el móvil no caben los 7 nombres: se ve solo el paso que toca. En pantallas mayores lo
          leen los lectores de pantalla (la pista es visual). */}
      <p className="mt-2 text-xs text-slate-600 sm:sr-only">{resumen}</p>
    </div>
  )
}
