# CU-005 — Seleccionar proveedor y preparar la información para el ERP

- **Objetivo:** adjudicar la compra a una oferta y tener listo, con el formato exacto, lo que hay que meter en el ERP (SAP) y el correo al proveedor elegido.
- **Actor principal:** Ingeniero (peticionario)
- **Actores secundarios:** IA (redacta la justificación y el resumen de lo adjudicado), Proveedor (recibe la adjudicación)
- **Disparador:** las ofertas están revisadas y el ingeniero decide.
- **Paso del proceso:** 4. Adjudicación → «Pendiente solicitud SAP»
- **Prioridad:** Alta
- **Estado:** Implementado

## Precondiciones

- La necesidad está en «En evaluación» y todas sus ofertas vigentes están revisadas (CU-004).

## Garantías

- **Si termina bien:** la necesidad tiene una oferta adjudicada, el texto para el ERP, la fecha de entrega inicial y el correo de adjudicación, y está en «Pendiente solicitud SAP».
- **Siempre:** las líneas fijas del texto y los formatos de la tabla los pone la aplicación, nunca la IA.

## Escenario principal

1. En la comparativa, el ingeniero elige una oferta.
2. El sistema compara la oferta elegida con las demás revisadas (precio y entrega).
3. La IA redacta la descripción de la inversión, con la necesidad, la oferta elegida, las otras ofertas, esa comparación y los comentarios de entregas anteriores de los proveedores (CU-008). También redacta un resumen de lo que se adjudica, para el correo al proveedor.
4. El sistema muestra:
   - **El texto para el ERP:** las líneas fijas de cabecera y, debajo, la descripción de la inversión.
   - **La tabla para el ERP:** una fila por partida de la oferta, con las columnas `Short Text`, `Quantity requested`, `Valuation Price`, `Delivery Date` y `Requisitioner`.
5. El ingeniero revisa la descripción y la edita si hace falta.
6. El ingeniero confirma la adjudicación.
7. El sistema guarda la oferta adjudicada, el texto y la fecha de entrega inicial, y pasa la necesidad a «Pendiente solicitud SAP».
8. El sistema prepara el correo al proveedor con la plantilla y el resumen de la IA; el ingeniero lo revisa y descarga el `.eml`.
9. El ingeniero copia el texto y las filas de la tabla en el ERP (fuera de la aplicación) y envía el correo desde su programa.

## Extensiones

- **2a. La oferta elegida no es la más barata o no es la que antes entrega:** el sistema avisa con el proveedor que la mejora y la diferencia (por ejemplo, «No es la oferta más barata: X ofrece 1.000,00 EUR sin IVA, 200,00 EUR menos. Explica en la descripción por qué se elige.»). El aviso no impide adjudicar: decide el ingeniero.
- **3a. La IA no está disponible o falla:** el sistema propone una descripción con el título, el proyecto, la descripción de la necesidad, el proveedor elegido y, si se deduce de los datos, el criterio («menor importe sin IVA», «entrega más próxima» o «proveedor único consultado»). Si no se deduce, pide al ingeniero que escriba el motivo. El resumen del correo son las partidas de la oferta, sin precios.
- **3b. La elegida no es la más barata y la IA no encuentra otro motivo en los datos:** la IA escribe «[INDICAR motivo de la elección]» y avisa, en lugar de inventar uno.
- **5a. El ingeniero quiere otra propuesta:** pide prepararla de nuevo y se vuelve a llamar a la IA.
- **5b. El ingeniero cambia de oferta antes de confirmar:** vuelve al paso 1.
- **8a. La oferta la envió otra persona de la empresa del proveedor:** el correo va al proveedor y a esa persona.

## Reglas de negocio

### Texto para el ERP

```text
SOLICITADO POR: <nombre del peticionario>
IR: NO
[Si se pidió oferta a menos de 3 proveedores:] Proveedor único por <motivo>. | Solo 2 proveedores consultados por <motivo>.
<descripción de la inversión>
```

- Las líneas fijas son literales y no se pueden editar.
- La descripción no incluye el código de la necesidad, porque no le sirve a quien la lee en el ERP; si la IA lo escribe, el sistema lo quita. Tampoco remite a los adjuntos, que no se suben al ERP.
- La IA usa tal cual la comparación calculada por el sistema: no puede decir que la elegida es la más barata si no lo es.
- Los comentarios de entregas anteriores (los 5 más recientes de cada proveedor) se pueden usar para justificar la elección, sin exagerarlos.

### Tabla para el ERP

| Columna | Contenido y formato |
| --- | --- |
| `Short Text` | La descripción de la partida. Si solo trae una referencia («R12345»), el título de la necesidad si ya la incluye, o «referencia – título». |
| `Quantity requested` | Con coma decimal y sin ceros sobrantes: `2,5`, `2`. |
| `Valuation Price` | Precio unitario sin IVA, con coma decimal, sin separador de miles y de 2 a 4 decimales: `1250,50`. |
| `Delivery Date` | `DD.MM.AAAA`. Si la partida no trae fecha, la de la oferta. |
| `Requisitioner` | El nombre del proveedor tal como está en la lista de la aplicación, nunca el de la oferta. |

- La tabla se copia con un botón, con las columnas separadas por tabuladores, para pegarla directamente en el ERP. No se genera ningún archivo.
- Los importes van en la moneda de la oferta, sin convertir.

### Fecha de entrega inicial

- La fecha de la oferta elegida. Si la oferta dio un plazo y no una fecha, se cuenta desde el día de la adjudicación, partida a partida si cada una tiene el suyo, y vale la más tardía. Si solo dio un mes, el último viernes de ese mes.

### Correo de adjudicación

```text
Asunto: <AAAAMMDDNN> | <Proyecto> | <Título>

Buenos días:

Les comunicamos que su oferta <número de oferta> para la necesidad «<AAAAMMDDNN> <Título>» ha sido seleccionada.

<Resumen de lo adjudicado, redactado por la IA>

Pueden comenzar con los trabajos. En los próximos días les enviaremos el pedido oficial de SAP.

Fecha de entrega según su oferta: <DD/MM/AAAA>.   [o: Plazo de entrega según su oferta: <plazo>.]

Un saludo,
<Nombre y apellido del peticionario>
<EMPRESA_NOMBRE>
```

- Si el proveedor dio un plazo o un mes, el correo repite lo que dijo, no una fecha calculada.
- Si no hay número de oferta, se omite.

## Criterios de aceptación

- Las dos primeras líneas del texto son siempre `SOLICITADO POR: <peticionario>` e `IR: NO`; con menos de 3 proveedores, la tercera explica el motivo y la IA no lo repite.
- Un precio de 1250,5 aparece como `1250,50`; uno de 1000, como `1000,00`.
- Una fecha del 15/11/2026 aparece como `15.11.2026`.
- Una cantidad de 2,5 aparece como `2,5`; una de 2, como `2`.
- Si la oferta dice «Ficmec S.L.» y en la lista el proveedor es «FICMEC», Requisitioner es `FICMEC`.
- La tabla tiene una fila por partida de la oferta elegida.
- Una partida «R12345» en la necesidad «Útil R12345» da Short Text «Útil R12345».
- Al elegir una oferta más cara, se avisa siempre, redacte la IA o no.
- Con un plazo de «3 semanas», el correo dice «Plazo de entrega según su oferta: 3 semanas.».
- El `.eml` va solo al proveedor adjudicatario (y al remitente de su empresa, si es otro).
- Tras confirmar, la necesidad está en «Pendiente solicitud SAP» con la fecha de entrega inicial guardada.

## Trazabilidad

- **Diseño:** [modelo de datos](../diseno/modelo-de-datos.md) (Necesidad, Oferta y LineaOferta) y [ADR 0011](../adr/0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md).
- **Código:** `backend/app/servicios/adjudicacion.py`, `backend/app/api/adjudicacion.py`, `backend/app/integraciones/ia.py`, `frontend/src/componentes/Adjudicar.jsx`, `frontend/src/componentes/InformacionSap.jsx`, `frontend/src/componentes/TablaSap.jsx` y `frontend/src/sap.js`.
- **Pruebas:** `backend/tests/test_adjudicacion.py` y `frontend/src/componentes/Adjudicar.test.jsx`.
