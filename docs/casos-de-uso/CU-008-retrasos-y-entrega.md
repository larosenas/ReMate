# CU-008 — Registrar retrasos y confirmar la entrega

- **Objetivo:** seguir la entrega del pedido hasta que llega, con un histórico fiable del cumplimiento de cada proveedor.
- **Actor principal:** Ingeniero (peticionario)
- **Disparador:** el proveedor avisa de un retraso, o llega el pedido.
- **Paso del proceso:** 7. Entrega → «Entregado»
- **Prioridad:** Alta
- **Estado:** Implementado

## Precondiciones

- La necesidad está en «Pendiente entrega» (CU-007).

## Garantías

- **Si termina bien:** la necesidad está en «Entregado», con su fecha de entrega real, y sus retrasos cuentan en el histórico del proveedor (CU-010).
- **Siempre:** cada retraso queda registrado con su motivo, quién lo registró y cuándo.

## Escenario principal: registrar un retraso

1. El proveedor avisa de que no llega a la fecha prevista.
2. El ingeniero registra el retraso con la nueva fecha y el motivo, e indica quién lo registra.
3. El sistema guarda el retraso (fecha anterior, fecha nueva, motivo, quién y cuándo) y la nueva fecha pasa a ser la prevista. El recordatorio de entrega (CU-009) se prepara de nuevo para esa fecha.

Se puede repetir tantas veces como haga falta.

## Escenario principal: confirmar la entrega

1. Llega el pedido y el ingeniero confirma la entrega.
2. El sistema propone como fecha real la de hoy.
3. El ingeniero la confirma o la cambia, indica quién confirma y, si quiere, deja un comentario (por ejemplo, que el paquete llegó dañado).
4. El sistema guarda la fecha real y el comentario, pasa la necesidad a «Entregado» y registra el cambio de estado. El caso queda cerrado.

## Extensiones

- **Retraso 2a. Sin motivo o sin fecha:** no se registra.
- **Retraso 2b. La nueva fecha no es posterior a la prevista:** no se registra; un retraso solo puede retrasar. Si el proveedor adelanta la entrega, se confirma cuando llegue.
- **Entrega 3a. La fecha real es posterior a la prevista:** el sistema pide el motivo y lo registra como un retraso más, para que el histórico del proveedor sea completo.
- **Entrega 3b. La fecha real es futura o anterior a la creación de la necesidad:** no se confirma.
- **Entrega 3c. El comentario supera los 1000 caracteres:** no se confirma y se explica.
- **Entrega 4a. El pedido llegó en la fecha prevista o antes:** los retrasos avisados se marcan «No se cumplió: llegó a tiempo» y no cuentan en el histórico del proveedor.

## Reglas de negocio

- Los retrasos solo se registran en «Pendiente entrega»; el cambio de fecha del paso 5 (CU-006) no cuenta como retraso.
- Una necesidad entregada ya no admite cambios ni cancelación.
- El comentario de la entrega aparece en la comparativa de futuras ofertas de ese proveedor (CU-004) y en su histórico (CU-010), y lo recibe la IA al redactar la adjudicación (CU-005). No cambia qué oferta se marca como mejor o peor.
- Los datos del histórico no caducan. Los archivos de las necesidades cerradas sí, pasado un tiempo ([ADR 0014](../adr/0014-caducidad-de-archivos-y-copias.md)).

## Criterios de aceptación

- Con la fecha prevista el 20/11/2026, un retraso al 27/11/2026 con motivo se guarda y la fecha prevista pasa a ser el 27/11/2026.
- Un retraso sin motivo, sin fecha o con una fecha que no es posterior a la prevista no se registra.
- Al confirmar la entrega se propone la fecha de hoy y la necesidad pasa a «Entregado» con su cambio de estado.
- Si la fecha real es posterior a la prevista, se pide el motivo y queda registrado como retraso.
- Una fecha real futura no se acepta.
- El comentario se guarda sin espacios sobrantes; uno demasiado largo se rechaza.
- Retrasos y entrega solo desde «Pendiente entrega»; una necesidad entregada no se puede cancelar.

## Trazabilidad

- **Diseño:** [estados de una necesidad](../diseno/estados-necesidad.md) y [modelo de datos](../diseno/modelo-de-datos.md) (Retraso).
- **Código:** `backend/app/servicios/entrega.py`, `backend/app/api/entrega.py` y `frontend/src/componentes/SeccionEntrega.jsx`.
- **Pruebas:** `backend/tests/test_entrega.py`, `frontend/src/componentes/SeccionEntrega.test.jsx` y `frontend/src/paginas/PaginaNecesidad.test.jsx`.
