// CU-010 — Histórico de retrasos de un proveedor: pedidos adjudicados, retraso medio por pedido,
// cuántos con retraso y cada retraso con su necesidad (del más reciente al más antiguo).
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { obtenerRetrasosProveedor } from '../api/listas.js'
import { SinEfecto } from '../componentes/SeccionEntrega.jsx'
import { diasMedios, fechaCorta, fechaHora, porcentajeConRetraso } from '../formatos.js'
import { esId } from '../rutas.js'

export default function PaginaRetrasosProveedor() {
  const { id } = useParams()
  if (!esId(id)) return <p className="text-slate-600">Esta pantalla no existe.</p>
  return <Historico key={id} id={id} />
}

function Historico({ id }) {
  const [datos, setDatos] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let vigente = true
    obtenerRetrasosProveedor(id)
      .then((respuesta) => vigente && setDatos(respuesta))
      .catch((e) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [id])

  if (error)
    return (
      <p role="alert" className="text-red-700">
        {error}
      </p>
    )
  if (!datos) return <p className="text-slate-600">Cargando…</p>

  // Lo que cuenta es el retraso medio por pedido, junto con la proporción.
  const cifras = [
    ['Retraso medio por pedido', datos.pedidos ? diasMedios(datos.retraso_medio, datos.con_retraso > 0) : '—'],
    ['Pedidos con retraso', datos.pedidos ? `${datos.con_retraso} de ${datos.pedidos} (${porcentajeConRetraso(datos)} %)` : '—'],
    ['Pedidos adjudicados', datos.pedidos],
  ]

  return (
    <div className="grid gap-8">
      <header>
        <Link to="/listas" className="text-sm text-slate-600 hover:text-marca-acento hover:underline">
          Proveedores y peticionarios
        </Link>
        <h1 className="mt-1 text-3xl font-normal md:text-4xl">Retrasos de {datos.proveedor.nombre}</h1>
        <p className="mt-1 text-sm text-slate-600">{datos.proveedor.email}</p>
      </header>

      <dl className="grid max-w-2xl grid-cols-3 gap-px overflow-hidden rounded-lg border border-slate-200 bg-slate-200">
        {cifras.map(([etiqueta, valor]) => (
          <div key={etiqueta} className="bg-white p-4">
            <dt className="text-sm text-slate-500">{etiqueta}</dt>
            <dd className="mt-1 text-2xl tabular-nums">{valor}</dd>
          </div>
        ))}
      </dl>

      <section aria-labelledby="titulo-retrasos">
        <h2 id="titulo-retrasos" className="mb-3 text-xl font-normal">
          Retrasos
        </h2>
        {datos.retrasos.length === 0 ? (
          <p className="text-sm text-slate-600">
            {datos.pedidos ? 'Ningún pedido de este proveedor ha tenido retrasos.' : 'Todavía no se le ha adjudicado ningún pedido.'}
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-160 text-sm">
              <thead>
                <tr className="border-b-2 border-marca-oscuro text-left">
                  <th className="py-3 pr-4 font-medium">Necesidad</th>
                  <th className="py-3 pr-4 font-medium">Fecha anterior</th>
                  <th className="py-3 pr-4 font-medium">Fecha nueva</th>
                  <th className="py-3 pr-4 text-right font-medium">Días</th>
                  <th className="py-3 pr-4 font-medium">Motivo</th>
                  <th className="py-3 font-medium">Registrado</th>
                </tr>
              </thead>
              <tbody>
                {datos.retrasos.map((r) => (
                  <tr key={`${r.necesidad.id}-${r.registrado_en}`} className="border-b border-slate-200 align-top">
                    <td className="py-3 pr-4">
                      <Link className="font-medium text-marca-acento tabular-nums hover:underline" to={`/necesidades/${r.necesidad.id}`}>
                        {r.necesidad.codigo}
                      </Link>
                      <p className="text-slate-600">{r.necesidad.titulo}</p>
                    </td>
                    <td className="py-3 pr-4 tabular-nums">{fechaCorta(r.fecha_anterior)}</td>
                    <td className="py-3 pr-4 tabular-nums">{fechaCorta(r.fecha_nueva)}</td>
                    <td className={`py-3 pr-4 text-right tabular-nums ${r.sin_efecto ? 'text-slate-500 line-through' : ''}`}>{r.dias}</td>
                    <td className="py-3 pr-4">
                      {r.motivo}
                      {r.sin_efecto && <SinEfecto />}
                    </td>
                    <td className="py-3 text-slate-600">
                      {fechaHora(r.registrado_en)}
                      <span className="block">{r.peticionario}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Lo que escribió el ingeniero al confirmar la entrega de sus pedidos. */}
      <section aria-labelledby="titulo-comentarios">
        <h2 id="titulo-comentarios" className="mb-3 text-xl font-normal">
          Comentarios de las entregas
        </h2>
        {!datos.comentarios?.length ? (
          <p className="text-sm text-slate-600">No hay comentarios de las entregas de este proveedor.</p>
        ) : (
          <ul className="grid max-w-3xl gap-3 text-sm">
            {datos.comentarios.map((c) => (
              <li key={c.necesidad_id} className="border-b border-slate-200 pb-3">
                <Link className="font-medium text-marca-acento tabular-nums hover:underline" to={`/necesidades/${c.necesidad_id}`}>
                  {c.codigo}
                </Link>{' '}
                <span className="text-slate-600">
                  {c.titulo} · entregado el {fechaCorta(c.fecha)}
                </span>
                <p className="mt-1 whitespace-pre-line">{c.texto}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
