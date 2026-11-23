# 0014 — Caducidad de los archivos y de la tabla `logs`, y copias que ocupan lo mínimo

- **Estado:** Aceptada
- **Fecha:** 2026-11-17
- **Relacionado con:** [0006](0006-despliegue-windows-sin-https.md) (despliegue y copias) y [0008](0008-registro-en-la-base-de-datos.md) (registro; cambia su punto 3, «no caduca»)

## Contexto y problema

Con unos 150 pedidos al año, cada necesidad deja unos 10-20 MB de archivos (planos, correos y adjuntos de las ofertas, `.eml` generados y el pedido del ERP): unos 1,5-3 GB al año que no caducaban. La copia diaria (`scripts/windows/copia-de-seguridad.ps1`) copiaba la carpeta de archivos entera cada día y guardaba 30 días: unas 30 veces lo que ocupa la carpeta. La tabla `logs` tampoco caducaba.

Las copias las hace solo este script, y el objetivo es ocupar lo mínimo. Los usuarios solo acceden a lo que ven en ReMate, no a las copias ni a las carpetas del servidor. Los correos siguen en el programa de correo y el pedido en el ERP; los planos de la necesidad sirven para volver a pedir la misma pieza.

## Decisión

1. **Archivos de las necesidades cerradas** («Entregado» o «Cancelada»), contando desde el día en que se cerraron:
   - Adjuntos de la necesidad (planos, modelos 3D…): se borran a los **24 meses**.
   - Todo lo demás (correos y adjuntos de las ofertas, respuestas de los proveedores, `.eml` generados y el PDF del pedido): a los **6 meses**.
   - Se borra el archivo y la fila se queda con `adjuntos.caducado_en`: la necesidad conserva todos sus datos (proveedor, precios, fechas, retrasos, comentarios) y el histórico de proveedores no cambia. La API devuelve `caducado: true`, la descarga responde `410 archivo_caducado` y la pantalla muestra «eliminado por antigüedad» en lugar del enlace.
   - Primero se anota y después se borra del disco: si el borrado falla, queda un archivo de más y se avisa, nunca una fila que apunte a un archivo que no está. Al día siguiente se vuelve a intentar (en Windows no se puede borrar un archivo abierto). Las filas se bloquean mientras tanto, para que dos ejecuciones a la vez no cuenten lo mismo.
2. **Tabla `logs`:** se borran los mensajes de más de **6 meses**.
3. Lo hace la **tarea diaria que ya existe** (`flask --app app enviar-recordatorios`), sin tareas programadas nuevas. Con `--prueba`, solo cuenta lo que se borraría. Los plazos están en las constantes `MESES_*` de `backend/app/servicios/caducidad.py`.
4. **Copias** (`copia-de-seguridad.ps1`):
   - **Base de datos:** un volcado por día. Se guardan los **7 últimos** y, de los anteriores, el más reciente de cada una de las **4 semanas** siguientes: se puede volver atrás hasta un mes con 11 volcados de pocos MB. Las semanas son las ISO, también en el cambio de año.
   - **Archivos:** **una sola copia espejo** (`robocopy /MIR`). Los archivos de ReMate no se modifican, así que basta con una copia; lo que caduca desaparece también del espejo.
   - Con `/MIR`, un origen equivocado vaciaría el espejo. Por eso el script no sigue si la carpeta de origen no existe, si tiene menos de la mitad de archivos que el espejo (salvo con `-ForzarEspejo`) o si el destino está dentro del origen o al revés. `/XJ` evita seguir uniones de directorios.

## Alternativas consideradas

- **Dejarlo como estaba:** a los 3 años, unos 150-250 GB solo de copias.
- **No caducar los archivos, solo cambiar las copias:** con este volumen ocupa poco (unos 3 GB al año), pero crece sin límite y guarda lo que no se va a usar.
- **Caducar todo a la vez, también los planos:** se perderían los planos para repetir pedidos.
- **Borrar las necesidades enteras:** se perdería el histórico de proveedores, y los datos ocupan muy poco.
- **Copias por versiones de los archivos** (guardar también lo borrado): protege de un borrado por error, pero ocupa más.

## Consecuencias

- **Positivas:** la carpeta de archivos se estabiliza (unos 1-2 GB con este volumen) y las copias ocupan más o menos lo mismo, más unos MB de volcados. Sin dependencias ni tareas nuevas.
- **Negativas:** pasados los plazos, los documentos solo están en el programa de correo y en el ERP. Un archivo borrado por error desaparece del espejo en la copia siguiente. Al restaurar un volcado antiguo, los archivos de las necesidades creadas después seguirán en el espejo, pero la base de datos restaurada no los conocerá.
