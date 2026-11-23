# Registros de decisiones de arquitectura (ADR)

Cada decisión de arquitectura duradera se registra en un ADR: contexto y problema, decisión, alternativas consideradas y consecuencias, con su estado y su fecha. Una decisión aceptada no se cambia en silencio: se registra otra que la sustituye y se enlazan las dos. Por eso aquí siguen también las decisiones sustituidas.

| ADR | Decisión | Estado |
| --- | --- | --- |
| [0001](0001-framework-django-5-2-lts.md) | Framework web: Django 5.2 LTS | Sustituida por 0003 |
| [0002](0002-base-de-datos-postgresql.md) | Base de datos: PostgreSQL | Sustituida por 0003 (PostgreSQL se mantiene) |
| [0003](0003-stack-react-tailwind-python-sqlalchemy.md) | Stack: React + Tailwind, Python + Flask + SQLAlchemy | Aceptada (la parte de la IA, sustituida por 0011) |
| [0004](0004-swagger-y-recordatorio-de-entrega.md) | Swagger, recordatorio con tarea programada y frontend servido por Flask | Aceptada |
| [0005](0005-navegacion-con-react-router.md) | Navegación con React Router; sin PWA | Aceptada |
| [0006](0006-despliegue-windows-sin-https.md) | Windows Server, sin HTTPS, con Waitress | Aceptada (el arranque, sustituido por 0009; el proxy, en 0016) |
| [0007](0007-ia-de-produccion-claude-code.md) | IA de producción: Claude Code por terminal | Sustituida por 0011 |
| [0008](0008-registro-en-la-base-de-datos.md) | Registro de la aplicación en la base de datos | Aceptada |
| [0009](0009-servicio-windows-con-winsw.md) | Servicio de Windows con WinSW y escucha configurable | Aceptada |
| [0010](0010-moneda-de-la-oferta-sin-conversiones.md) | Moneda de cada oferta, sin conversiones | Aceptada |
| [0011](0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md) | IA con la API de OpenAI, con consumo mínimo | Aceptada |
| [0012](0012-correos-msg-con-extract-msg.md) | Correos `.msg` de Outlook con `extract-msg` | Sustituida por 0013 |
| [0013](0013-correos-msg-con-lector-propio.md) | Correos `.msg` de Outlook con un lector propio, sin dependencias | Aceptada |
| [0014](0014-caducidad-de-archivos-y-copias.md) | Caducidad de los archivos y del registro, y copias que ocupan lo mínimo | Aceptada |
| [0015](0015-modo-admin-con-contrasena.md) | Modo admin con contraseña | Aceptada |
| [0016](0016-proxy-inverso-con-caddy.md) | Entrada por un nombre con un proxy inverso (Caddy) | Aceptada |

Plantilla para decisiones nuevas: [0000](0000-plantilla.md).
