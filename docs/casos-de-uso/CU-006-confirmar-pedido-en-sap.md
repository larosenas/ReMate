# CU-006 — Confirmar la solicitud en el ERP

- **Objetivo:** dejar constancia de que la solicitud de compra ya está en el ERP (SAP), con la fecha de entrega prevista, y avisar a quien tiene que emitir el pedido.
- **Actor principal:** Ingeniero (peticionario)
- **Actores secundarios:** Avisados del pedido (reciben el aviso), Sistema (tarea diaria, repite el aviso)
- **Disparador:** el ingeniero ha metido en el ERP el texto y la tabla preparados en CU-005.
- **Paso del proceso:** 5. Pedido en el ERP → «Pendiente pedido SAP»
- **Prioridad:** Alta
- **Estado:** Implementado

## Precondiciones

- La necesidad está en «Pendiente solicitud SAP» (CU-005).

## Garantías

- **Si termina bien:** la necesidad está en «Pendiente pedido SAP», con la fecha de entrega prevista, y los avisados han recibido el aviso.
- **Siempre:** si el aviso no se puede enviar, el paso se confirma igual y el aviso se reintenta.

## Escenario principal

1. El ingeniero confirma que la solicitud está en el ERP.
2. El sistema propone como fecha de entrega prevista la fecha de entrega inicial.
3. El ingeniero la confirma o la cambia (por ejemplo, si el proveedor ha dado otra fecha) e indica quién confirma.
4. El sistema guarda la fecha de entrega prevista, pasa la necesidad a «Pendiente pedido SAP» y registra el cambio de estado.
5. El sistema envía por correo a los avisados activos (CU-003) el aviso de que hay que emitir el pedido y enviarlo al proveedor, con el proveedor, la fecha prevista, el peticionario, quién confirmó y el enlace a la necesidad.
6. El sistema muestra cuándo se envió el aviso.

## Extensiones

- **2a. La oferta dio un plazo y no una fecha:** se propone ese plazo contado desde hoy, y la pantalla lo explica.
- **3a. Sin fecha, o con una fecha anterior a la creación de la necesidad:** el sistema no confirma y lo explica.
- **5a. No hay avisados o el correo falla:** el paso se confirma igual; el sistema lo dice y la tarea diaria lo reintenta cada mañana (CU-009).
- **5b. El servidor de correo rechaza a algún destinatario:** el sistema indica cuántos, sin mostrar sus direcciones.
- **Recordatorio semanal:** mientras la necesidad siga en este paso, la tarea diaria repite el aviso cada 7 días desde el último, indicando cuántos días lleva pendiente. Deja de enviarse al enviar el pedido al proveedor (CU-007).

## Reglas de negocio

- El cambio de fecha de este paso no cuenta como retraso: la diferencia queda entre la fecha de entrega inicial y la prevista. Los retrasos solo se registran en el paso 7 (CU-008).
- La fecha de entrega prevista es la referencia del recordatorio (CU-009) y de los retrasos (CU-008).
- El aviso usa una plantilla fija, sin IA, con el asunto común de la necesidad. El enlace solo se incluye si está configurada la dirección de la aplicación (`APP_URL`).
- Antes de enviar, la necesidad se bloquea y se vuelve a leer, para que dos envíos simultáneos no repitan el aviso.
- La espera al servidor de correo tiene un tiempo máximo, para no bloquear la pantalla.

## Criterios de aceptación

- Se propone la fecha de entrega inicial; si la oferta dio un plazo, ese plazo contado desde el día de la confirmación.
- Al confirmar con otra fecha, se guarda la nueva fecha prevista y la inicial no cambia.
- Sin fecha no se confirma, y solo se puede confirmar desde «Pendiente solicitud SAP».
- Al confirmar se avisa a los avisados activos, con el enlace a la necesidad.
- Sin avisados o sin correo configurado, se confirma igual, se dice y la tarea diaria lo reintenta.
- El aviso se repite cada 7 días hasta el envío del pedido, y nunca dos veces por ejecuciones simultáneas.

## Trazabilidad

- **Diseño:** [estados de una necesidad](../diseno/estados-necesidad.md) y [API](../diseno/api.md).
- **Código:** `backend/app/servicios/necesidades.py` (confirmación), `backend/app/servicios/avisos_pedido_sap.py`, `backend/app/integraciones/correo_saliente.py` y `frontend/src/componentes/ConfirmarPedidoSap.jsx`.
- **Pruebas:** `backend/tests/test_pedido_sap.py`, `backend/tests/test_avisos_pedido_sap.py` y `frontend/src/componentes/ConfirmarPedidoSap.test.jsx`.
