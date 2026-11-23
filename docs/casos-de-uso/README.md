# Casos de uso

Los requisitos funcionales de ReMate se describen como casos de uso, en el formato «completo» de Alistair Cockburn (*Writing Effective Use Cases*), adaptado: objetivo, actores, disparador, precondiciones, garantías, escenario principal, extensiones, reglas de negocio, criterios de aceptación y trazabilidad al código y a las pruebas.

El escenario principal describe lo que hace el usuario y lo que responde el sistema, sin detalles de pantalla. Las extensiones se numeran con el paso en el que aparecen (`3a` es una variante del paso 3). Cada criterio de aceptación está cubierto por pruebas automáticas.

## Actores

| Actor | Tipo | Descripción |
| --- | --- | --- |
| **Ingeniero** | Principal | Persona del departamento de ingeniería que pide la compra (el *peticionario*) y la lleva hasta la entrega. No hay inicio de sesión: la aplicación está en la red interna y cada acción indica quién la hace. |
| **Administrador técnico** | Principal | Persona responsable de la aplicación: carga inicial de datos, configuración y modo admin. |
| **Sistema (tarea diaria)** | Principal | Comando programado en el servidor que envía los recordatorios y avisos y aplica la caducidad de los archivos. |
| **IA** | Secundario | Servicio externo (API de OpenAI) que lee las ofertas y redacta textos. Solo propone: el ingeniero revisa todo lo que escribe. |
| **Proveedor** | Externo | Recibe las solicitudes, adjudicaciones y pedidos. No usa la aplicación: el ingeniero le envía los correos desde su programa de correo. |
| **Avisados del pedido** | Externo | Personas (normalmente de Compras) que reciben un aviso cuando hay que emitir un pedido en el ERP. |

## El proceso

Cada compra es una *necesidad* que pasa por siete pasos. Cada paso es un caso de uso y deja la necesidad en un estado ([diagrama de estados](../diagramas/salidas/estados-necesidad.png)):

| Paso | Caso de uso | Estado al terminar |
| --- | --- | --- |
| 1. Necesidad | [CU-001](CU-001-crear-necesidad.md) Crear necesidad | Necesidad creada |
| 2. Solicitud de ofertas | [CU-002](CU-002-solicitar-ofertas.md) Solicitar ofertas a proveedores | En cotización |
| 3. Ofertas | [CU-004](CU-004-recibir-y-comparar-ofertas.md) Recibir y comparar ofertas con IA | En evaluación |
| 4. Adjudicación | [CU-005](CU-005-seleccionar-proveedor-e-informacion-sap.md) Seleccionar proveedor y preparar la información para el ERP | Pendiente solicitud SAP |
| 5. Pedido en el ERP | [CU-006](CU-006-confirmar-pedido-en-sap.md) Confirmar la solicitud en el ERP | Pendiente pedido SAP |
| 6. Pedido al proveedor | [CU-007](CU-007-enviar-pedido-sap.md) Enviar el pedido oficial al proveedor | Pendiente entrega |
| 7. Entrega | [CU-008](CU-008-retrasos-y-entrega.md) Registrar retrasos y confirmar la entrega | Entregado |

Casos de uso de apoyo:

| Caso de uso | Actor principal |
| --- | --- |
| [CU-003](CU-003-gestionar-listas.md) Gestionar las listas de proveedores, peticionarios y avisados | Ingeniero y administrador técnico |
| [CU-009](CU-009-recordatorio-de-entrega.md) Enviar el recordatorio de entrega | Sistema |
| [CU-010](CU-010-panel-e-historico.md) Consultar el panel de seguimiento y el histórico de retrasos | Ingeniero |

Una necesidad se puede cancelar en cualquier paso antes de la entrega, con un motivo obligatorio; queda en estado «Cancelada» y conserva su historial.

## Reglas comunes

- **La IA solo propone.** Todo lo que lee o redacta la IA se muestra al ingeniero para que lo revise y corrija. Si la IA no está configurada o falla, el caso de uso sigue sin ella, con una propuesta más simple o con los datos a mano.
- **La aplicación no envía los correos a los proveedores.** Genera archivos `.eml` que el ingeniero abre, revisa y envía desde su programa de correo. Solo los recordatorios y avisos internos se envían por SMTP.
- **Asunto común.** Todos los correos de una necesidad llevan el asunto `AAAAMMDDNN | Proyecto | Título`, para que queden en la misma conversación.
- **Adjuntos:** 25 MB como máximo por archivo, el límite habitual de los programas de correo.
- **Historial:** cada cambio de estado se guarda con quién lo hizo y cuándo.

Plantilla para casos de uso nuevos: [CU-000](CU-000-plantilla.md).
