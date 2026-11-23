# 0012 — Correos `.msg` de Outlook con `extract-msg`

- **Estado:** Sustituida por [0013](0013-correos-msg-con-lector-propio.md) (2026-11-11), sin llegar a programarse
- **Fecha:** 2026-11-10
- **Relacionado con:** CU-004

## Contexto y problema

Los usuarios piden subir los correos de oferta tal como los arrastran desde Outlook, en `.msg`, y que la aplicación saque sus adjuntos. Hasta entonces solo se aceptaban `.eml`, que se leen con la biblioteca estándar de Python; los `.msg` se rechazaban con un mensaje que explicaba cómo guardarlos como `.eml`. Al arrastrar un correo desde Outlook al navegador llega un `.msg`.

Un `.msg` no es texto MIME como el `.eml`: es un archivo binario de Outlook (un contenedor de Office con propiedades MAPI). El asunto, el cuerpo (texto, HTML o RTF comprimido), el remitente y la fecha son propiedades, y cada adjunto va en una carpeta interna; un correo reenviado como adjunto es otro `.msg` dentro. La biblioteca estándar no lo lee.

Criterio para elegir: lo que menos dependa del exterior y menos dependencias añada.

## Decisión

- Leer los `.msg` con **`extract-msg`** (PyPI), a prueba, detrás de un módulo propio que devuelve lo mismo para `.eml` y `.msg` (fecha, remitente, asunto, cuerpo y adjuntos). Así el resto de la aplicación no depende de la biblioteca.
- **Privacidad:** se lee en memoria, sin las funciones de guardar de la biblioteca; su registro de mensajes se silencia, para que no lleguen trozos del correo a la tabla `logs`; y funciona sin conexión.

## Alternativas consideradas

- **`olefile` y un lector propio de las propiedades:** una sola dependencia, con licencia permisiva. Hay que escribir y mantener la lectura de las propiedades y no leería los cuerpos que solo vienen en RTF comprimido.
- **Leer el contenedor sin ninguna biblioteca:** posible, pero con más riesgo de errores.
- **Seguir pidiendo `.eml`:** es lo que había; los usuarios piden no tener que hacerlo.

## Consecuencias

**Positivas:**

- El ingeniero sube el correo tal como sale de Outlook, con sus adjuntos dentro.
- Lee los casos raros de Outlook (RTF comprimido, direcciones de Exchange, correos dentro de correos) sin código propio.

**Negativas:**

- **Licencia GPL v3.** Si el código se distribuye a terceros, la GPL puede exigir que el conjunto se distribuya con esa licencia.
- Trae varias dependencias más que instalar, auditar y mantener.
- Las pruebas necesitan un `.msg` de ejemplo con datos inventados, guardado desde Outlook.

## Por qué se sustituyó

Antes de programarlo se descartó por la licencia GPL v3, y se escribió un lector propio solo con la biblioteca estándar. Ver [ADR 0013](0013-correos-msg-con-lector-propio.md).
