// CU-004 — Añadir una oferta: el correo (.eml o .msg de Outlook) en su zona y los adjuntos en otra, cada uno con
// su tipo de archivo («+» para añadir más). La aplicación propone el tipo por la extensión.
// Al elegir el correo, el backend lo lee: sus adjuntos salen ya como filas (sin los
// logos de la firma) y, si reconoce al proveedor por el remitente o su dominio, queda elegido.
// Solo se guarda: la IA la lee después, con las demás, en «Analizar y comparar».
import { useId, useRef, useState } from 'react'
import { crear } from '../api/listas.js'
import { comprobarProveedorNuevo, erroresDeProveedorNuevo } from '../proveedorNuevo.js'
import { leerCorreo, subirOferta } from '../api/ofertas.js'
import { tipoPorExtension } from '../tiposArchivo.js'
import Campo, { claseEntrada, claseBoton, claseBotonSecundario } from './Campo.jsx'
import SelectorArchivo from './SelectorArchivo.jsx'

const MAX_ARCHIVO = 25 * 1024 * 1024
const TIPOS = [
  ['pdf', 'PDF'],
  ['excel', 'Excel'],
  ['word', 'Word'],
  ['imagen', 'Imagen'],
  ['otro', 'Otro'],
]
const OTRO = 'otro'

let siguienteFila = 1

export default function SubirOferta({ necesidad, proveedores, onSubida, onCancelar }) {
  const [correo, setCorreo] = useState(null)
  // Cambiar la clave vacía el selector del navegador (no se puede vaciar de otra forma).
  const [claveCorreo, setClaveCorreo] = useState(0)
  const [filas, setFilas] = useState([{ clave: 0, archivo: null, tipo: 'otro' }])
  // Adjuntos del propio correo: { indice, nombre, tipo }. Se guardan los que no se quiten.
  const [delCorreo, setDelCorreo] = useState([])
  const [leyendo, setLeyendo] = useState(false)
  const [avisoCorreo, setAvisoCorreo] = useState('')
  // Solo vale la respuesta del último correo elegido (se puede cambiar mientras se lee otro).
  const lectura = useRef(0)
  const [proveedorId, setProveedorId] = useState('')
  const [errores, setErrores] = useState({})
  const [enviando, setEnviando] = useState(false)
  // CU-004 4c: el proveedor ya tiene oferta; se pide confirmar antes de sustituirla.
  const [sustituir, setSustituir] = useState(null)
  // Proveedor nuevo («Otro», CU-004 4a), que se añade a la lista y queda elegido.
  const [nuevos, setNuevos] = useState([])
  const [nuevo, setNuevo] = useState({ nombre: '', email: '' })
  const [erroresNuevo, setErroresNuevo] = useState({})
  const idAdjuntos = useId()

  // Los solicitados van primero (casi siempre la oferta es de uno de ellos) y cada grupo, de la
  // A a la Z (anotada en CU-004).
  const todos = [...proveedores, ...nuevos.filter((n) => !proveedores.some((p) => p.id === n.id))].sort(
    (a, b) => a.nombre.localeCompare(b.nombre, 'es', { sensitivity: 'base' }),
  )
  const solicitados = new Set(necesidad.proveedores_solicitados.map((p) => p.id))
  const primero = todos.filter((p) => solicitados.has(p.id))
  const resto = todos.filter((p) => !solicitados.has(p.id))

  async function guardarProveedor() {
    const faltan = comprobarProveedorNuevo(nuevo)
    setErroresNuevo(faltan)
    if (Object.keys(faltan).length) return
    try {
      const creado = await crear('/api/proveedores', nuevo)
      setNuevos((n) => [...n, creado])
      setProveedorId(String(creado.id))
      setNuevo({ nombre: '', email: '' })
    } catch (error) {
      const existente = error.detalles?.existente
      if (existente?.activo) {
        // Ya está en la lista: se elige en lugar de duplicarlo.
        setNuevos((n) => [...n, existente])
        setProveedorId(String(existente.id))
        setNuevo({ nombre: '', email: '' })
      } else {
        setErroresNuevo(erroresDeProveedorNuevo(error))
      }
    }
  }

  function elegirCorreo(evento) {
    const archivo = evento.target.files?.[0] ?? null
    const nombre = archivo?.name.toLowerCase() ?? ''
    if (archivo && !nombre.endsWith('.eml') && !nombre.endsWith('.msg')) {
      olvidarCorreo()
      evento.target.value = ''
      setCorreo(null)
      setErrores({ correo: 'El correo de la oferta tiene que ser un archivo .eml o .msg.' })
      return false
    }
    setErrores({})
    setCorreo(archivo)
    leerAdjuntos(archivo)
  }

  function olvidarCorreo() {
    lectura.current += 1
    setDelCorreo([])
    setAvisoCorreo('')
    setLeyendo(false)
  }

  async function leerAdjuntos(archivo) {
    olvidarCorreo()
    if (!archivo) return
    const esta = lectura.current
    setLeyendo(true)
    try {
      const leido = await leerCorreo(necesidad.id, archivo)
      if (esta !== lectura.current) return
      setDelCorreo(leido.adjuntos.map((a) => ({ ...a, tipo: tipoPorExtension(a.nombre) })))
      setAvisoCorreo(leido.aviso_proveedor ?? '')
      const reconocido = leido.proveedor
      if (reconocido) {
        // Se elige solo si no se había elegido ya otro a mano.
        setNuevos((n) => (proveedores.some((p) => p.id === reconocido.id) || n.some((p) => p.id === reconocido.id) ? n : [...n, reconocido]))
        setProveedorId((actual) => actual || String(reconocido.id))
      }
    } catch (error) {
      if (esta !== lectura.current) return
      if (error.detalles?.campo === 'correo') {
        setCorreo(null)
        setClaveCorreo((n) => n + 1)
        setErrores({ correo: error.message })
      } else {
        // Sin la lectura previa se puede subir igual: los adjuntos se eligen a mano.
        setAvisoCorreo('No se han podido leer los adjuntos del correo: añádelos a mano si hacen falta.')
      }
    } finally {
      if (esta === lectura.current) setLeyendo(false)
    }
  }

  function cambiarFila(clave, cambio) {
    setFilas((actuales) => actuales.map((f) => (f.clave === clave ? { ...f, ...cambio } : f)))
  }

  function elegirAdjunto(clave, evento) {
    const archivo = evento.target.files?.[0] ?? null
    if (archivo && archivo.size > MAX_ARCHIVO) {
      evento.target.value = ''
      setErrores({ adjuntos: `«${archivo.name}» supera el máximo de 25 MB.` })
      return false
    }
    setErrores({})
    cambiarFila(clave, { archivo, tipo: archivo ? tipoPorExtension(archivo.name) : 'otro' })
  }

  // Con una sola fila, se vacía (nueva clave) en lugar de quitarla, para poder elegir otro archivo.
  function quitarFila(clave) {
    setFilas((actuales) =>
      actuales.length > 1
        ? actuales.filter((f) => f.clave !== clave)
        : [{ clave: siguienteFila++, archivo: null, tipo: 'otro' }],
    )
  }

  // `anadirDatos`: en lugar de sustituir la oferta del proveedor, la completa.
  async function enviar(evento, confirmarSustitucion = false, anadirDatos = false) {
    evento?.preventDefault()
    if (enviando || leyendo) return
    if (!correo) {
      setErrores({ correo: 'Sube el correo de la oferta (.eml o .msg).' })
      return
    }
    if (proveedorId === OTRO) {
      setErrores({ proveedor: 'Guarda antes el proveedor nuevo en la lista.' })
      return
    }
    setErrores({})
    setSustituir(null)
    setEnviando(true)
    try {
      const adjuntos = filas.filter((f) => f.archivo).map(({ archivo, tipo }) => ({ archivo, tipo }))
      const adjuntosCorreo = delCorreo.map(({ indice, tipo }) => ({ indice, tipo }))
      const oferta = await subirOferta(necesidad.id, { proveedorId, correo, adjuntos, adjuntosCorreo, confirmarSustitucion, anadirDatos })
      onSubida(oferta)
    } catch (error) {
      const campo = error.detalles?.campo
      if (error.codigo === 'oferta_existente') setSustituir(error.message)
      else if (campo === 'correo') setErrores({ correo: error.message })
      // Un adjunto sin tipo o demasiado grande: el error va en los adjuntos (o en el correo, si es él).
      else if (error.codigo === 'archivo_demasiado_grande')
        setErrores(error.detalles?.archivo === correo?.name ? { correo: error.message } : { adjuntos: error.message })
      else if (campo === 'tipos_adjunto') setErrores({ adjuntos: error.message })
      else if (campo === 'proveedor_id') setErrores({ proveedor: error.message })
      else setErrores({ general: error.message })
    } finally {
      setEnviando(false)
    }
  }

  return (
    <form onSubmit={enviar} noValidate className="grid gap-4 rounded border border-slate-200 p-4">
      <h3 className="text-lg font-medium">Añadir oferta</h3>
      <div className="flex flex-wrap items-end gap-3">
        <SelectorArchivo
          key={claveCorreo}
          etiqueta="Correo de la oferta (.eml o .msg)"
          accept=".eml,.msg,message/rfc822,application/vnd.ms-outlook"
          error={errores.correo}
          onChange={elegirCorreo}
        />
        {correo && (
          <button
            type="button"
            className="pb-1 text-sm text-slate-700 hover:underline"
            aria-label="Quitar el correo"
            onClick={() => {
              setCorreo(null)
              setClaveCorreo((n) => n + 1)
              olvidarCorreo()
            }}
          >
            Quitar
          </button>
        )}
      </div>

      <fieldset className="grid gap-2" aria-describedby={errores.adjuntos ? `${idAdjuntos}-error` : undefined}>
        <legend className="mb-1 text-sm font-medium">Adjuntos que importan (por ejemplo, el PDF de la oferta)</legend>
        <div aria-live="polite" className="text-sm text-slate-700">
          {leyendo && <p>Leyendo los adjuntos del correo…</p>}
          {avisoCorreo && <p>{avisoCorreo}</p>}
        </div>
        {delCorreo.map((adjunto) => (
          <div key={`correo-${adjunto.indice}`} className="flex flex-wrap items-center gap-3">
            <span className="break-all rounded bg-slate-50 px-3 py-1 text-sm text-slate-900">
              {adjunto.nombre} <span className="text-slate-600">(del correo)</span>
            </span>
            <select
              aria-label={`Tipo de ${adjunto.nombre}`}
              className="rounded border border-slate-300 px-2 py-1 text-sm focus:border-marca-acento focus:outline-none"
              value={adjunto.tipo}
              onChange={(e) => setDelCorreo((lista) => lista.map((a) => (a.indice === adjunto.indice ? { ...a, tipo: e.target.value } : a)))}
            >
              {TIPOS.map(([valor, texto]) => (
                <option key={valor} value={valor}>
                  {texto}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="text-sm text-slate-700 hover:underline"
              aria-label={`Quitar ${adjunto.nombre}`}
              onClick={() => setDelCorreo((lista) => lista.filter((a) => a.indice !== adjunto.indice))}
            >
              Quitar
            </button>
          </div>
        ))}
        {filas.map((fila, i) => (
          <div key={fila.clave} className="flex flex-wrap items-center gap-3">
            <SelectorArchivo
              etiqueta={`Adjunto ${i + 1}`}
              etiquetaVisible={false}
              onChange={(e) => elegirAdjunto(fila.clave, e)}
            />
            <select
              aria-label={`Tipo del adjunto ${i + 1}`}
              className="rounded border border-slate-300 px-2 py-1 text-sm focus:border-marca-acento focus:outline-none"
              value={fila.tipo}
              onChange={(e) => cambiarFila(fila.clave, { tipo: e.target.value })}
            >
              {TIPOS.map(([valor, texto]) => (
                <option key={valor} value={valor}>
                  {texto}
                </option>
              ))}
            </select>
            {(filas.length > 1 || fila.archivo) && (
              <button
                type="button"
                className="text-sm text-slate-700 hover:underline"
                aria-label={`Quitar el adjunto ${i + 1}`}
                onClick={() => quitarFila(fila.clave)}
              >
                Quitar
              </button>
            )}
          </div>
        ))}
        <button
          type="button"
          className="w-fit rounded border border-slate-300 px-3 py-1 text-sm hover:border-marca-acento"
          aria-label="Añadir otro adjunto"
          onClick={() => setFilas([...filas, { clave: siguienteFila++, archivo: null, tipo: 'otro' }])}
        >
          +
        </button>
        {errores.adjuntos && (
          <p id={`${idAdjuntos}-error`} role="alert" className="text-sm text-red-700">
            {errores.adjuntos}
          </p>
        )}
      </fieldset>

      <div className="max-w-sm">
        <Campo etiqueta="Proveedor" error={errores.proveedor}>
          {(props) => (
            <select {...props} className={claseEntrada} value={proveedorId} onChange={(e) => setProveedorId(e.target.value)}>
              <option value="">Reconocerlo por el remitente del correo</option>
              {primero.length > 0 && (
                <optgroup label="Proveedores solicitados">
                  {primero.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.nombre}
                    </option>
                  ))}
                </optgroup>
              )}
              <optgroup label="Otros proveedores">
                {resto.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.nombre}
                  </option>
                ))}
              </optgroup>
              <option value={OTRO}>Otro…</option>
            </select>
          )}
        </Campo>
      </div>

      {proveedorId === OTRO && (
        <fieldset className="grid gap-3 rounded border border-slate-200 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
          <legend className="px-1 text-sm font-medium">Proveedor nuevo</legend>
          <Campo etiqueta="Nombre del proveedor" error={erroresNuevo.nombre}>
            {(props) => (
              <input {...props} className={claseEntrada} maxLength={200} value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} />
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
        </fieldset>
      )}

      {sustituir && (
        <div role="alert" className="grid gap-2 rounded border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          <p>{sustituir}</p>
          <div className="flex flex-wrap items-center gap-4">
            <button type="button" className={claseBoton} disabled={enviando} onClick={() => enviar(null, true)}>
              Sí, sustituir la oferta anterior
            </button>
            {/* Su respuesta a la petición de datos: completa la oferta sin sustituirla. */}
            <button type="button" className={claseBotonSecundario} disabled={enviando} onClick={() => enviar(null, false, true)}>
              Añadir datos del proveedor
            </button>
            <button type="button" className="text-slate-700 hover:underline" onClick={() => setSustituir(null)}>
              No
            </button>
          </div>
        </div>
      )}

      {errores.general && (
        <p role="alert" className="text-sm text-red-700">
          {errores.general}
        </p>
      )}
      <div className="flex items-center gap-4">
        <button type="submit" className={claseBoton} disabled={enviando || leyendo}>
          {enviando ? 'Subiendo…' : 'Subir oferta'}
        </button>
        <button type="button" className="text-sm text-slate-700 hover:underline" onClick={onCancelar}>
          Cancelar
        </button>
      </div>
    </form>
  )
}
