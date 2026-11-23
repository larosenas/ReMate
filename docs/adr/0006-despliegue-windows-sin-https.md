# 0006 — Despliegue en Windows Server, sin HTTPS, con Waitress y el Programador de tareas

- **Estado:** Aceptada. El arranque de la aplicación (punto 3) y la cuenta de ejecución (punto 4) están sustituidos por [0009](0009-servicio-windows-con-winsw.md). La forma de entrar, completada por [0016](0016-proxy-inverso-con-caddy.md) (proxy inverso opcional)
- **Fecha:** 2026-10-29 (completada el 2026-11-03)
- **Relacionado con:** [0003](0003-stack-react-tailwind-python-sqlalchemy.md) (stack), [0004](0004-swagger-y-recordatorio-de-entrega.md) (Flask sirve el frontend y el recordatorio diario)

## Contexto y problema

Hay que preparar la instalación en producción antes de tener el servidor. Se fija sobre qué se instalará:

- **Sistema operativo:** Windows Server, el habitual en la organización. El desarrollo también se hace en Windows.
- **Sin HTTPS.** Es una aplicación interna a la que se entra por `http://<servidor>:2905` desde la red interna, sin certificado.

Flask trae un servidor solo para desarrollo. En producción hace falta un **servidor WSGI** que funcione en Windows, y algo que lo mantenga en marcha y lo arranque con el servidor. Gunicorn, el más usado en Linux, no funciona en Windows.

## Decisión

1. **Windows Server, sin HTTPS.** El puerto queda abierto **solo a la red interna** con una regla del cortafuegos de Windows limitada a su subred. Riesgo aceptado: los datos viajan sin cifrar dentro de la red interna.
2. **Waitress** como servidor WSGI: Python puro, funciona en Windows, lo mantiene el proyecto Pylons y tiene licencia ZPL 2.1. Probado con ReMate: sirve la API y la interfaz en el mismo puerto. Se instala con `requirements.txt`.
3. **El Programador de tareas de Windows** lo mantiene en marcha, sin software adicional:
   - una tarea que arranca la aplicación al iniciar el servidor y la reinicia si termina;
   - una tarea diaria a las 9:00 para el recordatorio (`flask enviar-recordatorios`);
   - otra para la copia de seguridad (`scripts/windows/copia-de-seguridad.ps1`).
4. **Una cuenta local sin privilegios de administrador** ejecuta las tres tareas, con acceso solo a la carpeta de ReMate.
5. **Sin acceso desde fuera de la red interna:** no se usa ningún túnel ni servicio de publicación. Los datos del servidor (nombre, cuentas, subred, SMTP y copias) no se guardan en el repositorio.

## Alternativas consideradas

- **IIS con `wfastcgi`:** el módulo está abandonado desde 2020 y añade un servidor web que no hace falta, porque Flask ya sirve el frontend (ADR 0004).
- **Servicio de Windows con NSSM o WinSW:** es más «de servicio», pero NSSM no publica versión desde 2017 y WinSW es un binario más que instalar y aprobar. (Se adoptó después, en el ADR 0009.)
- **HTTPS con un proxy inverso** (IIS o Caddy) y un certificado interno: protegería los datos en la red interna, pero necesita certificado y mantenimiento. Se puede añadir más adelante sin cambiar la aplicación.
- **Gunicorn:** no funciona en Windows.

## Consecuencias

- **Positivas:** se instala con Python y los comandos de Windows, sin servidor web ni servicios de terceros, y los pasos se pueden documentar con PowerShell.
- **Negativas:**
  - Sin HTTPS, las ofertas y los datos de las necesidades viajan sin cifrar dentro de la red interna.
  - El Programador de tareas reinicia el proceso, pero no avisa de las caídas: hay que vigilar el registro (ADR 0008) o `/api/salud`.
  - Waitress publicó su última versión en noviembre de 2024. Es estable y no se le conocen vulnerabilidades, pero hay que vigilarlo con `scripts/auditar_dependencias.py`.

## Revisiones

- **2026-11-04:** el equipo de sistemas pide administrar la aplicación como servicio de Windows y configurar la IP y el puerto. El [ADR 0009](0009-servicio-windows-con-winsw.md) sustituye la tarea de arranque por un servicio con WinSW y la cuenta dedicada por el usuario existente del servidor. Se mantienen Windows Server, Waitress, el acceso solo desde la red interna sin HTTPS y las tareas de recordatorio y copia.
- **2026-11-19:** se puede entrar por un nombre a través de un proxy inverso como Caddy ([ADR 0016](0016-proxy-inverso-con-caddy.md)). La aplicación toma la IP del equipo y el esquema de las cabeceras del proxy, y con HTTPS en el proxy la cookie del modo admin pasa a ser `Secure`. Sin proxy, todo sigue como aquí.
