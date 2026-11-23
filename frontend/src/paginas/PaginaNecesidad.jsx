// Detalle de una necesidad: datos, adjuntos, historial de estados y el paso que toca
// (CU-002 «Solicitar ofertas», CU-004 «Ofertas», CU-005, CU-006, CU-007 «Pedido SAP» y CU-008
// «Entrega»).
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router'
import { obtenerNecesidad, urlAdjunto, urlSolicitudEml } from '../api/necesidades.js'
import { urlPedidoEml } from '../api/pedidoSap.js'
import CancelarNecesidad from '../componentes/CancelarNecesidad.jsx'
import ConfirmarPedidoSap from '../componentes/ConfirmarPedidoSap.jsx'
import Desplegable from '../componentes/Desplegable.jsx'
import EnviarPedidoSap from '../componentes/EnviarPedidoSap.jsx'
import EtiquetaEstado from '../componentes/EtiquetaEstado.jsx'
import InformacionSap from '../componentes/InformacionSap.jsx'
import PistaProceso from '../componentes/PistaProceso.jsx'
import ResumenOfertas from '../componentes/ResumenOfertas.jsx'
import SeccionEntrega, { ListaRetrasos } from '../componentes/SeccionEntrega.jsx'
import SeccionOfertas from '../componentes/SeccionOfertas.jsx'
import SolicitarOfertas from '../componentes/SolicitarOfertas.jsx'
import { enfocarTitulo, llevarA, subirArriba } from '../desplazamiento.js'
import { ESTADOS, estadoAntesDeCancelar } from '../estados.js'
import { esId } from '../rutas.js'
import { fechaCorta, fechaHora } from '../formatos.js'
import EnlaceArchivo from '../componentes/EnlaceArchivo.jsx'

// Cambios de estado y de peticionario (al dar de baja al anterior), por orden de fecha.
function historialCompleto(necesidad) {
  return [...necesidad.historial, ...(necesidad.cambios_peticionario ?? [])].sort(
    (a, b) => new Date(a.cambiado_en) - new Date(b.cambiado_en),
  )
}

// La clave hace que, al pasar de una necesidad a otra, la pantalla empiece de cero (sin mostrar
// la anterior ni un error antiguo mientras carga).
export default function PaginaNecesidad() {
  const { id } = useParams()
  if (!esId(id)) return <p className="text-slate-600">Esta pantalla no existe.</p>
  return <DetalleNecesidad key={id} id={id} />
}

function DetalleNecesidad({ id }) {
  // Si se llegó desde el panel, «Necesidades» vuelve con los mismos filtros.
  const filtrosDelPanel = useLocation().state?.filtros ?? ''
  const [necesidad, setNecesidad] = useState(null)
  const [error, setError] = useState(null)

  const cargar = useCallback(() => obtenerNecesidad(id).then(setNecesidad), [id])

  useEffect(() => {
    let vigente = true
    obtenerNecesidad(id)
      .then((datos) => vigente && setNecesidad(datos))
      .catch((e) => vigente && setError(e.message))
    return () => {
      vigente = false
    }
  }, [id])

  // El paso que toca: al entrar se baja hasta él y, al pasar al siguiente, se baja hasta el nuevo
  // y se lleva allí el foco. Al entregarla o cancelarla se vuelve arriba y el foco va al título
  // (el botón pulsado desaparece).
  const pasoActivo = useRef(null)
  const titulo = useRef(null)
  const estadoVisto = useRef(null)
  useEffect(() => {
    if (!necesidad) return
    const antes = estadoVisto.current
    estadoVisto.current = necesidad.estado
    if (antes === necesidad.estado) return
    if (['entregado', 'cancelada'].includes(necesidad.estado)) {
      if (antes) {
        subirArriba()
        enfocarTitulo(titulo.current)
      }
      return
    }
    llevarA(pasoActivo.current, { enfocar: antes !== null })
  }, [necesidad])

  // Tras un cambio (adjuntos nuevos, solicitud generada) se usa la necesidad devuelta o se recarga.
  async function actualizada(datos) {
    if (datos) setNecesidad(datos)
    else await cargar()
  }

  if (error) {
    return (
      <p role="alert" className="text-red-700">
        {error}
      </p>
    )
  }
  if (!necesidad) return <p className="text-slate-600">Cargando…</p>

  const cerrada = ['entregado', 'cancelada'].includes(necesidad.estado)
  const datos = [
    ['Código', necesidad.codigo],
    ['Proyecto', necesidad.proyecto],
    ['Peticionario', necesidad.peticionario.nombre_completo],
    ['Creada', fechaHora(necesidad.creada_en)],
    necesidad.fecha_entrega_prevista && [
      'Entrega prevista',
      <>
        {fechaCorta(necesidad.fecha_entrega_prevista)}
        {necesidad.fecha_entrega_inicial && necesidad.fecha_entrega_inicial !== necesidad.fecha_entrega_prevista && (
          <span className="block text-xs text-slate-500">La oferta decía {fechaCorta(necesidad.fecha_entrega_inicial)}</span>
        )}
      </>,
    ],
    necesidad.fecha_entrega_real && ['Entregado el', fechaCorta(necesidad.fecha_entrega_real)],
    necesidad.numero_pedido_sap && ['Pedido SAP', necesidad.numero_pedido_sap],
    // CU-009: recordatorio al peticionario una semana antes de la entrega prevista.
    necesidad.estado === 'pendiente_entrega' && [
      'Recordatorio de entrega',
      necesidad.recordatorio_enviado_en ? `Enviado el ${fechaHora(necesidad.recordatorio_enviado_en)}` : 'Se enviará una semana antes',
    ],
  ].filter(Boolean)

  // Envuelve el paso que toca (solo hay uno a la vez).
  const paso = (contenido) => (
    <div ref={pasoActivo} className="scroll-mt-6">
      {contenido}
    </div>
  )

  return (
    <div className="grid grid-cols-1 gap-8">
      <header className="grid gap-5">
        <div>
          <Link to={`/${filtrosDelPanel}`} className="text-sm text-slate-600 hover:text-marca-acento hover:underline">
            Necesidades
          </Link>
          <h1 ref={titulo} className="mt-1 text-3xl font-normal text-balance md:text-4xl">
            {necesidad.titulo}
          </h1>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
            <span className="font-medium text-marca-acento tabular-nums">{necesidad.codigo}</span>
            <EtiquetaEstado estado={necesidad.estado} texto={necesidad.estado_texto} />
          </div>
        </div>
        <PistaProceso estado={necesidad.estado} estadoPrevio={estadoAntesDeCancelar(necesidad.historial)} />
        {necesidad.motivo_cancelacion && (
          <p className="rounded-lg border-l-4 border-slate-400 bg-slate-100 px-4 py-3 text-sm">
            <span className="font-medium">Motivo de la cancelación:</span> {necesidad.motivo_cancelacion}
          </p>
        )}
      </header>

      <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,1fr)_18rem]">
        <div className="grid min-w-0 grid-cols-1 gap-5">
        {/* Los pasos ya hechos empiezan plegados; la clave hace que se vuelvan a plegar al
            cambiar de estado. */}
        <Desplegable
          key={`necesidad-${necesidad.estado}`}
          titulo="1. Necesidad"
          resumen={`${necesidad.adjuntos.length} adjunto${necesidad.adjuntos.length === 1 ? '' : 's'}`}
          abiertoAlInicio={necesidad.estado === 'necesidad_creada'}
        >
          <h2 className="mb-2 font-medium">Descripción</h2>
          <p className="whitespace-pre-wrap text-sm">{necesidad.descripcion}</p>
          {necesidad.adjuntos.length > 0 && (
            <>
              <h2 className="mt-5 mb-2 font-medium">Adjuntos</h2>
              <ul className="grid gap-1 text-sm">
                {necesidad.adjuntos.map((a) => (
                  <li key={a.id}>
                    <EnlaceArchivo archivo={a} className="text-marca-acento hover:underline" href={urlAdjunto(necesidad.id, a.id)}>
                      {a.nombre_archivo}
                    </EnlaceArchivo>
                  </li>
                ))}
              </ul>
            </>
          )}
        </Desplegable>

        {necesidad.estado === 'necesidad_creada' && paso(<SolicitarOfertas necesidad={necesidad} onActualizada={actualizada} />)}

        {necesidad.solicitud_eml && (
          <Desplegable
            key={`solicitud-${necesidad.estado}`}
            titulo="2. Solicitud de ofertas"
            resumen={necesidad.proveedores_solicitados.map((p) => p.nombre).join(', ')}
          >
            <p className="text-sm">
              Abre el archivo con Outlook y envíalo. Proveedores en copia oculta:{' '}
              {necesidad.proveedores_solicitados.map((p) => p.nombre).join(', ')}.
            </p>
            <div className="mt-3 text-sm">
              <EnlaceArchivo
                archivo={necesidad.solicitud_eml}
                className="inline-block rounded bg-marca-acento px-4 py-2 font-medium text-white shadow hover:bg-marca-acento-oscuro"
                href={urlSolicitudEml(necesidad.id)}
              >
                Descargar el .eml
              </EnlaceArchivo>
            </div>
          </Desplegable>
        )}

        {['en_cotizacion', 'en_evaluacion'].includes(necesidad.estado) && (
          paso(<SeccionOfertas necesidad={necesidad} onActualizada={actualizada} />)
        )}

        {/* Pasada la evaluación, el paso 3 queda plegado y solo para consultar. */}
        {necesidad.solicitud_eml && !['en_cotizacion', 'en_evaluacion'].includes(necesidad.estado) && (
          <Desplegable key={`ofertas-${necesidad.estado}`} titulo="3. Ofertas">
            <ResumenOfertas necesidad={necesidad} />
          </Desplegable>
        )}

        {necesidad.oferta_adjudicada_id && (
          <Desplegable
            key={`sap-${necesidad.estado}`}
            titulo="4. Adjudicación e información para SAP"
            abiertoAlInicio={necesidad.estado === 'pendiente_solicitud_sap'}
          >
            <InformacionSap necesidad={necesidad} />
          </Desplegable>
        )}

        {necesidad.estado === 'pendiente_solicitud_sap' && paso(<ConfirmarPedidoSap necesidad={necesidad} onConfirmado={actualizada} />)}

        {/* Paso 5 ya hecho: la fecha confirmada al meter el pedido en SAP. */}
        {necesidad.fecha_entrega_prevista && necesidad.estado !== 'pendiente_solicitud_sap' && (
          <Desplegable key={`sap5-${necesidad.estado}`} titulo="5. Pedido en SAP" resumen="Pedido metido en SAP">
            <p className="text-sm">
              Pedido metido en SAP. Entrega prevista: {fechaCorta(necesidad.fecha_entrega_prevista)}
              {necesidad.fecha_entrega_inicial && necesidad.fecha_entrega_inicial !== necesidad.fecha_entrega_prevista
                ? ` (la oferta decía ${fechaCorta(necesidad.fecha_entrega_inicial)}).`
                : '.'}
            </p>
          </Desplegable>
        )}

        {necesidad.estado === 'pendiente_pedido_sap' && paso(<EnviarPedidoSap necesidad={necesidad} onEnviado={actualizada} />)}

        {necesidad.pedido_sap_eml && (
          <Desplegable
            key={`pedido-${necesidad.estado}`}
            titulo="6. Pedido al proveedor"
            resumen={necesidad.numero_pedido_sap ? `Pedido ${necesidad.numero_pedido_sap}` : undefined}
          >
            <p className="text-sm">
              {necesidad.numero_pedido_sap && (
                <>
                  <span className="font-medium">Número de pedido:</span> {necesidad.numero_pedido_sap}.{' '}
                </>
              )}
              <span className="font-medium">Pedido:</span>{' '}
              <EnlaceArchivo
                archivo={necesidad.pedido_sap}
                className="text-marca-acento hover:underline"
                href={urlAdjunto(necesidad.id, necesidad.pedido_sap.id)}
              >
                {necesidad.pedido_sap.nombre_archivo}
              </EnlaceArchivo>
            </p>
            <p className="mt-2 text-sm">Abre el correo con Outlook y envíalo al proveedor si aún no lo has hecho.</p>
            <div className="mt-3 text-sm">
              <EnlaceArchivo
                archivo={necesidad.pedido_sap_eml}
                className="inline-block rounded bg-marca-acento px-4 py-2 font-medium text-white shadow hover:bg-marca-acento-oscuro"
                href={urlPedidoEml(necesidad.id)}
              >
                Descargar el .eml del pedido
              </EnlaceArchivo>
            </div>
          </Desplegable>
        )}

        {necesidad.estado === 'pendiente_entrega' && paso(<SeccionEntrega necesidad={necesidad} onActualizada={actualizada} />)}

        {/* Entregada (o cancelada después de algún retraso): el paso 7 queda para consultar. */}
        {(necesidad.fecha_entrega_real || (necesidad.estado === 'cancelada' && necesidad.retrasos.length > 0)) && (
          <Desplegable
            key={`entrega-${necesidad.estado}`}
            titulo="7. Entrega"
            resumen={necesidad.fecha_entrega_real ? `Entregado el ${fechaCorta(necesidad.fecha_entrega_real)}` : undefined}
            abiertoAlInicio={necesidad.estado === 'entregado'}
          >
            {necesidad.fecha_entrega_real && (
              <p className="mb-3 text-sm">
                <span className="font-medium">Entregado el</span> {fechaCorta(necesidad.fecha_entrega_real)}
              </p>
            )}
            {necesidad.comentario_entrega && (
              <p className="mb-3 text-sm whitespace-pre-line">
                <span className="font-medium">Comentarios de la entrega:</span> {necesidad.comentario_entrega}
              </p>
            )}
            <h3 className="mb-2 font-medium">Retrasos</h3>
            <ListaRetrasos retrasos={necesidad.retrasos} />
          </Desplegable>
        )}
        </div>

        <aside className="grid gap-6 lg:sticky lg:top-6">
          <section className="rounded-lg border border-slate-200 p-5">
            <h2 className="mb-3 text-lg font-normal">Datos</h2>
            <dl className="grid gap-3 text-sm">
              {datos.map(([etiqueta, valor]) => (
                <div key={etiqueta}>
                  <dt className="text-slate-500">{etiqueta}</dt>
                  <dd className="font-medium">{valor}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="rounded-lg border border-slate-200 p-5" aria-labelledby="titulo-historial">
            <h2 id="titulo-historial" className="mb-3 text-lg font-normal">
              Historial
            </h2>
            <ol className="grid gap-3 border-l-2 border-slate-200 pl-4 text-sm">
              {historialCompleto(necesidad).map((c, i) => (
                <li key={i} className="relative">
                  <span className="absolute top-1.5 -left-[1.3rem] size-2 rounded-full bg-marca-acento" aria-hidden="true" />
                  {c.peticionario_nuevo ? (
                    <>
                      <p className="font-medium">
                        Cambio de peticionario: de {c.peticionario_anterior.nombre_completo} a {c.peticionario_nuevo.nombre_completo}
                      </p>
                      <p className="text-xs text-slate-500">
                        {fechaHora(c.cambiado_en)}, por la baja de {c.peticionario_anterior.nombre_completo}
                      </p>
                    </>
                  ) : (
                    <>
                      <p className="font-medium">{ESTADOS[c.estado_nuevo] ?? c.estado_nuevo}</p>
                      <p className="text-xs text-slate-500">
                        {fechaHora(c.cambiado_en)}, {c.peticionario.nombre_completo}
                      </p>
                    </>
                  )}
                </li>
              ))}
            </ol>
          </section>

          {!cerrada && <CancelarNecesidad necesidad={necesidad} onCancelada={actualizada} />}
        </aside>
      </div>
    </div>
  )
}
