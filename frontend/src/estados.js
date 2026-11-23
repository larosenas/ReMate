// Texto visible de cada estado de la necesidad (mismo que backend/app/modelos/necesidades.py).
export const ESTADOS = {
  necesidad_creada: 'Necesidad creada',
  en_cotizacion: 'En cotización',
  en_evaluacion: 'En evaluación',
  pendiente_solicitud_sap: 'Pendiente solicitud SAP',
  pendiente_pedido_sap: 'Pendiente pedido SAP',
  pendiente_entrega: 'Pendiente entrega',
  entregado: 'Entregado',
  cancelada: 'Cancelada',
}

// Los 7 pasos del proceso (docs/diseno/estados-necesidad.md) y el estado al que lleva cada uno.
export const PASOS = [
  { numero: 1, nombre: 'Necesidad', estado: 'necesidad_creada' },
  { numero: 2, nombre: 'Solicitud de ofertas', estado: 'en_cotizacion' },
  { numero: 3, nombre: 'Ofertas', estado: 'en_evaluacion' },
  { numero: 4, nombre: 'Adjudicación', estado: 'pendiente_solicitud_sap' },
  { numero: 5, nombre: 'Pedido en SAP', estado: 'pendiente_pedido_sap' },
  { numero: 6, nombre: 'Pedido al proveedor', estado: 'pendiente_entrega' },
  { numero: 7, nombre: 'Entrega', estado: 'entregado' },
]

// Pasos hechos para un estado (0 a 7). Una cancelada no tiene pasos: se pasa el estado anterior.
export function pasosHechos(estado) {
  return PASOS.find((p) => p.estado === estado)?.numero ?? 0
}

// Estado en que estaba una necesidad cancelada (el anterior a «Cancelada» en su historial).
export function estadoAntesDeCancelar(historial = []) {
  const cancelacion = [...historial].reverse().find((c) => c.estado_nuevo === 'cancelada')
  return cancelacion?.estado_anterior ?? null
}
