// Etiqueta, campo y mensaje de error enlazados para los lectores de pantalla.
// `children` es una función que recibe las props de accesibilidad para el campo.
import { useId } from 'react'

// Botón principal (rojo) y secundario (borde gris) de los formularios.
export const claseBoton = 'rounded bg-marca-acento px-4 py-2 text-sm font-medium text-white shadow hover:bg-marca-acento-oscuro disabled:opacity-50'
export const claseBotonSecundario = 'rounded border border-slate-300 px-4 py-2 text-sm hover:border-marca-acento disabled:opacity-50'

export const claseEntrada =
  'w-full rounded border border-slate-300 px-3 py-2 text-sm focus:border-marca-acento focus:outline-none aria-[invalid=true]:border-red-700'

// `ayuda` (opcional): texto bajo la etiqueta, enlazado al campo con `aria-describedby`.
export default function Campo({ etiqueta, error, ayuda, children }) {
  const id = useId()
  const descritoPor = [ayuda && `${id}-ayuda`, error && `${id}-error`].filter(Boolean).join(' ') || undefined
  return (
    <div className="text-sm">
      <label htmlFor={id} className="mb-1 block font-medium">
        {etiqueta}
      </label>
      {ayuda && (
        <p id={`${id}-ayuda`} className="mb-1 text-slate-600">
          {ayuda}
        </p>
      )}
      {children({ id, 'aria-invalid': Boolean(error), 'aria-describedby': descritoPor })}
      {error && (
        <p id={`${id}-error`} role="alert" className="mt-1 text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}
