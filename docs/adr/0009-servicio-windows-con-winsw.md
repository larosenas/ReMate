# 0009 — Servicio de Windows con WinSW y escucha configurable

- **Estado:** Aceptada
- **Fecha:** 2026-11-04
- **Sustituye:** el arranque de la aplicación (punto 3) y la cuenta de ejecución (punto 4) del [ADR 0006](0006-despliegue-windows-sin-https.md)
- **Relacionado con:** [0008](0008-registro-en-la-base-de-datos.md) (registro)

## Contexto y problema

El equipo de sistemas necesita administrar ReMate desde `services.msc` y configurar la IP y el puerto en el `.env`. Python ejecutando Waitress necesita un envoltorio que implemente el protocolo de servicios de Windows. La tarea de arranque del ADR 0006 deja de ser la solución elegida.

## Decisión

- **WinSW 2.12.0** (licencia MIT) ejecuta directamente el Python del entorno virtual. La versión se fija para reproducir la instalación. Se usa `WinSW.NET461.exe` con .NET Framework 4.8, para no depender del runtime .NET Core 3.1 incluido en otros binarios de esa versión.
- El XML `scripts/windows/remate-servicio.xml` se versiona; el ejecutable se descarga de la release oficial y se renombra `remate-servicio.exe` junto al XML. No se guardan binarios ni credenciales en el repositorio.
- `python -m app.servir` carga el `.env` y arranca Waitress. `HOST` admite una IP IPv4 o IPv6 local, y `PORT` un entero entre 1 y 65535; por defecto, `0.0.0.0` y `2905`. El entorno tiene prioridad sobre el `.env`, y un valor no válido impide el arranque. `flask run` conserva su configuración de desarrollo.
- El servicio se instala en modo manual y **no se arranca** hasta asignarle en `services.msc` la cuenta, el inicio automático y la recuperación tras fallos. WinSW usa LocalSystem si no se indica cuenta: hay que cambiarla antes del primer inicio. Las contraseñas solo se guardan en Windows, fuera del XML.
- **Cuenta:** el usuario existente del servidor, en lugar de una cuenta dedicada. Si ese usuario es administrador, el servicio hereda sus permisos; la instalación no los eleva ni cambia sus grupos.
- El comando del servicio es `python -m app.servir --log <ruta a remate.log>`, que reutiliza el respaldo en UTF-8 del ADR 0008, incluidos los errores de configuración. Los mensajes de WinSW van a su propio archivo. El recordatorio y la copia siguen como tareas programadas.

## Alternativas consideradas

- **Mantener la tarea de arranque:** funcionaba, pero no se gestiona como un servicio.
- **Registrar `python.exe` con `New-Service`:** no implementa el protocolo de servicios.
- **NSSM u otro envoltorio:** NSSM no publica versión desde 2017; añadir otro no aporta valor.

## Consecuencias

- **Positivas:** se puede arrancar, parar y recuperar ReMate desde Windows, y la IP y el puerto se cambian en el `.env`.
- **Negativas:** hay que mantener un binario adicional, .NET Framework y su configuración. El servicio puede tener un entorno y un perfil distintos de una consola interactiva, así que la instalación se valida en el servidor real.
- Cambiar `PORT` obliga a revisar también `APP_URL`, los enlaces y el cortafuegos.
- Antes de actualizar o copiar datos hay que detener y deshabilitar el servicio y las tareas, para que la recuperación automática no reabra la aplicación durante el mantenimiento.

## Fuentes consultadas

- [Release 2.12.0](https://github.com/winsw/winsw/releases/tag/v2.12.0).
- [Instalación de WinSW 2.12.0](https://github.com/winsw/winsw/blob/v2.12.0/doc/installation.md).
- [Configuración XML de esa versión](https://github.com/winsw/winsw/blob/v2.12.0/doc/xmlConfigFile.md).
- [Licencia MIT](https://github.com/winsw/winsw/blob/v2.12.0/LICENSE.txt).

## Revisiones

- **2026-11-17:** Waitress pasa de 8 a 16 hilos, para que las llamadas a la IA en espera no dejen sin atender el resto de la aplicación ([ADR 0011](0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md)).
