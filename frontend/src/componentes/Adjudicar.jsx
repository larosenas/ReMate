// CU-005 — Adjudicar la oferta elegida: revisar el texto y la tabla para SAP y el correo al
// proveedor, y confirmar. Las líneas fijas del texto las pone la aplicación.
import { useEffect, useId, useRef, useState } from 'react'
import { adjudicar, prepararAdjudicacion, urlAdjudicacionEml } from '../api/adjudicacion.js'
import { descargar } from '../api/descargar.js'
import { simboloMoneda } from '../formatos.js'
import { llevarA } from '../desplazamiento.js'
import { usePeticionarios } from '../usePeticionarios.js'
import { MENSAJE_SIN_COPIAR, useCopiar } from '../portapapeles.js'
import Campo, { claseEntrada, claseBoton, claseBotonSecundario } from './Campo.jsx'
import TablaSap from './TablaSap.jsx'

// Datos de la oferta que usa el borrador: si cambian (se corrige la oferta mientras se adjudica),
// los bloqueos, avisos y la tabla para SAP ya no valen y hay que volver a prepararlo.
const firma = (o) =>
  JSON.stringify([o.moneda, o.importe_sin_iva, o.fecha_entrega_estimada, o.numero_oferta, o.condiciones_pago, o.otros, o.condiciones, o.lineas])

export default function Adjudicar({ necesidad, oferta, onCancelar, onAdjudicada }) {
  const [borrador, setBorrador] = useState(null)
  const [descripcion, setDescripcion] = useState('')
  const [cuerpo, setCuerpo] = useState('')
  const { peticionarios, peticionarioId, setPeticionarioId, errorPeticionarios } = usePeticionarios(
    necesidad.peticionario.id,
  )
  const [errores, setErrores] = useState({})
  // «Volver a preparar» pide confirmación si se han editado los textos (se perderían).
  const [confirmarReinicio, setConfirmarReinicio] = useState(false)
  const [enviando, setEnviando] = useState(false)
  const [copiado, copiar] = useCopiar()
  const idDescripcion = useId()

  // Al elegir la oferta, la pantalla baja hasta aquí.
  const raiz = useRef(null)
  useEffect(() => llevarA(raiz.current, { enfocar: true }), [])

  // Cada cambio en `preparaciones` vuelve a calcular el borrador («Volver a preparar»).
  const [preparaciones, setPreparaciones] = useState(0)
  // Firma de la oferta con la que se preparó el borrador.
  const [preparadaCon, setPreparadaCon] = useState(null)

  useEffect(() => {
    let vigente = true
    prepararAdjudicacion(necesidad.id, oferta.id)
      .then((datos) => {
        if (!vigente) return
        setBorrador(datos)
        setPreparadaCon(firma(oferta))
        setDescripcion(datos.descripcion_inversion)
        setCuerpo(datos.correo.cuerpo)
      })
      .catch((e) => vigente && setErrores({ general: e.message }))
    return () => {
      vigente = false
    }
    // Solo se vuelve a pedir al cambiar de oferta o al pulsar «Volver a preparar».
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [necesidad.id, oferta.id, preparaciones])

  const ofertaCambiada = Boolean(borrador) && preparadaCon !== firma(oferta)

  const editado = borrador && (descripcion !== borrador.descripcion_inversion || cuerpo !== borrador.correo.cuerpo)

  function volverAPreparar(confirmado = false) {
    if (editado && !confirmado) {
      setConfirmarReinicio(true)
      return
    }
    setConfirmarReinicio(false)
    setBorrador(null)
    setErrores({})
    setPreparaciones((n) => n + 1)
  }

  async function confirmar() {
    if (enviando) return
    const faltan = {}
    if (!descripcion.trim()) faltan.descripcion_inversion = 'Escribe la descripción de la inversión.'
    if (!cuerpo.trim()) faltan.cuerpo_correo = 'El cuerpo del correo está vacío.'
    setErrores(faltan)
    if (Object.keys(faltan).length) return
    setEnviando(true)
    try {
      const actualizada = await adjudicar(necesidad.id, {
        peticionario_id: Number(peticionarioId),
        oferta_id: oferta.id,
        descripcion_inversion: descripcion,
        cuerpo_correo: cuerpo,
      })
      descargar(urlAdjudicacionEml(necesidad.id))
      await onAdjudicada(actualizada)
    } catch (e) {
      const campo = e.detalles?.campo
      setErrores(campo ? { [campo]: e.message } : { general: e.message })
    } finally {
      setEnviando(false)
    }
  }

  return (
    <div className="mt-4 grid gap-4 rounded border border-marca-acento/40 bg-white p-4">
      <h4 ref={raiz} className="scroll-mt-6 text-lg font-medium">
        Adjudicar a {oferta.proveedor.nombre}
      </h4>
      {!borrador && !errores.general && <p className="text-sm text-slate-600">Preparando la información para SAP…</p>}
      {borrador && (
        <>
          {borrador.bloqueos.length > 0 && (
            <div role="alert" className="rounded border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-800">
              <p className="font-medium">Hay que arreglar esto para poder adjudicar:</p>
              <ul className="list-disc pl-5">
                {borrador.bloqueos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          )}
          {borrador.avisos.length > 0 && (
            <div role="status" className="rounded bg-amber-50 px-4 py-2 text-sm text-amber-900">
              <p className="font-medium">Para revisar (no impide adjudicar):</p>
              <ul className="list-disc pl-5">
                {borrador.avisos.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </div>
          )}
          {/* Las líneas fijas y la descripción en la misma caja, para copiarlo todo de una vez.
              Las líneas fijas no se editan. */}
          <div className="text-sm">
            <label htmlFor={idDescripcion} className="mb-1 block font-medium">
              Texto para SAP{' '}
              <span className="font-normal text-slate-600">(escribe la descripción de la inversión debajo de las dos líneas fijas)</span>
            </label>
            <div
              className={`rounded border focus-within:border-marca-acento ${errores.descripcion_inversion ? 'border-red-700' : 'border-slate-300'}`}
            >
              <pre className="whitespace-pre-wrap px-3 pt-2 font-sans text-sm text-slate-600" aria-hidden="true">
                {borrador.texto_sap_fijo.trimEnd()}
              </pre>
              <textarea
                id={idDescripcion}
                rows={5}
                className="block w-full resize-y rounded-b border-0 px-3 pb-2 pt-0 text-sm focus:outline-none"
                aria-invalid={Boolean(errores.descripcion_inversion)}
                aria-describedby={errores.descripcion_inversion ? `${idDescripcion}-error` : undefined}
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
              />
            </div>
            {errores.descripcion_inversion && (
              <p id={`${idDescripcion}-error`} role="alert" className="mt-1 text-red-700">
                {errores.descripcion_inversion}
              </p>
            )}
            <button type="button" className="mt-1 text-marca-acento hover:underline" onClick={() => copiar(`${borrador.texto_sap_fijo}${descripcion.trim()}`)}>
              {/* El texto completo, tal como quedará en SAP (las líneas fijas y la descripción). */}
              {copiado === 'ok' ? 'Texto copiado' : 'Copiar el texto'}
            </button>
            {copiado === 'error' && (
              <p role="alert" className="text-red-700">
                {MENSAJE_SIN_COPIAR}
              </p>
            )}
          </div>
          <div>
            <p className="mb-1 text-sm font-medium">Tabla para SAP</p>
            <p className="mb-2 text-sm text-slate-600">Moneda de los precios: {borrador.moneda || oferta.moneda} ({simboloMoneda(borrador.moneda || oferta.moneda)}). Se conserva para SAP.</p>
            <TablaSap filas={borrador.tabla_sap} />
          </div>
          <div className="grid gap-2">
            <p className="text-sm font-medium">Correo al proveedor</p>
            <p className="text-sm">
              <span className="text-slate-600">Para:</span> {borrador.correo.para} · <span className="text-slate-600">Asunto:</span>{' '}
              {borrador.correo.asunto}
            </p>
            <Campo etiqueta="Cuerpo del correo" error={errores.cuerpo_correo}>
              {(props) => <textarea {...props} rows={12} className={`${claseEntrada} font-mono`} value={cuerpo} onChange={(e) => setCuerpo(e.target.value)} />}
            </Campo>
          </div>
          <div className="max-w-sm">
            <Campo etiqueta="Quién adjudica">
              {(props) => (
                <select {...props} className={claseEntrada} value={peticionarioId} onChange={(e) => setPeticionarioId(e.target.value)}>
                  {peticionarios.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre_completo}
                    </option>
                  ))}
                </select>
              )}
            </Campo>
          </div>
        </>
      )}
      {(errores.general || errores.oferta_id || errores.peticionario_id || errorPeticionarios) && (
        <p role="alert" className="text-sm text-red-700">
          {errores.general || errores.oferta_id || errores.peticionario_id || errorPeticionarios}
        </p>
      )}
      {confirmarReinicio && (
        <div className="flex flex-wrap items-center gap-3 rounded bg-amber-50 px-4 py-2 text-sm text-amber-900">
          <span>Se perderán los cambios que has hecho en los textos. ¿Volver a prepararlos?</span>
          <button type="button" className="text-marca-acento hover:underline" onClick={() => volverAPreparar(true)}>
            Sí
          </button>
          <button type="button" className="text-slate-700 hover:underline" onClick={() => setConfirmarReinicio(false)}>
            No
          </button>
        </div>
      )}
      {ofertaCambiada && (
        <p role="alert" className="rounded border border-red-300 bg-red-50 px-4 py-2 text-sm text-red-800">
          La oferta ha cambiado desde que se preparó esta información. Pulsa «Volver a preparar» antes de adjudicar.
        </p>
      )}
      <div className="flex items-center gap-4">
        <button
          type="button"
          className={claseBoton}
          disabled={!borrador || borrador.bloqueos.length > 0 || ofertaCambiada || enviando}
          onClick={confirmar}
        >
          {enviando ? 'Adjudicando…' : 'Confirmar la adjudicación'}
        </button>
        <button
          type="button"
          className={claseBotonSecundario}
          disabled={enviando || (!borrador && !errores.general)}
          onClick={() => volverAPreparar()}
        >
          Volver a preparar
        </button>
        <button type="button" className="text-sm text-slate-700 hover:underline" onClick={onCancelar}>
          Elegir otra oferta
        </button>
      </div>
    </div>
  )
}
