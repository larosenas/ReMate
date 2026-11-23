# CU-001 — Crear necesidad

- **Objetivo:** dejar registrada una compra que hace falta, con todo lo necesario para pedir ofertas.
- **Actor principal:** Ingeniero (peticionario)
- **Disparador:** se rompe o hace falta una pieza, un útil o un trabajo de un proveedor.
- **Paso del proceso:** 1. Necesidad → «Necesidad creada»
- **Prioridad:** Alta
- **Estado:** Implementado

## Precondiciones

- Ninguna. La lista de peticionarios (CU-003) puede estar vacía.

## Garantías

- **Si termina bien:** existe una necesidad con un código único, sus adjuntos y el primer registro de su historial.
- **Siempre:** si algo falla, no se crea nada a medias y no se pierde lo escrito en el formulario.

## Escenario principal

1. El ingeniero elige crear una necesidad.
2. El sistema pide título, proyecto, peticionario, descripción y adjuntos (opcionales).
3. El ingeniero rellena los datos, se elige como peticionario y adjunta planos, fotos u otros documentos.
4. El sistema valida los datos.
5. El sistema asigna el código `AAAAMMDDNN`, guarda la necesidad en «Necesidad creada» con sus adjuntos y registra el cambio de estado.
6. El sistema muestra la necesidad creada y ofrece pasar a la solicitud de ofertas (CU-002).

## Extensiones

- **3a. El peticionario no está en la lista:** el ingeniero da de alta su nombre y su correo desde el mismo formulario (CU-003) y queda elegido. Si el correo ya existe, el sistema propone el peticionario que lo tiene.
- **4a. Faltan datos obligatorios o no son válidos:** el sistema señala los campos con error y no crea la necesidad.
- **4b. Un adjunto supera el tamaño máximo:** el sistema lo rechaza con un mensaje y conserva el resto del formulario.
- **5a. Dos necesidades se crean a la vez:** cada una recibe un código distinto.
- **5b. Ya hay 99 necesidades ese día:** el sistema no la crea y lo explica.
- **6a. El ingeniero quiere corregir algo:** mientras la necesidad siga en «Necesidad creada», puede volver desde la solicitud de ofertas y cambiar los datos. El código no cambia.

## Reglas de negocio

- Título, proyecto, peticionario y descripción son obligatorios.
- **Código `AAAAMMDDNN`:** la fecha de creación y el orden de la necesidad dentro de ese día, con dos cifras. La fecha la calcula la base de datos, en la zona horaria Europe/Madrid, para que todos los equipos usen la misma.
- Los peticionarios se muestran de la A a la Z y solo los activos.
- Cada adjunto se guarda con un nombre interno único; el nombre original se conserva en la base de datos.

## Criterios de aceptación

- Con todos los campos obligatorios, la necesidad se crea en «Necesidad creada».
- La primera necesidad del 22/10/2026 recibe `2026102201`, la octava `2026102208` y la primera del día siguiente `2026102301`.
- Dos creaciones simultáneas nunca obtienen el mismo código.
- Si falta un campo obligatorio, no se crea nada y se indica qué falta.
- Un peticionario dado de alta desde el formulario queda en la lista en su posición alfabética.
- Un adjunto de más de 25 MB se rechaza sin perder el resto del formulario.
- El historial registra el cambio de estado con el peticionario y la hora.

## Trazabilidad

- **Diseño:** [modelo de datos](../diseno/modelo-de-datos.md) (Necesidad, Peticionario, Adjunto y CambioEstado) y [estados de una necesidad](../diseno/estados-necesidad.md).
- **Código:** `backend/app/servicios/necesidades.py`, `backend/app/api/necesidades.py`, `backend/app/integraciones/archivos.py` y `frontend/src/paginas/PaginaNuevaNecesidad.jsx`.
- **Pruebas:** `backend/tests/test_necesidades_servicio.py`, `backend/tests/test_necesidades_api.py` y `frontend/src/paginas/PaginaNuevaNecesidad.test.jsx`.
