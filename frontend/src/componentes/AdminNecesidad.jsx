// Modo admin (ADR 0015): buscar una necesidad por su código y deshacer su último paso, corregir
// datos cerrados o borrarla con todo lo suyo (escribiendo su código para confirmar).
import { useState } from 'react'
import { borrarNecesidad, corregirNecesidad, deshacerPaso } from '../api/admin.js'
import { listarNecesidades, obtenerNecesidad } from '../api/necesidades.js'
import { ESTADOS } from '../estados.js'
import Campo, { claseBoton, claseBotonSecundario, claseEntrada } from './Campo.jsx'

const CAMPOS = [
  ['fecha_entrega_prevista', 'Fecha de entrega prevista', 'date'],
  ['fecha_entrega_real', 'Fecha en que llegó', 'date'],
  ['numero_pedido_sap', 'Número de pedido SAP', 'text'],
  ['comentario_entrega', 'Comentario de la entrega', 'textarea'],
]

const valoresDe = (n) => Object.fromEntries(CAMPOS.map(([c]) => [c, n[c] ?? '']))

export default function AdminNecesidad({ alCaducarSesion }) {
  const [codigo, setCodigo] = useState('')
  const [necesidad, setNecesidad] = useState(null)
  const [valores, setValores] = useState({})
  const [confirmarDeshacer, setConfirmarDeshacer] = useState(false)
  const [codigoBorrado, setCodigoBorrado] = useState('')
  const [mensaje, setMensaje] = useState(null)
  const [error, setError] = useState(null)
  // Error de un campo concreto al corregir (`detalles.campo` de la API).
  const [errorCampo, setErrorCampo] = useState({})
  const [ocupado, setOcupado] = useState(false)

  async function hacer(accion) {
    setOcupado(true)
    setError(null)
    setErrorCampo({})
    setMensaje(null)
    try {
      await accion()
    } catch (e) {
      if (e.estado === 401) alCaducarSesion()
      else if (CAMPOS.some(([c]) => c === e.detalles?.campo)) setErrorCampo({ [e.detalles.campo]: e.message })
      else setError(e.message)
    } finally {
      setOcupado(false)
    }
  }

  function mostrar(n) {
    setNecesidad(n)
    setValores(valoresDe(n))
    setConfirmarDeshacer(false)
    setCodigoBorrado('')
  }

  const buscar = (evento) => {
    evento.preventDefault()
    hacer(async () => {
      const encontrada = (await listarNecesidades()).find((n) => n.codigo === codigo.trim())
      if (!encontrada) {
        setNecesidad(null)
        throw new Error(`No hay ninguna necesidad con el código ${codigo.trim()}.`)
      }
      mostrar(await obtenerNecesidad(encontrada.id))
    })
  }

  const ultimo = necesidad?.historial?.at(-1)
  const sePuedeDeshacer = ultimo?.estado_anterior && ultimo.estado_nuevo === necesidad.estado && necesidad.estado !== 'necesidad_creada'

  const deshacer = () =>
    hacer(async () => {
      mostrar(await deshacerPaso(necesidad.id, necesidad.estado))
      setMensaje(`Paso deshecho: ahora está en «${ESTADOS[ultimo.estado_anterior]}».`)
    })

  const corregir = () =>
    hacer(async () => {
      const cambios = Object.fromEntries(
        CAMPOS.filter(([c]) => (valores[c] ?? '') !== (necesidad[c] ?? '')).map(([c]) => [c, valores[c] === '' ? null : valores[c]]),
      )
      if (!Object.keys(cambios).length) throw new Error('No has cambiado nada.')
      mostrar(await corregirNecesidad(necesidad.id, cambios))
      setMensaje('Datos corregidos.')
    })

  const borrar = () =>
    hacer(async () => {
      const resultado = await borrarNecesidad(necesidad.id, codigoBorrado.trim())
      setNecesidad(null)
      setCodigo('')
      setMensaje(
        `Necesidad ${resultado.codigo} borrada, con ${resultado.archivos} archivo(s)` +
          (resultado.no_borrados ? ` (${resultado.no_borrados} no se han podido borrar del disco).` : '.'),
      )
    })

  return (
    <section aria-labelledby="admin-necesidad" className="grid gap-4 rounded-lg border border-slate-200 p-5">
      <h2 id="admin-necesidad" className="text-xl font-normal">
        Necesidad
      </h2>
      <form onSubmit={buscar} className="flex flex-wrap items-end gap-3">
        <div className="w-56">
          <Campo etiqueta="Código de la necesidad">
            {(props) => <input {...props} className={claseEntrada} inputMode="numeric" value={codigo} onChange={(e) => setCodigo(e.target.value)} />}
          </Campo>
        </div>
        <button type="submit" className={claseBotonSecundario} disabled={ocupado || !codigo.trim()}>
          Buscar
        </button>
      </form>
      {mensaje && (
        <p role="status" className="text-sm text-green-800">
          {mensaje}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-700">
          {error}
        </p>
      )}

      {necesidad && (
        <div className="grid gap-5">
          <p className="text-sm">
            <span className="font-medium">
              {necesidad.codigo} {necesidad.titulo}
            </span>{' '}
            · {ESTADOS[necesidad.estado]}
          </p>

          <div className="grid gap-2">
            <h3 className="font-medium">Deshacer el último paso</h3>
            {sePuedeDeshacer ? (
              confirmarDeshacer ? (
                <div className="flex flex-wrap items-center gap-3 text-sm">
                  <span>
                    Volverá a «{ESTADOS[ultimo.estado_anterior]}» y se quitará lo que guardó el paso (correos y archivos generados,
                    fechas…). Los retrasos registrados se mantienen.
                  </span>
                  <button type="button" className={claseBoton} disabled={ocupado} onClick={deshacer}>
                    Sí, deshacer
                  </button>
                  <button type="button" className={claseBotonSecundario} onClick={() => setConfirmarDeshacer(false)}>
                    No
                  </button>
                </div>
              ) : (
                <div>
                  <button type="button" className={claseBotonSecundario} onClick={() => setConfirmarDeshacer(true)}>
                    Deshacer «{ESTADOS[ultimo.estado_anterior]}» → «{ESTADOS[necesidad.estado]}»
                  </button>
                </div>
              )
            ) : (
              <p className="text-sm text-slate-600">No hay ningún paso que deshacer.</p>
            )}
          </div>

          <div className="grid gap-3">
            <h3 className="font-medium">Corregir datos</h3>
            <div className="grid gap-3 sm:grid-cols-2">
              {CAMPOS.map(([campo, etiqueta, tipo]) => (
                <Campo key={campo} etiqueta={etiqueta} error={errorCampo[campo]}>
                  {(props) =>
                    tipo === 'textarea' ? (
                      <textarea {...props} rows={2} maxLength={1000} className={claseEntrada} value={valores[campo]} onChange={(e) => setValores({ ...valores, [campo]: e.target.value })} />
                    ) : (
                      <input {...props} type={tipo} className={claseEntrada} value={valores[campo]} onChange={(e) => setValores({ ...valores, [campo]: e.target.value })} />
                    )
                  }
                </Campo>
              ))}
            </div>
            <div>
              <button type="button" className={claseBotonSecundario} disabled={ocupado} onClick={corregir}>
                Guardar las correcciones
              </button>
            </div>
          </div>

          <div className="grid gap-3 rounded border border-red-300 bg-red-50 p-4">
            <h3 className="font-medium text-red-900">Borrar la necesidad</h3>
            <p className="text-sm text-red-900">
              Se borra de verdad, con sus ofertas, archivos, historial, retrasos y comentarios. No se puede deshacer.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div className="w-56">
                <Campo etiqueta={`Escribe ${necesidad.codigo} para confirmar`}>
                  {(props) => <input {...props} className={claseEntrada} value={codigoBorrado} onChange={(e) => setCodigoBorrado(e.target.value)} />}
                </Campo>
              </div>
              <button type="button" className={claseBoton} disabled={ocupado || codigoBorrado.trim() !== necesidad.codigo} onClick={borrar}>
                Borrar definitivamente
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
