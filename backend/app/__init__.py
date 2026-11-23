"""Aplicación Flask de ReMate (ADR 0003 y 0004)."""

from flask_openapi3 import Info, OpenAPI

from app import admin_sesion, origen, registro
from app.api.errores import error_de_validacion, registrar_manejadores
from app.base_de_datos import crear_fabrica_de_sesiones, crear_motor
from app.config import Config, cargar_config
from app.integraciones import archivos


def create_app(config: Config | None = None) -> OpenAPI:
    """Crea la aplicación. Las pruebas pasan su propia `config`."""
    config = config or cargar_config()

    app = OpenAPI(
        __name__,
        info=Info(title="ReMate API", version="0.1.0"),
        doc_prefix="/api/docs",
        doc_url="/openapi.json",
        validation_error_status=400,
        validation_error_callback=error_de_validacion,
    )
    app.config["REMATE"] = config
    app.config["MAX_CONTENT_LENGTH"] = archivos.MAXIMO_POR_PETICION
    # Registro (logs) en la base de datos, con respaldo en archivo (ADR 0008).
    app.extensions["remate.registro"] = registro.instalar(
        app.logger, config.url_base_de_datos(), consola=not config.es_produccion
    )

    motor = crear_motor(config.url_base_de_datos())
    app.extensions["remate.motor"] = motor
    app.extensions["remate.sesiones"] = crear_fabrica_de_sesiones(motor)

    from app.api.adjudicacion import bp as adjudicacion_bp
    from app.api.admin import bp as admin_bp
    from app.api.entrega import bp as entrega_bp
    from app.api.listas import bp as listas_bp
    from app.api.necesidades import bp as necesidades_bp
    from app.api.ofertas import bp as ofertas_bp
    from app.api.pedido_sap import bp as pedido_sap_bp
    from app.api.salud import bp as salud_bp

    app.register_api(salud_bp)
    app.register_api(listas_bp)
    app.register_api(necesidades_bp)
    app.register_api(ofertas_bp)
    app.register_api(adjudicacion_bp)
    app.register_api(pedido_sap_bp)
    app.register_api(entrega_bp)
    app.register_api(admin_bp)
    registrar_manejadores(app)
    origen.registrar(app)
    admin_sesion.registrar(app)

    from app.frontend import registrar_frontend

    registrar_frontend(app, config.frontend_dist)

    from app.cli import registrar_comandos

    registrar_comandos(app)
    return app
