// CU-004 — Condiciones de la oferta: estados y cómo se leen. La lista de condiciones y
// sus nombres vienen de la API (`oferta.condiciones`, en orden); los estados son los mismos que
// en `backend/app/servicios/condiciones.py`.
export const ESTADOS_CONDICION = [
  ['no_especificado', 'No especificado'],
  ['especificado', 'Especificado'],
  ['incluido', 'Incluido'],
  ['no_incluido', 'No incluido'],
  ['no_aplica', 'No aplica'],
]
const NOMBRE_ESTADO = Object.fromEntries(ESTADOS_CONDICION)

// El texto si está especificada; si no, su estado y, si lo hay, el texto.
export function textoCondicion(condicion) {
  if (!condicion) return NOMBRE_ESTADO.no_especificado
  if (condicion.estado === 'especificado') return condicion.texto
  const estado = NOMBRE_ESTADO[condicion.estado] ?? NOMBRE_ESTADO.no_especificado
  return condicion.texto ? `${estado}: ${condicion.texto}` : estado
}
