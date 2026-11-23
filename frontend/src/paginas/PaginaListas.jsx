// CU-003 — Pantalla de las listas: proveedores, peticionarios y avisados del pedido SAP.
import TablaLista from '../componentes/TablaLista.jsx'

// Motivos de la baja definitiva (además de «Otro», que escribe el usuario).
const MOTIVOS_PROVEEDOR = [
  'Ha cerrado o ya no presta este servicio',
  'Registro duplicado',
  'Dado de alta por error',
  'Compras ha decidido no trabajar más con él',
]
const MOTIVOS_PETICIONARIO = ['Ya no trabaja en la empresa', 'Ha cambiado de departamento', 'Registro duplicado', 'Dado de alta por error']
const MOTIVOS_AVISADO = ['Ya no se encarga de los pedidos en SAP', ...MOTIVOS_PETICIONARIO]

export default function PaginaListas() {
  return (
    <>
      <h1 className="mb-6 text-3xl font-normal md:text-4xl">Proveedores y peticionarios</h1>
      <div className="grid gap-6 lg:grid-cols-2">
        <TablaLista titulo="Proveedores" ruta="/api/proveedores" campoNombre="nombre" etiquetaNombre="Nombre" motivosBaja={MOTIVOS_PROVEEDOR} conRetrasos />
        <TablaLista
          titulo="Peticionarios"
          ruta="/api/peticionarios"
          campoNombre="nombre_completo"
          etiquetaNombre="Nombre y apellido"
          motivosBaja={MOTIVOS_PETICIONARIO}
        />
        {/* Reciben un correo al confirmar el paso 5 y un recordatorio cada semana hasta el paso 6. */}
        <div className="grid content-start gap-2">
          <TablaLista
            titulo="Avisados del pedido SAP"
            ruta="/api/avisados-pedido-sap"
            campoNombre="nombre"
            etiquetaNombre="Nombre y apellido"
            motivosBaja={MOTIVOS_AVISADO}
          />
          <p className="text-sm text-slate-600">
            Reciben un correo cuando se mete en SAP la solicitud de compra (paso 5) y un recordatorio cada semana
            mientras el pedido no se envíe al proveedor (paso 6).
          </p>
        </div>
      </div>
    </>
  )
}
