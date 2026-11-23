// CU-004 — Paso 3 ya hecho: las ofertas que se recibieron, solo para consultarlas (desde la
// adjudicación en adelante). La adjudicada se marca.
import { useEffect, useState } from 'react'
import { listarOfertas } from '../api/ofertas.js'
import { importeEn } from '../formatos.js'
import EntregaOferta from './EntregaOferta.jsx'

export default function ResumenOfertas({ necesidad }) {
  // null mientras carga, para no decir «No se recibieron ofertas» antes de saberlo.
  const [ofertas, setOfertas] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let vigente = true
    listarOfertas(necesidad.id)
      .then((lista) => vigente && setOfertas(lista))
      .catch((e) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [necesidad.id])

  if (error)
    return (
      <p role="alert" className="text-sm text-red-700">
        {error}
      </p>
    )
  if (ofertas === null) return <p className="text-sm text-slate-600">Cargando…</p>
  if (ofertas.length === 0) return <p className="text-sm text-slate-600">No se recibieron ofertas.</p>
  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="border-b border-slate-200 text-left">
          <th className="py-2 font-medium">Proveedor</th>
          <th className="font-medium">Oferta</th>
          <th className="font-medium">Importe sin IVA</th>
          <th className="font-medium">Entrega</th>
          <th className="font-medium">Condiciones de pago</th>
        </tr>
      </thead>
      <tbody>
        {ofertas.map((o) => (
          <tr key={o.id} className="border-b border-slate-100">
            <td className="py-2">
              {o.proveedor.nombre}
              {o.id === necesidad.oferta_adjudicada_id && (
                <span className="ml-2 rounded bg-green-100 px-2 py-0.5 text-xs text-green-800">Adjudicada</span>
              )}
            </td>
            <td>{o.numero_oferta ?? '—'}</td>
            <td>{importeEn(o.importe_sin_iva, o.moneda)}</td>
            <td>
              <EntregaOferta oferta={o} />
            </td>
            <td>{o.condiciones_pago ?? '—'}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}
