# CU-002 — Solicitar ofertas a proveedores

- **Objetivo:** pedir oferta a varios proveedores con un único correo claro, sin que ninguno vea a los demás.
- **Actor principal:** Ingeniero (peticionario)
- **Actores secundarios:** IA (redacta la petición), Proveedor (recibe el correo)
- **Disparador:** la necesidad está creada y hay que pedir precio.
- **Paso del proceso:** 2. Solicitud de ofertas → «En cotización»
- **Prioridad:** Alta
- **Estado:** Implementado

## Precondiciones

- La necesidad está en «Necesidad creada» (CU-001).

## Garantías

- **Si termina bien:** la necesidad está en «En cotización», con los proveedores a los que se pidió oferta y el correo de solicitud listo para enviar.
- **Siempre:** la aplicación no envía nada por su cuenta; el correo lo envía el ingeniero.

## Escenario principal

1. El ingeniero elige solicitar ofertas.
2. El sistema muestra los proveedores activos, de la A a la Z, y los adjuntos de la necesidad.
3. El ingeniero elige los proveedores y revisa qué adjuntos se envían: puede quitar alguno o añadir otros.
4. El ingeniero pide preparar el correo.
5. La IA redacta, a partir de la descripción de la necesidad y del nombre de los adjuntos, qué se pide exactamente: piezas o trabajos, cantidades, materiales, tratamientos y referencias a los planos.
6. El sistema completa el correo con la plantilla (saludo, referencia, petición de precio y plazo, y firma) y lo muestra.
7. El ingeniero revisa el borrador y lo edita si quiere.
8. El ingeniero genera la solicitud.
9. El sistema genera un archivo `.eml` con los proveedores en copia oculta, el asunto común y los adjuntos elegidos; guarda a qué proveedores se pidió oferta y pasa la necesidad a «En cotización».
10. El ingeniero descarga el `.eml`, lo abre con su programa de correo y lo envía.

## Extensiones

- **3a. El proveedor no está en la lista:** el ingeniero lo da de alta con su nombre y su correo (CU-003) y queda elegido.
- **3b. Se eligen menos de 3 proveedores:** el sistema pide un motivo obligatorio y muestra cómo aparecerá en la información para el ERP (CU-005): «Proveedor único por {motivo}.» o «Solo 2 proveedores consultados por {motivo}.».
- **3c. No se elige ningún proveedor:** el sistema no prepara el correo y lo avisa.
- **3d. El ingeniero quiere corregir la necesidad:** vuelve al paso 1 (CU-001), cambia los datos y prepara el correo de nuevo.
- **5a. La IA no está disponible o falla:** el sistema usa la descripción tal cual y avisa. Si la descripción no tiene ninguna cifra, avisa también de que no dice cuántas unidades se piden.
- **5b. Falta un dato importante, como la cantidad:** la IA lo señala en el borrador (por ejemplo, «[INDICAR CANTIDAD]») en lugar de inventarlo.
- **9a. Con los adjuntos, el correo supera 25 MB:** el sistema no lo genera y lo explica, porque el programa de correo no podría enviarlo.
- **10a. El ingeniero necesita el correo otra vez:** puede volver a descargarlo desde la necesidad.

## Reglas de negocio

- Se ofrece la lista completa de proveedores, sin filtros por tipo de material.
- Los proveedores van siempre en copia oculta.
- Lo que se pide sale de la descripción del ingeniero: la IA no añade piezas, cantidades ni requisitos que no estén en ella o en los adjuntos, y escribe cada dato una sola vez.
- El asunto, el saludo, la referencia y la firma los pone la aplicación, no la IA. No se exige a los proveedores ningún formato de oferta; solo se les pide siempre el precio y el plazo de entrega.
- Los correos van en español.
- El nombre de la empresa sale de la variable `EMPRESA_NOMBRE`; si está vacía, se omite.
- El `.eml` lleva la cabecera `X-Unsent: 1`, para que el programa de correo lo abra como un mensaje nuevo listo para enviar.

### Plantilla del correo

```text
Asunto: <AAAAMMDDNN> | <Proyecto> | <Título>

Buenos días:

Desde el departamento de ingeniería de <EMPRESA_NOMBRE> les solicitamos oferta para lo siguiente:

<Petición redactada por la IA a partir de la descripción del ingeniero>

En su oferta, indiquen por favor el precio y el plazo de entrega.

[Si hay adjuntos: «Adjuntamos la documentación disponible.»] Para facilitar el seguimiento, mantengan por favor la referencia <AAAAMMDDNN> en el asunto de su respuesta.

Quedamos a la espera de su respuesta.

Un saludo,
<Nombre y apellido del peticionario>
<EMPRESA_NOMBRE>
```

## Criterios de aceptación

- El `.eml` se abre en el programa de correo con los proveedores en copia oculta, el asunto exacto y los adjuntos.
- El cuerpo pide lo que indica la descripción y termina con la firma del peticionario.
- Si la descripción no indica la cantidad, el borrador lo señala en lugar de inventarla.
- Si la IA falla, se puede generar el `.eml` con la descripción tal cual.
- Sin proveedores elegidos, no se genera el `.eml` ni cambia el estado.
- Con menos de 3 proveedores no se genera sin motivo; con 3 o más, no se pide.
- Quitar un adjunto del correo no lo borra de la necesidad.

## Trazabilidad

- **Diseño:** [modelo de datos](../diseno/modelo-de-datos.md) (Proveedor, ProveedorSolicitado y Adjunto).
- **Código:** `backend/app/servicios/solicitudes.py`, `backend/app/integraciones/ia.py`, `backend/app/integraciones/eml.py` y `frontend/src/componentes/SolicitarOfertas.jsx`.
- **Pruebas:** `backend/tests/test_solicitudes.py`, `backend/tests/test_ia.py` y `frontend/src/paginas/PaginaNecesidad.test.jsx`.
