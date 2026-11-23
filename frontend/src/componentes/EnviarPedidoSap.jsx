// CU-007 — Paso 6: subir el pedido oficial de SAP, confirmar el número de oferta (y, si se
// quiere, el de pedido), revisar el correo de la plantilla y generar el .eml al proveedor.
// El número de pedido se lee del PDF de SAP al elegirlo.
import { useEffect, useRef, useState } from 'react'
import { descargar } from '../api/descargar.js'
import { enviarPedido, leerNumeroPedido, obtenerPropuestaPedido, prepararCorreoPedido, urlPedidoEml } from '../api/pedidoSap.js'
import { fechaHora } from '../formatos.js'
import { usePeticionarios } from '../usePeticionarios.js'
import Campo, { claseEntrada, claseBoton } from './Campo.jsx'
import SelectorArchivo, { ArchivosElegidos } from './SelectorArchivo.jsx'

const ORIGEN = {
  oferta: 'Es el número de la oferta revisada.',
  archivo: 'Sacado del nombre del archivo de la oferta: compruébalo.',
}

export default function EnviarPedidoSap({ necesidad, onEnviado }) {
  const [propuesta, setPropuesta] = useState(null)
  const [pedido, setPedido] = useState(null)
  const [numeroOferta, setNumeroOferta] = useState('')
  const [numeroPedido, setNumeroPedido] = useState('')
  // El número de pedido salió del PDF: se dice debajo del campo para comprobarlo.
  const [delPdf, setDelPdf] = useState(false)
  // Lo escrito en el campo ahora mismo (la lectura del PDF termina después de elegirlo).
  const numeroEscrito = useRef('')
  // Solo la última lectura elegida puede proponer un número; una respuesta anterior se descarta.
  const lecturaPdf = useRef(0)
  // Con el correo preparado se pasa al segundo paso (revisar y generar).
  const [correo, setCorreo] = useState(null)
  const { peticionarios, peticionarioId, setPeticionarioId, errorPeticionarios } = usePeticionarios(
    necesidad.peticionario.id,
  )
  const [errores, setErrores] = useState({})
  const [ocupado, setOcupado] = useState(false)

  useEffect(() => {
    let vigente = true
    obtenerPropuestaPedido(necesidad.id)
      .then((datos) => {
        if (!vigente) return
        setPropuesta(datos)
        setNumeroOferta(datos.numero_oferta ?? '')
      })
      .catch((e) => vigente && setErrores({ general: e.message }))
    return () => {
      vigente = false
    }
  }, [necesidad.id])

  function errorDe(e) {
    const campo = e.detalles?.campo
    return campo && campo !== 'peticionario_id' ? { [campo]: e.message } : { general: e.message }
  }

  // Al elegir el PDF, ReMate lee el número de pedido y lo propone si el campo está vacío; si no lo
  // encuentra o falla, se escribe a mano, como antes.
  async function elegirPedido(archivo) {
    const lectura = ++lecturaPdf.current
    setPedido(archivo)
    setDelPdf(false)
    if (!archivo || !archivo.name.toLowerCase().endsWith('.pdf')) return
    try {
      const { numero_pedido: numero } = await leerNumeroPedido(necesidad.id, archivo)
      if (lectura !== lecturaPdf.current || !numero || numeroEscrito.current.trim()) return
      setNumeroPedido(numero)
      setDelPdf(true)
    } catch {
      // Sin el número del PDF se sigue igual: es opcional.
    }
  }

  async function preparar() {
    if (ocupado) return
    const nuevos = {}
    if (!pedido) nuevos.pedido = 'Sube el pedido oficial de SAP.'
    if (!numeroOferta.trim()) nuevos.numero_oferta = 'Indica el número de oferta del proveedor.'
    setErrores(nuevos)
    if (Object.keys(nuevos).length) return
    setOcupado(true)
    try {
      setCorreo(await prepararCorreoPedido(necesidad.id, { numeroOferta, numeroPedido }))
    } catch (e) {
      setErrores(errorDe(e))
    } finally {
      setOcupado(false)
    }
  }

  async function generar() {
    if (ocupado) return
    if (!correo.cuerpo.trim()) {
      setErrores({ cuerpo_correo: 'El cuerpo del correo está vacío.' })
      return
    }
    setErrores({})
    setOcupado(true)
    try {
      const actualizada = await enviarPedido(necesidad.id, {
        peticionarioId: Number(peticionarioId),
        pedido,
        numeroOferta,
        numeroPedido,
        cuerpo: correo.cuerpo,
      })
      descargar(urlPedidoEml(necesidad.id))
      await onEnviado(actualizada)
    } catch (e) {
      // Un error del pedido o de los números se corrige en el primer paso.
      const nuevos = errorDe(e)
      if (nuevos.pedido || nuevos.numero_oferta || nuevos.numero_pedido) setCorreo(null)
      setErrores(nuevos)
    } finally {
      setOcupado(false)
    }
  }

  const origen = propuesta?.origen_numero_oferta

  return (
    <section className="grid gap-4 rounded-lg border border-t-4 border-slate-200 border-t-marca-acento bg-white p-5 sm:p-6">
      <h2 className="text-2xl font-normal">6. Enviar el pedido SAP al proveedor</h2>
      {/* Aviso a los avisados del pedido SAP al confirmar el paso 5 y cada semana mientras siga aquí. */}
      {/* Lo que dice la API justo al confirmar el paso 5 (por ejemplo, una dirección rechazada). */}
      {necesidad.aviso_pedido_sap_en && necesidad.avisos?.length > 0 && (
        <ul role="status" className="grid gap-1 rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {necesidad.avisos.map((aviso) => (
            <li key={aviso}>{aviso}</li>
          ))}
        </ul>
      )}
      {necesidad.aviso_pedido_sap_en ? (
        <p className="text-sm text-slate-600">
          Se ha avisado a los avisados del pedido SAP (último aviso: {fechaHora(necesidad.aviso_pedido_sap_en)}). Mientras
          el pedido no se envíe al proveedor, se les recuerda cada semana.
        </p>
      ) : (
        <p role="status" className="rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          Todavía no se ha podido avisar a los avisados del pedido SAP: se reintentará cada mañana. Comprueba que hay
          alguien en la lista «Avisados del pedido SAP» (en «Proveedores y peticionarios»).
        </p>
      )}
      {propuesta && (
        <p className="text-sm text-slate-700">
          Cuando SAP apruebe el pedido, súbelo aquí. Se preparará el correo a {propuesta.proveedor} ({propuesta.para})
          con el pedido adjunto.
        </p>
      )}

      {!correo ? (
        <>
          {/* El nombre se muestra aparte para que siga a la vista al volver de «Cambiar los datos». */}
          <div>
            <SelectorArchivo
              etiqueta="Pedido oficial de SAP"
              error={errores.pedido}
              mostrarSeleccion={false}
              onChange={(e) => elegirPedido(e.target.files?.[0] ?? null)}
            />
            <ArchivosElegidos nombres={pedido ? [pedido.name] : []} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Campo etiqueta="Número de oferta del proveedor" error={errores.numero_oferta}>
                {(props) => (
                  <input {...props} className={claseEntrada} maxLength={100} value={numeroOferta} onChange={(e) => setNumeroOferta(e.target.value)} />
                )}
              </Campo>
              {propuesta && (
                <p className="mt-1 text-xs text-slate-600">{origen ? ORIGEN[origen] : 'No se ha encontrado: escríbelo.'}</p>
              )}
            </div>
            <div>
              <Campo etiqueta="Número de pedido de SAP (opcional)" error={errores.numero_pedido}>
                {(props) => (
                  <input
                    {...props}
                    className={claseEntrada}
                    maxLength={50}
                    value={numeroPedido}
                    onChange={(e) => {
                      lecturaPdf.current += 1
                      numeroEscrito.current = e.target.value
                      setNumeroPedido(e.target.value)
                      setDelPdf(false)
                    }}
                  />
                )}
              </Campo>
              {delPdf && <p className="mt-1 text-xs text-slate-600">Leído del PDF del pedido: compruébalo.</p>}
            </div>
          </div>
          <div>
            <button type="button" className={claseBoton} disabled={ocupado || !propuesta} onClick={preparar}>
              {ocupado ? 'Preparando…' : 'Preparar correo'}
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="text-sm">
            <p>
              <span className="font-medium">Para:</span> {correo.para}
            </p>
            <p>
              <span className="font-medium">Asunto:</span> {correo.asunto}
            </p>
            <p>
              <span className="font-medium">Adjunto:</span> {pedido.name}
            </p>
          </div>
          <Campo etiqueta="Cuerpo del correo" error={errores.cuerpo_correo}>
            {(props) => (
              <textarea {...props} rows={10} className={claseEntrada} value={correo.cuerpo} onChange={(e) => setCorreo({ ...correo, cuerpo: e.target.value })} />
            )}
          </Campo>
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo etiqueta="Quién lo envía">
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
          <div className="flex flex-wrap items-center gap-4">
            <button type="button" className={claseBoton} disabled={ocupado} onClick={generar}>
              {ocupado ? 'Generando…' : 'Generar el .eml'}
            </button>
            <button type="button" className="text-sm text-slate-700 hover:underline" onClick={() => setCorreo(null)}>
              Cambiar los datos
            </button>
          </div>
        </>
      )}

      {(errores.general || errorPeticionarios) && (
        <p role="alert" className="text-sm text-red-700">
          {errores.general || errorPeticionarios}
        </p>
      )}
    </section>
  )
}
