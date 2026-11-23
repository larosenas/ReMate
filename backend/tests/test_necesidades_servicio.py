"""CU-001 — Pruebas de las reglas para crear necesidades."""

import threading
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.integraciones import archivos
from app.integraciones.archivos import ArchivoDemasiadoGrande
from app.modelos.listas import AvisadoPedidoSap, Peticionario, Proveedor
from app.modelos.logs import Log
from app.modelos.necesidades import (
    Adjunto,
    CambioEstado,
    CambioPeticionario,
    CodigoBorrado,
    Necesidad,
    ProveedorSolicitado,
    Retraso,
)
from app.modelos.ofertas import LineaOferta, Oferta
from app.servicios import necesidades
from app.servicios.listas import DatosNoValidos
from app.servicios.necesidades import ArchivoSubido, DemasiadasNecesidades

DIA_22 = datetime(2026, 10, 22, 9, 30)


def vaciar(s):
    # Necesidades y ofertas se referencian entre sí: primero se suelta la oferta adjudicada.
    s.query(Necesidad).update({Necesidad.oferta_adjudicada_id: None})
    for modelo in (
        Retraso,
        LineaOferta,
        ProveedorSolicitado,
        CambioEstado,
        CambioPeticionario,
        Adjunto,
        Oferta,
        Necesidad,
        Peticionario,
        Proveedor,
        AvisadoPedidoSap,
        CodigoBorrado,
        Log,
    ):
        s.query(modelo).delete()
    s.commit()


@pytest.fixture
def sesion(app):
    with app.extensions["remate.sesiones"]() as s:
        yield s
        s.rollback()
        vaciar(s)


@pytest.fixture
def raiz(app):
    return app.config["REMATE"].archivos_dir


@pytest.fixture
def ana(sesion):
    p = Peticionario(nombre_completo="Ana Prueba", email="ana@ejemplo.test")
    sesion.add(p)
    sesion.commit()
    return p


def crear(sesion, raiz, peticionario, **cambios):
    datos = {
        "titulo": "Rodamiento roto",
        "proyecto": "Línea 3",
        "descripcion": "Cambiar el rodamiento 6204 de la cinta.",
        "peticionario_id": peticionario.id,
        "ahora": DIA_22,
    }
    datos.update(cambios)
    return necesidades.crear(sesion, raiz, **datos)


def test_crea_la_necesidad_en_necesidad_creada(sesion, raiz, ana):
    n = crear(sesion, raiz, ana)
    assert n.codigo == "2026102201"
    assert n.estado == "necesidad_creada"
    assert n.peticionario.nombre_completo == "Ana Prueba"
    assert [(c.estado_anterior, c.estado_nuevo, c.peticionario_id) for c in n.historial] == [
        (None, "necesidad_creada", ana.id)
    ]


def test_codigos_por_orden_dentro_del_dia_y_reinicio_al_dia_siguiente(sesion, raiz, ana):
    codigos = [crear(sesion, raiz, ana).codigo for _ in range(8)]
    assert codigos[0] == "2026102201"
    assert codigos[7] == "2026102208"
    assert crear(sesion, raiz, ana, ahora=datetime(2026, 10, 23, 0, 5)).codigo == "2026102301"


def test_no_caben_mas_de_99_al_dia(sesion, raiz, ana):
    sesion.add(
        Necesidad(
            codigo="2026102299",
            titulo="t",
            proyecto="p",
            descripcion="d",
            estado="necesidad_creada",
            peticionario=ana,
        )
    )
    sesion.commit()
    with pytest.raises(DemasiadasNecesidades):
        crear(sesion, raiz, ana)


def test_quita_espacios_sobrantes(sesion, raiz, ana):
    n = crear(sesion, raiz, ana, titulo="  Rodamiento  ", proyecto=" 2026 ")
    assert n.titulo == "Rodamiento"
    assert n.proyecto == "2026"


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("titulo", ""), ("proyecto", "   "), ("descripcion", None), ("titulo", "x" * 201)],
)
def test_campos_obligatorios(sesion, raiz, ana, campo, valor):
    with pytest.raises(DatosNoValidos) as error:
        crear(sesion, raiz, ana, **{campo: valor})
    assert error.value.campo == campo
    assert sesion.query(Necesidad).count() == 0


def test_peticionario_inexistente_o_inactivo(sesion, raiz, ana):
    with pytest.raises(DatosNoValidos) as error:
        crear(sesion, raiz, ana, peticionario_id=999999)
    assert error.value.campo == "peticionario_id"
    ana.activo = False
    sesion.commit()
    with pytest.raises(DatosNoValidos):
        crear(sesion, raiz, ana)


def test_guarda_los_adjuntos_en_disco(sesion, raiz, ana):
    n = crear(
        sesion,
        raiz,
        ana,
        adjuntos=[ArchivoSubido("Plano señal.PDF", "application/pdf", b"%PDF-1.7 prueba")],
    )
    [adjunto] = n.adjuntos
    assert adjunto.nombre_archivo == "Plano señal.PDF"
    assert adjunto.tamano == 15
    assert adjunto.ruta.startswith("2026102201/")
    assert adjunto.ruta.endswith(".pdf")
    assert archivos.ruta_absoluta(raiz, adjunto.ruta).read_bytes() == b"%PDF-1.7 prueba"


def test_rechaza_adjuntos_de_mas_de_25_mb_sin_crear_nada(sesion, raiz, ana):
    grande = ArchivoSubido("enorme.bin", "application/octet-stream", b"0" * (25 * 1024 * 1024 + 1))
    with pytest.raises(ArchivoDemasiadoGrande):
        crear(sesion, raiz, ana, adjuntos=[grande])
    assert sesion.query(Necesidad).count() == 0


def test_no_deja_archivos_si_falla_el_guardado(sesion, raiz, ana, monkeypatch):
    escritos = []
    guardar_real = archivos.guardar

    def guardar_y_fallar_al_segundo(*args):
        if escritos:
            raise OSError("disco lleno")
        escritos.append(guardar_real(*args))
        return escritos[-1]

    monkeypatch.setattr(archivos, "guardar", guardar_y_fallar_al_segundo)
    dos = [
        ArchivoSubido("a.txt", "text/plain", b"hola"),
        ArchivoSubido("b.txt", "text/plain", b"x"),
    ]
    with pytest.raises(OSError, match="disco lleno"):
        crear(sesion, raiz, ana, adjuntos=dos)
    assert not archivos.ruta_absoluta(raiz, escritos[0]).exists()
    assert sesion.query(Necesidad).count() == 0


def test_la_hora_por_defecto_es_la_de_madrid(sesion, raiz, ana):
    n = crear(sesion, raiz, ana, ahora=None)
    hoy = sesion.scalar(select(func.timezone("Europe/Madrid", func.now())))
    assert n.codigo == hoy.strftime("%Y%m%d") + "01"


def test_ruta_fuera_de_la_carpeta_de_archivos(raiz):
    with pytest.raises(ValueError, match="fuera de ARCHIVOS_DIR"):
        archivos.ruta_absoluta(raiz, "../fuera.txt")


def test_titulo_y_proyecto_en_una_linea(sesion, raiz, ana):
    n = crear(sesion, raiz, ana, titulo="Rodamiento\r\nroto", proyecto="Línea\n3")
    assert n.titulo == "Rodamiento roto"
    assert n.proyecto == "Línea 3"


def test_extension_saneada(raiz):
    ruta = archivos.guardar(raiz, "x", "oferta.eml:flujo", b"datos")
    assert ruta.endswith(".emlflujo")
    assert ":" not in ruta


def test_dos_creaciones_a_la_vez_no_repiten_codigo(app, sesion, raiz, ana, monkeypatch):
    """CU-001 (criterio de aceptación): dos personas crean una necesidad a la vez. La segunda
    choca en el índice único con el código de la primera, espera, reintenta y se lleva el
    siguiente."""
    resultado = {}

    def segunda():
        try:
            with app.extensions["remate.sesiones"]() as otra:
                resultado["codigo"] = crear(otra, raiz, ana).codigo
        except Exception as error:  # se comprueba abajo; en un hilo no llegaría a la prueba
            resultado["error"] = error

    hilo = threading.Thread(target=segunda)
    guardar_real = necesidades._guardar_adjuntos

    def guardar_con_la_otra_esperando(*args):
        # La primera ya tiene su código (insertado, sin commit): ahora crea la segunda.
        if not hilo.is_alive() and "codigo" not in resultado:
            hilo.start()
            hilo.join(timeout=1)
            resultado["esperaba"] = hilo.is_alive()
        return guardar_real(*args)

    monkeypatch.setattr(necesidades, "_guardar_adjuntos", guardar_con_la_otra_esperando)
    primera = crear(sesion, raiz, ana)
    hilo.join(timeout=10)
    assert "error" not in resultado, resultado.get("error")
    assert resultado["esperaba"], "la segunda debería esperar a que termine la primera"
    assert (primera.codigo, resultado["codigo"]) == ("2026102201", "2026102202")
