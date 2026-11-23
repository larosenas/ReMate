"""Modo admin (ADR 0015): sesión con contraseña, borrar, deshacer, corregir, tareas,
estado y registros."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import func, select
from werkzeug.security import generate_password_hash

from app import admin_sesion
from app.integraciones import archivos
from app.modelos.logs import Log
from app.modelos.necesidades import Adjunto, CambioEstado, Necesidad, Retraso
from app.modelos.ofertas import Oferta
from tests.test_adjudicacion import adjudicacion, datos, url  # noqa: F401
from tests.test_entrega import hoy, pendiente_entrega, retraso  # noqa: F401
from tests.test_pedido_sap_envio import enviar, pendiente_pedido  # noqa: F401

pytestmark = pytest.mark.usefixtures("limpiar")

CLAVE = "clave-de-prueba-123"


@pytest.fixture(autouse=True)
def configurado(app, monkeypatch):
    admin_sesion.reiniciar()
    config = replace(app.config["REMATE"], admin_clave_hash=generate_password_hash(CLAVE))
    monkeypatch.setitem(app.config, "REMATE", config)
    yield
    admin_sesion.reiniciar()


@pytest.fixture
def admin(cliente):
    respuesta = cliente.post("/api/admin/sesion", json={"clave": CLAVE})
    assert respuesta.status_code == 200, respuesta.json
    return cliente


def test_sin_configurar_esta_desactivado(app, cliente, monkeypatch):
    monkeypatch.setitem(app.config, "REMATE", replace(app.config["REMATE"], admin_clave_hash=""))
    assert cliente.get("/api/admin/sesion").json == {"activa": False, "configurado": False}
    assert cliente.post("/api/admin/sesion", json={"clave": CLAVE}).status_code == 503
    assert cliente.get("/api/admin/estado").status_code == 503


def test_sin_sesion_no_se_puede_hacer_nada(cliente):
    for metodo, ruta, cuerpo in (
        ("get", "/api/admin/estado", None),
        ("get", "/api/admin/registros", None),
        ("post", "/api/admin/necesidades/1/borrado", {"codigo": "x"}),
        ("post", "/api/admin/necesidades/1/deshacer", None),
        ("patch", "/api/admin/necesidades/1", {}),
        ("post", "/api/admin/tareas/caducidad", {"prueba": True}),
    ):
        respuesta = getattr(cliente, metodo)(ruta, json=cuerpo)
        assert respuesta.status_code == 401, (ruta, respuesta.json)
        assert respuesta.json["error"] == "sin_sesion_admin"


def test_entrar_y_salir(cliente):
    respuesta = cliente.post("/api/admin/sesion", json={"clave": CLAVE})
    cookie = respuesta.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Strict" in cookie
    assert "Path=/api/admin" in cookie
    assert cliente.get("/api/admin/sesion").json["activa"] is True
    assert cliente.get("/api/admin/estado").status_code == 200
    assert cliente.delete("/api/admin/sesion").status_code == 204
    assert cliente.get("/api/admin/sesion").json["activa"] is False
    assert cliente.get("/api/admin/estado").status_code == 401


def test_cinco_fallos_bloquean_15_minutos(app, cliente):
    for _ in range(admin_sesion.MAXIMO_FALLOS - 1):
        assert cliente.post("/api/admin/sesion", json={"clave": "mala"}).status_code == 401
    # El quinto fallo ya activa el bloqueo y lo dice.
    assert cliente.post("/api/admin/sesion", json={"clave": "mala"}).status_code == 429
    # Bloqueado: ni siquiera la buena entra.
    bloqueo = cliente.post("/api/admin/sesion", json={"clave": CLAVE})
    assert bloqueo.status_code == 429
    assert "espera" in bloqueo.json["mensaje"]
    with app.extensions["remate.sesiones"]() as sesion:
        mensajes = sesion.scalars(select(Log.mensaje)).all()
    assert all(CLAVE not in m and "mala" not in m for m in mensajes)


def test_un_hash_mal_copiado_no_da_error_500(app, cliente, monkeypatch):
    config = replace(app.config["REMATE"], admin_clave_hash="esto-no-es-un-hash")
    monkeypatch.setitem(app.config, "REMATE", config)
    assert cliente.post("/api/admin/sesion", json={"clave": CLAVE}).status_code == 401


def test_desde_otra_web_no(admin):
    respuesta = admin.post(
        "/api/admin/tareas/caducidad",
        json={"prueba": True},
        headers={"Origin": "http://otra-web.example"},
    )
    assert respuesta.status_code == 403


def test_borrar_una_necesidad_con_todo_lo_suyo(app, admin, pendiente_entrega):  # noqa: F811
    assert retraso(admin, pendiente_entrega).status_code == 200
    necesidad_id = pendiente_entrega["necesidad"]
    raiz = app.config["REMATE"].archivos_dir
    with app.extensions["remate.sesiones"]() as sesion:
        necesidad = sesion.get(Necesidad, necesidad_id)
        codigo = necesidad.codigo
        rutas = [a.ruta for a in necesidad.adjuntos]
    assert rutas
    assert all(archivos.ruta_absoluta(raiz, r).is_file() for r in rutas)
    ruta = f"/api/admin/necesidades/{necesidad_id}/borrado"
    mal = admin.post(ruta, json={"codigo": "2026000000"})
    assert mal.status_code == 400
    assert mal.json["detalles"] == {"campo": "codigo"}
    respuesta = admin.post(ruta, json={"codigo": codigo})
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json == {"codigo": codigo, "archivos": len(rutas), "no_borrados": 0}
    assert admin.get(f"/api/necesidades/{necesidad_id}").status_code == 404
    assert not any(archivos.ruta_absoluta(raiz, r).exists() for r in rutas)
    # Las carpetas que quedan vacías se quitan; si otras pruebas dejaron archivos con el mismo
    # código en esta carpeta compartida, se quedan solo esos.
    carpeta = raiz / codigo
    restantes = {p.relative_to(raiz).as_posix() for p in carpeta.rglob("*") if p.is_file()}
    assert not restantes & set(rutas)
    assert not any(p.is_dir() and not any(p.iterdir()) for p in carpeta.rglob("*"))
    with app.extensions["remate.sesiones"]() as sesion:
        for modelo in (Oferta, Adjunto, CambioEstado, Retraso):
            cuantos = sesion.scalar(
                select(func.count()).select_from(modelo).where(modelo.necesidad_id == necesidad_id)
            )
            assert cuantos == 0, modelo
        assert any(f"necesidad {codigo} borrada" in m for m in sesion.scalars(select(Log.mensaje)))
    assert admin.post(ruta, json={"codigo": codigo}).status_code == 404


def test_deshacer_pasos_uno_a_uno(app, admin, pendiente_entrega):  # noqa: F811
    necesidad_id = pendiente_entrega["necesidad"]
    ruta = f"/api/admin/necesidades/{necesidad_id}/deshacer"

    class _Deshacer:
        """Envía el estado actual, como la pantalla."""

        def post(self, ruta):
            estado = admin.get(f"/api/necesidades/{necesidad_id}").json["estado"]
            return admin.post(ruta, json={"estado": estado})

    paso = _Deshacer()
    # Paso 6 deshecho: sin pedido SAP ni su correo; se puede volver a enviar.
    respuesta = paso.post(ruta)
    assert respuesta.status_code == 200, respuesta.json
    necesidad = respuesta.json
    assert necesidad["estado"] == "pendiente_pedido_sap"
    assert necesidad["numero_pedido_sap"] is None
    assert necesidad["pedido_sap"] is None
    assert necesidad["pedido_sap_eml"] is None
    assert necesidad["historial"][-1]["estado_nuevo"] == "pendiente_pedido_sap"
    assert enviar(admin, pendiente_entrega).status_code == 200
    paso.post(ruta)
    # Paso 5 y paso 4 deshechos: sin fecha prevista ni adjudicación.
    assert paso.post(ruta).json["fecha_entrega_prevista"] is None
    deshecha = paso.post(ruta).json
    assert deshecha["estado"] == "en_evaluacion"
    assert deshecha["oferta_adjudicada_id"] is None
    assert deshecha["adjudicacion_eml"] is None
    assert (
        admin.post(
            url(pendiente_entrega, "/adjudicacion"), json=adjudicacion(pendiente_entrega)
        ).status_code
        == 200
    )
    paso.post(ruta)
    # En «En cotización» ya hay ofertas: no se deshace la solicitud.
    assert paso.post(ruta).json["estado"] == "en_cotizacion"
    con_ofertas = paso.post(ruta)
    assert con_ofertas.status_code == 400
    assert "ofertas" in con_ofertas.json["mensaje"]


def test_corregir_datos_cerrados(admin, pendiente_entrega, hoy, monkeypatch):  # noqa: F811
    hoy(date(2026, 11, 19))
    monkeypatch.setattr("app.fechas.hoy", lambda: date(2026, 11, 19))
    entrega = {"peticionario_id": pendiente_entrega["ana"]}
    admin.post(url(pendiente_entrega, "/entrega"), json=entrega)
    ruta = f"/api/admin/necesidades/{pendiente_entrega['necesidad']}"
    respuesta = admin.patch(
        ruta,
        json={
            "fecha_entrega_real": "2026-11-18",
            "numero_pedido_sap": " 4500099999 ",
            "comentario_entrega": "  Llegó con una caja abierta.  ",
        },
    )
    assert respuesta.status_code == 200, respuesta.json
    corregida = respuesta.json
    assert corregida["fecha_entrega_real"] == "2026-11-18"
    assert corregida["numero_pedido_sap"] == "4500099999"
    assert corregida["comentario_entrega"] == "Llegó con una caja abierta."
    assert admin.patch(ruta, json={"fecha_entrega_real": "2999-01-01"}).status_code == 400
    assert admin.patch(ruta, json={"fecha_entrega_real": None}).status_code == 400
    assert admin.patch(ruta, json={"estado": "cancelada"}).status_code == 400


def test_tareas_a_mano(admin):
    for tarea in ("recordatorios", "avisos", "caducidad"):
        respuesta = admin.post(f"/api/admin/tareas/{tarea}", json={"prueba": True})
        assert respuesta.status_code == 200, respuesta.json
        assert respuesta.json["prueba"] is True
        assert isinstance(respuesta.json["resumen"], dict)
    assert admin.post("/api/admin/tareas/otra", json={"prueba": True}).status_code == 400


def test_estado_y_registros(app, admin):
    ahora = datetime.now(UTC)
    with app.extensions["remate.sesiones"]() as sesion:
        sesion.add_all(
            [
                Log(
                    creado_en=ahora,
                    nivel="INFO",
                    origen="app.integraciones.ia",
                    mensaje=(
                        "OpenAI lectura: entrada=100, salida=20, caché=0, razonamiento=5 tokens"
                    ),
                ),
                Log(creado_en=ahora, nivel="ERROR", origen="prueba", mensaje="Algo ha fallado"),
            ]
        )
        sesion.commit()
    estado = admin.get("/api/admin/estado").json
    assert set(estado["necesidades"]) >= {"necesidad_creada", "entregado", "cancelada"}
    assert estado["ia_30_dias"]["llamadas"] >= 1
    assert estado["ia_30_dias"]["entrada"] >= 100
    assert estado["avisos_y_errores_7_dias"] >= 1
    assert estado["disco"]["libre"] > 0
    assert estado["ultima_copia"] is None
    errores = admin.get("/api/admin/registros", query_string={"nivel": "ERROR"}).json
    assert [r["mensaje"] for r in errores][:1] == ["Algo ha fallado"]
    assert all(r["nivel"] in ("ERROR", "CRITICAL") for r in errores)


def test_comando_que_genera_el_hash(app):
    from werkzeug.security import check_password_hash

    corta = app.test_cli_runner().invoke(args=["clave-admin"], input="corta\ncorta\n")
    assert corta.exit_code == 1
    salida = app.test_cli_runner().invoke(args=["clave-admin"], input=f"{CLAVE}\n{CLAVE}\n")
    assert salida.exit_code == 0, salida.output
    [linea] = [lin for lin in salida.output.splitlines() if lin.startswith("ADMIN_CLAVE_HASH=")]
    hash_clave = linea.removeprefix("ADMIN_CLAVE_HASH='").removesuffix("'")
    assert check_password_hash(hash_clave, CLAVE)
    assert CLAVE not in salida.output.replace(linea, "")


# --- Casos límite --------------------------------------------------------------------------------


def _ruta(datos):  # noqa: F811
    return f"/api/admin/necesidades/{datos['necesidad']}"


def _deshacer(admin, datos, estado):  # noqa: F811
    return admin.post(f"{_ruta(datos)}/deshacer", json={"estado": estado})


def _crear(cliente, datos, titulo):  # noqa: F811
    return cliente.post(
        "/api/necesidades",
        data={
            "titulo": titulo,
            "proyecto": "L1",
            "peticionario_id": str(datos["ana"]),
            "descripcion": "d",
        },
        content_type="multipart/form-data",
    ).json


def test_no_se_puede_vaciar_la_fecha_prevista(admin, pendiente_entrega):  # noqa: F811
    """Con la prevista vacía, registrar un retraso o confirmar la entrega darían un error 500."""
    respuesta = admin.patch(_ruta(pendiente_entrega), json={"fecha_entrega_prevista": None})
    assert respuesta.status_code == 400
    assert respuesta.json["detalles"] == {"campo": "fecha_entrega_prevista"}
    antes = admin.patch(_ruta(pendiente_entrega), json={"fecha_entrega_prevista": "2001-01-01"})
    assert antes.status_code == 400


def test_la_prevista_corregida_rearma_el_recordatorio(app, admin, pendiente_entrega):  # noqa: F811
    with app.extensions["remate.sesiones"]() as sesion:
        necesidad = sesion.get(Necesidad, pendiente_entrega["necesidad"])
        necesidad.recordatorio_enviado_en = datetime.now(UTC)
        sesion.commit()
    respuesta = admin.patch(_ruta(pendiente_entrega), json={"fecha_entrega_prevista": "2026-11-24"})
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json["recordatorio_enviado_en"] is None


def test_deshacer_la_solicitud_con_las_ofertas_borradas(admin, datos):  # noqa: F811
    """Las ofertas borradas no se siguen contando y el borrado se puede deshacer."""
    assert _deshacer(admin, datos, "en_evaluacion").status_code == 200
    for oferta in admin.get(url(datos, "/ofertas")).json:
        assert admin.delete(url(datos, f"/ofertas/{oferta['id']}")).status_code == 204
    respuesta = _deshacer(admin, datos, "en_cotizacion")
    assert respuesta.status_code == 200, respuesta.json
    assert respuesta.json["estado"] == "necesidad_creada"


def test_un_codigo_borrado_no_se_vuelve_a_usar(admin, datos):  # noqa: F811
    """Los correos ya enviados con ese código apuntarían a otra necesidad."""
    nueva = _crear(admin, datos, "Otra")
    borrada = admin.post(
        f"/api/admin/necesidades/{nueva['id']}/borrado", json={"codigo": nueva["codigo"]}
    )
    assert borrada.status_code == 200
    siguiente = _crear(admin, datos, "Otra más")
    assert siguiente["codigo"] > nueva["codigo"]


def test_la_cookie_dura_lo_que_el_navegador_esta_abierto(cliente):
    """Con Max-Age, el navegador la borraría a los 30 minutos de entrar aunque se usara; la
    caducidad por falta de uso la lleva el servidor."""
    cookie = cliente.post("/api/admin/sesion", json={"clave": CLAVE}).headers["Set-Cookie"]
    assert "Max-Age" not in cookie
    assert "Expires" not in cookie


def test_deshacer_indica_el_paso_y_no_deshace_dos(admin, pendiente_entrega):  # noqa: F811
    """Dos «deshacer» a la vez (o un reintento) no deshacen dos pasos."""
    assert _deshacer(admin, pendiente_entrega, "pendiente_entrega").status_code == 200
    repetido = _deshacer(admin, pendiente_entrega, "pendiente_entrega")
    assert repetido.status_code == 409
    detalle = admin.get(f"/api/necesidades/{pendiente_entrega['necesidad']}").json
    assert detalle["estado"] == "pendiente_pedido_sap"


def test_numero_de_pedido_con_nulo_o_espacios(admin, pendiente_entrega):  # noqa: F811
    nulo = admin.patch(_ruta(pendiente_entrega), json={"numero_pedido_sap": "4500\u0000123"})
    assert nulo.status_code == 400
    assert nulo.json["detalles"] == {"campo": "numero_pedido_sap"}
    espacios = admin.patch(_ruta(pendiente_entrega), json={"numero_pedido_sap": " 4500   1\t2 "})
    assert espacios.json["numero_pedido_sap"] == "4500 1 2"


def test_corregir_respeta_las_reglas_del_flujo(admin, pendiente_entrega, hoy, monkeypatch):  # noqa: F811
    monkeypatch.setattr("app.fechas.hoy", lambda: date(2026, 11, 25))
    hoy(date(2026, 11, 19))
    entrega = {"peticionario_id": pendiente_entrega["ana"]}
    admin.post(url(pendiente_entrega, "/entrega"), json=entrega)
    ruta = _ruta(pendiente_entrega)
    # Anterior a la creación de la necesidad.
    assert admin.patch(ruta, json={"fecha_entrega_real": "2001-01-01"}).status_code == 400
    # Real posterior a la prevista: sería un retraso sin registrar.
    tarde = admin.patch(ruta, json={"fecha_entrega_real": "2026-11-24"})
    assert tarde.status_code == 400
    assert "prevista" in tarde.json["mensaje"]
    # Las dos a la vez, coherentes: sí.
    juntas = admin.patch(
        ruta, json={"fecha_entrega_prevista": "2026-11-24", "fecha_entrega_real": "2026-11-24"}
    )
    assert juntas.status_code == 200, juntas.json
    assert admin.patch(ruta, json={}).status_code == 400
    nulo = admin.patch(ruta, json={"comentario_entrega": "con\u0000nulo"})
    assert nulo.json["detalles"] == {"campo": "comentario_entrega"}


def test_campos_que_no_existen_en_ese_estado(admin, datos):  # noqa: F811
    ruta = _ruta(datos)
    for campo, valor in (
        ("fecha_entrega_prevista", "2026-12-01"),
        ("fecha_entrega_real", "2026-11-01"),
        ("numero_pedido_sap", "4500"),
        ("comentario_entrega", "x"),
    ):
        respuesta = admin.patch(ruta, json={campo: valor})
        assert respuesta.status_code == 400, campo
        assert respuesta.json["detalles"] == {"campo": campo}


def test_deshacer_una_entrega_tardia_quita_su_retraso(admin, pendiente_entrega, hoy):  # noqa: F811
    """El retraso que creó la confirmación tardía se quita y vuelve la fecha prevista anterior;
    los registrados antes se quedan."""
    assert retraso(admin, pendiente_entrega, fecha_nueva="2026-11-22").status_code == 200
    hoy(date(2026, 11, 25))
    tarde = admin.post(
        url(pendiente_entrega, "/entrega"),
        json={"peticionario_id": pendiente_entrega["ana"], "motivo_retraso": "Error al teclear"},
    )
    assert len(tarde.json["retrasos"]) == 2
    deshecha = _deshacer(admin, pendiente_entrega, "entregado").json
    assert deshecha["estado"] == "pendiente_entrega"
    assert deshecha["fecha_entrega_prevista"] == "2026-11-22"
    assert len(deshecha["retrasos"]) == 1
    assert deshecha["retrasos"][0]["motivo"] != "Error al teclear"


def test_sin_sesion_es_401_aunque_el_cuerpo_no_valga(cliente):
    """La sesión se comprueba antes que el cuerpo."""
    for metodo, ruta, cuerpo in (
        ("post", "/api/admin/necesidades/1/borrado", {"codigo": "x" * 50}),
        ("patch", "/api/admin/necesidades/1", {"estado": "cancelada"}),
        ("post", "/api/admin/tareas/otra", {}),
    ):
        assert getattr(cliente, metodo)(ruta, json=cuerpo).status_code == 401, ruta


def test_el_codigo_con_espacios_vale(app, admin, pendiente_entrega):  # noqa: F811
    with app.extensions["remate.sesiones"]() as sesion:
        codigo = sesion.get(Necesidad, pendiente_entrega["necesidad"]).codigo
    respuesta = admin.post(f"{_ruta(pendiente_entrega)}/borrado", json={"codigo": f" {codigo} "})
    assert respuesta.status_code == 200, respuesta.json


def test_intentos_a_la_vez_no_superan_el_tope(app):
    """16 intentos simultáneos no comprueban 16 contraseñas."""
    import threading

    respuestas = []

    def intentar():
        with app.test_client() as c:
            respuestas.append(c.post("/api/admin/sesion", json={"clave": "mala"}).status_code)

    hilos = [threading.Thread(target=intentar) for _ in range(16)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert respuestas.count(401) <= admin_sesion.MAXIMO_FALLOS
    assert respuestas.count(429) >= 16 - admin_sesion.MAXIMO_FALLOS


def test_copias_dir_que_no_se_puede_leer(app, admin, tmp_path, monkeypatch):
    """Con COPIAS_DIR configurada pero inaccesible no se dice «Sin COPIAS_DIR»."""
    config = replace(app.config["REMATE"], copias_dir=tmp_path / "no-existe")
    monkeypatch.setitem(app.config, "REMATE", config)
    assert admin.get("/api/admin/estado").json["ultima_copia"] == {
        "carpeta": None,
        "completa": False,
        "accesible": False,
    }


def test_el_bloqueo_es_por_equipo(app):
    """Con un contador común, cualquiera de la red bloquearía al administrador con cinco
    intentos."""
    otro = app.test_client()
    for _ in range(admin_sesion.MAXIMO_FALLOS):
        otro.post(
            "/api/admin/sesion",
            json={"clave": "mala"},
            environ_base={"REMOTE_ADDR": "10.0.0.66"},
        )
    bloqueado = otro.post(
        "/api/admin/sesion", json={"clave": CLAVE}, environ_base={"REMOTE_ADDR": "10.0.0.66"}
    )
    assert bloqueado.status_code == 429
    mio = app.test_client().post(
        "/api/admin/sesion", json={"clave": CLAVE}, environ_base={"REMOTE_ADDR": "10.0.0.5"}
    )
    assert mio.status_code == 200


def test_la_tabla_de_equipos_no_se_puede_usar_para_intentar_sin_fin(app, monkeypatch):
    """Al llenarse la tabla no se borran los contadores a medias: una misma IP no puede hacer
    intentos sin fin intercalando otras."""
    monkeypatch.setattr(admin_sesion, "MAXIMO_IPS", 3)

    def intento(ip, clave="mala"):
        return (
            app.test_client()
            .post("/api/admin/sesion", json={"clave": clave}, environ_base={"REMOTE_ADDR": ip})
            .status_code
        )

    respuestas = []
    for vuelta in range(admin_sesion.MAXIMO_FALLOS + 2):
        respuestas.append(intento("10.0.0.1"))
        for otra in (f"10.1.{vuelta}.1", f"10.1.{vuelta}.2", f"10.1.{vuelta}.3"):
            intento(otra)
    # La IP que insiste queda bloqueada como mucho al quinto fallo.
    assert respuestas.count(401) <= admin_sesion.MAXIMO_FALLOS - 1
    assert 429 in respuestas
    # Con la tabla llena, un equipo nuevo no entra a probar contraseñas.
    assert intento("10.9.9.9", CLAVE) == 429
