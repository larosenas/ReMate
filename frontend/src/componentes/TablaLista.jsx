// CU-003 — Lista de proveedores o de peticionarios: consultar, añadir, editar, desactivar, reactivar
// y eliminar (baja definitiva, solo de los desactivados y con motivo).
// El orden de la A a la Z lo da la API; aquí solo se muestra.
import { useEffect, useId, useRef, useState } from 'react'
import { Link } from 'react-router'
import { actualizar, crear, listar } from '../api/listas.js'
import BajaDefinitiva from './BajaDefinitiva.jsx'
import Campo, { claseEntrada as entrada, claseBoton } from './Campo.jsx'

const VACIO = { nombre: '', email: '' }
// Mismos límites que la API (backend/app/api/listas.py).
const MAX_NOMBRE = 200
const MAX_EMAIL = 254

// Igual que el backend: sin distinguir mayúsculas y con los espacios repetidos reducidos a uno.
function claveNombre(texto) {
  return texto.split(/\s+/).filter(Boolean).join(' ').toLowerCase()
}

// Traduce un error de la API a errores por campo ('nombre', 'email' o 'general').
function erroresDe(error) {
  if (error.codigo === 'correo_duplicado') return { email: error.message }
  if (error.codigo === 'datos_no_validos') {
    const campos = error.detalles.campo ? [error.detalles.campo] : (error.detalles.campos ?? [])
    if (campos.some((c) => c.endsWith('email'))) return { email: error.message }
    if (campos.some((c) => c.endsWith('nombre') || c.endsWith('nombre_completo'))) return { nombre: error.message }
  }
  return { general: error.message }
}

function comprobarVacios(nombre, email, etiquetaNombre) {
  const faltan = {}
  if (!nombre.trim()) faltan.nombre = `${etiquetaNombre} es obligatorio.`
  if (!email.trim()) faltan.email = 'El correo es obligatorio.'
  return faltan
}

// `conRetrasos`: cada fila enlaza con el histórico de retrasos (solo proveedores, CU-010).
export default function TablaLista({ titulo, ruta, campoNombre, etiquetaNombre, motivosBaja = [], conRetrasos = false }) {
  const idTitulo = useId()
  const [registros, setRegistros] = useState([])
  const [verInactivos, setVerInactivos] = useState(false)
  const [cargando, setCargando] = useState(true)
  const [errorCarga, setErrorCarga] = useState(null)
  const [enviando, setEnviando] = useState(false)
  const [formulario, setFormulario] = useState(VACIO)
  const [errores, setErrores] = useState({})
  const [aviso, setAviso] = useState(null)
  // Nombre ya avisado (A3): si se vuelve a pulsar «Añadir» con el mismo nombre, se guarda.
  const [nombreAvisado, setNombreAvisado] = useState(null)
  const [duplicado, setDuplicado] = useState(null)
  const [editando, setEditando] = useState(null)
  const [erroresEdicion, setErroresEdicion] = useState({})
  // Recién desactivado (para ofrecer eliminarlo) y el que se está eliminando.
  const [desactivado, setDesactivado] = useState(null)
  const [eliminando, setEliminando] = useState(null)
  const [eliminado, setEliminado] = useState(null)
  const seccion = useRef(null)

  // Al cancelar la baja, el foco vuelve a su «Eliminar …» (si la fila está a la vista).
  function cancelarBaja() {
    const nombre = `Eliminar ${eliminando[campoNombre]}`
    setEliminando(null)
    const boton = [...(seccion.current?.querySelectorAll('button') ?? [])].find((b) => b.getAttribute('aria-label') === nombre)
    boton?.focus()
  }

  // Cada cambio en `recargas` vuelve a pedir la lista (tras un alta, edición o (des)activación).
  const [recargas, setRecargas] = useState(0)
  const recargar = () => setRecargas((n) => n + 1)

  useEffect(() => {
    let vigente = true
    listar(ruta, verInactivos)
      .then((datos) => {
        if (!vigente) return
        setRegistros(datos)
        setErrorCarga(null)
      })
      .catch((error) => vigente && setErrorCarga(error.message))
      .finally(() => vigente && setCargando(false))
    return () => {
      vigente = false
    }
  }, [ruta, verInactivos, recargas])

  function homonimo(nombre, exceptoId = null) {
    const clave = claveNombre(nombre)
    return registros.find((r) => r.id !== exceptoId && claveNombre(r[campoNombre]) === clave)
  }

  function limpiarMensajes() {
    setErrores({})
    setAviso(null)
    setDuplicado(null)
    setDesactivado(null)
    setEliminado(null)
  }

  function empezarBaja(registro) {
    limpiarMensajes()
    setEliminando(registro)
  }

  function bajaHecha(registro) {
    setEliminando(null)
    setEliminado(registro)
    recargar()
  }

  async function anadir(evento) {
    evento.preventDefault()
    if (enviando) return
    limpiarMensajes()
    const faltan = comprobarVacios(formulario.nombre, formulario.email, etiquetaNombre)
    if (Object.keys(faltan).length) {
      setErrores(faltan)
      return
    }
    const parecido = homonimo(formulario.nombre)
    const clave = claveNombre(formulario.nombre)
    if (parecido && nombreAvisado !== clave) {
      setNombreAvisado(clave)
      setAviso(
        `Ya existe «${parecido[campoNombre]}» (${parecido.email}). Si es otro contacto, pulsa «Añadir» de nuevo para guardarlo.`,
      )
      return
    }
    setEnviando(true)
    try {
      const nuevo = await crear(ruta, { [campoNombre]: formulario.nombre, email: formulario.email })
      setFormulario(VACIO)
      setNombreAvisado(null)
      // El backend también busca nombres repetidos (incluidos los inactivos que no se ven).
      if (nuevo.avisos?.length && !parecido) setAviso(nuevo.avisos.join(' '))
      recargar()
    } catch (error) {
      setErrores(erroresDe(error))
      if (error.codigo === 'correo_duplicado') setDuplicado(error.detalles.existente)
    } finally {
      setEnviando(false)
    }
  }

  // Desactivar o reactivar: los errores se muestran como mensaje general.
  async function cambiarActivo(id, activo) {
    if (enviando) return
    limpiarMensajes()
    setEnviando(true)
    try {
      const registro = await actualizar(ruta, id, { activo })
      // Al desactivar, se ofrece eliminarlo definitivamente.
      if (!activo) setDesactivado(registro)
      recargar()
    } catch (error) {
      setErrores({ general: error.message })
    } finally {
      setEnviando(false)
    }
  }

  function empezarEdicion(registro) {
    limpiarMensajes()
    setErroresEdicion({})
    setEditando({ ...registro, avisado: false })
  }

  function cancelarEdicion() {
    setErroresEdicion({})
    setEditando(null)
  }

  async function guardarEdicion() {
    if (enviando) return
    const faltan = comprobarVacios(editando[campoNombre], editando.email, etiquetaNombre)
    if (Object.keys(faltan).length) {
      setErroresEdicion(faltan)
      return
    }
    const original = registros.find((r) => r.id === editando.id)
    const cambiaNombre = claveNombre(original[campoNombre]) !== claveNombre(editando[campoNombre])
    const parecido = cambiaNombre && homonimo(editando[campoNombre], editando.id)
    if (parecido && !editando.avisado) {
      setEditando({ ...editando, avisado: true })
      setErroresEdicion({
        nombre: `Ya existe «${parecido[campoNombre]}». Pulsa «Guardar» de nuevo para mantenerlo.`,
      })
      return
    }
    setEnviando(true)
    try {
      await actualizar(ruta, editando.id, { [campoNombre]: editando[campoNombre], email: editando.email })
      cancelarEdicion()
      recargar()
    } catch (error) {
      setErroresEdicion(erroresDe(error))
    } finally {
      setEnviando(false)
    }
  }

  return (
    <section ref={seccion} aria-labelledby={idTitulo} className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="mb-3 flex items-center justify-between gap-4">
        <h2 id={idTitulo} className="text-xl font-medium">
          {titulo}
        </h2>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={verInactivos} onChange={(e) => setVerInactivos(e.target.checked)} />
          Ver inactivos
        </label>
      </div>

      {errorCarga && (
        <p role="alert" className="mb-3 text-sm text-red-700">
          {errorCarga}
        </p>
      )}

      <table className="mb-4 w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 text-left">
            <th className="py-2 font-medium">{etiquetaNombre}</th>
            <th className="font-medium">Correo</th>
            <th>
              <span className="sr-only">Acciones</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {registros.map((r) =>
            editando?.id === r.id ? (
              <FilaEdicion
                key={r.id}
                registro={editando}
                campoNombre={campoNombre}
                etiquetaNombre={etiquetaNombre}
                errores={erroresEdicion}
                enviando={enviando}
                onCambio={(cambio) => setEditando({ ...editando, ...cambio, avisado: false })}
                onGuardar={guardarEdicion}
                onCancelar={cancelarEdicion}
              />
            ) : (
              <tr key={r.id} className={`border-b border-slate-100 ${r.activo ? '' : 'text-slate-600 italic'}`}>
                <td className="py-2">
                  {r[campoNombre]}
                  {!r.activo && (
                    <span className="ml-2 rounded bg-slate-100 px-2 py-0.5 text-xs not-italic">Inactivo</span>
                  )}
                </td>
                <td>{r.email}</td>
                <td className="whitespace-nowrap py-1 text-right">
                  {conRetrasos && (
                    <Link className="mr-3 text-slate-700 hover:underline" to={`/proveedores/${r.id}/retrasos`} aria-label={`Retrasos de ${r[campoNombre]}`}>
                      Retrasos
                    </Link>
                  )}
                  <button
                    className="mr-3 text-marca-acento hover:underline disabled:opacity-50"
                    aria-label={`Editar ${r[campoNombre]}`}
                    disabled={enviando}
                    onClick={() => empezarEdicion(r)}
                  >
                    Editar
                  </button>
                  <button
                    className="text-slate-700 hover:underline disabled:opacity-50"
                    aria-label={`${r.activo ? 'Desactivar' : 'Reactivar'} ${r[campoNombre]}`}
                    disabled={enviando}
                    onClick={() => cambiarActivo(r.id, !r.activo)}
                  >
                    {r.activo ? 'Desactivar' : 'Reactivar'}
                  </button>
                  {!r.activo && (
                    <button
                      className="ml-3 text-red-700 hover:underline disabled:opacity-50"
                      aria-label={`Eliminar ${r[campoNombre]}`}
                      disabled={enviando}
                      onClick={() => empezarBaja(r)}
                    >
                      Eliminar
                    </button>
                  )}
                </td>
              </tr>
            ),
          )}
          {!registros.length && !errorCarga && (
            <tr>
              <td colSpan="3" className="py-3 text-slate-600" aria-live="polite">
                {cargando ? 'Cargando…' : 'No hay registros.'}
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {desactivado && !eliminando && (
        <p role="status" className="mb-4 text-sm text-slate-700">
          «{desactivado[campoNombre]}» desactivado: ya no saldrá para elegirlo.{' '}
          <button className="font-medium text-red-700 hover:underline" onClick={() => empezarBaja(desactivado)}>
            Eliminarlo definitivamente
          </button>
        </p>
      )}
      {eliminado && (
        <p role="status" className="mb-4 text-sm text-slate-700">
          «{eliminado[campoNombre]}» eliminado.
        </p>
      )}
      {eliminando && (
        <div className="mb-4">
          <BajaDefinitiva
            key={eliminando.id}
            ruta={ruta}
            registro={eliminando}
            nombre={eliminando[campoNombre]}
            motivos={motivosBaja}
            onEliminado={bajaHecha}
            onCancelar={cancelarBaja}
          />
        </div>
      )}

      <form onSubmit={anadir} noValidate className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-start">
        <Campo etiqueta={etiquetaNombre} error={errores.nombre}>
          {(props) => (
            <input
              {...props}
              className={entrada}
              maxLength={MAX_NOMBRE}
              value={formulario.nombre}
              onChange={(e) => setFormulario({ ...formulario, nombre: e.target.value })}
            />
          )}
        </Campo>
        <Campo etiqueta="Correo" error={errores.email}>
          {(props) => (
            <input
              {...props}
              type="email"
              className={entrada}
              maxLength={MAX_EMAIL}
              value={formulario.email}
              onChange={(e) => setFormulario({ ...formulario, email: e.target.value })}
            />
          )}
        </Campo>
        <button
          type="submit"
          disabled={enviando}
          className={`${claseBoton} sm:mt-6`}
        >
          Añadir
        </button>
      </form>

      {errores.general && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {errores.general}
        </p>
      )}
      {aviso && (
        <p role="status" className="mt-3 rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {aviso}
        </p>
      )}
      {duplicado && (
        <p className="mt-3 text-sm">
          El correo ya es de «{duplicado[campoNombre]}» ({duplicado.email})
          {duplicado.activo ? '.' : ', que está inactivo. '}
          {!duplicado.activo && (
            <button
              className="text-marca-acento hover:underline disabled:opacity-50"
              disabled={enviando}
              onClick={() => cambiarActivo(duplicado.id, true)}
            >
              Reactivarlo
            </button>
          )}
        </p>
      )}
    </section>
  )
}

function FilaEdicion({ registro, campoNombre, etiquetaNombre, errores, enviando, onCambio, onGuardar, onCancelar }) {
  // Cada error se enlaza a su campo, para los lectores de pantalla.
  const id = useId()
  // Intro guarda y Escape cancela, como en un formulario.
  function teclas(evento) {
    if (evento.key === 'Enter') onGuardar()
    if (evento.key === 'Escape') onCancelar()
  }
  return (
    <tr className="border-b border-slate-100 align-top">
      <td className="py-1 pr-2">
        <input
          aria-label={`Editar ${etiquetaNombre.toLowerCase()}`}
          aria-invalid={Boolean(errores.nombre)}
          aria-describedby={errores.nombre ? `${id}-nombre` : undefined}
          className={entrada}
          maxLength={MAX_NOMBRE}
          autoFocus
          value={registro[campoNombre]}
          onKeyDown={teclas}
          onChange={(e) => onCambio({ [campoNombre]: e.target.value })}
        />
        {errores.nombre && (
          <p id={`${id}-nombre`} role="alert" className="mt-1 text-red-700">
            {errores.nombre}
          </p>
        )}
      </td>
      <td className="py-1 pr-2">
        <input
          aria-label="Editar correo"
          aria-invalid={Boolean(errores.email)}
          aria-describedby={errores.email ? `${id}-email` : undefined}
          type="email"
          className={entrada}
          maxLength={MAX_EMAIL}
          value={registro.email}
          onKeyDown={teclas}
          onChange={(e) => onCambio({ email: e.target.value })}
        />
        {errores.email && (
          <p id={`${id}-email`} role="alert" className="mt-1 text-red-700">
            {errores.email}
          </p>
        )}
        {errores.general && (
          <p role="alert" className="mt-1 text-red-700">
            {errores.general}
          </p>
        )}
      </td>
      <td className="whitespace-nowrap py-3 text-right">
        <button className="mr-3 text-marca-acento hover:underline disabled:opacity-50" disabled={enviando} onClick={onGuardar}>
          Guardar
        </button>
        <button className="text-slate-700 hover:underline" onClick={onCancelar}>
          Cancelar
        </button>
      </td>
    </tr>
  )
}
