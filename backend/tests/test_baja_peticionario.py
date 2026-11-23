"""CU-003 — Baja definitiva de un peticionario con necesidades en curso: se avisa y
hay que pasarlas a otro peticionario activo. Datos inventados."""

from contextlib import contextmanager
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.integraciones import correo_saliente
from app.modelos.listas import Peticionario
from app.modelos.necesidades import Necesidad
from app.servicios import listas
from tests.test_adjudicacion import adjudicacion, datos, url  # noqa: F401
from tests.test_entrega import pendiente_entrega  # noqa: F401
from tests.test_pedido_sap_envio import enviar, pendiente_pedido  # noqa: F401
from tests.test_recordatorios import config, ejecutar, smtp  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar")

ENVIADO = datetime(2026, 11, 13, 7, 0, tzinfo=UTC)


@pytest.fixture
def ana_desactivada(app, cliente, pendiente_entrega):  # noqa: F811
    """Ana lleva una necesidad en «Pendiente entrega» (recordatorio ya enviado) y está desactivada;
    Luis está activo y Marta, desactivada."""
    with app.extensions["remate.sesiones"]() as s:
        luis = Peticionario(nombre_completo="Luis Prueba", email="luis@ejemplo.test")
        marta = Peticionario(
            nombre_completo="Marta Prueba", email="marta@ejemplo.test", activo=False
        )
        s.add_all([luis, marta])
        s.get(Necesidad, pendiente_entrega["necesidad"]).recordatorio_enviado_en = ENVIADO
        s.commit()
        ids = {**pendiente_entrega, "luis": luis.id, "marta": marta.id}
    assert (
        cliente.patch(f"/api/peticionarios/{ids['ana']}", json={"activo": False}).status_code == 200
    )
    return ids


def baja(cliente, datos, **cambios):  # noqa: F811
    cuerpo = {"motivo": "Ya no trabaja en la empresa", **cambios}
    return cliente.post(f"/api/peticionarios/{datos['ana']}/baja", json=cuerpo)


def necesidad(app, datos):  # noqa: F811
    with app.extensions["remate.sesiones"]() as s:
        n = s.get(Necesidad, datos["necesidad"])
        return n.peticionario_id, n.recordatorio_enviado_en, s.get(Peticionario, datos["ana"])


def test_con_necesidades_en_curso_avisa_y_no_elimina(cliente, app, ana_desactivada):
    respuesta = baja(cliente, ana_desactivada)
    assert respuesta.status_code == 409
    assert respuesta.json["error"] == "necesidades_en_curso"
    [en_curso] = respuesta.json["detalles"]["necesidades"]
    assert en_curso["id"] == ana_desactivada["necesidad"]
    assert en_curso["titulo"] == "Rodamientos"
    peticionario_id, _, ana = necesidad(app, ana_desactivada)
    assert peticionario_id == ana_desactivada["ana"]
    assert ana.eliminado_en is None


@pytest.mark.parametrize("quien", ["ana", "marta", "inexistente"])
def test_hay_que_pasarlas_a_otro_peticionario_activo(cliente, app, ana_desactivada, quien):
    reasignar_a = ana_desactivada.get(quien, 999999)
    respuesta = baja(cliente, ana_desactivada, reasignar_a=reasignar_a)
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "reasignar_a"}
    # No cambia nada: ni la necesidad ni la baja.
    peticionario_id, recordatorio, ana = necesidad(app, ana_desactivada)
    assert peticionario_id == ana_desactivada["ana"]
    assert recordatorio is not None
    assert ana.eliminado_en is None


def test_pasa_las_necesidades_al_nuevo_y_queda_constancia(
    cliente,
    app,
    config,  # noqa: F811
    smtp,  # noqa: F811
    ana_desactivada,
):
    assert baja(cliente, ana_desactivada, reasignar_a=ana_desactivada["luis"]).status_code == 204
    peticionario_id, recordatorio, ana = necesidad(app, ana_desactivada)
    assert peticionario_id == ana_desactivada["luis"]
    assert ana.eliminado_en is not None
    # El recordatorio se vacía para que le llegue al nuevo peticionario.
    assert recordatorio is None

    detalle = cliente.get(f"/api/necesidades/{ana_desactivada['necesidad']}").json
    assert detalle["peticionario"]["nombre_completo"] == "Luis Prueba"
    [cambio] = detalle["cambios_peticionario"]
    assert cambio["peticionario_anterior"]["nombre_completo"] == "Ana Prueba"
    assert cambio["peticionario_nuevo"]["nombre_completo"] == "Luis Prueba"
    # El historial de estados no cambia.
    assert detalle["historial"][-1]["estado_nuevo"] == "pendiente_entrega"

    resumen = ejecutar(app, config, date(2026, 11, 13))
    assert resumen.omitidos == []
    [mensaje] = smtp.enviados
    assert mensaje["To"] == "luis@ejemplo.test"


@pytest.mark.parametrize("estado", ["cancelada", "entregado"])
def test_las_entregadas_y_canceladas_no_cuentan(cliente, app, ana_desactivada, estado):
    with app.extensions["remate.sesiones"]() as s:
        s.get(Necesidad, ana_desactivada["necesidad"]).estado = estado
        s.commit()
    assert baja(cliente, ana_desactivada).status_code == 204
    peticionario_id, _, _ = necesidad(app, ana_desactivada)
    assert peticionario_id == ana_desactivada["ana"]


# --- Casos límite ---


@contextmanager
def sesion_que_no_espera(app):
    """Una sesión que, si una fila está bloqueada por otra, falla enseguida en lugar de esperar."""
    with app.extensions["remate.sesiones"]() as s:
        s.execute(text("SET lock_timeout = '300ms'"))
        yield s


def test_no_se_puede_eliminar_a_quien_esta_recibiendo_necesidades(app, ana_desactivada):
    """Mientras se pasan las necesidades de Ana a Luis, la fila de Luis está bloqueada: nadie puede
    desactivarlo ni eliminarlo a la vez (si no, la necesidad acabaría en manos de un eliminado)."""
    with app.extensions["remate.sesiones"]() as a:
        ana = listas._vigente(a, Peticionario, ana_desactivada["ana"], bloquear=True)
        listas._reasignar(a, ana, ana_desactivada["luis"])  # sin commit todavía
        with sesion_que_no_espera(app) as b, pytest.raises(OperationalError):
            listas.actualizar(b, Peticionario, ana_desactivada["luis"], activo=False)
        a.rollback()


def test_dos_bajas_a_la_vez_de_la_misma_persona(cliente, app, ana_desactivada):
    """La segunda baja espera a la primera y, al seguir, ya la ve eliminada: 404, sin pisar el
    motivo ni volver a pasar sus necesidades."""
    with app.extensions["remate.sesiones"]() as a:
        listas._vigente(a, Peticionario, ana_desactivada["ana"], bloquear=True)
        with sesion_que_no_espera(app) as b, pytest.raises(OperationalError):
            listas.eliminar(b, Peticionario, ana_desactivada["ana"], "Registro duplicado")
        a.rollback()
    assert baja(cliente, ana_desactivada, reasignar_a=ana_desactivada["luis"]).status_code == 204
    otra = baja(
        cliente, ana_desactivada, motivo="Registro duplicado", reasignar_a=ana_desactivada["luis"]
    )
    assert otra.status_code == 404
    with app.extensions["remate.sesiones"]() as s:
        assert s.get(Peticionario, ana_desactivada["ana"]).motivo_eliminacion == (
            "Ya no trabaja en la empresa"
        )


def test_un_eliminado_no_puede_hacer_acciones(app, ana_desactivada):
    with app.extensions["remate.sesiones"]() as s:
        ana = s.get(Peticionario, ana_desactivada["ana"])
        ana.activo, ana.eliminado_en = True, ENVIADO
        s.commit()
        with pytest.raises(listas.DatosNoValidos):
            listas.peticionario_activo(s, ana.id, "Elige quién lo hace.")


def test_el_recordatorio_no_sale_si_la_necesidad_cambia_de_peticionario_mientras_se_envia(
    cliente,
    app,
    config,  # noqa: F811
    smtp,  # noqa: F811
    pendiente_entrega,  # noqa: F811
    monkeypatch,
):
    with app.extensions["remate.sesiones"]() as s:
        luis = Peticionario(nombre_completo="Luis Prueba", email="luis@ejemplo.test")
        s.add(luis)
        s.commit()
        luis_id = luis.id
    original = correo_saliente.conexion

    @contextmanager
    def baja_mientras_se_conecta(cfg):
        # Ana está activa al preparar el correo y se la da de baja justo antes de enviarlo.
        cliente.patch(f"/api/peticionarios/{pendiente_entrega['ana']}", json={"activo": False})
        respuesta = cliente.post(
            f"/api/peticionarios/{pendiente_entrega['ana']}/baja",
            json={"motivo": "Ya no trabaja en la empresa", "reasignar_a": luis_id},
        )
        assert respuesta.status_code == 204
        with original(cfg) as servidor:
            yield servidor

    monkeypatch.setattr(correo_saliente, "conexion", baja_mientras_se_conecta)
    assert ejecutar(app, config, date(2026, 11, 13)).enviados == []
    assert smtp.enviados == []
    monkeypatch.setattr(correo_saliente, "conexion", original)
    assert len(ejecutar(app, config, date(2026, 11, 14)).enviados) == 1
    [mensaje] = smtp.enviados
    assert mensaje["To"] == "luis@ejemplo.test"


@pytest.mark.parametrize("reasignar_a", [2**31, True, 0])
def test_reasignar_a_fuera_de_rango_o_booleano(cliente, ana_desactivada, reasignar_a):
    """Un id enorme daba error 500; `true` se tomaba como el id 1."""
    assert baja(cliente, ana_desactivada, reasignar_a=reasignar_a).status_code == 400


def test_ids_enormes_en_la_ruta_no_dan_500(cliente, ana_desactivada):
    assert cliente.get(f"/api/necesidades/{2**31}").status_code == 400
    assert cliente.post(f"/api/peticionarios/{2**31}/baja", json={"motivo": "x"}).status_code == 400


def test_la_baja_de_un_proveedor_no_admite_reasignar_a(cliente, ana_desactivada):
    respuesta = cliente.post(
        f"/api/proveedores/{ana_desactivada['ficmec']}/baja", json={"motivo": "x", "reasignar_a": 1}
    )
    assert respuesta.status_code == 400
