# Arquitectura

Diagrama: [arquitectura](../diagramas/salidas/arquitectura.png) (fuente en `docs/diagramas/fuentes/arquitectura.puml`). Basada en los ADR [0003](../adr/0003-stack-react-tailwind-python-sqlalchemy.md) (stack) y [0004](../adr/0004-swagger-y-recordatorio-de-entrega.md) (Swagger, recordatorio y frontend servido por Flask).

## Visión general

- **Una sola aplicación en producción:** Flask sirve la interfaz compilada (`dist/`) y la API en `/api`, en el mismo puerto (ADR 0004). Waitress la ejecuta como servicio de Windows con WinSW, con la IP y el puerto configurables (`HOST` y `PORT`, [ADR 0009](../adr/0009-servicio-windows-con-winsw.md)). El recordatorio y la copia de seguridad son tareas programadas.
- **El frontend solo habla con el backend a través de la API REST** (JSON). Toda la lógica de negocio y las reglas de formato están en el backend.
- **El backend se organiza en capas:** API → servicios de negocio → modelos e integraciones. Las rutas no contienen lógica: validan la entrada y llaman a los servicios.
- **Las integraciones externas** (IA, lectura de correos, generación de `.eml`, SMTP y archivos) están aisladas en módulos propios, de forma que se pueden sustituir o simular en las pruebas.

## Backend (`backend/`)

| Componente | Responsabilidad | Casos de uso |
| --- | --- | --- |
| **API REST** (`app/api/`) | Rutas de Flask con flask-openapi3: validación de entradas con Pydantic, respuestas JSON y documentación en Swagger UI | Todos |
| **Servicios de negocio** (`app/servicios/`) | Código `AAAAMMDDNN`, transiciones de estado, comparativa de ofertas, cálculo de plazos, formatos del ERP, listas maestras, avisos, caducidad y modo admin | Todos |
| **Modelos** (`app/modelos/`) | Tablas de SQLAlchemy según el [modelo de datos](modelo-de-datos.md); migraciones con Alembic (`migraciones/`) | Todos |
| **Cliente de IA** (`app/integraciones/ia.py`) | Llamadas a la API de OpenAI (Responses API) para leer las ofertas, redactar el correo de petición, la petición de datos que faltan y los textos de la adjudicación. Respuestas con esquema JSON estricto, consumo registrado en `logs` y como mucho 8 llamadas a la vez ([ADR 0011](../adr/0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md)) | CU-002, CU-004, CU-005 |
| **Lector de correos** (`app/integraciones/correos_entrada.py` y `correos_msg.py`) | Leer el correo de oferta, `.eml` o `.msg`, solo con la biblioteca estándar: fecha, remitente, asunto, cuerpo y adjuntos, sin las imágenes del cuerpo ([ADR 0013](../adr/0013-correos-msg-con-lector-propio.md)). Rechaza los archivos fabricados para colgar el servidor | CU-004 |
| **Adjuntos para la IA** (`app/integraciones/adjuntos_ia.py`) | Preparar los adjuntos: los PDF y las imágenes se envían como archivo; los Word y Excel se pasan a texto con la biblioteca estándar, con límites de tamaño; lo que no se puede leer se salta con un aviso | CU-004 |
| **Pedido en PDF** (`app/integraciones/pedido_pdf.py`) | Leer el número de pedido del PDF del ERP, sin IA ni dependencias | CU-007 |
| **Generador de `.eml`** (`app/integraciones/eml.py`) | Componer los `.eml` de solicitud (en copia oculta), adjudicación, petición de datos y pedido, con la biblioteca estándar | CU-002, CU-004, CU-005, CU-007 |
| **Envío de correo** (`app/integraciones/correo_saliente.py`) | Enviar por SMTP el recordatorio de entrega y los avisos del paso 5 | CU-006, CU-009 |
| **Almacén de archivos** (`app/integraciones/archivos.py`) | Guardar adjuntos, correos y pedidos en una carpeta del disco; la base de datos guarda solo la ruta. Máximo 25 MB por archivo | CU-001, CU-004, CU-007 |
| **Comandos** (`app/cli.py`) | `enviar-recordatorios` (a diario: recordatorio de entrega, avisos del paso 5 y caducidad, cada uno con su propio control de errores), `cargar-listas`, `vaciar-listas` (solo en desarrollo), `clave-admin` y `probar-ia` | CU-003, CU-006, CU-009 |
| **Arranque** (`app/servir.py`) | Cargar la configuración y ejecutar Waitress con 16 hilos, más que las llamadas a la IA simultáneas, para que siempre quede alguno libre | Todos |
| **Modo admin** (`app/admin_sesion.py`, `app/api/admin.py` y `app/servicios/admin.py`) | Sesión con contraseña y herramientas de mantenimiento ([ADR 0015](../adr/0015-modo-admin-con-contrasena.md)) | Todos |
| **Protecciones de origen** (`app/origen.py`) | Como no hay inicio de sesión, protege frente a otras webs abiertas en el navegador de alguien de la red interna: rechaza los cambios enviados desde otro origen (`403`), impide mostrar la aplicación dentro de un marco y, con `APP_URL` o `HOSTS_PERMITIDOS`, solo atiende peticiones con un `Host` permitido (protección frente a DNS rebinding) | Todos |
| **Registro** (`app/registro.py`) | Guardar los mensajes de la aplicación en la tabla `logs`, en un hilo aparte; lo que no se puede guardar va a un archivo de respaldo ([ADR 0008](../adr/0008-registro-en-la-base-de-datos.md)) | Todos |

```text
backend/
├── app/
│   ├── __init__.py        # create_app(): configuración, rutas y servir dist/
│   ├── config.py          # lee las variables de entorno
│   ├── registro.py        # registro en la base de datos
│   ├── api/               # rutas por recurso
│   ├── servicios/         # lógica de negocio
│   ├── modelos/           # tablas de SQLAlchemy
│   ├── integraciones/     # IA, correos, archivos, SMTP
│   └── cli.py             # comandos de Flask
├── migraciones/           # Alembic
├── tests/
├── requirements.txt
└── requirements-dev.txt
```

## Frontend (`frontend/`)

| Componente | Responsabilidad |
| --- | --- |
| **Páginas** (`src/paginas/`) | Panel de seguimiento, nueva necesidad, detalle de una necesidad con su paso actual, listas maestras, histórico de un proveedor y modo admin |
| **Componentes** (`src/componentes/`) | Formularios, tablas, desplegables con alta rápida, subida del correo de oferta y sus adjuntos, comparativa, información para el ERP, avisos y errores |
| **Cliente de la API** (`src/api/`) | Funciones que llaman a `/api` con `fetch` y devuelven los datos o el error |

- En desarrollo, el servidor de Vite (`npm run dev`) redirige `/api` al Flask local, de modo que el código es el mismo que en producción.
- Navegación con React Router en modo declarativo ([ADR 0005](../adr/0005-navegacion-con-react-router.md)).

## Flujo de ejemplo: añadir y comparar ofertas (CU-004)

1. El ingeniero elige el correo del proveedor. El cliente lo envía a `POST /api/necesidades/{id}/ofertas/correo`, que lo lee sin guardar nada y devuelve sus adjuntos y el proveedor reconocido.
2. El ingeniero confirma el proveedor y los adjuntos. El cliente los envía a `POST /api/necesidades/{id}/ofertas`; la API valida tipo y tamaño y el servicio guarda los archivos. La oferta queda «Sin analizar».
3. Con todas las ofertas subidas, el ingeniero pide analizar y comparar (`POST /api/necesidades/{id}/evaluacion`). La necesidad pasa a «En evaluación» y el cliente de IA lee a la vez, hasta 4, las ofertas pendientes.
4. El servicio convierte los plazos en fechas, comprueba que las partidas suman el total y deja cada oferta sin revisar.
5. El frontend muestra la comparativa. El ingeniero revisa cada oferta; con todas revisadas, se marcan el mejor y el peor valor y se puede elegir una.

## Decisiones de diseño

- **Correo y adjuntos de la oferta:** al elegir el correo, la aplicación propone sus adjuntos con su tipo, y el ingeniero quita los que no importan (logotipos, condiciones generales…). Así la IA no recibe ruido.
- **Adjuntos para la IA:** los PDF y las imágenes van como archivo; los Word (`.docx`) y Excel (`.xlsx`) se pasan a texto en el backend, sin dependencias nuevas. Los formatos antiguos (`.doc`, `.xls`) se saltan con un aviso que pide guardarlos como PDF o en el formato nuevo.
- **Copias de seguridad:** la base de datos y la carpeta de archivos (`ARCHIVOS_DIR`), con `scripts/windows/copia-de-seguridad.ps1` ([ADR 0014](../adr/0014-caducidad-de-archivos-y-copias.md)).
