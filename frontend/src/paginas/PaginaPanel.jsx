// Panel de seguimiento (CU-010): lista de necesidades de la más reciente a la más antigua, con el
// paso del proceso en que está cada una. Se filtra por estado, peticionario, proveedor adjudicado,
// fecha de creación y texto (por defecto, todas). Los filtros van en la dirección (?estado=…&…)
// para conservarlos al volver del detalle. Se filtra en el navegador sobre la lista ya cargada.
import { useEffect, useId, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'
import { listarNecesidades } from '../api/necesidades.js'
import EtiquetaEstado from '../componentes/EtiquetaEstado.jsx'
import PistaProceso from '../componentes/PistaProceso.jsx'
import { ESTADOS } from '../estados.js'
import { fechaCorta, hoyIso } from '../formatos.js'

const CAMPOS = ['estado', 'peticionario', 'proveedor', 'desde', 'hasta', 'texto']
const EN_CURSO = 'en_curso'
const CERRADOS = ['entregado', 'cancelada']

function Estado({ necesidad }) {
  return (
    <div className="grid justify-items-start gap-1.5">
      <div className="flex flex-wrap items-baseline gap-x-2">
        <EtiquetaEstado estado={necesidad.estado} texto={necesidad.estado_texto} />
        {/* Cuándo pasó a ese estado. */}
        {necesidad.estado_desde && (
          <span className="text-xs text-slate-500 tabular-nums">desde {fechaCorta(necesidad.estado_desde)}</span>
        )}
      </div>
      {/* De una cancelada el listado no sabe en qué paso se quedó: sin pista. */}
      {necesidad.estado !== 'cancelada' && <PistaProceso estado={necesidad.estado} compacta />}
    </div>
  )
}

// Día de creación en la hora local («2026-10-26»), para compararlo con los campos de fecha.
const diaDe = (iso) => hoyIso(new Date(iso))

// Para buscar sin distinguir mayúsculas ni tildes («rodamiento» encuentra «Rodamientos»).
const normalizar = (texto) =>
  texto
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()

// Personas o proveedores distintos de la lista, de la A a la Z.
function distintos(elementos, nombre) {
  const porId = Object.fromEntries(elementos.filter(Boolean).map((e) => [e.id, e]))
  return Object.values(porId).sort((a, b) => a[nombre].localeCompare(b[nombre], 'es'))
}

function cumple(n, filtros) {
  const texto = normalizar(filtros.texto.trim())
  return (
    (!filtros.estado ||
      (filtros.estado === EN_CURSO ? !CERRADOS.includes(n.estado) : n.estado === filtros.estado)) &&
    (!filtros.peticionario || String(n.peticionario.id) === filtros.peticionario) &&
    (!filtros.proveedor || String(n.proveedor_adjudicado?.id) === filtros.proveedor) &&
    (!filtros.desde || diaDe(n.creada_en) >= filtros.desde) &&
    (!filtros.hasta || diaDe(n.creada_en) <= filtros.hasta) &&
    (!texto || normalizar(`${n.codigo} ${n.titulo} ${n.proyecto}`).includes(texto))
  )
}

// Controles compactos y discretos: borde fino, sin caja de fondo; el que filtra se marca en rojo.
const claseControl = (activo) =>
  `h-9 rounded border bg-white px-2 text-sm text-marca-texto hover:border-slate-400 focus:border-marca-acento focus:outline-none focus-visible:ring-2 focus-visible:ring-marca-acento/40 ${
    activo ? 'border-marca-acento' : 'border-slate-200'
  }`

function Filtros({ peticionarios, proveedores, filtros, cambiar, limpiar }) {
  const activos = Object.values(filtros).some(Boolean)
  const id = useId()
  return (
    <form
      role="search"
      aria-label="Filtrar necesidades"
      className="mb-6 flex flex-wrap items-center gap-x-5 gap-y-3 text-sm text-slate-500"
      onSubmit={(e) => e.preventDefault()}
    >
      <div className="flex items-center gap-2">
        <label htmlFor={`${id}-texto`}>Buscar</label>
        <input
          id={`${id}-texto`}
          type="search"
          placeholder="Código, título o proyecto"
          className={`${claseControl(filtros.texto)} w-56`}
          value={filtros.texto}
          onChange={(e) => cambiar('texto', e.target.value)}
        />
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor={`${id}-estado`}>Estado</label>
        <select id={`${id}-estado`} className={claseControl(filtros.estado)} value={filtros.estado} onChange={(e) => cambiar('estado', e.target.value)}>
          <option value="">Todos</option>
          <option value={EN_CURSO}>En curso</option>
          {Object.entries(ESTADOS).map(([valor, texto]) => (
            <option key={valor} value={valor}>
              {texto}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor={`${id}-peticionario`}>Peticionario</label>
        <select
          id={`${id}-peticionario`}
          className={claseControl(filtros.peticionario)}
          value={filtros.peticionario}
          onChange={(e) => cambiar('peticionario', e.target.value)}
        >
          <option value="">Todos</option>
          {peticionarios.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nombre_completo}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor={`${id}-proveedor`}>Proveedor</label>
        <select id={`${id}-proveedor`} className={claseControl(filtros.proveedor)} value={filtros.proveedor} onChange={(e) => cambiar('proveedor', e.target.value)}>
          <option value="">Todos</option>
          {proveedores.map((p) => (
            <option key={p.id} value={p.id}>
              {p.nombre}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label htmlFor={`${id}-desde`}>Creada desde</label>
        <input
          id={`${id}-desde`}
          type="date"
          className={claseControl(filtros.desde)}
          value={filtros.desde}
          max={filtros.hasta || undefined}
          onChange={(e) => cambiar('desde', e.target.value)}
        />
        <label htmlFor={`${id}-hasta`}>hasta</label>
        <input
          id={`${id}-hasta`}
          aria-label="Creada hasta"
          type="date"
          className={claseControl(filtros.hasta)}
          value={filtros.hasta}
          min={filtros.desde || undefined}
          onChange={(e) => cambiar('hasta', e.target.value)}
        />
      </div>
      {activos && (
        <button type="button" className="font-medium text-marca-acento hover:underline" onClick={limpiar}>
          Quitar filtros
        </button>
      )}
    </form>
  )
}

export default function PaginaPanel() {
  const [necesidades, setNecesidades] = useState(null)
  const [error, setError] = useState(null)
  const navegar = useNavigate()
  const [parametros, setParametros] = useSearchParams()
  const filtros = Object.fromEntries(CAMPOS.map((c) => [c, parametros.get(c) ?? '']))

  function cambiar(campo, valor) {
    const nuevos = new URLSearchParams(parametros)
    if (valor) nuevos.set(campo, valor)
    else nuevos.delete(campo)
    // `replace`: cambiar un filtro no añade una entrada al historial del navegador.
    setParametros(nuevos, { replace: true })
  }

  useEffect(() => {
    let vigente = true
    listarNecesidades()
      .then((lista) => vigente && setNecesidades(lista))
      .catch((e) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [])

  // Los que aparecen en las necesidades (también los desactivados), de la A a la Z.
  const peticionarios = distintos((necesidades ?? []).map((n) => n.peticionario), 'nombre_completo')
  const proveedores = distintos((necesidades ?? []).map((n) => n.proveedor_adjudicado), 'nombre')
  const filtradas = (necesidades ?? []).filter((n) => cumple(n, filtros))
  const filtrando = filtradas.length !== necesidades?.length
  const enCurso = filtradas.filter((n) => !CERRADOS.includes(n.estado)).length

  return (
    <>
      <div className="mb-6">
        <h1 className="text-3xl font-normal md:text-4xl">Necesidades</h1>
        {necesidades?.length > 0 && (
          <p className="mt-1 text-sm text-slate-600" aria-live="polite">
            {filtrando
              ? `${filtradas.length} de ${necesidades.length} con estos filtros, ${enCurso} en curso.`
              : `${enCurso} en curso de ${necesidades.length}. La más reciente, primero.`}
          </p>
        )}
      </div>
      {necesidades?.length > 0 && (
        <Filtros
          peticionarios={peticionarios}
          proveedores={proveedores}
          filtros={filtros}
          cambiar={cambiar}
          limpiar={() => setParametros({}, { replace: true })}
        />
      )}
      {error && (
        <p role="alert" className="mb-4 text-sm text-red-700">
          {error}
        </p>
      )}
      {necesidades === null && !error && <p className="text-slate-600">Cargando…</p>}
      {necesidades?.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 px-6 py-12 text-center">
          <p className="text-slate-600">Todavía no hay necesidades.</p>
          <p className="mt-1 text-sm text-slate-500">Cuando se rompa una pieza, empieza con «Nueva necesidad».</p>
        </div>
      )}
      {necesidades?.length > 0 && filtradas.length === 0 && (
        <div className="rounded-lg border border-dashed border-slate-300 px-6 py-10 text-center text-slate-600">
          Ninguna necesidad cumple estos filtros. Cambia algún filtro o quítalos.
        </div>
      )}
      {filtradas.length > 0 && (
        <>
          {/* Escritorio: tabla; cada fila abre el detalle (el código es el enlace accesible). */}
          <table className="hidden w-full text-sm md:table">
            <thead>
              <tr className="border-b-2 border-marca-oscuro text-left">
                <th className="py-3 pr-4 font-medium">Código</th>
                <th className="py-3 pr-4 font-medium">Necesidad</th>
                <th className="py-3 pr-4 font-medium">Peticionario</th>
                <th className="py-3 pr-4 font-medium">Proveedor</th>
                <th className="py-3 pr-4 font-medium">Entrega prevista</th>
                <th className="py-3 font-medium">Estado</th>
              </tr>
            </thead>
            <tbody>
              {filtradas.map((n) => (
                <tr
                  key={n.id}
                  className="cursor-pointer border-b border-slate-200 align-top hover:bg-slate-50"
                  onClick={() => navegar(`/necesidades/${n.id}`, { state: { filtros: parametros.size ? `?${parametros}` : '' } })}
                >
                  <td className="py-4 pr-4">
                    <Link
                      className="font-medium text-marca-acento tabular-nums hover:underline focus-visible:outline-2 focus-visible:outline-marca-acento"
                      to={`/necesidades/${n.id}`}
                      state={{ filtros: parametros.size ? `?${parametros}` : '' }}
                      onClick={(e) => e.stopPropagation()}
                    >
                      {n.codigo}
                    </Link>
                  </td>
                  <td className="py-4 pr-4">
                    <p className="font-medium">{n.titulo}</p>
                    <p className="text-slate-600">{n.proyecto}</p>
                  </td>
                  <td className="py-4 pr-4">{n.peticionario.nombre_completo}</td>
                  <td className="py-4 pr-4">{n.proveedor_adjudicado?.nombre ?? <span className="text-slate-400">—</span>}</td>
                  <td className="py-4 pr-4 tabular-nums">{n.fecha_entrega_prevista ? fechaCorta(n.fecha_entrega_prevista) : '—'}</td>
                  <td className="py-4">
                    <Estado necesidad={n} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Móvil: una tarjeta por necesidad. */}
          <ul className="grid gap-3 md:hidden">
            {filtradas.map((n) => (
              <li key={n.id}>
                <Link
                  to={`/necesidades/${n.id}`}
                  state={{ filtros: parametros.size ? `?${parametros}` : '' }}
                  className="block rounded-lg border border-slate-200 p-4 hover:border-marca-acento focus-visible:outline-2 focus-visible:outline-marca-acento"
                >
                  <p className="text-sm font-medium text-marca-acento tabular-nums">{n.codigo}</p>
                  <p className="mt-1 font-medium">{n.titulo}</p>
                  <p className="text-sm text-slate-600">
                    {n.proyecto}, {n.peticionario.nombre_completo}
                    {n.proveedor_adjudicado && `. Proveedor: ${n.proveedor_adjudicado.nombre}`}
                  </p>
                  <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
                    <Estado necesidad={n} />
                    {n.fecha_entrega_prevista && (
                      <span className="text-sm text-slate-600">Entrega {fechaCorta(n.fecha_entrega_prevista)}</span>
                    )}
                  </div>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}
