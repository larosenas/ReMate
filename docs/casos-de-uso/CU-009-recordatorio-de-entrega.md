# CU-009 — Enviar el recordatorio de entrega

- **Objetivo:** que el peticionario sepa con una semana de margen que llega su pedido, para comprobarlo con el proveedor.
- **Actor principal:** Sistema (tarea diaria del servidor)
- **Actores secundarios:** Ingeniero (peticionario, recibe el correo)
- **Disparador:** la ejecución diaria programada.
- **Paso del proceso:** 7. Entrega (la necesidad sigue en «Pendiente entrega»)
- **Prioridad:** Media
- **Estado:** Implementado

## Precondiciones

- El correo saliente está configurado (`SMTP_*`) y la tarea diaria está programada en el servidor ([ADR 0004](../adr/0004-swagger-y-recordatorio-de-entrega.md)).

## Garantías

- **Si termina bien:** cada necesidad que lo necesitaba tiene su recordatorio enviado y anotado.
- **Siempre:** un fallo con una necesidad no impide enviar las demás, y lo que no se envía se reintenta al día siguiente.

## Escenario principal

1. El planificador del servidor ejecuta una vez al día `flask --app app enviar-recordatorios`.
2. El sistema busca las necesidades en «Pendiente entrega» con la fecha prevista a 7 días o menos y sin recordatorio enviado.
3. Para cada una, envía por SMTP un correo al peticionario con el código, el título, el proyecto, el proveedor, el número de pedido y la fecha prevista, y un enlace a la necesidad.
4. El sistema anota la fecha y la hora del envío, que se ve en la necesidad.
5. El comando indica cuántos recordatorios ha enviado.

En la misma ejecución, el sistema reintenta los avisos a los avisados del pedido y envía su recordatorio semanal (CU-006), y aplica la caducidad de los archivos ([ADR 0014](../adr/0014-caducidad-de-archivos-y-copias.md)).

## Extensiones

- **2a. La fecha prevista ya pasó y no hubo recordatorio** (el servidor estuvo parado, por ejemplo): se envía igualmente.
- **3a. Falla el envío de un correo:** se registra el error, no se marca como enviado y se sigue con las demás. El comando termina con error para que se note en el planificador.
- **3b. El peticionario está desactivado o eliminado:** no se envía ni se marca, y el comando lo avisa cada día hasta que se reactiva a la persona o se confirma la entrega.
- **3c. El correo saliente no está configurado:** el comando no envía nada y lo explica.
- **Modo de prueba (`--prueba`):** en lugar de enviar, guarda cada correo como `.eml` en la carpeta de archivos y no marca nada. Sirve para probar sin servidor de correo.

## Reglas de negocio

- Un solo recordatorio por fecha prevista: si se registra un retraso (CU-008), el recordatorio se vuelve a enviar para la nueva fecha.
- Una necesidad entregada o cancelada no recibe recordatorios.
- «Hoy» es la fecha del servidor.
- Antes de cada envío se vuelve a comprobar la necesidad y se bloquea, para que un retraso, una entrega o dos ejecuciones simultáneas no se pisen.
- Con usuario de SMTP, la conexión tiene que ir cifrada (TLS). La salida del comando no muestra correos de personas.
- Plantilla fija, sin IA. El enlace solo se incluye si está configurada la dirección de la aplicación (`APP_URL`).
- Cada ejecución queda en el registro de la aplicación ([ADR 0008](../adr/0008-registro-en-la-base-de-datos.md)).

## Criterios de aceptación

- Con una fecha prevista a 8 días no se envía; a 7 días, sí.
- Al ejecutar el comando dos veces el mismo día, la segunda no envía nada.
- Tras registrar un retraso, el recordatorio se vuelve a enviar para la nueva fecha.
- Una necesidad entregada o cancelada no recibe recordatorio.
- Si falla un envío, no se marca como enviado y el resto sigue.
- Con `--prueba`, los correos se guardan como `.eml` y no se marca nada.
- Las pruebas automáticas usan un servidor de correo simulado.

## Trazabilidad

- **Diseño:** [ADR 0004](../adr/0004-swagger-y-recordatorio-de-entrega.md) (tarea programada y SMTP).
- **Código:** `backend/app/servicios/recordatorios.py`, `backend/app/integraciones/correo_saliente.py`, `backend/app/cli.py` y `scripts/windows/enviar-recordatorios.ps1`.
- **Pruebas:** `backend/tests/test_recordatorios.py` y `frontend/src/paginas/PaginaNecesidad.test.jsx`.
