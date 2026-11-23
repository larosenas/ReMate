# CU-007 — Enviar el pedido oficial al proveedor

- **Objetivo:** hacer llegar al proveedor el pedido oficial del ERP (SAP), vinculado a su oferta.
- **Actor principal:** Ingeniero (peticionario)
- **Actores secundarios:** Proveedor (recibe el pedido)
- **Disparador:** el ERP ha aprobado el pedido y el ingeniero tiene el documento oficial (normalmente un PDF).
- **Paso del proceso:** 6. Pedido al proveedor → «Pendiente entrega»
- **Prioridad:** Alta
- **Estado:** Implementado

## Precondiciones

- La necesidad está en «Pendiente pedido SAP» (CU-006).

## Garantías

- **Si termina bien:** la necesidad está en «Pendiente entrega», con el pedido guardado, el número de oferta confirmado y el correo al proveedor, que se puede volver a descargar.
- **Siempre:** la aplicación no envía el correo; lo envía el ingeniero.

## Escenario principal

1. El ingeniero elige enviar el pedido al proveedor y sube el pedido oficial.
2. El sistema lee el número de pedido del PDF y propone el número de oferta del proveedor.
3. El ingeniero confirma o corrige los dos números e indica quién hace el envío.
4. El sistema prepara el correo con una plantilla fija, sin IA.
5. El ingeniero revisa el correo y lo retoca si quiere.
6. El ingeniero genera el correo.
7. El sistema guarda el pedido y el `.eml`, con el pedido adjunto, y pasa la necesidad a «Pendiente entrega». Los avisos semanales a los avisados (CU-006) dejan de enviarse.
8. El ingeniero descarga el `.eml` y lo envía desde su programa de correo.

## Extensiones

- **1a. Sin archivo o con más de 25 MB:** el sistema no prepara el correo y lo explica.
- **2a. El PDF no indica el número de pedido o no es un pedido del ERP:** el campo queda vacío; el número de pedido es opcional.
- **2b. La oferta adjudicada no tiene número:** el sistema lo busca en el nombre del archivo con el que el proveedor envió su oferta (por ejemplo, `Oferta HN-1182.pdf` → «HN-1182»). Si tampoco, el ingeniero lo escribe.
- **3a. Sin número de oferta:** el sistema no genera el correo y lo pide.
- **5a. El ingeniero cambia el archivo o los números:** el texto retocado se descarta y se prepara de nuevo.
- **5b. Cuerpo vacío:** no se genera el correo.
- **6a. La oferta la envió otra persona de la empresa del proveedor:** el correo va al proveedor y a esa persona.

## Reglas de negocio

- El número de oferta es obligatorio, porque vincula el pedido con la oferta. Se guarda en la oferta adjudicada.
- El número de pedido se lee sin IA y sin dependencias externas: el sistema busca en el texto del PDF la frase «PURCHASE ORDER NO.» seguida de 6 a 12 cifras. Nunca sustituye un número escrito a mano, y el ingeniero lo debe comprobar.
- En el nombre del archivo, el número de oferta es el fragmento más largo con letras y al menos 2 cifras, o un número de 3 cifras o más, sin contar el código de la necesidad.

### Plantilla del correo

```text
Asunto: <AAAAMMDDNN> | <Proyecto> | <Título>

Buenos días:

Les adjuntamos el pedido <número de pedido | oficial de SAP> correspondiente a su oferta <número de oferta>, para la necesidad «<AAAAMMDDNN> <Título>».

Fecha de entrega prevista: <DD/MM/AAAA>. Si no pueden cumplirla, avísennos lo antes posible.

Por favor, indiquen el número de pedido en el albarán y en la factura.

Un saludo,
<Nombre y apellido del peticionario>
<EMPRESA_NOMBRE>
```

## Criterios de aceptación

- Si la oferta adjudicada tiene número, se propone ese número; si no, el del nombre del archivo de la oferta.
- Al elegir el PDF del pedido se propone su número, sin sustituir uno escrito a mano.
- Sin número de oferta, sin pedido o con el cuerpo vacío, no se genera el correo.
- El `.eml` va al proveedor adjudicatario, lleva el pedido adjunto y el asunto común de la necesidad.
- Al generar el correo, la necesidad pasa a «Pendiente entrega» con su cambio de estado, y solo se puede hacer desde «Pendiente pedido SAP».
- El pedido y el `.eml` se pueden descargar después desde la necesidad.

## Trazabilidad

- **Diseño:** [estados de una necesidad](../diseno/estados-necesidad.md) y [API](../diseno/api.md).
- **Código:** `backend/app/servicios/pedido_sap.py`, `backend/app/api/pedido_sap.py`, `backend/app/integraciones/pedido_pdf.py` y `frontend/src/componentes/EnviarPedidoSap.jsx`.
- **Pruebas:** `backend/tests/test_pedido_sap_envio.py`, `frontend/src/componentes/EnviarPedidoSap.test.jsx` y `frontend/src/paginas/PaginaNecesidad.test.jsx`.
