"""Cliente de OpenAI: siempre simulado, sin llamadas de red."""

import logging
from dataclasses import replace
from types import SimpleNamespace

import httpx2
import pytest
from openai import APITimeoutError, AuthenticationError, InternalServerError

from app.integraciones import ia


@pytest.fixture
def config(config_pruebas):
    return replace(config_pruebas, ia_api_key="clave-ficticia", ia_modelo="gpt-prueba")


def cliente_que_responde(texto=None, error=None, uso=None, recibido=None, status="completed"):
    """Cliente simulado; `llamadas` cuenta las peticiones (cada una se paga)."""

    def crear(**kwargs):
        cliente.llamadas += 1
        if recibido is not None:
            recibido.update(kwargs)
        if error:
            raise error
        detalles = SimpleNamespace(reason="max_output_tokens")
        return SimpleNamespace(
            output_text=texto, usage=uso, status=status, incomplete_details=detalles
        )

    cliente = SimpleNamespace(responses=SimpleNamespace(create=crear), llamadas=0)
    return cliente


def _respuesta_http(codigo):
    peticion = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    return httpx2.Response(codigo, request=peticion)


def test_sin_configurar(config_pruebas):
    with pytest.raises(ia.ErrorIA, match="IA_API_KEY"):
        ia.leer_oferta(config_pruebas, [{"type": "input_text", "text": "Oferta"}])


def test_responses_api_recibe_solo_extraccion(config, monkeypatch):
    recibido = {}
    falso = cliente_que_responde('{"numero_oferta":"OF-1"}', recibido=recibido)
    monkeypatch.setattr(ia, "_cliente", lambda _config: falso)
    partes = [
        {"type": "input_text", "text": "Correo"},
        {
            "type": "input_file",
            "filename": "oferta.pdf",
            "file_data": "data:application/pdf;base64,JVBERi0=",
            "detail": "low",
        },
    ]
    assert ia.leer_oferta(config, partes) == {"numero_oferta": "OF-1"}
    assert recibido["model"] == "gpt-prueba"
    assert recibido["input"] == [{"role": "user", "content": partes}]
    assert recibido["text"] == {"format": ia.FORMATO_OFERTA}
    assert recibido["text"]["format"]["type"] == "json_schema"
    assert recibido["text"]["format"]["strict"] is True
    assert recibido["reasoning"] == {"effort": "low"}
    assert recibido["max_output_tokens"] == ia.MAXIMO_SALIDA
    assert recibido["store"] is False
    assert recibido["timeout"] == ia.TIEMPO_OFERTA
    assert "extrae" in recibido["instructions"].lower()


def test_error_de_api_se_reintenta_una_vez(config, monkeypatch):
    error = APITimeoutError(request=SimpleNamespace(method="POST", url="https://api.openai.com"))
    intentos = 0

    def crear(**_kwargs):
        nonlocal intentos
        intentos += 1
        if intentos == 1:
            raise error
        return SimpleNamespace(output_text='{"numero_oferta":"OF-2"}', usage=None)

    monkeypatch.setattr(
        ia, "_cliente", lambda _config: SimpleNamespace(responses=SimpleNamespace(create=crear))
    )
    assert ia.leer_oferta(config, [{"type": "input_text", "text": "x"}]) == {
        "numero_oferta": "OF-2"
    }
    assert intentos == 2


def test_fallo_del_servidor_se_repite_solo_una_vez(config, monkeypatch):
    error = InternalServerError("caído", response=_respuesta_http(500), body=None)
    falso = cliente_que_responde(error=error)
    monkeypatch.setattr(ia, "_cliente", lambda _config: falso)
    with pytest.raises(ia.ErrorIA, match="no ha respondido"):
        ia.leer_oferta(config, [{"type": "input_text", "text": "x"}])
    assert falso.llamadas == ia.INTENTOS


def test_clave_no_valida_no_se_repite(config, monkeypatch):
    error = AuthenticationError("clave", response=_respuesta_http(401), body=None)
    falso = cliente_que_responde(error=error)
    monkeypatch.setattr(ia, "_cliente", lambda _config: falso)
    with pytest.raises(ia.ErrorIA):
        ia.leer_oferta(config, [{"type": "input_text", "text": "x"}])
    assert falso.llamadas == 1


@pytest.mark.parametrize("texto", ["no es JSON", "[]", "", '{"x": NaN}'])
def test_respuesta_no_valida_no_se_repite(config, monkeypatch, texto):
    # Volvería a salir igual y se pagaría dos veces (ADR 0011).
    falso = cliente_que_responde(texto)
    monkeypatch.setattr(ia, "_cliente", lambda _config: falso)
    with pytest.raises(ia.ErrorIA):
        ia.leer_oferta(config, [{"type": "input_text", "text": "x"}])
    assert falso.llamadas == 1


def test_respuesta_cortada_avisa_y_no_se_repite(config, monkeypatch):
    falso = cliente_que_responde('{"numero_oferta":', status="incomplete")
    monkeypatch.setattr(ia, "_cliente", lambda _config: falso)
    with pytest.raises(ia.ErrorIA, match="cortada"):
        ia.leer_oferta(config, [{"type": "input_text", "text": "x"}])
    assert falso.llamadas == 1


def test_normaliza_claves_y_texto_no_guardable(config, monkeypatch):
    respuesta = (
        '{"Currency":"EUR","Offer Number":"OF-3","Lines":'
        '[{"Description":"pieza\\ud800","unit_price":1e400}]}'
    )
    monkeypatch.setattr(ia, "_cliente", lambda _config: cliente_que_responde(respuesta))
    datos = ia.leer_oferta(config, [{"type": "input_text", "text": "x"}])
    assert datos["moneda"] == "EUR"
    assert datos["numero_oferta"] == "OF-3"
    assert ia.claves(datos["lineas"][0]) == {"descripcion": "pieza?", "precio_unitario": None}


def test_registra_tokens_sin_contenido(config, monkeypatch, caplog):
    uso = SimpleNamespace(
        input_tokens=1200,
        output_tokens=300,
        input_tokens_details=SimpleNamespace(cached_tokens=200),
        output_tokens_details=SimpleNamespace(reasoning_tokens=100),
    )
    monkeypatch.setattr(
        ia,
        "_cliente",
        lambda _config: cliente_que_responde('{"numero_oferta":"SECRETA-77"}', uso=uso),
    )
    logging.getLogger("app").addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.INFO):
            ia.leer_oferta(config, [{"type": "input_text", "text": "importe 9999"}])
    finally:
        logging.getLogger("app").removeHandler(caplog.handler)
    assert "OpenAI gpt-prueba, razonamiento low, oferta: entrada=1200" in caplog.text
    assert "razonamiento=100" in caplog.text
    assert "SECRETA" not in caplog.text
    assert "9999" not in caplog.text


def test_modelo_usado(config):
    assert ia.modelo_usado(config) == "gpt-prueba"


@pytest.mark.parametrize(
    "nombre",
    [
        "INSTRUCCIONES_OFERTA",
        "INSTRUCCIONES_PETICION",
        "INSTRUCCIONES_ADJUDICACION",
        "INSTRUCCIONES_PETICION_DATOS",
    ],
)
def test_las_instrucciones_llevan_el_nombre_de_la_empresa(config, nombre):
    texto = getattr(ia, nombre)
    assert "<EMPRESA>" in texto
    con_nombre = ia.instrucciones(texto, replace(config, empresa_nombre="Industrias Ficticias"))
    assert "<EMPRESA>" not in con_nombre
    assert "de Industrias Ficticias" in con_nombre
    sin_nombre = ia.instrucciones(texto, replace(config, empresa_nombre=""))
    assert "de la empresa" in sin_nombre


def test_instrucciones_conservan_los_controles_de_extraccion():
    instrucciones = " ".join(ia.INSTRUCCIONES_OFERTA.split())
    assert "no inventes" in instrucciones
    assert "No conviertas importes" in instrucciones
    assert "nunca en primera persona" in instrucciones


def test_la_peticion_se_redacta_como_lista_tecnica_flexible():
    """CU-002 — El correo se sintetiza; no es una copia ni un formulario fijo."""
    instrucciones = " ".join(ia.INSTRUCCIONES_PETICION.split())
    assert "tono técnico, profesional y natural" in instrucciones
    assert "lista con guiones" in instrucciones
    assert "Incluye solo los grupos que existan" in instrucciones
    assert "no como campos de un formulario" in instrucciones
    assert "ni las conviertas en una plantilla" in instrucciones.lower()


def _objetos(esquema):
    if esquema.get("type") == "object":
        yield esquema
        for propiedad in esquema["properties"].values():
            yield from _objetos(propiedad)
    elif esquema.get("type") == "array":
        yield from _objetos(esquema["items"])


def test_el_esquema_cumple_el_modo_estricto():
    """En modo estricto, OpenAI rechaza un esquema con campos opcionales o sin
    additionalProperties: false (guía «Structured outputs»)."""
    objetos = list(_objetos(ia.FORMATO_OFERTA["schema"]))
    # La oferta, el proveedor, cada línea, las condiciones y cada una de las 9.
    assert len(objetos) == 13
    for objeto in objetos:
        assert objeto["additionalProperties"] is False
        assert sorted(objeto["required"]) == sorted(objeto["properties"])


def test_el_razonamiento_se_elige_en_el_env(config, monkeypatch):
    recibido = {}
    monkeypatch.setattr(
        ia, "_cliente", lambda _config: cliente_que_responde("{}", recibido=recibido)
    )
    ia.leer_oferta(
        replace(config, ia_razonamiento="minimal"), [{"type": "input_text", "text": "x"}]
    )
    assert recibido["reasoning"] == {"effort": "minimal"}


def test_como_mucho_unas_pocas_llamadas_a_la_vez(config, monkeypatch):
    """Sin límite, cualquiera de la red podría lanzar llamadas de pago sin fin y ocupar los
    hilos del servidor."""
    import threading

    turnos = threading.BoundedSemaphore(1)
    monkeypatch.setattr(ia, "_turnos", turnos)
    monkeypatch.setattr(ia, "ESPERA_TURNO", 0.05)
    falso = cliente_que_responde('{"numero_oferta":"OF-1"}')
    monkeypatch.setattr(ia, "_cliente", lambda _config: falso)
    turnos.acquire()  # otra llamada en curso
    with pytest.raises(ia.ErrorIA, match="muchas peticiones a la vez"):
        ia.leer_oferta(config, [{"type": "input_text", "text": "x"}])
    assert falso.llamadas == 0
    turnos.release()
    # Con turno libre, sí; y el turno se devuelve aunque la llamada falle.
    assert ia.leer_oferta(config, [{"type": "input_text", "text": "x"}])["numero_oferta"] == "OF-1"
    monkeypatch.setattr(
        ia,
        "_cliente",
        lambda _config: cliente_que_responde(
            error=InternalServerError("caído", response=_respuesta_http(500), body=None)
        ),
    )
    with pytest.raises(ia.ErrorIA):
        ia.leer_oferta(config, [{"type": "input_text", "text": "x"}])
    assert turnos.acquire(blocking=False)
