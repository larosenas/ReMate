# 0013 — Correos `.msg` de Outlook con un lector propio, sin dependencias

- **Estado:** Aceptada (revisada el 2026-11-17)
- **Fecha:** 2026-11-11
- **Sustituye a:** [0012](0012-correos-msg-con-extract-msg.md) (`extract-msg`), que no se llegó a programar
- **Relacionado con:** CU-004

## Contexto y problema

El ADR 0012 decidió leer los `.msg` con `extract-msg`. Antes de programarlo se descarta por su licencia, GPL v3: el código se entrega a terceros, y la GPL podría exigir distribuir el conjunto con esa licencia. Criterio: lo que menos dependa del exterior y menos dependencias añada.

Un `.msg` es un archivo compuesto de Office (MS-CFB, un pequeño sistema de archivos con carpetas y archivos dentro) con las propiedades del correo según MS-OXMSG. Las dos especificaciones son públicas (Microsoft Open Specifications).

## Decisión

- Un lector propio, `backend/app/integraciones/correos_msg.py`, **solo con la biblioteca estándar** (unas 300 líneas con los comentarios). Lee el contenedor (cabecera, FAT, DIFAT, mini FAT y directorio) y las propiedades que necesita ReMate: asunto, remitente (dirección SMTP o, si no, la de las cabeceras de Internet), fecha de envío, cuerpo en texto o, si no, en HTML, y los adjuntos (nombre, tipo MIME, datos, Content-ID y si están ocultos).
- `correos_entrada.leer` devuelve lo mismo para `.eml` y `.msg`. Las imágenes del cuerpo (las que usa el HTML con `cid:` o las que Outlook marca como ocultas) no cuentan como adjuntos.
- Un correo adjunto dentro del `.msg` se devuelve convertido en `.eml`, que ya saben leer la aplicación y la IA.
- **El archivo viene de fuera y no es de fiar:** todas las cadenas y bucles tienen límite, y cualquier error de formato acaba en un mensaje que explica cómo guardarlo como `.eml`. Sin escribir en disco, sin registrar el contenido y sin conexión.

## Alternativas consideradas

- **`extract-msg` (ADR 0012):** lee más casos raros sin código propio, pero tiene licencia GPL v3 y varias dependencias.
- **`olefile` 0.47 y un lector propio de las propiedades:** licencia BSD y sin dependencias propias. Unas 100 líneas propias menos, a cambio de una dependencia cuya última versión es antigua. Queda como alternativa si el contenedor diera problemas.
- **Seguir pidiendo `.eml`:** los usuarios piden no tener que hacerlo.

## Consecuencias

**Positivas:**

- Sin licencias ni dependencias nuevas: nada que instalar ni que auditar.
- Probado con un `.msg` de ejemplo con datos ficticios (`backend/tests/datos/oferta-ficticia.msg`): el PDF adjunto sale idéntico byte a byte al original, y la fecha, el remitente y el asunto coinciden con los del `.eml` del mismo correo. Las pruebas incluyen 300 alteraciones al azar del archivo, que se leen o se rechazan sin otros errores.

**Negativas:**

- El código es propio: hay que mantenerlo.
- Un cuerpo que solo venga en RTF comprimido no se lee (queda vacío; la IA sigue leyendo los adjuntos). Outlook guarda casi siempre también el texto.
- Algún `.msg` raro puede no leerse; en ese caso se avisa y se puede guardar como `.eml`.

## Revisiones

- **2026-11-17, revisión de seguridad:** un `.msg` de 1 KB con la DIFAT en ciclo hacía crecer la FAT hasta llenar la memoria, porque el límite de sectores no tenía en cuenta el tamaño real del archivo. Ahora ninguna cadena de sectores ni de minisectores puede pasar dos veces por el mismo sector ni tener más sectores de los que caben en el archivo, y lo que se lee de un `.msg` en total no puede pasar de 3 veces su tamaño (mínimo 1 MB). Si no se cumple, el `.msg` se rechaza como «dañado o incompleto». La decisión no cambia: completa el punto de que todas las cadenas y bucles tienen límite.
