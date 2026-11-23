// Selector de archivos con un botón propio y una zona para arrastrar y soltar los archivos. El
// <input type="file"> del navegador queda oculto: así solo el botón abre el diálogo (el del
// navegador también se abría al pulsar la etiqueta o el texto de al lado). Lo que se suelta pasa
// por el mismo `onChange` que lo elegido con el botón. Lo elegido se ve debajo de la zona, con
// letra normal: dentro, pequeño y en gris, no se veía.
import { useEffect, useId, useRef, useState } from 'react'

// Nombres de los archivos elegidos, uno por línea. El contenedor está siempre: así el lector de
// pantalla anuncia los archivos al elegirlos o soltarlos.
export function ArchivosElegidos({ nombres }) {
  return (
    <div aria-live="polite">
      {nombres.length > 0 && (
        <ul className="mt-1 grid gap-1 text-sm" aria-label="Archivos elegidos">
          {nombres.map((nombre, i) => (
            <li key={`${nombre}-${i}`} className="break-all rounded bg-slate-50 px-3 py-1 text-slate-900">
              {nombre}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// Si un archivo se suelta fuera de la zona, el navegador lo abriría y se perdería lo escrito en
// el formulario: mientras haya un selector en pantalla, eso no se hace.
function noAbrirLoSoltado(evento) {
  if (evento.dataTransfer?.types?.includes('Files')) evento.preventDefault()
}

export default function SelectorArchivo({
  etiqueta,
  etiquetaVisible = true,
  multiple = false,
  accept,
  disabled = false,
  error,
  // false cuando la pantalla ya muestra aparte la lista de archivos elegidos.
  mostrarSeleccion = true,
  // Si devuelve false (archivo rechazado), no se muestra como elegido.
  onChange,
}) {
  const id = useId()
  const entrada = useRef(null)
  const [nombres, setNombres] = useState([])
  const [encima, setEncima] = useState(false)

  useEffect(() => {
    window.addEventListener('dragover', noAbrirLoSoltado)
    window.addEventListener('drop', noAbrirLoSoltado)
    return () => {
      window.removeEventListener('dragover', noAbrirLoSoltado)
      window.removeEventListener('drop', noAbrirLoSoltado)
    }
  }, [])

  function cambiar(evento) {
    const elegidos = Array.from(evento.target.files ?? []).map((f) => f.name)
    if (onChange(evento) !== false) setNombres(elegidos)
  }

  function arrastrando(evento) {
    evento.preventDefault()
    // Desactivado: el cursor no debe invitar a soltar.
    evento.dataTransfer.dropEffect = disabled ? 'none' : 'copy'
    if (!disabled) setEncima(true)
  }

  // Al pasar por encima del botón, el navegador «sale» de la zona: solo cuenta salir de verdad.
  function saliendo(evento) {
    if (!evento.currentTarget.contains(evento.relatedTarget)) setEncima(false)
  }

  function soltar(evento) {
    evento.preventDefault()
    setEncima(false)
    if (disabled) return
    const soltados = Array.from(evento.dataTransfer.files ?? [])
    if (!soltados.length) return
    // Con un solo archivo permitido, se toma el primero de los que se suelten.
    cambiar({ target: { files: multiple ? soltados : soltados.slice(0, 1), value: '' } })
  }

  return (
    <div className="text-sm">
      {etiquetaVisible && <p className="mb-1 font-medium">{etiqueta}</p>}
      <input
        ref={entrada}
        id={id}
        type="file"
        className="sr-only"
        tabIndex={-1}
        aria-label={etiqueta}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        multiple={multiple}
        accept={accept}
        disabled={disabled}
        onChange={cambiar}
      />
      {/* Soltar archivos es un atajo para el ratón; con el teclado se usa el botón «Elegir». */}
      {/* eslint-disable-next-line jsx-a11y-x/no-static-element-interactions */}
      <div
        data-zona-archivos
        className={`flex flex-wrap items-center gap-3 rounded border-2 border-dashed px-3 py-2 transition-colors motion-reduce:transition-none ${
          encima ? 'border-marca-acento bg-teal-50' : error ? 'border-red-300' : 'border-slate-300'
        }`}
        onDragEnter={arrastrando}
        onDragOver={arrastrando}
        onDragLeave={saliendo}
        onDrop={soltar}
      >
        <button
          type="button"
          className="rounded border border-marca-acento bg-white px-3 py-1.5 font-medium text-marca-acento hover:bg-marca-acento hover:text-white disabled:opacity-50"
          disabled={disabled}
          aria-label={`${etiqueta}: elegir ${multiple ? 'archivos' : 'archivo'}`}
          aria-describedby={error ? `${id}-error` : undefined}
          onClick={() => entrada.current?.click()}
        >
          {multiple ? 'Elegir archivos' : 'Elegir archivo'}
        </button>
        <span className={`text-xs ${encima ? 'text-slate-600' : 'text-slate-500'}`} aria-hidden="true">
          {encima ? 'Suelta aquí' : `o ${multiple ? 'arrástralos' : 'arrástralo'} aquí`}
        </span>
      </div>
      {mostrarSeleccion && <ArchivosElegidos nombres={nombres} />}
      {error && (
        <p id={`${id}-error`} role="alert" className="mt-1 text-red-700">
          {error}
        </p>
      )}
    </div>
  )
}
