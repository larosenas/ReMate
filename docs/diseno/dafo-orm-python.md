# DAFO: alternativas a Sequelize en Python

> 2026-10-21. Apoya la decisión del ORM en el ADR 0003 (`docs/adr/0003-stack-react-tailwind-python-sqlalchemy.md`).

## Contexto

Sequelize es un ORM de Node.js: no se puede usar con un backend en Python. Se buscan ORM de Python que cubran lo mismo que Sequelize en ReMate:

- Modelos y relaciones (necesidad, proveedor, peticionario, oferta, adjunto, retraso).
- **Migraciones** del esquema, porque el histórico no caduca y la base de datos irá cambiando sin perder datos.
- PostgreSQL 18 y Python 3.15 (las versiones más recientes, ADR 0003).
- Encaje con una API REST (FastAPI u otra).

Datos de versiones, fechas y licencias tomados de PyPI el 2026-10-21. En DAFO, **Debilidades y Fortalezas** son propias de la herramienta; **Amenazas y Oportunidades** vienen de su entorno (comunidad, mantenimiento, encaje con el proyecto).

## Resumen comparativo

| ORM | Versión (fecha) | Estado en PyPI | Python 3.15 | Migraciones | Licencia |
| --- | --- | --- | --- | --- | --- |
| **SQLAlchemy** | 2.1.5 (16/10/2026) | Estable | Sí (paquete para 3.15) | Alembic 1.20.0, estable | MIT |
| **SQLModel** | 0.0.48 (06/10/2026) | Beta | Sí (pide ≥ 3.10) | Alembic | MIT |
| **Peewee** | 4.5.3 (07/10/2026) | Estable | Sí (pide ≥ 3.8) | Módulo propio, sin generación automática | No figura en PyPI (por verificar) |
| **Tortoise ORM** | 1.1.9 (14/10/2026) | Alfa | Sí (pide ≥ 3.10) | Aerich 0.10.1, alfa | Apache-2.0 |
| **Piccolo** | 1.36.0 (27/07/2026) | Sin indicar | Declarada hasta 3.14 | Propias, automáticas | MIT |
| **Pony ORM** | 0.7.20 (09/08/2026) | Beta | **No** (pide < 3.15) | Sin herramienta estable | Apache-2.0 |

## SQLAlchemy 2 (+ Alembic)

| **Fortalezas** | **Debilidades** |
| --- | --- |
| ORM de referencia en Python y equivalente más directo de Sequelize (modelos, relaciones, transacciones, consultas complejas). Estable y muy completo. Migraciones automáticas maduras con Alembic. Soporte completo de PostgreSQL. Funciona igual con FastAPI, Flask o scripts | Curva de aprendizaje mayor que los ORM sencillos. Más código repetitivo: los modelos de base de datos y los esquemas de la API (Pydantic) se definen por separado |
| **Oportunidades** | **Amenazas** |
| Documentación, tutoriales y ejemplos abundantes, también con FastAPI. Muy probable que cualquier persona que herede el proyecto lo conozca. Permite pasar a SQLModel más adelante sin cambiar de base | Pocas: proyecto muy maduro y mantenido. Los cambios entre versiones mayores (de la 1.x a la 2.x) exigieron adaptar código; podría repetirse en el futuro |

## SQLModel

| **Fortalezas** | **Debilidades** |
| --- | --- |
| Un mismo modelo sirve para la base de datos y para la API (une SQLAlchemy y Pydantic): menos código. Creado por el autor de FastAPI, encaja de forma natural con él. Por debajo es SQLAlchemy, así que usa Alembic | Versión 0.0.x y en **beta**: puede cambiar sin aviso. Cubre bien los casos sencillos; para consultas complejas hay que bajar a SQLAlchemy igualmente |
| **Oportunidades** | **Amenazas** |
| Si madura, será la opción más cómoda con FastAPI. Se puede adoptar más adelante sobre un proyecto hecho con SQLAlchemy | Su desarrollo depende sobre todo de su autor, lo que puede frenar el ritmo de cambios. Menos documentación que SQLAlchemy para casos avanzados |

## Peewee

| **Fortalezas** | **Debilidades** |
| --- | --- |
| Sencillo, ligero y fácil de aprender. Estable y con años de uso. Pocas dependencias | Las migraciones no se generan solas: hay que escribirlas a mano, lo que es arriesgado con un histórico que no caduca. Menos funciones avanzadas de PostgreSQL. Pensado para código síncrono |
| **Oportunidades** | **Amenazas** |
| Buena opción para prototipos o herramientas pequeñas | Comunidad más pequeña que la de SQLAlchemy. La licencia no figura en PyPI y habría que comprobarla. Menos ejemplos de uso con FastAPI |

## Tortoise ORM

| **Fortalezas** | **Debilidades** |
| --- | --- |
| Sintaxis parecida a la del ORM de Django, cómoda de aprender. Asíncrono de base, como FastAPI | Marcado como **alfa** en PyPI. Las migraciones dependen de Aerich, también en alfa. Menos maduro con consultas complejas |
| **Oportunidades** | **Amenazas** |
| Comunidad activa alrededor de proyectos asíncronos | Riesgo de cambios que rompan el código entre versiones. Menos documentación y menos personas que lo conozcan para mantener el proyecto |

## Piccolo

| **Fortalezas** | **Debilidades** |
| --- | --- |
| Moderno y asíncrono. Migraciones automáticas propias. Incluye un panel de administración que podría servir para las listas de proveedores y peticionarios. Pensado para PostgreSQL | Comunidad pequeña. La última versión es de julio de 2026 y declara compatibilidad hasta Python 3.14 |
| **Oportunidades** | **Amenazas** |
| El panel de administración ahorraría pantallas de mantenimiento | Que no se adapte a tiempo a Python 3.15. Poca gente lo conoce, lo que complica el traspaso del proyecto |

## Pony ORM

| **Fortalezas** | **Debilidades** |
| --- | --- |
| Consultas escritas como expresiones de Python, muy legibles | **No admite Python 3.15** (pide una versión inferior). Sin herramienta de migraciones estable. En beta |
| **Oportunidades** | **Amenazas** |
| Ninguna relevante para ReMate | Mantenimiento lento; queda descartado mientras no admita 3.15 |

## Descartados de entrada

- **ORM de Django:** está ligado al framework Django, que se ha descartado.
- **Sequelize y Prisma (Node.js):** no funcionan con Python.

## Conclusión

1. **SQLAlchemy 2 + Alembic (recomendado):** es el único que reúne a la vez estabilidad, migraciones automáticas maduras, soporte de Python 3.15 y PostgreSQL 18, y una comunidad grande. Es la opción de menor riesgo para un proyecto con un único desarrollador que otra persona tendrá que mantener.
2. **SQLModel (alternativa):** más cómodo con FastAPI, pero en beta. Como se apoya en SQLAlchemy, se puede incorporar más adelante sin rehacer lo hecho.
3. **Peewee, Tortoise ORM y Piccolo:** viables para proyectos pequeños, pero con alguna debilidad importante para ReMate (migraciones manuales, estado alfa o soporte de Python 3.15 sin confirmar).
4. **Pony ORM:** descartado por no admitir Python 3.15.
