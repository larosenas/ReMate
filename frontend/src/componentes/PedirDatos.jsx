// CU-004 — Pedir al proveedor los datos que faltan en su oferta. La IA redacta el
// correo, el ingeniero lo revisa y lo descarga como .eml para enviarlo él. No se guarda en
// ReMate.
import { useEffect, useState } from 'react'
import { borradorPeticionDatos, generarPeticionDatos } from '../api/ofertas.js'
import { descargar } from '../api/descargar.js'
import Campo, { claseEntrada, claseBoton } from './Campo.jsx'

export default function PedirDatos({ necesidadId, oferta, onCerrar }) {
  const [borrador, setBorrador] = useState(null)
  const [cuerpo, setCuerpo] = useState('')
  const [error, setError] = useState('')
  const [errorCuerpo, setErrorCuerpo] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [descargado, setDescargado] = useState(false)

  useEffect(() => {
    let vigente = true
    borradorPeticionDatos(necesidadId, oferta.id)
      .then((datos) => {
        if (!vigente) return
        setBorrador(datos)
        setCuerpo(datos.cuerpo)
      })
      .catch((e) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [necesidadId, oferta.id])

  async function generar() {
    if (!cuerpo.trim()) {
      setErrorCuerpo('El cuerpo del correo está vacío.')
      return
    }
    setErrorCuerpo('')
    setError('')
    setOcupado(true)
    try {
      const { blob, nombre } = await generarPeticionDatos(necesidadId, oferta.id, cuerpo)
      const url = URL.createObjectURL(blob)
      descargar(url, nombre)
      // Se libera después: algunos navegadores empiezan la descarga tras el clic.
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      setDescargado(true)
    } catch (e) {
      if (e.detalles?.campo === 'cuerpo') setErrorCuerpo(e.message)
      else setError(e.message)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <section aria-label={`Pedir los datos que faltan a ${oferta.proveedor.nombre}`} className="grid gap-3 rounded border border-slate-200 p-4 text-sm">
      <h4 className="font-medium">Pedir los datos que faltan</h4>
      {!borrador && !error && <p role="status">Preparando el correo…</p>}
      {borrador && (
        <>
          {borrador.avisos.length > 0 && (
            <div role="status" className="rounded bg-amber-50 px-4 py-2 text-amber-900">
              <ul>
                {borrador.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          )}
          <p>
            <span className="font-medium">Para:</span> {borrador.para}
          </p>
          <p>
            <span className="font-medium">Asunto:</span> {borrador.asunto}
          </p>
          <Campo etiqueta="Cuerpo del correo (revísalo y edítalo si hace falta)" error={errorCuerpo}>
            {(props) => <textarea {...props} rows={14} className={`${claseEntrada} font-mono`} value={cuerpo} onChange={(e) => setCuerpo(e.target.value)} />}
          </Campo>
          {descargado && <p role="status">Correo descargado: ábrelo con Outlook y envíalo. No se guarda en ReMate.</p>}
        </>
      )}
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-4">
        {borrador && (
          <button type="button" className={claseBoton} disabled={ocupado} onClick={generar}>
            {ocupado ? 'Generando…' : 'Descargar el .eml'}
          </button>
        )}
        <button type="button" className="text-slate-700 hover:underline" onClick={onCerrar}>
          Cerrar
        </button>
      </div>
    </section>
  )
}
