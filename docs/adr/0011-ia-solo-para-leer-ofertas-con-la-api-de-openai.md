# 0011 — IA con la API de OpenAI, con consumo mínimo

- **Estado:** Aceptada (revisada el 2026-11-05 y el 2026-11-17)
- **Fecha:** 2026-11-04
- **Sustituye a:** [0007](0007-ia-de-produccion-claude-code.md) (Claude Code por terminal en producción) y, del [0003](0003-stack-react-tailwind-python-sqlalchemy.md), el uso de OpenRouter en desarrollo
- **Relacionado con:** CU-002, CU-004, CU-005, [0008](0008-registro-en-la-base-de-datos.md) (registro) y [0010](0010-moneda-de-la-oferta-sin-conversiones.md) (moneda)

> El nombre del archivo conserva el título de la primera versión («IA solo para leer ofertas») para no romper los enlaces. La revisión del 2026-11-05 amplió el alcance; el título actual describe la decisión vigente.

## Contexto y problema

La API de OpenAI se paga por tokens. Hasta entonces la aplicación llamaba a la IA en cuatro sitios, con dos motores distintos (OpenRouter en desarrollo y Claude Code en producción):

| Dónde | Para qué |
| --- | --- |
| CU-002 | Redactar la parte central del correo de petición de oferta |
| CU-004 | Leer cada oferta (correo y adjuntos) y extraer sus datos |
| CU-004 | Resumir la comparativa: ventajas e inconvenientes de cada oferta |
| CU-005 | Redactar la justificación para el ERP y el resumen del correo al adjudicatario |

Solo la lectura de las ofertas necesita de verdad una IA: los correos y los adjuntos (PDF, escaneados, imágenes) llegan en formatos que no se pueden leer con reglas fijas. Las demás tareas trabajan con datos que la aplicación ya tiene ordenados.

## Decisión

1. **Un solo proveedor y un solo camino:** la API de OpenAI (Responses API, biblioteca `openai`) en desarrollo y en producción. Se quitan Claude Code por terminal y OpenRouter. Configuración: `IA_API_KEY`, `IA_MODELO` (`gpt-5-mini`) e `IA_RAZONAMIENTO` (`low`). El modelo se cambia sin tocar el código.
2. **Qué hace la IA y qué hace el código:**

   | Dónde | Con IA | Si la IA no está configurada o falla |
   | --- | --- | --- |
   | CU-002: petición de oferta | Sí. Recibe la descripción de la necesidad y los nombres de los adjuntos (no los archivos) | La descripción del ingeniero tal cual y, si no dice cuántas unidades, un aviso |
   | CU-004: leer cada oferta | Sí. Recibe el correo, los adjuntos y el título y la descripción de la necesidad | Los datos se escriben a mano |
   | CU-004: petición de datos que faltan | Sí. Recibe el proveedor, la necesidad, el número de oferta y la lista de lo que falta | La lista tal cual |
   | CU-004: ventajas e inconvenientes | **No**: el código marca el mejor y el peor valor de cada fila | — |
   | CU-005: justificación y resumen | Sí, en una sola llamada. Recibe la necesidad, las ofertas revisadas, la comparación de la elegida con las demás **ya calculada por el código** y los comentarios de entregas anteriores | El código propone los textos con los datos de la necesidad y de la oferta |

3. **Los hechos los calcula el código, no la IA.** Al adjudicar, el código compara la oferta elegida con las demás y avisa si no es la más barata o la que antes entrega. Esos hechos se pasan a la IA con la instrucción de no contradecirlos y de pedir el motivo («[INDICAR motivo de la elección]») si los datos no lo explican.
4. **Consumo mínimo:**
   - Salida estructurada con un esquema JSON estricto: la respuesta siempre trae los campos pedidos, sin ejemplos de JSON en las instrucciones.
   - Poco razonamiento (`reasoning.effort`, `low` por defecto) y un máximo de 16 000 tokens de salida, que incluye el razonamiento y deja sitio a las ofertas con muchas partidas. Un valor de `IA_RAZONAMIENTO` no admitido impide arrancar.
   - Los PDF van con `detail: low`: el texto se extrae igual y las imágenes de las páginas gastan menos. Word y Excel se pasan a texto en la aplicación.
   - Solo se repite la petición si falla la conexión o el servidor de OpenAI. Una respuesta cortada o no válida no se repite: saldría igual y se pagaría dos veces. Cada intento espera como mucho 120 s.
   - `store=False`: OpenAI no guarda la respuesta para reutilizarla.
   - Cada llamada deja en el registro (tabla `logs`) los tokens de entrada, salida, caché y razonamiento, nunca el contenido.
5. **Límite de llamadas simultáneas:** como mucho 8 llamadas a la vez en toda la aplicación. Una petición sin turno en 2 s no llama a la API y muestra el aviso de que la IA está ocupada. Sin este límite, como la aplicación no tiene inicio de sesión, cualquiera de la red interna podría lanzar llamadas de pago sin control y ocupar todos los hilos del servidor.

## Alternativas consideradas

- **Mantener Claude Code por terminal junto a la API:** dos caminos que probar y mantener.
- **Volver a OpenRouter en desarrollo:** habría que recuperar la configuración de la URL y comprobar si su Responses API, en beta, admite el JSON estricto, los PDF y el razonamiento.
- **La IA solo para leer ofertas** (primera versión de este ADR): todo lo demás lo haría el código, con textos menos elaborados que el ingeniero tendría que completar. No llegó a aplicarse así: el código final mantuvo la IA en la petición y en la adjudicación, con los hechos calculados por el código (punto 3).
- **Un modelo más capaz:** se puede probar cambiando solo `IA_MODELO` si alguna oferta se lee mal.

## Consecuencias

- **Positivas:** un solo proveedor de IA y el mismo código en desarrollo y en producción; la comparativa es inmediata, gratuita y siempre igual; todo funciona aunque la IA falle; el consumo queda medido en el registro.
- **Negativas:** depende de la API de OpenAI y de su saldo: sin clave o sin saldo, las ofertas se escriben a mano y los textos los propone el código. Los PDF escaneados (sin texto) se leen con menos resolución; si alguno no se lee bien, habrá que probar `detail: high`, que cuesta más.
- **Datos que salen de la organización:** las ofertas de los proveedores, la descripción de la necesidad y, al adjudicar, los comentarios de las entregas anteriores. Su envío a OpenAI tiene que estar aprobado por la organización.

## Revisiones

- **2026-11-05:** la IA vuelve a redactar la petición (CU-002) y los textos de la adjudicación (CU-005), con el código calculando los hechos (punto 3). Se fija el modelo `gpt-5-mini`.
- **2026-11-11:** se añade la petición de datos que faltan (CU-004).
- **2026-11-17:** límite de llamadas simultáneas (punto 5), tras una revisión de seguridad. Waitress pasa de 8 a 16 hilos ([ADR 0009](0009-servicio-windows-con-winsw.md)). La IA de la adjudicación recibe los comentarios de entregas anteriores.
- **2026-11-18:** la lectura de ofertas recibe el título y la descripción de la necesidad, para elegir la opción o el tramo de precio que corresponde a lo pedido. El máximo de salida pasa de 4 000 a 16 000 tokens, y el tiempo máximo de 60 a 120 s.
