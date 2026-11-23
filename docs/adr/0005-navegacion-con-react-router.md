# 0005 — Navegación del frontend con React Router; PWA descartada de momento

- **Estado:** Aceptada
- **Fecha:** 2026-10-23
- **Relacionado con:** [0003](0003-stack-react-tailwind-python-sqlalchemy.md) (stack), [0004](0004-swagger-y-recordatorio-de-entrega.md) (Flask sirve el frontend)

## Contexto y problema

La interfaz tiene varias pantallas (panel, nueva necesidad, listas y el detalle de cada necesidad). Hace falta que cada pantalla tenga su propia dirección, que funcionen los botones «atrás» y «adelante» del navegador y que se pueda guardar o compartir el enlace a una necesidad. Hasta entonces se usaba una navegación provisional sin bibliotecas, en la que cada enlace recargaba la página. También se planteó convertir la aplicación en una PWA.

## Decisión

- **React Router 8** (paquete `react-router` 8.5.0, licencia MIT; admite React ≥ 19.2.7 y Node ≥ 22.22) en **modo declarativo**: `BrowserRouter` en `main.jsx`, `Routes`/`Route` en `App.jsx` y `NavLink` en la cabecera, que marca la página actual con `aria-current="page"`.
- **PWA descartada de momento.** Solo se reconsiderará si el servidor tiene HTTPS y los usuarios necesitan instalar la aplicación.

## Alternativas consideradas

- **Navegación propia** (elegir la pantalla según `window.location.pathname`): sin dependencias, pero cada enlace recarga la página y habría que programar a mano los parámetros de las rutas (`/necesidades/:id`).
- **Modo «framework» o «data» de React Router** (cargadores, acciones, renderizado en servidor): más de lo que necesita una aplicación interna pequeña con el frontend servido como archivos estáticos.
- **PWA:** resuelve otra cosa (instalar la web como programa) y necesita HTTPS.

## Consecuencias

**Positivas:**

- Cambio de pantalla sin recargar, enlaces directos a cada pantalla y botones del navegador funcionando.
- Funciona con el despliegue elegido: Flask devuelve `index.html` en cualquier ruta que no sea de la API (ADR 0004).
- Las pruebas usan `MemoryRouter` con la ruta que necesitan.

**Negativas:**

- Una dependencia más (unos 45 kB más en el JavaScript del build sin comprimir).
- Las versiones mayores de React Router han cambiado su API con frecuencia; al actualizar habrá que revisar las notas de cambio.
