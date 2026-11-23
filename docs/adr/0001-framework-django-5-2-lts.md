# 0001 — Framework web: Django 5.2 LTS

- **Estado:** Sustituida por [0003](0003-stack-react-tailwind-python-sqlalchemy.md) (2026-10-21)
- **Fecha:** 2026-10-20

## Contexto y problema

ReMate es una aplicación web interna, con páginas HTML generadas en el servidor, que se iba a alojar en una máquina virtual Linux solo con consola. Casi todo son formularios (pasos 1 a 7), listas maestras (proveedores y peticionarios), estados de cada necesidad, un histórico sin caducidad y un correo programado (recordatorio de entrega).

Restricciones que condicionan la elección:

- Backend en Python; frontend en HTML, CSS y JavaScript.
- El servidor tenía Python 3.10.12, que se usaría de forma provisional aunque ya no tiene soporte.
- Dependencias instaladas con pip en un `.venv` del proyecto, a partir de `requirements.txt`.
- Un único desarrollador: conviene que el framework resuelva de serie lo habitual.

Versiones comprobadas el 2026-10-20 en PyPI y en djangoproject.com:

| Paquete | Versión | Python que pide | Licencia |
| --- | --- | --- | --- |
| Django (rama 6.x) | 6.1.2 | ≥ 3.12 | BSD-3-Clause |
| Django (rama 5.2 LTS) | 5.2.18 | ≥ 3.10 | BSD-3-Clause |
| Flask | 3.1.3 | ≥ 3.9 | BSD-3-Clause |
| FastAPI | 0.151.0 | ≥ 3.10 | MIT |

## Decisión

Se usa **Django 5.2 LTS** (`Django>=5.2,<5.3`).

- Es la rama más reciente de Django compatible con Python 3.10.
- Al ser LTS, recibe parches de seguridad hasta abril de 2028.
- Aporta de serie lo que necesita la aplicación: plantillas HTML, formularios con validación, ORM y migraciones, panel de administración (útil para las listas maestras), envío de correo por SMTP y comandos de gestión (para el recordatorio diario lanzado con `cron`).

La base de datos queda para su propio ADR (0002).

## Alternativas consideradas

- **Django 6.1:** es la versión actual, pero pide Python 3.12.
- **Flask 3.1:** más ligero y sencillo al principio, pero los formularios, el ORM, las migraciones y el panel de administración habría que montarlos con extensiones elegidas y mantenidas una a una.
- **FastAPI:** está pensado para construir APIs, mientras que ReMate necesitaba sobre todo páginas y formularios.

## Consecuencias

**Positivas:**

- Menos código propio y menos dependencias que mantener.
- Panel de administración inmediato para las listas maestras.
- Migraciones de la base de datos desde el principio.
- Mucha documentación y una comunidad amplia.

**Negativas:**

- Hay que aprender las convenciones de Django (proyecto, apps, ORM).
- La rama 5.2 ya no recibe funciones nuevas, solo parches; pasar a Django 6.x exige subir antes de Python.
- En producción hace falta un servidor de aplicaciones aparte y una solución para los archivos estáticos.

## Por qué se sustituyó

Al día siguiente se descartó la premisa del servidor con Python 3.10 y se decidió usar las versiones más recientes, con un frontend en React separado de una API en Python. Con un frontend en React, gran parte de lo que aporta Django (plantillas y formularios) deja de usarse. Ver [ADR 0003](0003-stack-react-tailwind-python-sqlalchemy.md).
