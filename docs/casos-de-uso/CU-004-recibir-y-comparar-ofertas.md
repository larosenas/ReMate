# CU-004 — Recibir y comparar ofertas con IA

- **Objetivo:** pasar las ofertas de los proveedores, cada una en su formato, a datos comparables y revisados.
- **Actor principal:** Ingeniero (peticionario)
- **Actores secundarios:** IA (lee las ofertas y redacta la petición de datos que faltan), Proveedor (envía la oferta y, si hace falta, los datos que faltan)
- **Disparador:** llegan las respuestas de los proveedores a la solicitud de ofertas.
- **Paso del proceso:** 3. Ofertas → «En evaluación»
- **Prioridad:** Alta
- **Estado:** Implementado

## Precondiciones

- La necesidad está en «En cotización» o en «En evaluación» (CU-002).

## Garantías

- **Si termina bien:** cada oferta está guardada con su correo, sus adjuntos, los datos revisados por el ingeniero y la respuesta original de la IA; la necesidad está en «En evaluación» y la comparativa permite elegir proveedor (CU-005).
- **Siempre:** ningún correo subido se pierde aunque la IA falle, y lo escrito a mano por el ingeniero nunca lo sustituye una lectura automática.

## Escenario principal

1. El ingeniero añade una oferta: sube el correo del proveedor (`.eml` o `.msg`, también arrastrado desde Outlook).
2. El sistema lee el correo sin guardarlo todavía, propone sus adjuntos con su tipo (PDF, Excel, Word, imagen u otro) y reconoce al proveedor por el remitente.
3. El ingeniero confirma el proveedor, quita los adjuntos que no importan (logotipos, condiciones generales…) o añade otros, y guarda.
4. El sistema guarda la oferta como «Sin analizar», con la fecha de envío, el remitente, el asunto y el cuerpo del correo.
   Los pasos 1 a 4 se repiten con cada oferta que llega.
5. Cuando tiene las ofertas, el ingeniero pide analizar y comparar.
6. El sistema pasa la necesidad a «En evaluación» y envía a la IA, a la vez, todas las ofertas sin analizar, con el título y la descripción de la necesidad.
7. La IA devuelve los datos de cada oferta en un formato estructurado: número de oferta, moneda, partidas (descripción, cantidad, precio unitario sin IVA y plazo), importe total sin IVA, plazo o fecha de entrega, condiciones de pago, otras condiciones, información adicional, idioma del proveedor y avisos.
8. El sistema convierte los plazos en fechas, comprueba los datos y muestra la comparativa: proveedores en columnas y, en filas, precio sin IVA, entrega, retrasos del proveedor (CU-010), comentarios de entregas anteriores, condiciones de pago, otras condiciones e información adicional.
9. El ingeniero revisa cada oferta: corrige lo que haga falta, con los avisos del sistema a la vista, y la marca como revisada.
10. Con todas las ofertas revisadas, el sistema marca en verde el mejor valor y en rojo el peor de precio, entrega y retrasos, y permite elegir una (CU-005).

## Extensiones

- **1a. El archivo no es un correo válido o está dañado:** el sistema lo rechaza y explica cómo guardarlo de nuevo desde el programa de correo.
- **1b. La oferta viene solo en el cuerpo del correo o solo en un adjunto:** se acepta; basta con uno de los dos.
- **2a. El remitente no es el correo del proveedor, pero es de su misma empresa** (mismo dominio o un subdominio): se reconoce al proveedor. Nunca con dominios de correo públicos. Si varios proveedores comparten dominio, se elige el que estaba entre los solicitados; si sigue habiendo varios, se pregunta.
- **2b. El proveedor no está entre los solicitados:** el ingeniero lo elige de la lista o lo da de alta (CU-003).
- **3a. El proveedor ya tenía oferta:** el ingeniero elige entre sustituir la anterior, que deja de contar, o añadir el correo como respuesta a esa oferta (ver «Datos que faltan»).
- **5a. No hay ofertas:** no se puede analizar.
- **6a. Ya se está analizando esa necesidad** (otra pestaña u otra persona): el sistema lo dice y no vuelve a llamar a la IA.
- **6b. La IA está ocupada con otras peticiones:** la oferta queda «Sin analizar» con un aviso para intentarlo en un momento.
- **7a. La IA falla con una oferta:** el sistema avisa con el nombre del proveedor y guarda las demás. El ingeniero puede volver a pedir la lectura de esa oferta o rellenar los datos a mano.
- **7b. La IA no encuentra un dato:** el campo queda vacío y señalado.
- **8a. Un plazo no se puede interpretar:** se guarda el texto y se pide la fecha a mano.
- **8b. Las ofertas vienen en monedas distintas:** el sistema lo avisa y no marca el mejor ni el peor precio; el ingeniero convierte a mano si lo necesita.
- **9a. Las partidas no suman el total, o la fecha de entrega es anterior al correo o está a más de 3 años:** el sistema lo avisa mientras se revisa.
- **9b. Faltan datos en la oferta:** el ingeniero pide los datos que faltan (ver más abajo).
- **10a. Llega otra oferta estando en evaluación:** se añade y se analiza igual; las marcas de mejor y peor se quitan hasta revisarla.
- **10b. Sobra una oferta** (subida por error, por ejemplo): mientras no se haya elegido proveedor, el ingeniero la borra y deja de contar.

### Datos que faltan

1. El sistema calcula qué falta en la oferta: importe, moneda (si la IA no la vio), entrega, condiciones de pago, partidas o condiciones sin especificar.
2. El ingeniero pide los datos que faltan. La IA redacta la lista con el nombre del proveedor, el título de la necesidad, el número de oferta y lo que falta; el sistema añade el saludo, la referencia y la firma.
3. El ingeniero revisa el borrador y descarga el `.eml`, dirigido al proveedor y, si es otra persona de su empresa, al remitente de la oferta. El borrador no se guarda.
4. Cuando el proveedor responde, el ingeniero sube su correo como respuesta a esa oferta (extensión 3a).
5. La IA lee solo la respuesta, junto con la lista de lo que faltaba, y el sistema la combina con la oferta: rellena lo vacío y cambia lo que la respuesta dice distinto, con un aviso de cada cambio («antes → ahora»). Lo que la respuesta no menciona se queda como estaba.
6. La oferta vuelve a «Sin revisar» para que el ingeniero compruebe el resultado.

Si la IA falla al redactar, el correo lleva la lista tal cual. Si la IA falla al leer la respuesta, los archivos se guardan y se avisa. Si el proveedor no escribe en español, el correo va en inglés.

## Reglas de negocio

### Lectura con IA

- La IA solo propone: para elegir cualquier oferta hay que haber revisado todas, también las que la IA no pudo leer.
- Para dar una oferta por revisada hacen falta el importe sin IVA y la fecha de entrega. Si después se borra uno de los dos, deja de estar revisada.
- La IA recibe el cuerpo del correo y los adjuntos elegidos. Los PDF y las imágenes se envían como archivo; los Word y Excel se pasan antes a texto en la aplicación.
- El contenido de las ofertas son datos, no instrucciones: si una oferta contiene instrucciones dirigidas a la IA, la IA las ignora y lo avisa.
- La IA escribe en español el plazo, las condiciones, los avisos y las descripciones, sin traducir referencias ni nombres propios.
- Con el título y la descripción de la necesidad, la IA elige la opción o el tramo de precio que corresponde a lo pedido y avisa de lo que la oferta no incluye.
- No se tiene en cuenta el membrete ni el pie del documento, ni los datos de la empresa cliente, y el código del asunto no se toma como número de oferta.

### Importes

- Todos los importes son sin IVA. La aplicación no lee ni calcula el importe con IVA.
- Cada oferta tiene su moneda (código ISO de tres letras), EUR por defecto con aviso si no está clara. No se convierten importes.
- La IA da el precio de una unidad: si la oferta lo da por 100 o por 1000, lo divide y avisa. Si una partida solo trae su total, se divide entre la cantidad.
- Los descuentos que vienen como partida aparte (con precio negativo) no se guardan, porque el ERP no admite partidas negativas; se avisa con su importe para repartirlo o pedir los precios con el descuento aplicado.
- Si la oferta no da el importe total, se usa la suma de las partidas, con aviso.

### Plazos y fechas

- Un plazo relativo se cuenta desde la fecha del correo de la oferta. Los días laborables son de lunes a viernes, sin festivos.
- Con un rango («18-20 días») se toma el número más alto. Con varios plazos en el texto, el más largo. No cuentan los días de validez, pago o garantía.
- Se entienden decimales («1,5 semanas»), «mes y medio», horas («48 h»), números en letra, sumas («2 semanas + 3 días») y plazos en inglés.
- Si la oferta solo da un mes, la fecha es el último viernes de ese mes; si solo da una semana del calendario («KW 50»), el viernes de esa semana. Al proveedor se le repite lo que dijo, no la fecha calculada.
- Una fecha concreta manda sobre un mes, y un mes sobre un plazo.
- Si cada partida trae su plazo, cada una tiene su fecha. Si la oferta no da una fecha para todo, la de la oferta es la más tardía, porque el pedido no está completo hasta que llega todo.
- Si el proveedor da un plazo y no una fecha, la fecha calculada se muestra como orientación debajo del plazo.

### Comparativa

- El mejor y el peor valor solo se marcan con todas las ofertas vigentes revisadas. El precio solo se marca entre ofertas en la misma moneda. Los retrasos se comparan con el retraso medio sin redondear.
- Las otras condiciones no se marcan, porque ningún valor es siempre mejor.
- Otras condiciones: embalaje; Incoterm o condiciones de entrega; transporte; qué incluye el precio; validez de la oferta; revisión por precio de materia prima; utillaje; tratamientos térmicos o recubrimientos; y condiciones de pedido. Cada una con un estado (especificado, incluido, no incluido, no aplica o no especificado) y un texto.

### Límites

- Un correo `.eml` con más de 30 niveles de partes anidadas, un `.msg` dañado o un `.msg` cuyo cuerpo solo viene en RTF comprimido no se leen.
- Un Excel se pasa a texto con límites (20 MB descomprimidos en total, 10 MB por cada parte interna y 50 hojas); si los supera, ese adjunto se salta con un aviso.
- La IA lee como mucho 4 ofertas a la vez por necesidad, y la aplicación hace como mucho 8 llamadas a la IA a la vez en total.

## Criterios de aceptación

- Un `.msg` de Outlook se lee igual que un `.eml`, con sus adjuntos y sin las imágenes del cuerpo.
- Al subir `oferta.pdf`, el tipo propuesto es «PDF».
- Una oferta enviada por otra persona del mismo dominio se asocia a su proveedor, pero nunca por un dominio de correo público.
- Al subir una oferta no se llama a la IA; al analizar se leen todas las pendientes y no se repiten las ya leídas ni se pisa lo escrito a mano.
- Con una oferta que dice «4 semanas» y un correo del 22/10/2026, la fecha estimada es el 19/11/2026.
- Si las partidas no suman el total, se muestra un aviso.
- Si la IA falla con una oferta, las demás se guardan y esa se puede completar a mano.
- No se puede elegir ninguna oferta hasta revisarlas todas.
- El mejor y el peor valor solo se marcan con todas las ofertas revisadas, y el precio solo entre ofertas en la misma moneda.
- Una segunda oferta del mismo proveedor sustituye a la anterior en la comparativa.
- Se puede borrar una oferta en «En cotización» y «En evaluación», pero no después.
- La respuesta del proveedor completa la oferta, cambia lo que dice distinto con un aviso y no borra las partidas que no menciona.
- El correo de datos que faltan solo se ofrece si falta algo y no se guarda.
- Las pruebas automáticas no llaman a la IA real.

## Trazabilidad

- **Diseño:** [modelo de datos](../diseno/modelo-de-datos.md) (Oferta, LineaOferta y Adjunto), [ADR 0010](../adr/0010-moneda-de-la-oferta-sin-conversiones.md) (moneda), [ADR 0011](../adr/0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md) (IA) y [ADR 0013](../adr/0013-correos-msg-con-lector-propio.md) (lector de `.msg`).
- **Código:** `backend/app/servicios/ofertas.py`, `backend/app/servicios/comparativa.py`, `backend/app/servicios/condiciones.py`, `backend/app/servicios/peticion_datos.py`, `backend/app/integraciones/ia.py`, `backend/app/integraciones/correos_entrada.py`, `backend/app/integraciones/correos_msg.py`, `backend/app/integraciones/adjuntos_ia.py`, `frontend/src/componentes/SeccionOfertas.jsx`, `frontend/src/componentes/SubirOferta.jsx`, `frontend/src/componentes/EditorOferta.jsx` y `frontend/src/componentes/PedirDatos.jsx`.
- **Pruebas:** `backend/tests/test_ofertas.py`, `backend/tests/test_condiciones.py`, `backend/tests/test_monedas.py`, `backend/tests/test_correos_msg.py`, `backend/tests/test_adjuntos_ia.py`, `backend/tests/test_ia.py`, `frontend/src/componentes/SeccionOfertas.test.jsx`, `frontend/src/componentes/PedirDatos.test.jsx`, `frontend/src/componentes/SelectorArchivo.test.jsx` y `frontend/src/componentes/Monedas.test.jsx`.
