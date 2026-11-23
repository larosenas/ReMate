// CU-005 — Información para SAP de una necesidad adjudicada, lista para copiar, y el .eml al
// proveedor adjudicatario.
import { useEffect, useState } from 'react'
import { obtenerInformacionSap, urlAdjudicacionEml } from '../api/adjudicacion.js'
import { fechaCorta, simboloMoneda } from '../formatos.js'
import { MENSAJE_SIN_COPIAR, useCopiar } from '../portapapeles.js'
import TablaSap from './TablaSap.jsx'
import EnlaceArchivo from './EnlaceArchivo.jsx'

export default function InformacionSap({ necesidad }) {
  const [sap, setSap] = useState(null)
  const [error, setError] = useState(null)
  const [copiado, copiar] = useCopiar()

  useEffect(() => {
    let vigente = true
    obtenerInformacionSap(necesidad.id)
      .then((datos) => vigente && setSap(datos))
      .catch((e) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [necesidad.id])

  if (error) {
    return (
      <p role="alert" className="text-sm text-red-700">
        {error}
      </p>
    )
  }
  if (!sap) return <p className="text-sm text-slate-600">Cargando…</p>

  return (
    <div className="grid gap-4">
      <p className="text-sm">
        Adjudicada a <span className="font-medium">{sap.proveedor}</span> · Entrega inicial: {fechaCorta(sap.fecha_entrega_inicial)}
      </p>
      <div>
        <p className="mb-1 text-sm font-medium">Texto para SAP</p>
        <pre className="whitespace-pre-wrap rounded bg-slate-50 px-3 py-2 text-sm">{sap.texto_sap}</pre>
        <button type="button" className="mt-1 text-sm text-marca-acento hover:underline" onClick={() => copiar(sap.texto_sap)}>
          {copiado === 'ok' ? 'Texto copiado' : 'Copiar el texto'}
        </button>
        {copiado === 'error' && (
          <p role="alert" className="text-sm text-red-700">
            {MENSAJE_SIN_COPIAR}
          </p>
        )}
      </div>
      <div>
        <p className="mb-1 text-sm font-medium">Tabla para SAP</p>
        <p className="mb-2 text-sm text-slate-600">Moneda de los precios: {sap.moneda} ({simboloMoneda(sap.moneda)}).</p>
        <TablaSap filas={sap.tabla_sap} />
      </div>
      {necesidad.adjudicacion_eml && (
        <div>
          <p className="mb-2 text-sm">Abre el correo al proveedor con Outlook y envíalo.</p>
          <p className="text-sm">
            <EnlaceArchivo
              archivo={necesidad.adjudicacion_eml}
              className="inline-block rounded bg-marca-acento px-4 py-2 font-medium text-white shadow hover:bg-marca-acento-oscuro"
              href={urlAdjudicacionEml(necesidad.id)}
            >
              Descargar el .eml de adjudicación
            </EnlaceArchivo>
          </p>
        </div>
      )}
    </div>
  )
}
