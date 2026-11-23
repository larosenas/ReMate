# 0008 — Registro de la aplicación (logs) en la base de datos

- **Estado:** Aceptada. El punto 3 está cambiado por [0014](0014-caducidad-de-archivos-y-copias.md): la tabla guarda 6 meses
- **Fecha:** 2026-11-03
- **Relacionado con:** [0006](0006-despliegue-windows-sin-https.md) (despliegue en Windows Server)

## Contexto y problema

El registro de la aplicación iba a archivos de texto: `remate.log` (la salida de Waitress) y `recordatorios.log` (el recordatorio diario). Al revisarlo antes de instalar salieron dos problemas:

- **Se perdía información.** Flask solo deja pasar avisos y errores si no se configura otra cosa, así que los mensajes de información («Necesidad creada: …», «Oferta subida…») nunca llegaban al archivo.
- **Los archivos crecían sin límite** y no caducaban.

Quien administra el servidor consulta el registro con un cliente SQL conectado a PostgreSQL.

## Decisión

1. **El registro va a la base de datos**, a la tabla `logs`: fecha y hora, nivel (`INFO`, `WARNING`, `ERROR`, `CRITICAL`), origen (el módulo, por ejemplo `app.integraciones.ia`), mensaje y traza del error si la hay.
2. **Desde el nivel de información** (`INFO`), para toda la aplicación, también el recordatorio diario.
3. **No caduca.** Son unos pocos miles de filas al año, y entran en las copias de la base de datos.
4. **Las peticiones no escriben en la base de datos:** dejan el mensaje en una cola (hasta 10 000) y siguen. Un hilo aparte lo guarda con su propia conexión, fuera de la transacción de la petición (así queda guardado también el error de una petición que se deshace), y con tiempos máximos: 5 s para conectar, 2 s esperando un bloqueo y 5 s por consulta. Una base de datos lenta, caída o con la tabla bloqueada no detiene la aplicación. Si la cola se llena o no se puede guardar, el mensaje va al respaldo.
5. **Respaldo en archivo:** lo que no se puede guardar en la base de datos (no responde, la tabla no existe, falta configuración al arrancar, fallos de Waitress o de Python fuera de la aplicación) va a `remate.log` o `recordatorios.log`, con fecha, hora y motivo. Los escribe Python en UTF-8 (`app/a_archivo.py`), no la redirección de PowerShell 5.1, que escribe en UTF-16. El logger de la aplicación no pasa al raíz, para que Waitress no repita cada mensaje en el archivo.
6. **Sin datos sensibles:** códigos de necesidad e identificadores, nunca importes ni datos de las ofertas. Los errores de la base de datos no llevan los valores de la consulta (`hide_parameters=True`), y en la traza el texto de cada error de PostgreSQL se sustituye por su código SQLSTATE y la restricción, porque su `DETAIL` podía repetir el valor (por ejemplo, un correo duplicado). Al parar, se espera como mucho 20 s a que se vacíe la cola. Los caracteres que PostgreSQL no admite se escapan.
7. **En desarrollo** (`APP_ENV=development`) los mensajes salen también por la consola.
8. **El recordatorio diario** deja en la tabla un resumen de cada ejecución (enviados, omitidos y fallidos, solo con códigos).

## Alternativas consideradas

- **Solo archivos, con rotación y caducidad en los scripts:** más simple, pero obliga a buscar en archivos de texto.
- **Solo base de datos, sin archivo:** los errores más graves (la base de datos caída, el arranque) no quedarían en ningún sitio.
- **El Visor de eventos de Windows:** exige registrar un origen de eventos con permisos de administrador y es incómodo de filtrar por necesidad.

## Consecuencias

- **Positivas:** todo el registro en un sitio, consultable con SQL (por fecha, nivel u origen); se guarda también la información; no hay archivos que crezcan sin control; entra en las copias.
- **Negativas:** una escritura en la base de datos por mensaje, en un hilo aparte; si la aplicación se cae de golpe, se pueden perder los mensajes que estuvieran en la cola; ante una caída de la base de datos hay dos sitios que mirar; quien consulta la tabla necesita acceso a PostgreSQL (mejor con un usuario de solo lectura).
- Las migraciones de Alembic no desactivan los loggers existentes (`disable_existing_loggers=False`); si no, en las pruebas el registro dejaba de guardar después de probar las migraciones.

## Trazabilidad

`backend/app/registro.py` (la cola y el manejador), `backend/app/a_archivo.py` (respaldo en archivo), `backend/app/modelos/logs.py` y `backend/tests/test_registro.py`.

## Revisiones

- **2026-11-04:** la tabla pasa a llamarse `logs` (se creó como `registros`), sin perder los mensajes. Con el [ADR 0009](0009-servicio-windows-con-winsw.md), la aplicación la arranca el servicio de Windows con `python -m app.servir --log <ruta>`, que usa el mismo respaldo en UTF-8.
- **2026-11-17:** la tabla guarda 6 meses; la tarea diaria borra lo anterior ([ADR 0014](0014-caducidad-de-archivos-y-copias.md)).
