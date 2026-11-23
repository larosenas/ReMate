// CU-002 — Solicitar ofertas: elegir proveedores y adjuntos, preparar el correo con código,
// revisarlo y generar el .eml (proveedores en CCO). La aplicación no envía el correo.
// Con menos de 3 proveedores hay que dar el motivo, que va al texto para SAP.
import { useEffect, useId, useState } from 'react'
import { Link } from 'react-router'
import { descargar } from '../api/descargar.js'
import { crear, listar } from '../api/listas.js'
import { comprobarProveedorNuevo, erroresDeProveedorNuevo } from '../proveedorNuevo.js'
import { anadirAdjuntos, generarSolicitud, prepararSolicitud, urlSolicitudEml } from '../api/necesidades.js'
import { useFocoDeVuelta } from '../foco.js'
import { usePeticionarios } from '../usePeticionarios.js'
import Campo, { claseEntrada, claseBoton } from './Campo.jsx'
import SelectorArchivo from './SelectorArchivo.jsx'

const MAX_ADJUNTO = 25 * 1024 * 1024
const MINIMO_PROVEEDORES = 3

// Cómo empieza la línea del texto para SAP (la completa el motivo; ver adjudicacion.py).
function inicioLineaSap(cuantos) {
  return cuantos === 1 ? 'Proveedor único por' : `Solo ${cuantos} proveedores consultados por`
}

export default function SolicitarOfertas({ necesidad, onActualizada }) {
  const [proveedores, setProveedores] = useState([])
  const { peticionarios, peticionarioId, setPeticionarioId, errorPeticionarios } = usePeticionarios(
    necesidad.peticionario.id,
  )
  const [elegidos, setElegidos] = useState([])
  const [motivo, setMotivo] = useState('')
  const idAyudaMotivo = useId()
  const pocos = elegidos.length > 0 && elegidos.length < MINIMO_PROVEEDORES
  // Por defecto van todos los adjuntos de la necesidad; quitar uno aquí no lo borra (CU-002).
  const [quitados, setQuitados] = useState([])
  const [borrador, setBorrador] = useState(null)
  const [cuerpo, setCuerpo] = useState('')
  const [errores, setErrores] = useState({})
  const [ocupado, setOcupado] = useState(false)
  const [recargas, setRecargas] = useState(0)

  // Proveedor nuevo («Otro», flujo 3a).
  const [verOtro, setVerOtro] = useState(false)
  const [nuevo, setNuevo] = useState({ nombre: '', email: '' })
  const [erroresNuevo, setErroresNuevo] = useState({})
  // Error al cargar la lista: aparte de los errores del formulario, que se limpian al preparar.
  const [errorCarga, setErrorCarga] = useState(null)
  // Al «Volver a elegir», el foco vuelve a «Preparar correo».
  const botonPreparar = useFocoDeVuelta(Boolean(borrador))

  useEffect(() => {
    let vigente = true
    listar('/api/proveedores')
      .then((lista) => {
        if (!vigente) return
        setProveedores(lista)
        setErrorCarga(null)
      })
      .catch((error) => vigente && setErrorCarga(`No se ha podido cargar la lista de proveedores: ${error.message}`))
    return () => {
      vigente = false
    }
  }, [recargas])

  const adjuntoIds = necesidad.adjuntos.map((a) => a.id).filter((id) => !quitados.includes(id))

  function alternar(lista, setLista, id) {
    setLista(lista.includes(id) ? lista.filter((x) => x !== id) : [...lista, id])
  }

  async function guardarProveedor() {
    if (ocupado) return
    const faltan = comprobarProveedorNuevo(nuevo)
    setErroresNuevo(faltan)
    if (Object.keys(faltan).length) return
    setOcupado(true)
    try {
      const creado = await crear('/api/proveedores', nuevo)
      setElegidos((e) => [...e, creado.id])
      setNuevo({ nombre: '', email: '' })
      setVerOtro(false)
      setRecargas((n) => n + 1)
    } catch (error) {
      const existente = error.detalles?.existente
      if (existente?.activo) {
        // El proveedor ya está en la lista: se marca en lugar de duplicarlo.
        setElegidos((e) => (e.includes(existente.id) ? e : [...e, existente.id]))
        setErroresNuevo({ general: `${error.message} Se ha marcado «${existente.nombre}».` })
      } else {
        setErroresNuevo(erroresDeProveedorNuevo(error))
      }
    } finally {
      setOcupado(false)
    }
  }

  async function subirAdjuntos(evento) {
    const archivos = Array.from(evento.target.files ?? [])
    evento.target.value = ''
    const grandes = archivos.filter((a) => a.size > MAX_ADJUNTO)
    if (grandes.length) {
      setErrores({ adjuntos: `«${grandes[0].name}» supera el máximo de 25 MB.` })
      return
    }
    setOcupado(true)
    try {
      await anadirAdjuntos(necesidad.id, archivos)
      setErrores({})
    } catch (error) {
      setErrores({ adjuntos: error.message })
      return
    } finally {
      setOcupado(false)
    }
    try {
      await onActualizada()
    } catch {
      setErrores({ adjuntos: 'Los adjuntos se han guardado, pero no se ha podido recargar la página: recárgala.' })
    }
  }

  async function preparar() {
    if (!elegidos.length) {
      setErrores({ proveedores: 'Elige al menos un proveedor.' })
      return
    }
    if (pocos && !motivo.trim().replace(/\.+$/, '').trim()) {
      setErrores({ motivo: `Con menos de ${MINIMO_PROVEEDORES} proveedores, indica el motivo.` })
      return
    }
    setErrores({})
    setOcupado(true)
    try {
      const datos = await prepararSolicitud(necesidad.id, adjuntoIds)
      setBorrador(datos)
      setCuerpo(datos.cuerpo)
    } catch (error) {
      setErrores({ general: error.message })
    } finally {
      setOcupado(false)
    }
  }

  async function generar() {
    if (!cuerpo.trim()) {
      setErrores({ cuerpo: 'El cuerpo del correo está vacío.' })
      return
    }
    setOcupado(true)
    try {
      const actualizada = await generarSolicitud(necesidad.id, {
        peticionario_id: Number(peticionarioId),
        proveedor_ids: elegidos,
        adjunto_ids: adjuntoIds,
        cuerpo,
        motivo_pocos_proveedores: pocos ? motivo : null,
      })
      descargar(urlSolicitudEml(necesidad.id))
      await onActualizada(actualizada)
    } catch (error) {
      const campo = error.detalles?.campo
      if (campo === 'proveedor_ids') setErrores({ proveedores: error.message })
      else if (campo === 'motivo_pocos_proveedores') setErrores({ motivo: error.message })
      else setErrores({ general: error.message })
    } finally {
      setOcupado(false)
    }
  }

  return (
    <section className="rounded-lg border border-t-4 border-slate-200 border-t-marca-acento bg-white p-5 sm:p-6">
      <h2 className="mb-4 text-2xl font-normal">2. Solicitar ofertas</h2>

      <fieldset className="mb-5" aria-describedby={errores.proveedores ? 'error-proveedores' : undefined}>
        <legend className="mb-2 text-sm font-medium">Proveedores (irán en copia oculta)</legend>
        <div className="grid gap-1 sm:grid-cols-2">
          {proveedores.map((p) => (
            <label key={p.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={elegidos.includes(p.id)}
                disabled={Boolean(borrador)}
                onChange={() => alternar(elegidos, setElegidos, p.id)}
              />
              {p.nombre} <span className="text-slate-600">({p.email})</span>
            </label>
          ))}
        </div>
        {!borrador && (
          <button type="button" className="mt-2 text-sm text-marca-acento hover:underline" onClick={() => setVerOtro(!verOtro)}>
            Otro proveedor…
          </button>
        )}
        {errores.proveedores && (
          <p id="error-proveedores" role="alert" className="mt-1 text-sm text-red-700">
            {errores.proveedores}
          </p>
        )}
      </fieldset>

      {pocos && (
        <div className="mb-5 max-w-2xl">
          <Campo etiqueta={`Motivo de pedir oferta a menos de ${MINIMO_PROVEEDORES} proveedores`} error={errores.motivo}>
            {(props) => (
              <textarea
                {...props}
                aria-describedby={[props['aria-describedby'], idAyudaMotivo].filter(Boolean).join(' ')}
                rows={2}
                className={claseEntrada}
                disabled={Boolean(borrador)}
                value={motivo}
                onChange={(e) => {
                  setMotivo(e.target.value)
                  if (errores.motivo) setErrores({})
                }}
              />
            )}
          </Campo>
          <p id={idAyudaMotivo} className="mt-1 text-sm text-slate-600">
            Irá en el texto para SAP: «{inicioLineaSap(elegidos.length)} {motivo.trim().replace(/\.+$/, '') || '…'}.»
          </p>
        </div>
      )}

      {verOtro && !borrador && (
        <div className="mb-5 grid gap-3 rounded border border-slate-200 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <Campo etiqueta="Nombre del proveedor" error={erroresNuevo.nombre}>
            {(props) => (
              <input
                {...props}
                className={claseEntrada}
                maxLength={200}
                value={nuevo.nombre}
                onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })}
              />
            )}
          </Campo>
          <Campo etiqueta="Correo del proveedor" error={erroresNuevo.email}>
            {(props) => (
              <input
                {...props}
                type="email"
                className={claseEntrada}
                maxLength={254}
                value={nuevo.email}
                onChange={(e) => setNuevo({ ...nuevo, email: e.target.value })}
              />
            )}
          </Campo>
          <button type="button" className={claseBoton} onClick={guardarProveedor}>
            Guardar en la lista
          </button>
          {erroresNuevo.general && (
            <p role="alert" className="text-sm text-red-700 sm:col-span-3">
              {erroresNuevo.general}
            </p>
          )}
        </div>
      )}

      <fieldset className="mb-5">
        <legend className="mb-2 text-sm font-medium">Adjuntos del correo</legend>
        {necesidad.adjuntos.length === 0 && <p className="text-sm text-slate-600">La necesidad no tiene adjuntos.</p>}
        {necesidad.adjuntos.map((a) => (
          <label key={a.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!quitados.includes(a.id)}
              disabled={Boolean(borrador)}
              onChange={() => alternar(quitados, setQuitados, a.id)}
            />
            {a.nombre_archivo}
          </label>
        ))}
        {!borrador && (
          <div className="mt-2">
            <SelectorArchivo
              etiqueta="Añadir adjuntos a la necesidad"
              multiple
              mostrarSeleccion={false}
              disabled={ocupado}
              error={errores.adjuntos}
              onChange={subirAdjuntos}
            />
          </div>
        )}
      </fieldset>

      <div className="mb-5 max-w-sm">
        <Campo etiqueta="Quién hace la solicitud">
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

      {!borrador ? (
        <div className="flex items-center gap-4">
          {/* Atrás: volver al paso 1 para corregir los datos de la necesidad. */}
          <Link to={`/necesidades/${necesidad.id}/editar`} className="text-sm text-slate-700 hover:underline">
            Atrás
          </Link>
          <button ref={botonPreparar} type="button" className={claseBoton} disabled={ocupado} onClick={preparar}>
            {ocupado ? 'Preparando…' : 'Preparar correo'}
          </button>
        </div>
      ) : (
        <div className="grid gap-4">
          {borrador.avisos.length > 0 && (
            <ul role="status" className="rounded bg-amber-50 px-4 py-2 text-sm text-amber-900">
              {borrador.avisos.map((aviso) => (
                <li key={aviso}>{aviso}</li>
              ))}
            </ul>
          )}
          <p className="text-sm">
            <span className="font-medium">Asunto:</span> {borrador.asunto}
          </p>
          <Campo etiqueta="Cuerpo del correo (revísalo y edítalo si hace falta)" error={errores.cuerpo}>
            {(props) => (
              // Al pasar a revisar el correo, el foco va al cuerpo.
              <textarea {...props} autoFocus rows={16} className={`${claseEntrada} font-mono`} value={cuerpo} onChange={(e) => setCuerpo(e.target.value)} />
            )}
          </Campo>
          <div className="flex gap-4">
            <button type="button" className={claseBoton} disabled={ocupado} onClick={generar}>
              {ocupado ? 'Generando…' : 'Generar solicitud'}
            </button>
            <button type="button" className="text-sm text-slate-700 hover:underline disabled:opacity-50" disabled={ocupado} onClick={() => setBorrador(null)}>
              Volver a elegir
            </button>
          </div>
        </div>
      )}

      {(errores.general || errorCarga || errorPeticionarios) && (
        <p role="alert" className="mt-4 text-sm text-red-700">
          {errores.general || errorCarga || errorPeticionarios}
        </p>
      )}
    </section>
  )
}
