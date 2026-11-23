// Modo admin (ADR 0015). Se llega con el enlace «admin» del pie. Sin
// sesión pide la contraseña; con ella: estado del servidor, acciones sobre una necesidad, tareas
// a mano y registros. El servidor comprueba la sesión en cada llamada.
import { useCallback, useEffect, useState } from 'react'
import { entrar, lanzarTarea, salir, verEstado, verRegistros, verSesion } from '../api/admin.js'
import AdminNecesidad from '../componentes/AdminNecesidad.jsx'
import Campo, { claseBoton, claseBotonSecundario, claseEntrada } from '../componentes/Campo.jsx'
import { ESTADOS } from '../estados.js'
import { fechaHora } from '../formatos.js'

const megas = (bytes) => `${(bytes / 1_000_000).toLocaleString('es-ES', { maximumFractionDigits: 1 })} MB`
const gigas = (bytes) => `${(bytes / 1_000_000_000).toLocaleString('es-ES', { maximumFractionDigits: 1 })} GB`
const numero = (n) => n.toLocaleString('es-ES')

const TAREAS = [
  ['recordatorios', 'Recordatorio de entrega'],
  ['avisos', 'Avisos del pedido SAP'],
  ['caducidad', 'Caducidad de archivos y registros'],
]

function Acceso({ alEntrar }) {
  const [clave, setClave] = useState('')
  const [error, setError] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  async function enviar(evento) {
    evento.preventDefault()
    setOcupado(true)
    setError(null)
    try {
      await entrar(clave)
      setClave('')
      alEntrar()
    } catch (e) {
      setError(e.message)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <form onSubmit={enviar} className="grid max-w-sm gap-4">
      <Campo etiqueta="Contraseña del modo admin" error={error}>
        {(props) => <input {...props} type="password" autoComplete="current-password" autoFocus className={claseEntrada} value={clave} onChange={(e) => setClave(e.target.value)} />}
      </Campo>
      <div>
        <button type="submit" className={claseBoton} disabled={ocupado || !clave}>
          Entrar
        </button>
      </div>
    </form>
  )
}

// Sin COPIAS_DIR, con COPIAS_DIR que no se puede leer (no existe, sin permisos, unidad de red
// caída) o con la última copia, completa o no.
function textoCopia(copia) {
  if (!copia) return 'Sin COPIAS_DIR en el .env'
  if (copia.accesible === false) return 'No se puede leer la carpeta de COPIAS_DIR'
  if (!copia.carpeta) return 'Ninguna'
  return `${copia.carpeta}${copia.completa ? '' : ' (incompleta)'}`
}

function Estado({ estado }) {
  const cifras = [
    ['Archivos guardados', `${numero(estado.archivos.cantidad)} (${megas(estado.archivos.bytes)})`],
    ['Disco libre', estado.disco ? `${gigas(estado.disco.libre)} de ${gigas(estado.disco.total)}` : '—'],
    [
      'Última copia de seguridad',
      textoCopia(estado.ultima_copia),
    ],
    ['IA, últimos 30 días', `${numero(estado.ia_30_dias.llamadas)} llamadas; ${numero(estado.ia_30_dias.entrada)} tokens de entrada y ${numero(estado.ia_30_dias.salida)} de salida`],
    ['Avisos y errores, últimos 7 días', numero(estado.avisos_y_errores_7_dias)],
  ]
  return (
    <div className="grid gap-4">
      <dl className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
        {cifras.map(([etiqueta, valor]) => (
          <div key={etiqueta} className="rounded border border-slate-200 p-3">
            <dt className="text-slate-500">{etiqueta}</dt>
            <dd className="mt-1">{valor}</dd>
          </div>
        ))}
      </dl>
      <p className="text-sm text-slate-700">
        <span className="font-medium">Necesidades:</span>{' '}
        {Object.entries(estado.necesidades)
          .map(([codigo, cuantas]) => `${ESTADOS[codigo] ?? codigo}: ${cuantas}`)
          .join(' · ')}
      </p>
    </div>
  )
}

function Tareas({ alCaducarSesion }) {
  const [resultado, setResultado] = useState(null)
  const [confirmar, setConfirmar] = useState(null)
  const [error, setError] = useState(null)
  const [ocupado, setOcupado] = useState(false)

  async function lanzar(nombre, prueba) {
    setOcupado(true)
    setError(null)
    setConfirmar(null)
    try {
      setResultado(await lanzarTarea(nombre, prueba))
    } catch (e) {
      if (e.estado === 401) alCaducarSesion()
      else setError(e.message)
    } finally {
      setOcupado(false)
    }
  }

  return (
    <div className="grid gap-3">
      <p className="text-sm text-slate-700">Son las de la tarea diaria. «Probar» no envía ni borra nada: dice lo que haría.</p>
      <ul className="grid gap-2">
        {TAREAS.map(([nombre, texto]) => (
          <li key={nombre} className="flex flex-wrap items-center gap-3 text-sm">
            <span className="w-64">{texto}</span>
            <button type="button" className={claseBotonSecundario} disabled={ocupado} onClick={() => lanzar(nombre, true)}>
              Probar
            </button>
            {confirmar === nombre ? (
              <>
                <button type="button" className={claseBoton} disabled={ocupado} onClick={() => lanzar(nombre, false)}>
                  Sí, ejecutar
                </button>
                <button type="button" className={claseBotonSecundario} onClick={() => setConfirmar(null)}>
                  No
                </button>
              </>
            ) : (
              <button type="button" className={claseBotonSecundario} disabled={ocupado} onClick={() => setConfirmar(nombre)}>
                Ejecutar
              </button>
            )}
          </li>
        ))}
      </ul>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {resultado && (
        <div role="status" className="rounded border border-slate-200 bg-slate-50 p-3 text-sm">
          <p className="font-medium">
            {TAREAS.find(([n]) => n === resultado.tarea)?.[1]} {resultado.prueba ? '(prueba)' : '(ejecutada)'}
          </p>
          <ul className="mt-1">
            {Object.entries(resultado.resumen).map(([clave, valor]) => (
              <li key={clave}>
                {clave}: {Array.isArray(valor) ? valor.map((v) => (Array.isArray(v) ? v.join(': ') : v)).join(', ') || 'ninguno' : String(valor)}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Registros({ alCaducarSesion }) {
  const [nivel, setNivel] = useState('WARNING')
  const [lista, setLista] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let vigente = true
    verRegistros(nivel)
      .then((datos) => {
        if (!vigente) return
        setLista(datos)
        // El error de un filtro anterior no se queda al cambiarlo.
        setError(null)
      })
      .catch((e) => {
        if (!vigente) return
        if (e.estado === 401) alCaducarSesion()
        else setError(e.message)
      })
    return () => {
      vigente = false
    }
  }, [nivel, alCaducarSesion])

  return (
    <div className="grid gap-3">
      <div className="w-64">
        <Campo etiqueta="Mostrar">
          {(props) => (
            <select {...props} className={claseEntrada} value={nivel} onChange={(e) => setNivel(e.target.value)}>
              <option value="">Todo</option>
              <option value="WARNING">Avisos y errores</option>
              <option value="ERROR">Solo errores</option>
            </select>
          )}
        </Campo>
      </div>
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}
      {lista && lista.length === 0 && <p className="text-sm text-slate-600">No hay mensajes.</p>}
      {lista && lista.length > 0 && (
        <ul className="grid gap-2 text-sm">
          {lista.map((r) => (
            <li key={r.id} className="border-b border-slate-200 pb-2">
              <span className="text-slate-500 tabular-nums">{fechaHora(r.creado_en)}</span> · <span className="font-medium">{r.nivel}</span> ·{' '}
              <span className="text-slate-500">{r.origen}</span>
              <p className="whitespace-pre-line">{r.mensaje}</p>
              {r.traza && (
                <details>
                  <summary className="cursor-pointer text-slate-600">Traza</summary>
                  <pre className="overflow-x-auto text-xs">{r.traza}</pre>
                </details>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function PaginaAdmin() {
  const [sesion, setSesion] = useState(null)
  const [estado, setEstado] = useState(null)
  const [error, setError] = useState(null)

  const comprobar = useCallback(() => {
    verSesion()
      .then(setSesion)
      .catch((e) => setError(e.message))
  }, [])
  const caducada = useCallback(() => setSesion({ activa: false, configurado: true, caducada: true }), [])

  useEffect(comprobar, [comprobar])

  const cargarEstado = useCallback(() => {
    verEstado()
      .then(setEstado)
      .catch((e) => (e.estado === 401 ? caducada() : setError(e.message)))
  }, [caducada])

  useEffect(() => {
    if (sesion?.activa) cargarEstado()
  }, [sesion, cargarEstado])

  async function cerrar() {
    await salir().catch(() => null)
    setEstado(null)
    setSesion({ activa: false, configurado: true })
  }

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl font-normal md:text-4xl">Modo admin</h1>
        {sesion?.activa && (
          <button type="button" className={claseBotonSecundario} onClick={cerrar}>
            Cerrar la sesión
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      {sesion && !sesion.configurado && (
        <p className="text-slate-700">El modo admin no está configurado: falta ADMIN_CLAVE_HASH en el .env del servidor (manual de operación).</p>
      )}
      {sesion?.configurado && !sesion.activa && (
        <>
          {sesion.caducada && <p className="text-sm text-amber-900">La sesión ha caducado: vuelve a entrar.</p>}
          <Acceso alEntrar={comprobar} />
        </>
      )}
      {sesion?.activa && (
        <>
          <section aria-labelledby="admin-estado" className="grid gap-3 rounded-lg border border-slate-200 p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 id="admin-estado" className="text-xl font-normal">
                Estado del servidor
              </h2>
              <button type="button" className={claseBotonSecundario} onClick={cargarEstado}>
                Actualizar
              </button>
            </div>
            {estado ? <Estado estado={estado} /> : <p className="text-sm text-slate-600">Cargando…</p>}
          </section>
          <AdminNecesidad alCaducarSesion={caducada} />
          <section aria-labelledby="admin-tareas" className="grid gap-3 rounded-lg border border-slate-200 p-5">
            <h2 id="admin-tareas" className="text-xl font-normal">
              Tareas a mano
            </h2>
            <Tareas alCaducarSesion={caducada} />
          </section>
          <section aria-labelledby="admin-registros" className="grid gap-3 rounded-lg border border-slate-200 p-5">
            <h2 id="admin-registros" className="text-xl font-normal">
              Registros
            </h2>
            <Registros alCaducarSesion={caducada} />
          </section>
        </>
      )}
    </div>
  )
}
