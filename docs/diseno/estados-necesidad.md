# Estados de una necesidad

Diagrama: [estados de una necesidad](../diagramas/salidas/estados-necesidad.png) (fuente en `docs/diagramas/fuentes/estados-necesidad.puml`). Los pasos se describen en detalle en los [casos de uso](../casos-de-uso/README.md).

## Transiciones

| Desde | Acción (quién) | Hacia | Qué hace la aplicación | Condición |
| --- | --- | --- | --- | --- |
| — | 1. Crear necesidad (ingeniero) | **Necesidad creada** | Asigna el código `AAAAMMDDNN` y guarda los adjuntos | Título, proyecto, peticionario y descripción obligatorios |
| Necesidad creada | 2. Elegir proveedores y generar la solicitud (ingeniero) | **En cotización** | Genera un `.eml` con los proveedores en copia oculta, el asunto `AAAAMMDDNN \| Proyecto \| Título` y los adjuntos | Al menos un proveedor; con menos de 3, un motivo |
| En cotización | Añadir oferta (ingeniero) | En cotización | La guarda «Sin analizar». Si el proveedor ya tenía oferta, la nueva la sustituye o se añade como respuesta | — |
| En cotización o En evaluación | Borrar una oferta (ingeniero) | (sin cambio) | La oferta deja de contar en la comparativa | — |
| En cotización | 3. Analizar y comparar (ingeniero) | **En evaluación** | La IA lee a la vez las ofertas sin analizar y sale la comparativa | Al menos una oferta |
| En evaluación | Añadir ofertas, analizarlas o revisarlas (ingeniero) | En evaluación | Recalcula la comparativa. No se descarta ninguna oferta hasta elegir una | — |
| En evaluación | 4. Seleccionar proveedor (ingeniero) | **Pendiente solicitud SAP** | Prepara el texto y la tabla para el ERP, fija la fecha de entrega inicial y genera el `.eml` al adjudicatario | Todas las ofertas vigentes revisadas; la elegida, con al menos una partida |
| Pendiente solicitud SAP | 5. Confirmar la solicitud en el ERP (ingeniero) | **Pendiente pedido SAP** | Guarda la fecha de entrega prevista y avisa por correo a los avisados del pedido | Fecha prevista |
| Pendiente pedido SAP | 6. Enviar el pedido oficial (ingeniero) | **Pendiente entrega** | Genera el `.eml` al proveedor con el pedido adjunto, vinculado a su número de oferta | Pedido adjunto y número de oferta |
| Pendiente entrega | Registrar retraso (ingeniero) | Pendiente entrega | Guarda la nueva fecha y el motivo, y prepara de nuevo el recordatorio | Motivo y fecha posterior a la prevista |
| Pendiente entrega | (automático) 7 días antes de la fecha prevista | Pendiente entrega | Envía el recordatorio al peticionario | Recordatorio no enviado para esa fecha |
| Pendiente entrega | 7. Confirmar entrega (ingeniero) | **Entregado** | Guarda la fecha de entrega real y el comentario, y cierra el caso | Fecha real no futura |
| Cualquiera salvo Entregado | Cancelar (ingeniero) | **Cancelada** | Guarda el motivo y cierra el caso conservando el histórico | Motivo obligatorio |

Cada cambio de estado se registra en `CambioEstado`, con el peticionario y la fecha.

## Reglas

1. Se pasa a evaluación cuando lo decide el ingeniero.
2. No se vuelve atrás: en evaluación se siguen añadiendo ofertas según llegan y no se descarta ninguna hasta elegir una. Solo el [modo admin](../adr/0015-modo-admin-con-contrasena.md) puede deshacer un paso.
3. Una necesidad se puede cancelar en cualquier estado salvo «Entregado», con un motivo.
4. Los retrasos solo se registran en «Pendiente entrega». En el paso 5 se puede cambiar la fecha prevista, pero no cuenta como retraso: la diferencia queda entre `fecha_entrega_inicial` y `fecha_entrega_prevista`.
5. Una segunda oferta del mismo proveedor sustituye a la anterior. En «En cotización» y «En evaluación» se pueden borrar ofertas.
