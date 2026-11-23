# API REST

Contrato entre el frontend (React) y el backend (Flask). La referencia exacta de cada ruta (campos y tipos) es la que genera flask-openapi3 a partir del código, en `/api/docs/swagger` ([ADR 0004](../adr/0004-swagger-y-recordatorio-de-entrega.md)); este documento explica qué hace cada una y sus reglas.

## Convenciones

- **Base:** todas las rutas cuelgan de `/api`. Documentación interactiva en `/api/docs` (Swagger UI en `/api/docs/swagger`). `GET /api/salud` comprueba que la API y la base de datos responden (`200`, o `503` si la base de datos no responde).
- **Formato:** JSON en UTF-8. Los archivos se suben con `multipart/form-data`. Los `.eml` se descargan como archivo (`message/rfc822`).
- **Nombres:** recursos en plural y en español, sin tildes (`/necesidades`, `/proveedores`). Campos en `snake_case`, como en el modelo de datos.
- **Fechas:** ISO 8601 (`2026-11-15`; con hora, `2026-10-22T10:30:00+02:00`). Los formatos del ERP (`DD.MM.AAAA`, coma decimal) solo aparecen en la información para el ERP.
- **Importes:** como texto decimal exacto (`"1250.50"`), nunca como número de coma flotante, para no perder céntimos. El frontend los muestra con formato español.
- **Sin inicio de sesión:** las acciones que cambian el estado de una necesidad llevan el `peticionario_id` de quien las hace, para el historial (`CambioEstado`).
- **Identificadores:** números enteros de 1 a 2.147.483.647; fuera de ese rango, o como booleano, la validación responde `400`.
- **Errores:** formato común, con el código HTTP que corresponda:

  ```json
  { "error": "transicion_no_permitida", "mensaje": "La necesidad no está en «En evaluación».", "detalles": {} }
  ```

  | Código | Cuándo |
  | --- | --- |
  | 400 | Datos no válidos (los errores de validación de Pydantic van en `detalles`). En cualquier ruta, también la interfaz, `host_no_permitido`: con `APP_URL` o `HOSTS_PERMITIDOS` configuradas, la cabecera `Host` no es la de `APP_URL`, `localhost`, `127.0.0.1`, `::1` ni una de `HOSTS_PERMITIDOS` (protección frente a DNS rebinding). Sin ninguna de las dos variables no se comprueba |
  | 403 | `origen_no_permitido`: un cambio (POST, PUT, PATCH, DELETE) enviado desde otra web, con `Origin` distinto de la dirección de ReMate o `Sec-Fetch-Site: cross-site`. Las peticiones sin `Origin` (curl, scripts) se aceptan |
  | 404 | El recurso no existe |
  | 409 | Conflicto: transición de estado no permitida, correo duplicado |
  | 410 | `archivo_caducado`: el archivo se borró por antigüedad ([ADR 0014](../adr/0014-caducidad-de-archivos-y-copias.md)) |
  | 413 | `archivo_demasiado_grande`: un archivo de más de 25 MB; `subida_demasiado_grande`: más de 100 MB entre todos los de una petición |
  | 422 | `archivo_no_aceptado`: el correo no es un `.eml` ni un `.msg`, o no se puede leer |
  | 503 | `GET /api/salud`: la base de datos no responde |

- **Cabeceras de seguridad:** todas las respuestas llevan `X-Frame-Options: DENY`, `Content-Security-Policy: frame-ancestors 'none'` y `X-Content-Type-Options: nosniff`, para que ReMate no se pueda mostrar dentro de un marco de otra web.
- **Fallos de la IA:** no hay código de error. La respuesta es `200` con un aviso (y `con_ia: false` donde existe ese campo), y la acción se puede repetir o completar a mano. Lo mismo si la IA está ocupada: como mucho hay 8 llamadas a la vez y cada una espera su turno hasta 2 s ([ADR 0011](../adr/0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md)).
- **Moneda:** las ofertas llevan `moneda` (código de tres letras, en mayúsculas; EUR por defecto). Un código que no sea de tres letras da `400`. Los precios nunca se convierten ([ADR 0010](../adr/0010-moneda-de-la-oferta-sin-conversiones.md)).

## Listas maestras (CU-003)

| Método y ruta | Qué hace | Entrada | Respuesta |
| --- | --- | --- | --- |
| `GET /api/proveedores` | Lista los proveedores activos, de la A a la Z | `?incluir_inactivos=true` (opcional) | `[{id, nombre, email, activo}]` |
| `POST /api/proveedores` | Alta de un proveedor | `{nombre, email}` | `201` con el proveedor. `409` si el correo ya existe (incluye el existente) |
| `PATCH /api/proveedores/{id}` | Editar o desactivar | `{nombre?, email?, activo?}` | El proveedor |
| `GET /api/peticionarios` | Lista los peticionarios activos, de la A a la Z | `?incluir_inactivos=true` | `[{id, nombre_completo, email, activo}]` |
| `POST /api/peticionarios` | Alta de un peticionario | `{nombre_completo, email}` | `201`; `409` si el correo ya existe |
| `PATCH /api/peticionarios/{id}` | Editar o desactivar | `{nombre_completo?, email?, activo?}` | El peticionario |
| `POST /api/proveedores/{id}/baja` y `POST /api/peticionarios/{id}/baja` | Baja definitiva de un registro desactivado | `{motivo}`; para un peticionario con necesidades en curso, también `reasignar_a` | `204`. Deja de salir en las listas y su correo queda libre. `409 sigue_activo` si no se ha desactivado antes; `400` sin motivo; `404` si no existe o ya está eliminado. Un peticionario con necesidades en curso y sin `reasignar_a` da `409 necesidades_en_curso`, con la lista en `detalles.necesidades` |
| `GET` y `POST /api/avisados-pedido-sap`, `PATCH /api/avisados-pedido-sap/{id}` y `POST /api/avisados-pedido-sap/{id}/baja` | Lista de quienes reciben el aviso del paso 5 (CU-006). Funciona igual que la de proveedores | Como los proveedores | Como los proveedores |

No hay `DELETE` en las listas: los registros se desactivan o se eliminan con motivo, sin borrar la fila. Si el correo ya existe, `409` devuelve el registro existente para que el frontend ofrezca usarlo o reactivarlo. La carga inicial no es una ruta, sino el comando `flask cargar-listas <csv>`.

## Necesidades

| Método y ruta | Qué hace | CU | Entrada | Respuesta |
| --- | --- | --- | --- | --- |
| `GET /api/necesidades` | Panel de seguimiento | CU-010 | — (los filtros se aplican en el navegador) | `[{id, codigo, titulo, proyecto, estado, estado_texto, peticionario, creada_en, fecha_entrega_prevista, proveedor_adjudicado, estado_desde}]`, de la más reciente a la más antigua |
| `POST /api/necesidades` | Crear necesidad | CU-001 | `multipart`: `titulo`, `proyecto`, `peticionario_id`, `descripcion` y `adjuntos` (uno por archivo) | `201` con la necesidad y su código `AAAAMMDDNN`. `409 codigo_agotado` con 99 necesidades ese día |
| `PUT /api/necesidades/{id}` | Corregir los datos del paso 1 | CU-001, CU-002 | `{titulo, proyecto, peticionario_id, descripcion}` | La necesidad. `409` si ya no está en «Necesidad creada» |
| `GET /api/necesidades/{id}` | Detalle | Todos | — | La necesidad con peticionario, adjuntos, proveedores solicitados, ofertas, oferta adjudicada, retrasos, historial de estados y cambios de peticionario, y las fechas de recordatorio y de aviso. Incluye `fecha_entrega_propuesta`, la que se propone en el paso 5 |
| `POST /api/necesidades/{id}/adjuntos` | Añadir adjuntos desde la solicitud de ofertas | CU-002 | `multipart`: `adjuntos` | `201` con los adjuntos nuevos. `409` si no está en «Necesidad creada» |
| `GET /api/necesidades/{id}/adjuntos/{adjunto_id}` | Descargar un adjunto | — | — | El archivo, o `410 archivo_caducado`. Los adjuntos llevan `caducado: true` si se borraron |
| `POST /api/necesidades/{id}/cancelar` | Cancelar | — | `{peticionario_id, motivo}` | La necesidad en «Cancelada». `409` si ya está «Entregado» o «Cancelada» |

## Paso 2: solicitar ofertas (CU-002)

| Método y ruta | Qué hace | Entrada | Respuesta |
| --- | --- | --- | --- |
| `POST /api/necesidades/{id}/solicitud/borrador` | La IA redacta qué se pide; la aplicación pone el resto del correo | `{adjunto_ids[]}` | `{asunto, cuerpo, avisos[], con_ia}`. Si la IA falla, la descripción tal cual y un aviso, y otro si no dice cuántas unidades |
| `POST /api/necesidades/{id}/solicitud` | Genera el `.eml` y pasa a «En cotización» | `{peticionario_id, proveedor_ids[], adjunto_ids[], cuerpo, motivo_pocos_proveedores}` (el motivo, obligatorio con menos de 3 proveedores) | La necesidad. `400` (`campo: motivo_pocos_proveedores`) si falta el motivo; `409` si no está en «Necesidad creada» |
| `GET /api/necesidades/{id}/solicitud.eml` | Descarga (o vuelve a descargar) el `.eml` | — | Archivo `.eml` |

## Paso 3: ofertas (CU-004)

| Método y ruta | Qué hace | Entrada | Respuesta |
| --- | --- | --- | --- |
| `POST /api/necesidades/{id}/ofertas/correo` | Lee el correo de una oferta sin guardar nada, para proponer sus adjuntos y su proveedor | `multipart`: `correo` (`.eml` o `.msg`) | `{remitente, proveedor, aviso_proveedor, adjuntos: [{indice, nombre, tamano}]}`, sin las imágenes del cuerpo. `proveedor` es el reconocido por el remitente o su dominio, o `null` con el motivo. `422 archivo_no_aceptado` si no se puede leer |
| `GET /api/necesidades/{id}/ofertas` | Ofertas vigentes, de la última subida a la primera | — | `[oferta]` con sus partidas, archivos y `avisos[]` |
| `POST /api/necesidades/{id}/ofertas` | Sube una oferta; se guarda «Sin analizar» | `multipart`: `correo`, `proveedor_id` (opcional: si falta, se busca por el remitente y su dominio), `adjuntos` y `tipos_adjunto` (`pdf`, `excel`, `word`, `imagen` u `otro`, en el mismo orden), `adjuntos_correo` y `tipos_adjunto_correo` (los adjuntos del propio correo que se guardan, por su `indice`), `confirmar_sustitucion` y `anadir_datos` | `201` con la oferta y `sin_analizar: true`. Si el proveedor ya tiene oferta y no se confirma, `409 oferta_existente`. Con `anadir_datos: true`, el correo es la respuesta del proveedor: se guarda en su oferta, la IA lee solo la respuesta y la oferta se completa; responde `200` con los avisos de lo completado y lo cambiado |
| `PATCH /api/necesidades/{id}/ofertas/{oferta_id}` | Corregir los datos y marcarla como revisada | `{moneda?, numero_oferta?, importe_sin_iva?, plazo_entrega_texto?, fecha_entrega_estimada?, condiciones_pago?, condiciones?, otros?, lineas?, revisada?}` | La oferta. Si cambia algún dato sin `revisada: true`, deja de estar revisada. En `condiciones` solo cambian las que se envían |
| `DELETE /api/necesidades/{id}/ofertas/{oferta_id}` | Borrar una oferta (queda marcada como `borrada`) | — | `204`. `409` si la necesidad ya no está en «En cotización» o «En evaluación» |
| `POST /api/necesidades/{id}/ofertas/{oferta_id}/analisis` | Volver a leer la oferta con la IA. Sus datos sustituyen a los de la oferta, que queda sin revisar | — | La oferta con `avisos[]`. Si la IA falla, los datos no cambian |
| `POST /api/necesidades/{id}/evaluacion` | Analizar y comparar: en «En cotización» pasa a «En evaluación», y la IA lee a la vez, hasta 4, las ofertas sin analizar. Nunca sustituye datos escritos a mano | `{peticionario_id}` (obligatorio en «En cotización») | `{necesidad, avisos[]}`. `409` si no hay ofertas, el estado no lo permite o ya se están analizando |
| `GET /api/necesidades/{id}/comparativa` | Comparativa de las ofertas vigentes | — | Las ofertas con datos, de más barata a más cara (sin importe, al final), con `revisada`, `historial_proveedor: {pedidos, con_retraso, dias_retraso, retraso_medio, comentarios}` y `destacados: {importe, entrega, retrasos}` (`"mejor"`, `"peor"` o `null`, solo con todas las ofertas revisadas) |
| `POST /api/necesidades/{id}/ofertas/{oferta_id}/peticion-datos/borrador` | Correo para pedir al proveedor los datos que faltan, redactado por la IA. No guarda nada | — | `{para, asunto, cuerpo, faltan[], avisos[], con_ia}`. `400` si no falta nada |
| `POST /api/necesidades/{id}/ofertas/{oferta_id}/peticion-datos` | Descarga ese correo como `.eml`. No se guarda | `{cuerpo}` | Archivo `.eml`. `400` si el cuerpo está vacío |

**Campos de cada oferta:**

- `fecha_calculada`: la fecha no la dio el proveedor; es su plazo contado desde el correo y solo sirve para comparar. Con un rango se cuenta el número más alto.
- `fecha_de_mes`: la oferta solo dio un mes y la fecha es su último viernes. Es fija: no se vuelve a contar desde el pedido.
- `lineas[].plazo_entrega_texto` y `lineas[].fecha_calculada`: el plazo propio de cada partida y si su fecha se cuenta desde el correo. Si la oferta solo da plazos por partida, su `plazo_entrega_texto` es el de la partida que más tarda.
- `condiciones`: las nueve condiciones, `[{clave, nombre, estado, texto}]`, con `estado` igual a `especificado`, `incluido`, `no_incluido`, `no_aplica` o `no_especificado`. `otros` es la información adicional.
- `datos_que_faltan`: lo que se puede pedir al proveedor; vacío si la IA aún no ha leído la oferta.

## Pasos 4 y 5: adjudicación y solicitud en el ERP (CU-005 y CU-006)

| Método y ruta | Qué hace | Entrada | Respuesta |
| --- | --- | --- | --- |
| `POST /api/necesidades/{id}/adjudicacion/borrador` | Prepara la información para el ERP y el correo al adjudicatario. No guarda nada | `{oferta_id}` | `{texto_sap_fijo, descripcion_inversion, moneda, tabla_sap[], correo: {para, asunto, cuerpo}, bloqueos[], avisos[]}`. `bloqueos`: lo que impide adjudicar. `avisos` empieza siempre por «No es la oferta más barata…» o «No es la que antes entrega…» si la elegida no lo es. Si la IA falla, la aplicación propone los textos |
| `POST /api/necesidades/{id}/adjudicacion` | Confirma la adjudicación y pasa a «Pendiente solicitud SAP» | `{peticionario_id, oferta_id, descripcion_inversion, cuerpo_correo}` | La necesidad. `400` si la oferta no está vigente, revisada y con partidas; `409` si la necesidad no está en «En evaluación» |
| `GET /api/necesidades/{id}/sap` | Información para el ERP, lista para copiar | — | `{proveedor, moneda, fecha_entrega_inicial, texto_sap, tabla_sap: [{short_text, quantity_requested, valuation_price, delivery_date, requisitioner}]}`, con los formatos del ERP (`"1250,50"`, `"15.11.2026"`, `"2,5"`) |
| `GET /api/necesidades/{id}/adjudicacion.eml` | Descarga el `.eml` al adjudicatario | — | Archivo `.eml` |
| `POST /api/necesidades/{id}/pedido-en-sap` | Paso 5: confirma la solicitud en el ERP con la fecha de entrega prevista y avisa a los avisados | `{peticionario_id, fecha_entrega_prevista}` | La necesidad en «Pendiente pedido SAP», con `aviso_pedido_sap_en` si el aviso se envió; si no, `avisos` lo dice y la tarea diaria lo reintenta. `400` si falta la fecha; `409` si no está en «Pendiente solicitud SAP» |

En la información para el ERP, un plazo sin fecha se cuenta desde el día de la adjudicación (o, ya confirmada la solicitud, es la fecha propuesta o confirmada), y `short_text` usa el título de la necesidad si la partida solo trae una referencia.

## Pasos 6 y 7: pedido y entrega (CU-007 a CU-009)

| Método y ruta | Qué hace | Entrada | Respuesta |
| --- | --- | --- | --- |
| `GET /api/necesidades/{id}/pedido-sap/propuesta` | Proveedor adjudicatario y número de oferta propuesto | — | `{proveedor, para, numero_oferta, origen_numero_oferta, fecha_entrega_prevista}`; `origen_numero_oferta` es `oferta`, `archivo` o `null`. `409` si no está en «Pendiente pedido SAP» |
| `POST /api/necesidades/{id}/pedido-sap/numero` | Lee el número de pedido del PDF («PURCHASE ORDER NO. …»), sin IA y sin guardar nada | `multipart`: `pedido` | `{numero_pedido}`, o `null` si el PDF no lo dice |
| `POST /api/necesidades/{id}/pedido-sap/borrador` | Correo al proveedor con la plantilla fija. No guarda nada | `{numero_oferta, numero_pedido?}` | `{para, asunto, cuerpo}`. `400` si falta el número de oferta |
| `POST /api/necesidades/{id}/pedido-sap` | Guarda el pedido, genera el `.eml` al proveedor con el pedido adjunto y pasa a «Pendiente entrega» | `multipart`: `peticionario_id`, `pedido`, `numero_oferta`, `numero_pedido` (opcional) y `cuerpo_correo` | La necesidad. `400` con `campo` si falta algo; `409` si no está en «Pendiente pedido SAP» |
| `GET /api/necesidades/{id}/pedido-sap.eml` | Descarga (o vuelve a descargar) el `.eml` con el pedido | — | Archivo `.eml` |
| `POST /api/necesidades/{id}/retrasos` | Registra un retraso | `{peticionario_id, fecha_nueva, motivo}` | La necesidad con el retraso y la nueva fecha prevista. `400` sin motivo o si la fecha no es posterior a la prevista; `409` si no está en «Pendiente entrega» |
| `POST /api/necesidades/{id}/entrega` | Confirma la entrega | `{peticionario_id, fecha_entrega_real?, motivo_retraso?, comentario?}` (fecha por defecto, hoy; comentario de 1000 caracteres como máximo) | La necesidad en «Entregado». Si la fecha real es posterior a la prevista, `motivo_retraso` es obligatorio y se registra como retraso. `400` si la fecha es futura o anterior a la creación; `409` si no está en «Pendiente entrega» |

El recordatorio de entrega (CU-009) y los avisos del paso 5 no tienen ruta: los envía a diario el comando `flask --app app enviar-recordatorios [--prueba]`.

## Histórico (CU-010)

| Método y ruta | Qué hace | Respuesta |
| --- | --- | --- |
| `GET /api/proveedores/{id}/retrasos` | Histórico de un proveedor | `{proveedor, pedidos, con_retraso, dias_retraso, retraso_medio, comentarios, retrasos: [{necesidad: {id, codigo, titulo}, fecha_anterior, fecha_nueva, dias, motivo, peticionario, registrado_en, sin_efecto}]}`, retrasos del más reciente al más antiguo. `sin_efecto`: el pedido llegó a tiempo y el retraso no cuenta. `retraso_medio`: días de retraso por pedido, con un decimal (`null` sin pedidos). `404` si no existe |

## Modo admin ([ADR 0015](../adr/0015-modo-admin-con-contrasena.md))

Todas las rutas cuelgan de `/api/admin`. Salvo `…/sesion`, todas piden una sesión de admin vigente: sin ella, `401 sin_sesion_admin` (se comprueba antes que el cuerpo de la petición). Sin `ADMIN_CLAVE_HASH`, `503 admin_no_configurado`. Los cambios pasan además por la comprobación de origen, y todo queda en `logs` con nivel WARNING.

| Método y ruta | Qué hace | Entrada | Respuesta |
| --- | --- | --- | --- |
| `GET /api/admin/sesion` | Si hay sesión de admin y si el modo admin está configurado | — | `{activa, configurado}` |
| `POST /api/admin/sesion` | Entrar con la contraseña | `{clave}` | `{activa, configurado}` y la cookie `remate_admin` (`HttpOnly`, `SameSite=Strict`, ruta `/api/admin`). `401 clave_incorrecta`; `429 demasiados_intentos` tras 5 fallos seguidos desde la misma IP, durante 15 minutos |
| `DELETE /api/admin/sesion` | Cerrar la sesión | — | `204` |
| `GET /api/admin/estado` | Estado del servidor | — | `{necesidades (por estado), archivos: {cantidad, bytes}, disco: {total, libre}, ultima_copia, ia_30_dias: {llamadas, entrada, salida}, avisos_y_errores_7_dias}` |
| `GET /api/admin/registros` | Últimos mensajes de `logs`, del más reciente al más antiguo | `?nivel=INFO\|WARNING\|ERROR\|CRITICAL` (ese y los más graves) y `&limite=1-1000` (100 por defecto) | `[{id, creado_en, nivel, origen, mensaje, traza}]` |
| `POST /api/admin/necesidades/{id}/borrado` | Borra la necesidad con todo lo suyo, también sus archivos. Su código no se vuelve a usar | `{codigo}` (el de la necesidad, para confirmar) | `{codigo, archivos, no_borrados}`. `400` si el código no coincide; `404` si no existe |
| `POST /api/admin/necesidades/{id}/deshacer` | Vuelve al estado anterior, quita lo que guardó ese paso y su línea del historial | `{estado}` (el actual) | La necesidad. `409 estado_cambiado` si ya no está en ese estado; `400` si no hay paso que deshacer o, en «En cotización», si hay ofertas |
| `PATCH /api/admin/necesidades/{id}` | Corrige datos con las reglas del flujo | `{fecha_entrega_prevista?, fecha_entrega_real?, numero_pedido_sap?, comentario_entrega?}` | La necesidad |
| `POST /api/admin/tareas/{nombre}` | Lanza a mano una tarea diaria: `recordatorios`, `avisos` o `caducidad` | `{prueba}` (`true` por defecto: no envía ni borra, dice lo que haría) | `{tarea, prueba, resumen}`. `502 correo_no_disponible` si no se puede conectar con el servidor de correo |

## Reglas comunes de las rutas de estado

- Cada acción solo se permite desde su estado de origen ([estados de una necesidad](estados-necesidad.md)); si no, `409 transicion_no_permitida`.
- Cada cambio de estado se guarda en `CambioEstado` con el `peticionario_id` recibido y la hora.
- Las respuestas de la IA nunca se aplican sin revisión: vuelven como borrador o como oferta pendiente de revisar.
- **Sin paginación** en el panel: el volumen previsto es de decenas de necesidades al mes. Se puede añadir si hace falta.
- **Solo el último `.eml`:** si se vuelve a generar un `.eml` después de editar el borrador, sustituye al anterior.
