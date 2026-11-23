"""Tipos comunes de las entradas de la API."""

from typing import Annotated

from pydantic import BeforeValidator, Field

# Los id son columnas INTEGER de PostgreSQL: un número mayor daría error 500 al consultar.
# Fuera de rango, la validación responde 400 como con cualquier dato.
MAXIMO_ID = 2**31 - 1


def _sin_booleanos(valor):
    # En modo laxo, pydantic convierte `true` en 1: un id nunca es un booleano.
    if isinstance(valor, bool):
        raise ValueError("Tiene que ser un número.")
    return valor


Id = Annotated[int, BeforeValidator(_sin_booleanos), Field(ge=1, le=MAXIMO_ID)]
