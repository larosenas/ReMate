// CU-005 — Columnas de la tabla para SAP (en el orden de SAP) y su copia como texto.
export const COLUMNAS_SAP = [
  ['short_text', 'Short Text'],
  ['quantity_requested', 'Quantity requested'],
  ['valuation_price', 'Valuation Price'],
  ['delivery_date', 'Delivery Date'],
  ['requisitioner', 'Requisitioner'],
]

// Un tabulador o un salto de línea dentro de un campo partiría la fila al pegarla en SAP.
const celda = (valor) => String(valor ?? '').replace(/\s+/g, ' ').trim()

export function filasComoTexto(filas) {
  return filas.map((fila) => COLUMNAS_SAP.map(([clave]) => celda(fila[clave])).join('\t')).join('\n')
}
