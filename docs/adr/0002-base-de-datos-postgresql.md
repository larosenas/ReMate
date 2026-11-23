# 0002 — Base de datos: PostgreSQL en desarrollo y en producción

- **Estado:** Sustituida por [0003](0003-stack-react-tailwind-python-sqlalchemy.md) (2026-10-21). PostgreSQL se mantiene; cambian la versión y el acceso (SQLAlchemy sobre psycopg)
- **Fecha:** 2026-10-20

## Contexto y problema

ReMate tiene que guardar necesidades con sus estados y fechas, listas de proveedores y peticionarios, ofertas, comparativas y un histórico de retrasos que no caduca. Varias personas pueden usarla a la vez y sin inicio de sesión, y el identificador `AAAAMMDDNN` no puede repetirse.

El servidor previsto ya tenía PostgreSQL instalado. El framework era Django 5.2 LTS (ADR 0001), que admite PostgreSQL 14 o posterior con el controlador psycopg 3.1.8 o posterior.

## Decisión

Se usa **PostgreSQL** tanto en producción como en desarrollo (instalado en el equipo de cada persona desarrolladora).

- Controlador: `psycopg` 3 (versión 3.3.6 el 2026-10-20; licencia LGPL-3.0, sin problema para usarlo como biblioteca).
- Los datos de conexión van en variables de entorno (`.env`), nunca en el código.
- En desarrollo conviene usar la misma versión mayor de PostgreSQL que en producción.
- Las pruebas usan una base de datos propia, nunca la de producción.

## Alternativas consideradas

- **Archivos JSON:** sirven para un prototipo, pero no aguantan escrituras simultáneas, no garantizan identificadores únicos y obligan a programar las consultas a mano.
- **SQLite en desarrollo y PostgreSQL en producción:** no hace falta instalar nada, pero las diferencias entre ambos (tipos, bloqueos, ordenación de texto con acentos) solo aparecerían en el servidor.
- **SQLite en todos los entornos:** sencillo, pero se desaprovecha el PostgreSQL que ya estaba disponible y soporta peor la concurrencia.

## Consecuencias

**Positivas:**

- Lo que funciona en desarrollo funciona igual en producción.
- La concurrencia y la unicidad del identificador las resuelve la base de datos.
- Se aprovecha la infraestructura existente.

**Negativas:**

- Cada persona desarrolladora tiene que instalar y configurar PostgreSQL en su equipo.
- La versión del servidor previsto (14) dejaba de tener soporte en noviembre de 2026; el ADR 0003 pasa a PostgreSQL 18.
