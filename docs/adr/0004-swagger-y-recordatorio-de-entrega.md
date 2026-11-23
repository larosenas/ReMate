# 0004 — Documentación de la API con flask-openapi3, recordatorio de entrega con una tarea programada y frontend servido por Flask

- **Estado:** Aceptada
- **Fecha:** 2026-10-22
- **Relacionado con:** [0003](0003-stack-react-tailwind-python-sqlalchemy.md) (stack)

## Contexto y problema

1. La API de Flask se documenta con Swagger/OpenAPI (ADR 0003), pero Flask no lo hace por sí solo: hace falta una extensión.
2. Una semana antes de la fecha de entrega prevista hay que enviar un correo de recordatorio al peticionario (CU-009). El sistema operativo del servidor estaba por definir.
3. En producción, los archivos estáticos que genera `npm run build` (`dist/`) tienen que servirse al navegador: o los sirve el propio Flask o un servidor web aparte (nginx, IIS).

## Decisión

1. **flask-openapi3** (4.3.2, «Production/Stable» en PyPI, licencia MIT; depende de Flask y Pydantic). Genera la especificación OpenAPI desde el código, sirve Swagger UI (con el complemento **flask-openapi3-swagger** 5.31.0, MIT) y valida las entradas con Pydantic, con lo que se recupera la validación automática que se valoraba en FastAPI.
2. **Un comando de Flask, `flask enviar-recordatorios`, ejecutado una vez al día por el planificador del sistema operativo** (cron en Linux o el Programador de tareas en Windows). El comando busca las necesidades en «Pendiente entrega» con la fecha prevista a 7 días o menos y sin `recordatorio_enviado_en`, envía el correo por SMTP (variables `SMTP_*`) y anota la fecha de envío. Si la fecha prevista cambia por un retraso, `recordatorio_enviado_en` se vacía para que el aviso se envíe respecto a la nueva fecha.
3. **Flask sirve también el frontend:** una sola aplicación en `http://<ip>:<puerto>`; la interfaz se sirve desde `dist/` y la API cuelga de `/api`. Las rutas que no son de la API devuelven `index.html` para que funcione la navegación de React. Basta para una aplicación interna con pocos usuarios.

## Alternativas consideradas

- **flask-smorest** (0.47.0, beta) y **APIFlask** (3.1.2, estable): válidas, pero usan marshmallow en lugar de Pydantic; flask-openapi3 es más directa.
- **Servidor web aparte para `dist/`** (nginx o IIS delante de Flask): mejor rendimiento con mucho tráfico, pero un programa más que instalar y configurar.
- **Planificador dentro de la aplicación (APScheduler 3.11.3):** no necesita configurar el sistema, pero se ejecutaría una vez por cada proceso del servidor web (avisos duplicados) y se perdería si la aplicación está parada a la hora prevista.

## Consecuencias

**Positivas:**

- Swagger UI y validación de datos con poco código.
- El recordatorio funciona igual en Linux y en Windows, se puede lanzar a mano para probarlo y no envía duplicados.
- Despliegue sencillo: un solo programa y un solo puerto; frontend y API en el mismo origen, sin configurar CORS en producción.

**Negativas:**

- Hay que dar de alta la tarea diaria en el servidor. En Windows (ADR 0006) se hace con `scripts/windows/enviar-recordatorios.ps1`, como explica la [guía de instalación](../../documentacion/guia-de-instalacion.md).
- flask-openapi3 tiene una comunidad más pequeña que Flask.
