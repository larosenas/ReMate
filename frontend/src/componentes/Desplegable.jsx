// Tarjeta que se pliega y despliega (<details> del navegador). Se usa para los pasos ya hechos,
// que empiezan plegados para llegar sin bajar tanto al paso en curso.
import { useState } from 'react'

export default function Desplegable({ titulo, resumen, abiertoAlInicio = false, children }) {
  const [abierto, setAbierto] = useState(abiertoAlInicio)
  return (
    <details
      open={abierto}
      onToggle={(e) => setAbierto(e.currentTarget.open)}
      className="group rounded-lg border border-slate-200 bg-white"
    >
      <summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-4 sm:px-6 [&::-webkit-details-marker]:hidden">
        <span aria-hidden="true" className="text-sm text-marca-acento transition-transform group-open:rotate-90 motion-reduce:transition-none">
          ▶
        </span>
        <span className="text-lg font-medium sm:text-xl">{titulo}</span>
        {resumen && !abierto && <span className="hidden truncate text-sm text-slate-600 sm:inline">{resumen}</span>}
      </summary>
      <div className="px-4 pb-5 sm:px-6 sm:pb-6">{children}</div>
    </details>
  )
}
