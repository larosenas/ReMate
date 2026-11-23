# CU-003 — Gestionar las listas de proveedores, peticionarios y avisados

- **Objetivo:** mantener al día las personas y empresas con las que trabaja la aplicación, sin perder el histórico.
- **Actor principal:** Ingeniero (mantenimiento diario); administrador técnico (carga inicial)
- **Disparador:** hay un proveedor o una persona nueva, un dato cambia o alguien deja de usarse.
- **Paso del proceso:** apoyo a los pasos 1, 2 y 5
- **Prioridad:** Alta
- **Estado:** Implementado

## Precondiciones

- La base de datos está creada.

## Garantías

- **Si termina bien:** las listas reflejan el cambio y los desplegables de la aplicación muestran solo los registros activos.
- **Siempre:** las necesidades existentes conservan los nombres con los que se hicieron.

## Escenario principal: mantener las listas

1. El ingeniero abre las listas.
2. El sistema muestra tres listas, siempre de la A a la Z y por defecto solo con los registros activos:
   - **Proveedores:** nombre y correo.
   - **Peticionarios:** nombre, apellido y correo.
   - **Avisados del pedido:** nombre y correo de quienes reciben el aviso cuando hay que emitir el pedido en el ERP (CU-006).
3. El ingeniero añade un registro, edita el nombre o el correo de uno, o lo desactiva o reactiva.
4. El sistema valida los datos, guarda el cambio y lo muestra en su posición alfabética.

## Escenario alternativo: carga inicial

1. El administrador técnico prepara un archivo CSV, fuera del repositorio, con una línea por registro: `tipo;nombre;correo`, donde `tipo` es `proveedor` o `peticionario`.
2. Ejecuta `flask --app app cargar-listas <archivo.csv>`.
3. El sistema valida cada línea, crea los registros nuevos y omite los que ya existen (mismo correo), sin modificarlos.
4. El sistema muestra un resumen: creados, omitidos y líneas con error, con su número y el motivo.

Se puede ejecutar varias veces sin crear duplicados.

## Extensiones

- **3a. Alta desde otro caso de uso:** en la creación de la necesidad (CU-001) o en la solicitud de ofertas (CU-002) se puede dar de alta un peticionario o un proveedor sin salir de la pantalla, con las mismas validaciones. Queda elegido.
- **3b. Desactivar un registro que se usa en necesidades en curso:** se permite. Las necesidades no cambian; el registro solo deja de aparecer en los desplegables.
- **3c. Eliminar definitivamente:** solo un registro desactivado. El sistema pide un motivo de una lista (por ejemplo, «registro duplicado», «dado de alta por error» o «ya no trabaja en la empresa») o uno escrito. El registro deja de salir en todas las listas, sigue con su nombre en las necesidades antiguas y su correo queda libre.
- **3d. Eliminar un peticionario con necesidades en curso:** el sistema muestra cuáles son y obliga a elegir otro peticionario activo que las lleve. Cada necesidad registra el cambio en su historial y, si ya se había enviado el recordatorio de entrega (CU-009), se vuelve a enviar al nuevo.
- **4a. El correo ya existe:** no se crea un duplicado; el sistema muestra el registro que lo tiene y, si está inactivo, ofrece reactivarlo.
- **4b. El nombre se repite con otro correo:** se permite, pero el sistema avisa antes de guardar.
- **4c. Datos no válidos:** el sistema marca el campo y no guarda.
- **Carga 3a. Una línea del CSV está mal formada:** se informa con su número y se cargan las demás.

## Reglas de negocio

- **Orden:** de la A a la Z, sin distinguir mayúsculas y con las letras con tilde junto a su letra sin tilde («Ángel» junto a la «A»).
- **Correo:** obligatorio, con formato válido y único dentro de cada lista entre los registros no eliminados, sin distinguir mayúsculas. Se guarda en minúsculas y sin espacios en los extremos. Un solo correo por registro.
- El correo de los avisados no admite tildes ni «ñ»: la aplicación les envía correos, y un servidor sin SMTPUTF8 los rechazaría.
- **Nombre:** obligatorio, sin espacios sobrantes. El del proveedor se guarda tal como se escribe, porque es el que se usa en el ERP (CU-005).
- **Nada se borra de verdad:** primero se desactiva y después, si se quiere, se elimina con motivo; el registro se conserva para el histórico.
- Cambiar un correo no modifica los `.eml` ya generados.
- Los avisados se dan de alta desde la aplicación; la carga por CSV es solo para proveedores y peticionarios.

## Criterios de aceptación

- Con los proveedores «TORNIMEC», «Abedul» y «ÁBACO TEC», la lista muestra ÁBACO TEC, Abedul y TORNIMEC.
- Dar de alta un correo que ya existe, aunque cambien las mayúsculas, no crea otro registro y muestra el existente.
- Un correo sin «@» o con espacios intermedios se rechaza con un mensaje.
- Un proveedor desactivado no aparece en una necesidad nueva, pero sí en las antiguas en las que participó.
- La carga por CSV crea los registros, no crea duplicados al repetirla e informa de las líneas con error sin detenerse.
- Los avisados admiten alta, orden, detección de duplicados, desactivación y baja definitiva, igual que los proveedores.
- Las pruebas usan datos inventados.

## Trazabilidad

- **Diseño:** [modelo de datos](../diseno/modelo-de-datos.md) (Proveedor, Peticionario y AvisadoPedidoSap) y [API](../diseno/api.md) (listas maestras).
- **Código:** `backend/app/servicios/listas.py`, `backend/app/api/listas.py`, `backend/app/cli.py` (`cargar-listas`), `frontend/src/paginas/PaginaListas.jsx` y `frontend/src/componentes/TablaLista.jsx`.
- **Pruebas:** `backend/tests/test_listas_servicio.py`, `backend/tests/test_listas_api.py`, `backend/tests/test_cargar_listas.py`, `backend/tests/test_baja_peticionario.py` y `frontend/src/componentes/TablaLista.test.jsx`.
