# 0010 — Moneda de cada oferta, sin conversiones

- **Estado:** Aceptada
- **Fecha:** 2026-11-04
- **Relacionado con:** CU-004 y CU-005

## Contexto y problema

Los importes de las ofertas no decían en qué moneda estaban, y la comparativa los ordenaba como si todos fueran euros. Casi todas las ofertas llegan en EUR, pero algunas pueden llegar en USD, PLN u otra moneda.

## Decisión

- Cada oferta guarda **su moneda** (`ofertas.moneda`, código ISO de tres letras), que vale para el importe total y para los precios unitarios de sus partidas.
- **EUR por defecto**, porque es la moneda de casi todas las ofertas.
- La IA lee la moneda de la oferta. Si no aparece, el símbolo es ambiguo (como «$») o hay varias, se pone EUR y la oferta lleva el aviso «La IA no ha visto la moneda de la oferta: se ha puesto EUR. Compruébalo.» El aviso se calcula con la respuesta guardada de la IA y sigue hasta que se revisa la oferta o se cambia la moneda. Una moneda escrita a mano no la sustituye una lectura posterior.
- Al revisar, cada precio lleva al lado un desplegable con el símbolo (€, $, £, zł, CHF, ¥). Todos muestran la misma moneda: al cambiar uno, cambian los demás. Una moneda que no está en la lista sale con su código (por ejemplo, SEK). Sin moneda, la oferta no se puede dar por revisada.
- Las tarjetas de las ofertas y la comparativa muestran los importes con el símbolo de su moneda («4.636,00 €»).
- **ReMate no convierte importes.** Si en la comparativa hay más de una moneda, la pantalla avisa de que no se pueden comparar directamente y no marca el mejor ni el peor precio; la conversión la hace el ingeniero. La IA tampoco convierte: cita cada importe con su moneda.
- La información para el ERP indica la moneda y conserva los precios originales.

## Alternativas consideradas

Si más adelante se quiere convertir, se parte de aquí:

- **Descargar los cambios del Banco Central Europeo desde la aplicación** (el XML diario público, sin clave). Se llegó a implementar (caché en la base de datos, cambios por necesidad y cambios manuales) y se descartó el mismo día: añade salida a internet, mucha lógica y una pantalla más para algo que se resuelve a mano.
- **Un CSV de cambios en el repositorio, cargado al desplegar:** los cambios quedarían congelados en una fecha y harían falta las mismas pantallas y avisos.
- **Lista cerrada de monedas en la base de datos:** innecesaria; basta con el código de tres letras.

## Consecuencias

- **Positivas:** la moneda queda clara en la comparativa, en la adjudicación y en el ERP, sin dependencias, servicios ni conexión a internet.
- **Negativas:** una oferta en otra moneda que la IA no lea bien queda en EUR hasta que el ingeniero la corrige (lleva aviso). Con ofertas en monedas distintas, la comparación de precios la hace el ingeniero.
- Para añadir conversiones hay que decidirlo en un ADR nuevo que sustituya a este.
