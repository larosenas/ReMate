// CU-001 — Pantalla «Nueva necesidad». Con un `id` en la ruta (/necesidades/:id/editar) sirve
// para corregir los datos con «Atrás» desde el paso 2, mientras siga en «Necesidad creada».
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { esId } from '../rutas.js'
import { actualizar, crear, listar } from '../api/listas.js'
import { actualizarNecesidad, anadirAdjuntos as subirAdjuntos, crearNecesidad, obtenerNecesidad } from '../api/necesidades.js'
import Campo, { claseEntrada, claseBoton } from '../componentes/Campo.jsx'
import SelectorArchivo from '../componentes/SelectorArchivo.jsx'

const RUTA_PETICIONARIOS = '/api/peticionarios'
const OTRO = 'otro'
const MAX_ADJUNTO = 25 * 1024 * 1024 // 25 MB por archivo, igual que el backend
const VACIO = { titulo: '', proyecto: '', peticionario_id: '', descripcion: '' }
function megas(bytes) {
  return `${(bytes / (1024 * 1024)).toLocaleString('es-ES', { maximumFractionDigits: 1 })} MB`
}

// Sin id, alta de una necesidad nueva; con id, corrección («Atrás» desde el paso 2).
export default function PaginaNuevaNecesidad() {
  const { id } = useParams()
  if (id !== undefined && !esId(id)) return <p className="text-slate-600">Esta pantalla no existe.</p>
  return <FormularioNecesidad id={id} />
}

function FormularioNecesidad({ id }) {
  const navegar = useNavigate()
  const [original, setOriginal] = useState(null)
  const [peticionarios, setPeticionarios] = useState([])
  const [errorCarga, setErrorCarga] = useState(null)
  // Error al cargar la necesidad que se corrige (aparte del de la lista de peticionarios).
  const [errorNecesidad, setErrorNecesidad] = useState(null)
  const [datos, setDatos] = useState(VACIO)
  const [adjuntos, setAdjuntos] = useState([])
  const [errores, setErrores] = useState({})
  const [enviando, setEnviando] = useState(false)
  const [creada, setCreada] = useState(null)

  // Peticionario nuevo («Otro», flujo 3a).
  const [nuevo, setNuevo] = useState({ nombre_completo: '', email: '' })
  const [erroresNuevo, setErroresNuevo] = useState({})
  const [existente, setExistente] = useState(null)

  const [recargas, setRecargas] = useState(0)
  useEffect(() => {
    let vigente = true
    listar(RUTA_PETICIONARIOS)
      .then((lista) => vigente && setPeticionarios(lista))
      .catch((error) => vigente && setErrorCarga(error.message))
    return () => {
      vigente = false
    }
  }, [recargas])

  // Al corregir, se cargan los datos actuales de la necesidad.
  useEffect(() => {
    if (!id) return
    let vigente = true
    obtenerNecesidad(id)
      .then((n) => {
        if (!vigente) return
        if (n.estado !== 'necesidad_creada') {
          setErrorNecesidad('Los datos ya no se pueden cambiar: ya se han pedido ofertas.')
          return
        }
        setOriginal(n)
        setDatos({ titulo: n.titulo, proyecto: n.proyecto, peticionario_id: String(n.peticionario.id), descripcion: n.descripcion })
      })
      .catch((error) => vigente && setErrorNecesidad(error.message))
    return () => {
      vigente = false
    }
  }, [id])

  const cambiar = (campo) => (evento) => setDatos({ ...datos, [campo]: evento.target.value })

  function elegirPeticionario(id) {
    setDatos((d) => ({ ...d, peticionario_id: String(id) }))
    setNuevo({ nombre_completo: '', email: '' })
    setErroresNuevo({})
    setExistente(null)
    setRecargas((n) => n + 1)
  }

  async function guardarPeticionario() {
    setErroresNuevo({})
    setExistente(null)
    const faltan = {}
    if (!nuevo.nombre_completo.trim()) faltan.nombre_completo = 'El nombre y apellido es obligatorio.'
    if (!nuevo.email.trim()) faltan.email = 'El correo es obligatorio.'
    if (Object.keys(faltan).length) {
      setErroresNuevo(faltan)
      return
    }
    try {
      const creado = await crear(RUTA_PETICIONARIOS, nuevo)
      elegirPeticionario(creado.id)
    } catch (error) {
      if (error.codigo === 'correo_duplicado') {
        setExistente(error.detalles.existente)
        setErroresNuevo({ email: error.message })
      } else if (error.detalles.campo === 'email') {
        setErroresNuevo({ email: error.message })
      } else {
        setErroresNuevo({ nombre_completo: error.message })
      }
    }
  }

  async function usarExistente() {
    try {
      if (!existente.activo) await actualizar(RUTA_PETICIONARIOS, existente.id, { activo: true })
      elegirPeticionario(existente.id)
    } catch (error) {
      setErroresNuevo({ email: error.message })
    }
  }

  function anadirAdjuntos(evento) {
    const elegidos = Array.from(evento.target.files ?? [])
    evento.target.value = ''
    const grandes = elegidos.filter((a) => a.size > MAX_ADJUNTO)
    setAdjuntos((actuales) => [...actuales, ...elegidos.filter((a) => a.size <= MAX_ADJUNTO)])
    setErrores((e) => ({
      ...e,
      adjuntos: grandes.length
        ? `No se ha añadido ${grandes.map((a) => `«${a.name}» (${megas(a.size)})`).join(', ')}: el máximo es 25 MB por archivo.`
        : undefined,
    }))
  }

  async function enviar(evento) {
    evento.preventDefault()
    if (enviando) return
    const faltan = {}
    if (!datos.titulo.trim()) faltan.titulo = 'El título es obligatorio.'
    if (!datos.proyecto.trim()) faltan.proyecto = 'El proyecto es obligatorio.'
    // Un peticionario desactivado no sale en la lista: no se envía aunque fuera el de la necesidad.
    if (!peticionarios.some((p) => String(p.id) === datos.peticionario_id))
      faltan.peticionario_id = 'Elige un peticionario de la lista.'
    if (!datos.descripcion.trim()) faltan.descripcion = 'La descripción es obligatoria.'
    setErrores(faltan)
    if (Object.keys(faltan).length) return
    setEnviando(true)
    try {
      if (id) {
        await actualizarNecesidad(id, { ...datos, peticionario_id: Number(datos.peticionario_id) })
        if (adjuntos.length) {
          try {
            await subirAdjuntos(id, adjuntos)
          } catch (error) {
            setErrores({ adjuntos: `Los datos se han guardado, pero no se han podido subir los adjuntos: ${error.message}` })
            return
          }
        }
        navegar(`/necesidades/${id}`)
      } else {
        setCreada(await crearNecesidad(datos, adjuntos))
      }
    } catch (error) {
      if (error.codigo === 'archivo_demasiado_grande') setErrores({ adjuntos: error.message })
      else if (error.codigo === 'datos_no_validos' && error.detalles.campo)
        setErrores({ [error.detalles.campo]: error.message })
      else setErrores({ general: error.message })
    } finally {
      setEnviando(false)
    }
  }

  function otraNecesidad() {
    setCreada(null)
    setDatos(VACIO)
    setAdjuntos([])
    setErrores({})
  }

  if (creada) {
    return (
      <section className="max-w-3xl">
        <h1 className="mb-6 text-4xl font-normal">Nueva necesidad</h1>
        <div role="status" className="rounded-lg border border-slate-200 bg-white p-5 sm:p-6">
          <p className="text-sm text-slate-600">Necesidad creada · {creada.estado_texto}</p>
          <p className="mt-1 text-2xl">
            <span className="font-medium">{creada.codigo}</span> {creada.titulo}
          </p>
          <div className="mt-6 flex flex-wrap items-center gap-4">
            <Link to={`/necesidades/${creada.id}`} className={claseBoton}>
              Solicitar ofertas (paso 2)
            </Link>
            <button className="text-sm text-slate-700 hover:underline" onClick={otraNecesidad}>
              Crear otra necesidad
            </button>
          </div>
        </div>
      </section>
    )
  }

  if (id && !original) {
    return errorNecesidad ? (
      <p role="alert" className="text-red-700">
        {errorNecesidad}
      </p>
    ) : (
      <p className="text-slate-600">Cargando…</p>
    )
  }

  return (
    <section className="max-w-3xl">
      <h1 className="mb-6 text-4xl font-normal">
        {original ? `Corregir la necesidad ${original.codigo}` : 'Nueva necesidad'}
      </h1>
      {errorCarga && (
        <p role="alert" className="mb-4 text-sm text-red-700">
          No se ha podido cargar la lista de peticionarios: {errorCarga}
        </p>
      )}
      <form onSubmit={enviar} noValidate className="grid gap-5 rounded-lg border border-slate-200 bg-white p-5 sm:p-6">
        <div className="grid gap-5 sm:grid-cols-2">
          <Campo etiqueta="Título" error={errores.titulo}>
            {(props) => (
              <input {...props} className={claseEntrada} maxLength={200} value={datos.titulo} onChange={cambiar('titulo')} />
            )}
          </Campo>
          <Campo etiqueta="Proyecto" error={errores.proyecto}>
            {(props) => (
              <input {...props} className={claseEntrada} maxLength={200} value={datos.proyecto} onChange={cambiar('proyecto')} />
            )}
          </Campo>
        </div>

        <Campo etiqueta="Peticionario" error={errores.peticionario_id}>
          {(props) => (
            <select {...props} className={claseEntrada} value={datos.peticionario_id} onChange={cambiar('peticionario_id')}>
              <option value="">Elige tu nombre…</option>
              {peticionarios.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.nombre_completo}
                </option>
              ))}
              <option value={OTRO}>Otro…</option>
            </select>
          )}
        </Campo>

        {datos.peticionario_id === OTRO && (
          <fieldset className="grid gap-3 rounded border border-slate-200 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-start">
            <legend className="px-1 text-sm font-medium">Peticionario nuevo</legend>
            <Campo etiqueta="Nombre y apellido" error={erroresNuevo.nombre_completo}>
              {(props) => (
                <input
                  {...props}
                  className={claseEntrada}
                  maxLength={200}
                  value={nuevo.nombre_completo}
                  onChange={(e) => setNuevo({ ...nuevo, nombre_completo: e.target.value })}
                />
              )}
            </Campo>
            <Campo etiqueta="Correo" error={erroresNuevo.email}>
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
            <button type="button" className={`${claseBoton} sm:mt-6`} onClick={guardarPeticionario}>
              Guardar en la lista
            </button>
            {existente && (
              <p className="text-sm sm:col-span-3">
                El correo ya es de «{existente.nombre_completo}»{existente.activo ? '' : ' (inactivo)'}.{' '}
                <button type="button" className="text-marca-acento hover:underline" onClick={usarExistente}>
                  Usar «{existente.nombre_completo}»
                </button>
              </p>
            )}
          </fieldset>
        )}

        <Campo etiqueta="Descripción de la necesidad" error={errores.descripcion}>
          {(props) => (
            <textarea {...props} rows={6} className={claseEntrada} value={datos.descripcion} onChange={cambiar('descripcion')} />
          )}
        </Campo>

        {original?.adjuntos.length > 0 && (
          <p className="text-sm">
            <span className="font-medium">Adjuntos ya guardados:</span>{' '}
            {original.adjuntos.map((a) => a.nombre_archivo).join(', ')}
          </p>
        )}
        <SelectorArchivo
          etiqueta={original ? 'Añadir adjuntos (opcional, máximo 25 MB por archivo)' : 'Adjuntos (opcional, máximo 25 MB por archivo)'}
          multiple
          mostrarSeleccion={false}
          error={errores.adjuntos}
          onChange={anadirAdjuntos}
        />
        {adjuntos.length > 0 && (
          <ul className="-mt-2 grid gap-1 text-sm">
            {adjuntos.map((archivo, i) => (
              <li key={`${archivo.name}-${i}`} className="flex items-center justify-between rounded bg-slate-50 px-3 py-1">
                <span>
                  {archivo.name} <span className="text-slate-600">({megas(archivo.size)})</span>
                </span>
                <button
                  type="button"
                  className="text-slate-700 hover:underline"
                  aria-label={`Quitar ${archivo.name}`}
                  onClick={() => setAdjuntos(adjuntos.filter((_, j) => j !== i))}
                >
                  Quitar
                </button>
              </li>
            ))}
          </ul>
        )}

        {errores.general && (
          <p role="alert" className="text-sm text-red-700">
            {errores.general}
          </p>
        )}
        <div>
          {original ? (
            <div className="flex items-center gap-4">
              <button type="submit" className={claseBoton} disabled={enviando}>
                {enviando ? 'Guardando…' : 'Guardar y volver'}
              </button>
              <Link to={`/necesidades/${id}`} className="text-sm text-slate-700 hover:underline">
                Cancelar
              </Link>
            </div>
          ) : (
            <button type="submit" className={claseBoton} disabled={enviando}>
              {enviando ? 'Creando…' : 'Crear'}
            </button>
          )}
        </div>
      </form>
    </section>
  )
}
