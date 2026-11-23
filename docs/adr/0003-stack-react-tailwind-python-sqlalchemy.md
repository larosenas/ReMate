# 0003 — Stack tecnológico: React + Tailwind en el frontend, Python + SQLAlchemy en el backend

- **Estado:** Aceptada. La parte de la IA está sustituida por [0007](0007-ia-de-produccion-claude-code.md) y después por [0011](0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md)
- **Fecha:** 2026-10-21 (framework de la API decidido el 2026-10-22)
- **Sustituye a:** [0001](0001-framework-django-5-2-lts.md) (Django 5.2 LTS) y [0002](0002-base-de-datos-postgresql.md) (PostgreSQL con psycopg)

## Contexto y problema

Las decisiones 0001 y 0002 partían de que la aplicación se alojaría en una máquina virtual Linux solo con consola, con Python 3.10 y PostgreSQL 14, y elegían las versiones compatibles con esas piezas. Esa premisa se descarta y se fija lo siguiente:

- Se usan las **versiones más recientes** de cada herramienta.
- **Frontend:** React y Tailwind CSS. Se entrega la carpeta `dist/` que genera `npm run build`.
- **Backend:** en Python. Se entrega el código fuente.
- Se deja de usar Django.
- **IA:** OpenRouter en desarrollo y la API de OpenAI en producción.

Se había propuesto Sequelize para el backend, pero Sequelize es una biblioteca de Node.js y no se puede usar desde Python; lo mismo ocurre con Express. Hacen falta sus equivalentes en Python: un ORM para la base de datos y un framework para la API.

## Decisión

| Capa | Tecnología | Versión (comprobada el 2026-10-21) | Licencia |
| --- | --- | --- | --- |
| Frontend: interfaz | React (+ react-dom) | 19.3.1 | MIT |
| Frontend: estilos | Tailwind CSS (+ `@tailwindcss/vite`) | 4.3.3 | MIT |
| Frontend: build | Vite (+ `@vitejs/plugin-react`) | 8.3.5 | MIT |
| Frontend: entorno de build | Node.js LTS | 24 (24.22.1) | MIT |
| Backend: lenguaje | Python | 3.15 (3.15.0) | PSF |
| Backend: ORM | **SQLAlchemy** | 2.1.5 | MIT |
| Backend: migraciones | **Alembic** | 1.20.0 | MIT |
| Backend: controlador PostgreSQL | psycopg | 3.3.6 | LGPL-3.0 |
| Backend: framework de la API | **Flask** | 3.1.3 | BSD-3-Clause |
| Backend: documentación de la API | Swagger / OpenAPI con flask-openapi3 (ADR 0004) | 4.3.2 | MIT |
| Backend: cliente de IA | Biblioteca `openai` de Python | — | Apache-2.0 |
| Base de datos | PostgreSQL | 18 (18.6) | PostgreSQL License |
| IA | OpenRouter en desarrollo y API de OpenAI en producción | — | Servicio externo |

- **SQLAlchemy 2 + Alembic:** es el ORM de referencia en Python y el equivalente directo de Sequelize; Alembic genera las migraciones del esquema sin perder datos. Elegido tras el [DAFO de ORM en Python](../diseno/dafo-orm-python.md).
- **IA:** como la API de OpenRouter es compatible con la de OpenAI, el código es el mismo en los dos entornos y solo cambian las variables de entorno.
- **Flask:** elegido frente a FastAPI por ser estable (versión 3.x, «Production/Stable» en PyPI), maduro y sencillo. Como Flask no genera la documentación de la API ni valida los datos por sí solo, se añade una extensión que genere la especificación OpenAPI y sirva Swagger UI (ADR 0004). SQLAlchemy y Alembic se usan directamente, sin Flask-SQLAlchemy ni Flask-Migrate.
- **Python 3.15:** las bibliotecas compiladas que se necesitan (pydantic-core, psycopg-binary, SQLAlchemy) ya publican paquetes para 3.15. Si apareciera alguna incompatibilidad, se bajaría a 3.14.
- **Node.js** solo hace falta para construir el frontend, no para ejecutarlo en producción.

## Alternativas consideradas

- **FastAPI:** incluye Swagger y validación automática, pero sigue en versión 0.x. Descartado en favor de Flask.
- **Express + Sequelize:** son de Node.js y el backend tiene que ser Python.
- **Django:** gran parte de lo que aporta (plantillas HTML, formularios) no se usa con un frontend de React.
- **Otros ORM de Python** (SQLModel, Peewee, Tortoise ORM, Piccolo, Pony ORM): comparados en el DAFO. SQLModel queda como posible mejora futura, porque funciona sobre SQLAlchemy.
- **API de OpenAI también en desarrollo:** posible, pero OpenRouter permitía probar distintos modelos con una sola clave.

## Consecuencias

**Positivas:**

- Separación clara: el frontend es estático (`dist/`) y el backend es una API.
- Versiones recientes y con soporte.
- Cambiar de proveedor de IA es solo cambiar variables de entorno.

**Negativas:**

- Dos lenguajes y dos gestores de paquetes (npm para el frontend; pip con `.venv` para el backend).
- Sin el panel de administración de Django, las listas maestras necesitan sus propias pantallas.
- OpenRouter es un servicio externo más por el que pasan datos.
- Hay que instalar Python 3.15 y PostgreSQL 18 en el equipo de desarrollo.

## Revisiones

- **2026-11-02:** la IA de producción pasa a ser Claude Code por terminal ([ADR 0007](0007-ia-de-produccion-claude-code.md)).
- **2026-11-04:** la API de OpenAI pasa a ser la IA de desarrollo y de producción, y se deja OpenRouter ([ADR 0011](0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md)). El código vuelve a ser el mismo en los dos entornos.
