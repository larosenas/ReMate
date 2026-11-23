# Modelo de dominio

Diagrama: [modelo de dominio](../diagramas/salidas/modelo-de-dominio.png) (fuente en `docs/diagramas/fuentes/modelo-de-dominio.puml`). Describe los **conceptos del negocio** de una compra de repuestos en un departamento de ingeniería y cómo se relacionan. No habla de tablas ni de columnas: eso está en el [modelo de datos](modelo-de-datos.md), que es su traducción a la base de datos.

## Para qué sirve

- Fija un **vocabulario común**: una «necesidad», una «oferta» o una «adjudicación» significan lo mismo en las conversaciones, en los casos de uso, en la pantalla y en el código.
- Explica **las reglas del negocio** sin entrar en cómo se guardan.
- Sirve de puente entre los [casos de uso](../casos-de-uso/README.md) y el modelo de datos.

## Conceptos

| Concepto | Qué es | Casos de uso |
| --- | --- | --- |
| **Peticionario** | Ingeniero que necesita la pieza y lleva la compra. Sin inicio de sesión: en cada paso se elige quién lo hace | CU-001, CU-003 |
| **Proveedor** | Empresa a la que se piden ofertas y que, si se le adjudica, sirve el pedido | CU-002, CU-003 |
| **Avisado del pedido** | Persona (normalmente de Compras) a la que se avisa cuando hay que emitir el pedido en el ERP | CU-003, CU-006 |
| **Necesidad** | Una compra: lo que hace falta (título, proyecto y descripción), quién la pide y en qué paso está. Se identifica con un código `AAAAMMDDNN` | CU-001 a CU-010 |
| **Documento de la necesidad** | Planos, fotos u otros archivos que explican lo que hace falta | CU-001 |
| **Solicitud de ofertas** | Correo a varios proveedores, en copia oculta, pidiendo oferta, con los documentos elegidos | CU-002 |
| **Oferta** | Respuesta de un proveedor: su correo y adjuntos, importe sin IVA en su moneda, plazo de entrega y condiciones. La lee la IA y la revisa el ingeniero | CU-004 |
| **Partida** | Cada artículo ofertado: descripción, cantidad, precio unitario sin IVA y fecha de entrega | CU-004, CU-005 |
| **Comparativa** | Las ofertas vigentes de una necesidad, lado a lado, con el histórico de cada proveedor y, con todas revisadas, el mejor y el peor precio, entrega y retrasos | CU-004, CU-010 |
| **Adjudicación** | La elección de una oferta: fija el proveedor, la fecha de entrega inicial y el correo al adjudicatario | CU-005 |
| **Información para el ERP** | Texto (cabecera fija y justificación) y tabla de partidas, con los formatos del ERP (SAP), para copiarlos en la solicitud de pedido | CU-005 |
| **Pedido** | El pedido oficial que emite el ERP: su PDF, su número y el correo que lo envía al proveedor | CU-006, CU-007 |
| **Fecha de entrega prevista** | La fecha en que se espera el pedido. Empieza siendo la de la oferta y cambia con cada retraso | CU-006, CU-008 |
| **Retraso** | Aviso de que el pedido llegará más tarde: fecha anterior, fecha nueva y motivo. Si al final llega a tiempo, no cuenta | CU-008, CU-010 |
| **Entrega** | La llegada del pedido, con su fecha real y un comentario opcional. Cierra la necesidad | CU-008 |
| **Recordatorio** | Correo al peticionario una semana antes de la fecha prevista | CU-009 |
| **Cambio de estado** | Cada paso dado en la necesidad: de qué estado a cuál, quién y cuándo | Todos |
| **Cambio de peticionario** | Paso de una necesidad en curso a otra persona, al dar de baja a la que la llevaba | CU-003 |
| **Histórico del proveedor** | Cuántos pedidos se le han adjudicado, cuántos llegaron tarde, su retraso medio por pedido y los comentarios de sus entregas | CU-010 |

**Fuera de ReMate**, pero en el dominio: la **IA** (lee ofertas y redacta textos; nunca decide), el **ERP** (donde se meten la solicitud y el pedido, a mano) y el **programa de correo** (donde se abren y envían los `.eml` que prepara ReMate).

## Relaciones

- Un **peticionario** lleva muchas necesidades; cada **necesidad** la lleva un peticionario, y puede pasar a otro si se le da de baja.
- Una necesidad tiene sus **documentos**, una **solicitud de ofertas** a uno o varios proveedores y recibe **ofertas**, cada una de un proveedor y con sus **partidas**.
- Las ofertas vigentes forman la **comparativa**. Se **adjudica una sola**: el proveedor de la necesidad es siempre el de la oferta adjudicada.
- La adjudicación da la **información para el ERP**; después llegan el **pedido**, los **retrasos** y la **entrega**.
- Cada paso deja un **cambio de estado** con el peticionario que lo dio.
- El **histórico del proveedor** se saca de sus necesidades adjudicadas, sus retrasos y sus entregas.

## Reglas del dominio

- **Siete pasos en orden,** más «Cancelada» (ver [estados de una necesidad](estados-necesidad.md)). No se puede saltar un paso.
- **Un proveedor por necesidad.** Si hay piezas para proveedores distintos, se crea una necesidad por proveedor.
- **Una oferta por proveedor:** una nueva del mismo proveedor sustituye a la anterior en la comparativa. Las sustituidas o borradas no se eliminan.
- **Importes sin IVA,** en la moneda de cada oferta, sin conversiones ([ADR 0010](../adr/0010-moneda-de-la-oferta-sin-conversiones.md)).
- **La IA ayuda, pero no decide:** el ingeniero revisa cada oferta y cada texto antes de usarlos.
- **Retrasos solo en «Pendiente entrega».** Un retraso avisado que no se cumple (el pedido llega antes de la fecha avisada) no cuenta en el histórico.
- **Nada se borra en el uso normal:** proveedores y peticionarios se desactivan y, si se quiere, se eliminan con motivo, pero siguen en las necesidades antiguas.
- **Sin inicio de sesión:** el historial guarda quién dio cada paso según el peticionario elegido.
