# 0007 — IA de producción: Claude Code por terminal

- **Estado:** Sustituida por [0011](0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md) (2026-11-04)
- **Fecha:** 2026-11-02
- **Sustituye en parte a:** [0003](0003-stack-react-tailwind-python-sqlalchemy.md) (solo la IA de producción; OpenRouter sigue en desarrollo)
- **Relacionado con:** [0006](0006-despliegue-windows-sin-https.md) (despliegue en Windows Server)

## Contexto y problema

El ADR 0003 eligió la API de OpenAI para producción, pero esa decisión se reabrió. Se probó otra forma de llamar a la IA: **Claude Code por terminal** (`claude -p`), en lugar de una API con clave. La prueba de principio a fin, con datos ficticios (lectura de dos ofertas, comparativa y adjudicación), tardó 69 s en total.

## Decisión

1. **Producción:** `IA_MOTOR=claude-cli`. ReMate llama a `claude -p` en el servidor para redactar los correos a los proveedores, leer las ofertas, resumir la comparativa y redactar la adjudicación (CU-002, CU-004 y CU-005), con las mismas instrucciones que con la API.
2. **Desarrollo:** sin cambios, `IA_MOTOR=api` con OpenRouter (ADR 0003). El código elige el motor con esa variable; el resto de la aplicación no cambia.
3. **Claude Code solo puede leer.** Cada llamada se hace en una carpeta temporal con los datos, con `--tools Read`, sin terminal, sin escribir, sin web, sin la configuración ni los complementos del equipo (`--safe-mode`, `--strict-mcp-config`), con las herramientas de archivos limitadas a esa carpeta (`--restricted`, para que una oferta con instrucciones escondidas no pueda pedir que lea otros archivos del servidor) y sin guardar la sesión. La carpeta se borra al terminar.
4. **Una sola llamada por petición**, con 240 s como máximo. Si falla (no está instalado, sin sesión, sin límite de uso, respuesta no válida), la aplicación sigue sin IA, como con la API.
5. **En el servidor:** Claude Code se instala para la cuenta que ejecuta ReMate, con la sesión iniciada o con una credencial en el `.env`. `IA_CLI_MODELO` elige el modelo.

## Alternativas consideradas

- **API de OpenAI** (decisión inicial del ADR 0003): reabierta en ese momento.
- **API de Anthropic con la biblioteca `openai`** (endpoint compatible): sería el mismo código que en desarrollo, pero con pago por uso.
- **OpenRouter también en producción:** reenvía los datos a un tercero más, y sus modelos gratuitos fallaban a menudo.

## Consecuencias

**Positivas:**

- Lee bien las ofertas probadas (PDF e imágenes) con las mismas instrucciones.
- No hace falta una clave de API si la sesión se inicia en el servidor.
- Claude Code queda limitado a leer una carpeta temporal: no puede ejecutar órdenes ni tocar otros archivos.

**Negativas:**

- Hay que instalar y mantener Claude Code en el servidor y vigilar que la sesión no caduque.
- Cada llamada es más lenta que con la API.
- Desarrollo (OpenRouter) y producción (Claude) usan modelos distintos, que pueden leer las ofertas de forma distinta.
- Si Claude Code cambia sus opciones de línea de órdenes, hay que adaptar la integración (las pruebas lo simulan, no lo ejecutan).

## Por qué se sustituyó

Dos días después se decidió usar un único proveedor y un único camino en los dos entornos: la API de OpenAI, con salida estructurada, consumo medido y menos piezas que mantener en el servidor. Ver [ADR 0011](0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md).
