// Formatos para mostrar y leer números y fechas en español.

// "1250.5" → "1.250,50". Sin símbolo de moneda: la oferta puede venir en cualquier moneda.
export function importe(texto) {
  if (texto === null || texto === undefined || texto === '') return '—'
  // useGrouping 'always': «1.250,50» (en español, por defecto no se separan los miles con 4 cifras).
  return Number(texto).toLocaleString('es-ES', { minimumFractionDigits: 2, maximumFractionDigits: 4, useGrouping: 'always' })
}

// Monedas de los desplegables, con su símbolo (ADR 0010). ReMate no convierte importes.
export const MONEDAS = [
  ['EUR', '€'],
  ['USD', '$'],
  ['GBP', '£'],
  ['PLN', 'zł'],
  ['CHF', 'CHF'],
  ['JPY', '¥'],
]

// Una moneda que no está en la lista se muestra con su código (por ejemplo, SEK).
export const simboloMoneda = (codigo) => MONEDAS.find(([c]) => c === codigo)?.[1] ?? codigo ?? ''

// Importe con el símbolo de su moneda: «4.636,00 €».
export function importeEn(texto, moneda) {
  const valor = importe(texto)
  return valor === '—' || !moneda ? valor : `${valor} ${simboloMoneda(moneda)}`
}

const dosCifras =(n) => String(n).padStart(2, '0')

// Fecha en el formato de la aplicación y de SAP: "DD.MM.AAAA". Una fecha sola ("2026-11-19")
// se toma tal cual; una con hora ("2026-10-22T09:15:00+02:00") se pasa a la hora local.
export function fechaCorta(iso) {
  if (!iso) return '—'
  if (iso.length <= 10) {
    const [anio, mes, dia] = iso.split('-')
    return `${dia}.${mes}.${anio}`
  }
  const d = new Date(iso)
  return `${dosCifras(d.getDate())}.${dosCifras(d.getMonth() + 1)}.${d.getFullYear()}`
}

// Fecha de hoy en el formato de los campos de fecha («2026-10-26»), en la hora local.
export function hoyIso(ahora = new Date()) {
  return `${ahora.getFullYear()}-${dosCifras(ahora.getMonth() + 1)}-${dosCifras(ahora.getDate())}`
}

// "DD.MM.AAAA HH:MM" en hora local (historial de estados).
export function fechaHora(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return `${fechaCorta(iso)} ${dosCifras(d.getHours())}:${dosCifras(d.getMinutes())}`
}

// Lo que escribe el ingeniero → texto decimal para la API. Admite «1.250,50», «1250,50»,
// «2,5», «1250.50» y «1.250» (con punto de miles). Devuelve null si está vacío y NaN si no es un
// número o es ambiguo («1,250.50»). `decimales` limita las cifras decimales (como la API).
export function aDecimal(texto, decimales = 4) {
  const limpio = String(texto ?? '').trim().replace(/\s/g, '')
  if (!limpio) return null
  let normalizado
  if (limpio.includes(',')) {
    // Coma decimal: los puntos solo pueden ser de miles («1.250,50»).
    if (!/^-?\d{1,3}(\.\d{3})*,\d+$|^-?\d+,\d+$/.test(limpio)) return NaN
    normalizado = limpio.replace(/\./g, '').replace(',', '.')
  } else if (/^-?\d{1,3}(\.\d{3})+$/.test(limpio)) {
    // «1.250» o «12.500.000»: en español, el punto separa los miles.
    normalizado = limpio.replace(/\./g, '')
  } else {
    normalizado = limpio
  }
  if (!/^-?\d+(\.\d+)?$/.test(normalizado)) return NaN
  const parteDecimal = normalizado.split('.')[1] ?? ''
  return parteDecimal.length > decimales ? NaN : normalizado
}

// "1250.50" (API) → "1250,50" para editarlo en un campo de texto.
export function paraEditar(texto) {
  return texto === null || texto === undefined ? '' : String(texto).replace('.', ',')
}

// CU-010: retraso medio de un proveedor (días por pedido, con un decimal): 7.5 → «7,5 días».
// `conRetraso`: hubo algún retraso; si el medio redondea a 0, no son «0 días».
export function diasMedios(dias, conRetraso = false) {
  const numero = Number(dias ?? 0)
  if (conRetraso && numero === 0) return 'menos de 0,1 días'
  return `${numero.toLocaleString('es-ES', { maximumFractionDigits: 1 })} ${numero === 1 ? 'día' : 'días'}`
}

// CU-010: proporción de pedidos con retraso, en tanto por ciento redondeado (2 de 4 → 50).
export function porcentajeConRetraso({ pedidos, con_retraso }) {
  return pedidos ? Math.round((100 * con_retraso) / pedidos) : 0
}
