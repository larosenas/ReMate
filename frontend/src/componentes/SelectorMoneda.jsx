import { MONEDAS } from '../formatos.js'

// Desplegable pequeño con el símbolo de la moneda, al lado de cada precio de la oferta. Todos los
// del editor comparten el mismo valor: la oferta tiene una sola moneda (ADR 0010). Sin conversiones.

export default function SelectorMoneda({ value, onChange, etiqueta, original, disabled = false }) {
  // Una moneda que no está en la lista (la ha leído la IA, como SEK) sale con su código. También
  // la que traía la oferta (`original`), para poder volver a ella tras cambiarla.
  const extra = [...new Set([original, value])].filter((c) => c && !MONEDAS.some(([codigo]) => codigo === c))
  const opciones = [...MONEDAS, ...extra.map((c) => [c, c])]
  return (
    <select
      aria-label={etiqueta}
      className="shrink-0 rounded border border-slate-300 bg-white px-2 py-2 text-sm focus:border-marca-acento focus:outline-none"
      disabled={disabled}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {opciones.map(([codigo, simbolo]) => (
        <option key={codigo} value={codigo}>
          {simbolo}
        </option>
      ))}
    </select>
  )
}
