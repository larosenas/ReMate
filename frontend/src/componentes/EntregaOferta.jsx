// Entrega de una oferta. Si el proveedor dio un plazo y no una fecha («3 semanas»), se muestra su
// plazo; la fecha contada desde su correo va debajo, solo como orientación para comparar. Al hacer
// el pedido, el plazo se cuenta desde ese día.
// Si solo dio un mes («diciembre»), se muestra el mes y debajo su último viernes, que es la fecha
// que se usa.
import { fechaCorta } from '../formatos.js'

export default function EntregaOferta({ oferta }) {
  if (oferta.fecha_de_mes) {
    return (
      <>
        {oferta.plazo_entrega_texto}
        <span className="block text-xs text-slate-600">{fechaCorta(oferta.fecha_entrega_estimada)} (último viernes del mes)</span>
      </>
    )
  }
  if (!oferta.fecha_calculada) return fechaCorta(oferta.fecha_entrega_estimada)
  return (
    <>
      {oferta.plazo_entrega_texto}
      <span className="block text-xs text-slate-600">≈ {fechaCorta(oferta.fecha_entrega_estimada)} desde su oferta</span>
    </>
  )
}
