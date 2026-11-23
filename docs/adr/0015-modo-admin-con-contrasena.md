# 0015 — Modo admin con contraseña

- **Estado:** Aceptada (revisada el 2026-11-17 y el 2026-11-20)
- **Fecha:** 2026-11-17
- **Relacionado con:** [0006](0006-despliegue-windows-sin-https.md) (sin HTTPS en la red interna), [0008](0008-registro-en-la-base-de-datos.md) (registro) y [0014](0014-caducidad-de-archivos-y-copias.md) (caducidad)

## Contexto y problema

El responsable técnico de la aplicación necesita borrar necesidades (de prueba, duplicadas o creadas por error), deshacer un paso hecho por equivocación, corregir datos que la aplicación ya no deja tocar, lanzar a mano las tareas diarias y ver el estado del servidor y el registro sin conectarse a la base de datos.

ReMate no tiene inicio de sesión: entra cualquiera de la red interna. El código de la interfaz se descarga entero en el navegador, así que cualquier atajo oculto lo puede descubrir cualquiera: no protege nada por sí solo.

## Decisión

- **Acceso:** un enlace discreto, «admin», a la derecha del pie de página, abre `/admin`, que pide la **contraseña**. Lo que protege es la contraseña, que comprueba el servidor; el enlace no protege nada (ver «Revisiones»).
- **Contraseña:** en el `.env` va solo su hash, `ADMIN_CLAVE_HASH`, generado con `flask --app app clave-admin` (Werkzeug, que ya viene con Flask: sin dependencias nuevas). Mínimo 12 caracteres. Sin `ADMIN_CLAVE_HASH`, el modo admin está desactivado. La contraseña no se guarda ni se registra; el hash se puede generar en otro equipo, para que la contraseña no pase por el servidor.
- **Sesión:** un token al azar en la memoria del servidor, en una cookie `HttpOnly` y `SameSite=Strict`, limitada a `/api/admin`. Caduca a los 30 minutos sin uso y al reiniciar el servicio, y solo vale en el navegador en el que se entró. La sesión se comprueba antes que el cuerpo de la petición, y los cambios pasan además por la comprobación de origen de `app/origen.py`.
- **Bloqueo:** tras 5 intentos fallidos seguidos desde un mismo equipo (por IP; detrás de un proxy inverso, la que este indica, [ADR 0016](0016-proxy-inverso-con-caddy.md)), ese equipo no puede intentarlo durante 15 minutos. Los intentos se comprueban uno a uno, también si llegan a la vez.
- **Herramientas** (`backend/app/api/admin.py` y `backend/app/servicios/admin.py`):
  - **Borrar una necesidad de verdad**, con todo lo suyo (ofertas, adjuntos y sus archivos, historial, retrasos y comentarios). Hay que escribir su código para confirmar. Sus retrasos y comentarios dejan de contar en el histórico del proveedor. **Su código no se vuelve a usar** (tabla `codigos_borrados`), porque los correos ya enviados con ese código apuntarían a otra necesidad.
  - **Deshacer el último paso:** vuelve al estado anterior, quita lo que guardó ese paso (por ejemplo, el `.eml` y la adjudicación) y borra su línea del historial. Hay que indicar el estado actual; si ya no lo es (otro «deshacer» a la vez o un reintento), responde 409 y no deshace otro paso. No se deshace la solicitud de ofertas si hay ofertas.
  - **Corregir** las fechas de entrega prevista y real, el número de pedido y el comentario de la entrega, con las mismas reglas que el flujo normal.
  - **Tareas a mano:** recordatorio de entrega, avisos del pedido y caducidad, primero en modo de prueba.
  - **Estado del servidor:** necesidades por estado, archivos y disco, última copia, consumo de la IA en 30 días y avisos y errores en 7 días.
  - **Registro:** los últimos mensajes de `logs`, por nivel.
- Todo lo que se hace queda en `logs`, con nivel WARNING.

## Alternativas consideradas

- **Solo un enlace o un atajo, sin contraseña:** cualquiera de la red podría borrar necesidades.
- **Usuarios y roles para toda la aplicación:** cambia toda la aplicación para un único administrador.
- **Sesión de Flask firmada (`SECRET_KEY`):** obliga a gestionar otra clave y no se puede cerrar desde el servidor; el token en memoria es más simple para un solo administrador.
- **Seguir con un cliente SQL y comandos:** más lento y propenso a errores al borrar en cascada.

## Consecuencias

- **Positivas:** las correcciones y los borrados se hacen sin tocar la base de datos a mano, con las mismas reglas que la aplicación y con registro. Sin dependencias nuevas.
- **Negativas:** sin HTTPS (ADR 0006), la contraseña viaja sin cifrar por la red interna al entrar. Borrar y deshacer no tienen vuelta atrás salvo restaurar una copia. Al reiniciar el servicio hay que volver a entrar.

## Revisiones

- **2026-11-17, revisión de seguridad:** el contador de intentos fallidos era común, así que cualquiera de la red podía bloquear al administrador con 5 contraseñas incorrectas. Ahora el contador y el bloqueo son por IP (`backend/app/admin_sesion.py`): un equipo bloqueado no bloquea a los demás. La tabla de IP se limita a 1000 entradas y se vacía de las que ya no están bloqueadas.
- **2026-11-20, enlace en el pie:** al principio se entraba con tres clics seguidos en el título (menos de 0,6 s entre ellos). Nadie lo descubría y, como el título lleva al panel, a veces navegaba en vez de abrir el modo admin. Se cambia por el enlace «admin» del pie (`frontend/src/App.jsx`), del mismo color tenue que el texto del pie, y el título solo lleva al panel. La seguridad no cambia: lo que protege es la contraseña.
