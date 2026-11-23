# Guía de estilo visual

ReMate se usa en el departamento de ingeniería de una planta industrial. La identidad parte de ese mundo: el acero de las máquinas y la tornillería de los repuestos. Es sobria, para que lo que destaque sean los datos (estados, fechas e importes), y tiene un único elemento propio y reconocible: el logotipo.

## Colores

Definidos como variables de Tailwind en `frontend/src/index.css` (`@theme`); se usan con clases como `bg-marca-oscuro` o `text-marca-acento`.

| Variable | Valor | Uso |
| --- | --- | --- |
| `marca-oscuro` | `#17262f` | Acero: barra superior, pie del panel y línea bajo la cabecera de las tablas |
| `marca-acento` | `#0b6e6e` | Petróleo: botones principales, enlaces, foco del teclado y paso que toca |
| `marca-acento-oscuro` | `#08514f` | Botones al pasar el ratón e inicio del degradado decorativo |
| `marca-acento-claro` | `#4fb3a9` | Final del degradado decorativo y aro del logotipo (solo decoración) |
| `marca-ambar` | `#e3a72f` | Punto del logotipo (solo decoración, nunca para texto) |
| `marca-tarjeta` | `#34495a` | Pizarra: etiquetas de estado en curso, con texto blanco |
| `marca-texto` | `#1c2329` | Texto principal sobre fondo blanco |
| (blanco) | `#ffffff` | Fondo general |

- **Contraste:** el petróleo cumple WCAG AA (unos 6:1) como texto sobre blanco y con texto blanco encima; el acero y la pizarra, de sobra. El verde claro y el ámbar no se usan para texto.
- **Colores con significado:** el rojo es solo para errores, avisos de borrado y el «peor» valor de la comparativa; el verde, para «entregada» y el «mejor» valor. Por eso la marca no usa ni rojo ni verde puro: así no se confunde una acción con un estado.

## Tipografía

- La del sistema: `Segoe UI` en Windows, Roboto en Android, y si no, Helvetica Neue o Arial. No se incluye ninguna fuente en la aplicación, para no depender de servicios externos.
- Títulos grandes en peso normal, no en negrita; menú y botones en peso medio.
- Importes y fechas con números tabulares (`tabular-nums`).

## Logotipo

- **Símbolo:** una tuerca hexagonal (la pieza de repuesto por excelencia) en blanco, con el aro interior en `marca-acento-claro` y un punto `marca-ambar` en una esquina. Es SVG (`frontend/src/componentes/Logotipo.jsx`), así que no depende de imágenes.
- **Nombre:** «Re» en seminegrita y «Mate» en peso normal y algo más tenue, sobre la barra de acero.
- **Icono de la pestaña:** el mismo símbolo sobre un cuadrado de acero redondeado (`frontend/public/favicon.svg`).
- El logotipo enlaza con el panel. El modo admin se abre con el enlace discreto «admin» del pie, del mismo color que su texto ([ADR 0015](../adr/0015-modo-admin-con-contrasena.md)).

## Componentes

- **Cabecera:** barra de acero de 72 px con una línea fina debajo en degradado de `marca-acento-oscuro` a `marca-acento-claro`. A la izquierda, el logotipo; a la derecha, los enlaces en blanco atenuado, con la página actual en blanco y subrayada en petróleo, y «Nueva necesidad», la acción principal, como botón. En el móvil, los enlaces pasan a una segunda fila que se desplaza en horizontal.
- **Botón principal:** fondo `marca-acento`, texto blanco, esquinas ligeramente redondeadas y sombra suave.
- **Etiqueta de estado:** en curso, fondo `marca-tarjeta` con texto blanco; entregada, verde; cancelada, gris.
- **Decoración:** una onda con el degradado de petróleo al pie del panel, unida al pie de acero. Solo en la página de inicio: nunca sobre formularios ni tablas, para no restar legibilidad.
- **Pie:** «ReMate, desarrollado por Laro Señas», el enlace «admin» a la derecha, del mismo color tenue, y el estado del servidor, discreto si todo va bien.

## Patrones de la interfaz

- **Pista del proceso** (`PistaProceso.jsx`): los 7 pasos como tramos. En petróleo, los hechos; en acero, el que toca; en gris, los pendientes; todos en gris apagado si se canceló. Completa con los nombres bajo el título del detalle y compacta en cada fila del panel. En el móvil se ve «Paso N de 7: …»; en pantallas mayores, ese texto es solo para lectores de pantalla.
- **Panel:** tabla con una línea de acero bajo la cabecera y filas separadas por líneas finas, sin tarjetas ni sombras. El título va en negrita con el proyecto debajo, junto al estado aparece «desde DD.MM.AAAA» y toda la fila abre el detalle. En el móvil, una tarjeta por necesidad.
- **Filtros:** en la misma línea que el título, sin caja de fondo; etiquetas en gris pequeño y controles compactos de borde fino. El filtro que está actuando se marca con el borde en petróleo y aparece «Quitar filtros».
- **Detalle de la necesidad:** a la izquierda, los pasos; a la derecha (debajo en el móvil), una columna con los datos, el historial como línea de tiempo y «Cancelar la necesidad» como enlace discreto, porque es destructivo y poco habitual. El paso que toca lleva un borde superior en petróleo de 4 px; los ya hechos quedan plegados.
- **Subir archivos** (`SelectorArchivo.jsx`): botón «Elegir archivo(s)» dentro de una zona de borde discontinuo en la que también se puede arrastrar y soltar; al pasar un archivo por encima, la zona se marca en petróleo («Suelta aquí»). Lo elegido se ve debajo, un archivo por línea.
- **Desplazamiento:** al entrar en una necesidad la pantalla baja hasta el paso que toca; al pasar al siguiente, baja hasta él y lleva el foco a su título. Sin animación si el sistema pide menos movimiento (`src/desplazamiento.js`).
- **Plazo sin fecha:** se muestra el plazo del proveedor y debajo, en gris pequeño, «≈ fecha desde su oferta» (`EntregaOferta.jsx`).
- **Retraso que no se cumplió:** días tachados en gris y la etiqueta «No se cumplió: llegó a tiempo».
- **Bordes, no sombras:** las tarjetas usan un borde fino (`slate-200`); las sombras quedan solo en los botones.
- **Tablas anchas:** en el móvil se desplazan en horizontal dentro de su caja; los importes, alineados a la derecha.
- **Accesibilidad:** foco visible con el teclado en petróleo en todos los controles (`index.css`), animaciones desactivadas si el sistema pide reducir el movimiento y comprobación automática con axe-core en las pruebas.
