"""Condiciones de la oferta en una tabla en lugar de «Otros» (el módulo; las pruebas por la API
están en test_ofertas.py, junto a sus datos de prueba)."""

import typing

import pytest

from app.api.ofertas import EstadoCondicion
from app.servicios import condiciones

CLAVES = [c for c, _ in condiciones.CONDICIONES]


def test_una_oferta_antigua_las_tiene_todas_sin_especificar():
    todas = condiciones.normalizar(None)
    assert list(todas) == CLAVES
    assert all(c == {"estado": "no_especificado", "texto": None} for c in todas.values())


@pytest.mark.parametrize(
    ("entrada", "esperada"),
    [
        (
            {"estado": "especificado", "texto": "  FCA  Barcelona "},
            ("especificado", "FCA Barcelona"),
        ),
        # «Especificado» sin texto no dice nada.
        ({"estado": "especificado", "texto": "  "}, ("no_especificado", None)),
        ({"estado": "incluido", "texto": None}, ("incluido", None)),
        ({"estado": "inventado", "texto": "x"}, ("no_especificado", "x")),
        ({"estado": "no_aplica"}, ("no_aplica", None)),
        ("no es un objeto", ("no_especificado", None)),
        ({"estado": "especificado", "texto": "a" * 600}, ("especificado", "a" * 500)),
    ],
)
def test_normaliza_cada_condicion(entrada, esperada):
    una = condiciones.normalizar({"incoterm": entrada})["incoterm"]
    assert (una["estado"], una["texto"]) == esperada


def test_las_claves_desconocidas_se_ignoran():
    assert list(condiciones.normalizar({"garantia": {"estado": "incluido"}})) == CLAVES


def test_el_resumen_omite_lo_no_especificado():
    texto = condiciones.resumen(
        {
            "incoterm": {"estado": "especificado", "texto": "FCA Barcelona"},
            "utillaje": {"estado": "no_incluido", "texto": "1.200 € aparte"},
            "embalaje": {"estado": "incluido", "texto": None},
        }
    )
    assert texto.splitlines() == [
        "Embalaje: Incluido",
        "Incoterm / condiciones de entrega: FCA Barcelona",
        "Utillaje: No incluido: 1.200 € aparte",
    ]


def test_la_api_admite_los_mismos_estados():
    assert set(typing.get_args(EstadoCondicion)) == set(condiciones.ESTADOS)
