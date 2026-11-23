# CU-010 — Consultar el panel de seguimiento y el histórico de retrasos

- **Objetivo:** ver de un vistazo en qué punto está cada compra y cómo cumple cada proveedor.
- **Actor principal:** Ingeniero
- **Disparador:** el ingeniero quiere saber cómo van las compras o comparar proveedores.
- **Paso del proceso:** todos (consulta)
- **Prioridad:** Media
- **Estado:** Implementado

## Precondiciones

- Ninguna. Sin necesidades, el panel sale vacío.

## Garantías

- **Siempre:** es solo consulta; no cambia ningún dato.

## Escenario principal: panel de seguimiento

1. El ingeniero abre el panel, que es la página de inicio.
2. El sistema muestra todas las necesidades, de la más reciente a la más antigua, con su paso del proceso, la fecha en que pasó al estado actual, el peticionario, el proveedor adjudicado y la fecha de entrega prevista.
3. El ingeniero filtra por estado (todos, en curso o uno concreto), peticionario, proveedor adjudicado, fecha de creación o texto (código, título y proyecto).
4. El sistema combina los filtros y los conserva en la dirección de la página, para no perderlos al volver de una necesidad.

## Escenario principal: histórico de un proveedor

1. Desde la lista de proveedores, el ingeniero abre los retrasos de uno.
2. El sistema muestra el retraso medio por pedido, los pedidos con retraso («x de y», con el porcentaje), los pedidos adjudicados, la lista de retrasos (necesidad, fecha anterior, fecha nueva, días, motivo, quién y cuándo) y los comentarios de las entregas.
3. Desde cada retraso, el ingeniero puede abrir su necesidad.

## Extensiones

- **Histórico en la comparativa:** en la comparativa de ofertas (CU-004), cada proveedor muestra un resumen de su histórico («Sin retrasos» o, por ejemplo, «Retraso medio: 2,4 días por pedido. 2 de 5 pedidos con retraso (40 %)»), sus dos comentarios de entrega más recientes y un enlace a su histórico completo.

## Reglas de negocio

- La búsqueda por texto no distingue mayúsculas ni tildes. «En curso» deja fuera las entregadas y las canceladas.
- El filtro de proveedor muestra solo las necesidades adjudicadas a él.
- Un pedido cuenta en el histórico desde que se adjudica al proveedor, aunque después se cancele.
- **Días de retraso de un pedido:** si ya llegó, los días entre la fecha prevista original y la real (0 si llegó a tiempo). Si no ha llegado, la suma de lo avisado.
- **Retraso medio:** los días de retraso entre todos los pedidos del proveedor, también los que llegaron a tiempo. Por ejemplo, 4 pedidos con 10 y 20 días de retraso en dos de ellos dan 7,5 días por pedido y «2 de 4 pedidos con retraso (50 %)».
- **Redondeo:** el retraso medio con un decimal y el porcentaje sin decimales, redondeando la mitad hacia arriba, igual en pantalla que en lo que recibe la IA. Si hubo algún retraso pero el medio redondea a 0, se muestra «menos de 0,1 días». Para marcar el mejor y el peor en la comparativa se usa el valor sin redondear.
- El panel carga el listado en una sola consulta y filtra en el navegador. Si el volumen crece, los filtros pueden pasar a la API.

## Criterios de aceptación

- Los filtros se combinan y, por defecto, salen todas las necesidades.
- Buscar «rodamiento» encuentra «Rodamientos y grasa…», también en el código y el proyecto.
- El filtro de proveedor solo muestra las necesidades adjudicadas a él.
- Con dos retrasos de 7 y 3 días en uno de los dos pedidos de un proveedor, su histórico muestra un retraso medio de 5 días por pedido y 1 de 2 con retraso (50 %).
- Prevista el 20/11, se avisa del 27/11 y llega el 19/11: el pedido cuenta sin retraso y el aviso sale como «No se cumplió: llegó a tiempo».
- Prevista el 20/11, se avisa del 30/11 y llega el 23/11: cuentan 3 días, no 10.
- 1 día de retraso en 21 pedidos sale como peor que 0 días en 5 pedidos.
- El listado del panel no hace una consulta por cada necesidad.

## Trazabilidad

- **Diseño:** [API](../diseno/api.md) (`GET /api/necesidades` y `GET /api/proveedores/{id}/retrasos`).
- **Código:** `backend/app/servicios/historico.py`, `backend/app/api/listas.py`, `backend/app/api/necesidades.py`, `frontend/src/paginas/PaginaPanel.jsx`, `frontend/src/paginas/PaginaRetrasosProveedor.jsx` y `frontend/src/componentes/SeccionOfertas.jsx`.
- **Pruebas:** `backend/tests/test_historico.py`, `backend/tests/test_necesidades_api.py`, `frontend/src/paginas/PaginaPanel.test.jsx`, `frontend/src/paginas/PaginaRetrasosProveedor.test.jsx` y `frontend/src/componentes/SeccionOfertas.test.jsx`.
