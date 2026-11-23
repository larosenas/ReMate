// CU-005 — Tabla para SAP con las columnas y los formatos exactos, y botón para copiar sus filas
// (separadas por tabuladores, para pegarlas en SAP).
import { MENSAJE_SIN_COPIAR, useCopiar } from '../portapapeles.js'
import { COLUMNAS_SAP as COLUMNAS, filasComoTexto } from '../sap.js'

export default function TablaSap({ filas }) {
  const [copiado, copiar] = useCopiar()

  if (!filas.length) return <p className="text-sm text-slate-600">La oferta no tiene líneas.</p>
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left">
              {COLUMNAS.map(([clave, titulo]) => (
                <th key={clave} className="py-2 pr-4 font-medium">
                  {titulo}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="font-mono">
            {filas.map((fila, i) => (
              <tr key={i} className="border-b border-slate-100">
                {COLUMNAS.map(([clave]) => (
                  <td key={clave} className="py-1 pr-4">
                    {fila[clave]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button type="button" className="mt-2 text-sm text-marca-acento hover:underline" onClick={() => copiar(filasComoTexto(filas))}>
        {copiado === 'ok' ? 'Filas copiadas' : 'Copiar las filas'}
      </button>
      {copiado === 'error' && (
        <p role="alert" className="text-sm text-red-700">
          {MENSAJE_SIN_COPIAR}
        </p>
      )}
    </div>
  )
}
