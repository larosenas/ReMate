# Modelo de datos

Diagrama: [modelo de datos](../diagramas/salidas/modelo-de-datos.png) (fuente en `docs/diagramas/fuentes/modelo-de-datos.puml`). Implementado con modelos de SQLAlchemy y migraciones de Alembic ([ADR 0003](../adr/0003-stack-react-tailwind-python-sqlalchemy.md)). Los conceptos del negocio en los que se basa están en el [modelo de dominio](modelo-de-dominio.md).

## Entidades

| Entidad | Qué guarda | Paso del proceso |
| --- | --- | --- |
| **Peticionario** | Persona de ingeniería que hace el trámite: nombre completo y correo, único entre los no eliminados. Se puede desactivar y, después, eliminar con motivo | 1 |
| **Proveedor** | Nombre y un único correo, único entre los no eliminados. Se puede desactivar y, después, eliminar con motivo | 2 |
| **AvisadoPedidoSap** | Persona a la que se avisa cuando hay que emitir el pedido en el ERP: nombre y correo. Sin relaciones con otras tablas | 5 |
| **Necesidad** | El trámite completo: código `AAAAMMDDNN`, título, proyecto, descripción, peticionario, estado, motivo de pocos proveedores, oferta adjudicada, texto para el ERP, fechas de entrega (inicial, prevista y real), número de pedido, comentario de la entrega, fechas de envío del recordatorio y del aviso del paso 5, y motivo de cancelación | 1 a 7 |
| **ProveedorSolicitado** | A qué proveedores se pidió oferta | 2 |
| **Oferta** | La respuesta de un proveedor: fecha, remitente y asunto del correo, número de oferta, moneda, importe total sin IVA, plazo de entrega (texto original y fecha), condiciones de pago, otras condiciones (JSONB), información adicional, la respuesta original de la IA (JSON), si el ingeniero la ha revisado y su estado (`vigente`, `sustituida` o `borrada`) | 3 |
| **LineaOferta** | Cada partida de la oferta: descripción (el *Short Text* del ERP), cantidad, precio unitario sin IVA, fecha de entrega y, si lo da, su propio plazo | 3, 4 |
| **Adjunto** | Archivos guardados, con su tipo: adjuntos de la necesidad, correos de oferta y sus adjuntos (con el formato que indica el ingeniero), respuestas de los proveedores, los `.eml` de solicitud, adjudicación y envío del pedido, y el pedido del ERP. Si el archivo caducó, la fecha en que se borró | 1 a 6 |
| **Retraso** | Cada retraso de la entrega: fecha anterior, fecha nueva (siempre posterior), motivo, quién lo registra y cuándo | 7 |
| **CambioEstado** | Historial de estados: de qué estado a cuál, quién (peticionario) y cuándo | Todos |
| **CambioPeticionario** | Paso de una necesidad en curso a otro peticionario, al dar de baja definitiva al que la llevaba | 1 a 7 |
| **CodigoBorrado** | Códigos de las necesidades borradas con el modo admin, que no se vuelven a usar | — |
| **Log** | El registro de la aplicación: fecha y hora, nivel, origen, mensaje y traza. Sin relaciones con otras tablas ([ADR 0008](../adr/0008-registro-en-la-base-de-datos.md)) | — |

## Reglas que recoge el modelo

- **Código `AAAAMMDDNN`:** único; `NN` es el orden de creación dentro del día. La base de datos impide duplicados aunque dos personas creen una necesidad a la vez.
- **Proveedor adjudicado:** es el de la oferta adjudicada (`Necesidad.oferta_adjudicada_id → Oferta.proveedor_id`). Es el nombre que va en *Requisitioner* en el ERP, no el que aparezca en la oferta.
- **Importes:** todos sin IVA, en la moneda de la oferta ([ADR 0010](../adr/0010-moneda-de-la-oferta-sin-conversiones.md)), como número decimal exacto (no de coma flotante). La coma decimal y el formato `DD.MM.AAAA` se aplican solo al preparar la información para el ERP.
- **Cantidades:** número decimal exacto; en el ERP se escriben con coma decimal y sin ceros sobrantes (`2,5`; `2`).
- **Plazo de entrega:** se guarda el texto tal como lo da el proveedor («4 semanas») y, siempre, una fecha. Si el plazo es relativo, se cuenta desde la fecha en que el proveedor envió el correo (`fecha_correo`), no desde el día en que se registra en la aplicación, para que un retraso en revisarla no altere el plazo. Esa fecha solo sirve para comparar: al adjudicar, el plazo se cuenta desde ese día. Si cada partida trae su plazo, se guarda en la partida.
- **Un proveedor por necesidad:** si hay piezas para proveedores distintos, se crea una necesidad por proveedor.
- **Estados:** los 7 del proceso más «Cancelada» (ver [estados de una necesidad](estados-necesidad.md)).
- **Retrasos:** solo se registran en «Pendiente entrega». El cambio de fecha del paso 5 se ve comparando `fecha_entrega_inicial` con `fecha_entrega_prevista`.
- **Ofertas sustituidas o borradas:** no se eliminan de la base de datos; cambia su `estado_oferta`, y solo las vigentes cuentan en la comparativa. Así queda constancia de las versiones anteriores.
- **Histórico de retrasos por proveedor:** se obtiene uniendo `Retraso` con la necesidad y su oferta adjudicada.
- **Recordatorio y avisos:** `recordatorio_enviado_en` y `aviso_pedido_sap_en` evitan enviar dos veces el mismo correo. Un retraso o un cambio de peticionario vacían `recordatorio_enviado_en`.
- **Nada se borra en el uso normal:** proveedores y peticionarios se desactivan (`activo = falso`) o se eliminan con motivo (`eliminado_en`), sin borrar la fila. Solo el modo admin borra necesidades ([ADR 0015](../adr/0015-modo-admin-con-contrasena.md)).
- **Archivos:** se guardan en disco; la base de datos solo guarda su ruta y sus datos. Los de las necesidades cerradas caducan, pero la fila se queda con `caducado_en` ([ADR 0014](../adr/0014-caducidad-de-archivos-y-copias.md)).

## Migraciones

Cada caso de uso añadió sus tablas y columnas con una migración de Alembic (`backend/migraciones/versions/`):

| Cambio | Origen | Migración |
| --- | --- | --- |
| `Peticionario` y `Proveedor` | CU-003 | `e93c7ac66e88` |
| Baja definitiva (`eliminado_en`, `motivo_eliminacion`) e índice único parcial del correo | CU-003 | `ea6bbc70eba5` |
| `Necesidad`, `Adjunto` y `CambioEstado` | CU-001 | `48e04ae59807` |
| `ProveedorSolicitado` | CU-002 | `22b3401af4f1` |
| `Oferta` y `LineaOferta` | CU-004 | `0fd55d61d35e` |
| `Necesidad.motivo_cancelacion` | Cancelar | `a3c5621a5ca3` |
| Adjudicación: `oferta_adjudicada_id`, `texto_sap` y `fecha_entrega_inicial` | CU-005 | `71f61f8917cf` |
| `Necesidad.fecha_entrega_prevista` | CU-006 | `294b63f14f2c` |
| `Necesidad.numero_pedido_sap` | CU-007 | `2ae4fdc4109c` |
| `Retraso` y `Necesidad.fecha_entrega_real` | CU-008 | `55e5a21bc9f4` |
| `Necesidad.recordatorio_enviado_en` | CU-009 | `eb5f07e3d753` |
| `CambioPeticionario` | CU-003 | `9918cb3cea0d` |
| `Log` | ADR 0008 | `a8804a7f53fc` y `d91f26b83a04` |
| `Oferta.moneda` | ADR 0010 | `c47e24f16d32` |
| Quita el importe con IVA: todos los importes pasan a ser sin IVA | CU-004 | `3437cbe3bc83` |
| Respuestas de los proveedores (tipo de adjunto `respuesta_oferta`) | CU-004 | `c4e8a2d6f913` |
| `Oferta.condiciones` | CU-004 | `8b2d4f6a1c37` |
| `Necesidad.motivo_pocos_proveedores` | CU-002 | `5e1a7c3b9d20` |
| `LineaOferta.plazo_entrega_texto` | CU-004 | `42a815165416` |
| `CodigoBorrado` | ADR 0015 | `e1ca0f1cb0b1` |
| `Adjunto.caducado_en` | ADR 0014 | `e63d4108ff5e` |
| `AvisadoPedidoSap`, `Necesidad.aviso_pedido_sap_en` y `Necesidad.comentario_entrega` | CU-003, CU-006 y CU-008 | `8199666dcdb7` |
