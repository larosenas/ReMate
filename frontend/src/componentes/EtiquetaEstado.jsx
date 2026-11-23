// Estado de la necesidad: en curso (pizarra, color de la marca), entregada (verde) o
// cancelada (gris).
const CLASES = {
  entregado: 'bg-green-100 text-green-900',
  cancelada: 'bg-slate-200 text-slate-700',
}

export default function EtiquetaEstado({ estado, texto }) {
  return (
    <span className={`inline-block rounded px-2.5 py-0.5 text-sm font-medium ${CLASES[estado] ?? 'bg-marca-tarjeta text-white'}`}>
      {texto}
    </span>
  )
}
