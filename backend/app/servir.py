"""Arranque de producción: python -m app.servir [--log <archivo>] (ADR 0009)."""

import argparse

from waitress import serve

from app import create_app
from app.config import Config, cargar_config
from app.integraciones import archivos


def ajustes_de_proxy(config: Config) -> dict:
    """Detrás de un proxy inverso (ADR 0016): Waitress toma la IP del equipo (X-Forwarded-For) y
    el https (X-Forwarded-Proto) solo si la conexión viene de PROXY_DE_CONFIANZA; si no, borra
    esas cabeceras (`clear_untrusted_proxy_headers`, activo por defecto). El proxy deja pasar el
    Host tal cual, así que no se toma X-Forwarded-Host."""
    if not config.proxy_de_confianza:
        return {}
    return {
        "trusted_proxy": config.proxy_de_confianza,
        "trusted_proxy_count": 1,
        "trusted_proxy_headers": {"x-forwarded-for", "x-forwarded-proto"},
    }


def servir() -> None:
    """Carga una sola configuración y sirve la interfaz y la API con Waitress."""
    config = cargar_config()
    serve(
        create_app(config),
        host=config.host,
        port=config.port,
        # Por encima de las llamadas a la IA a la vez (ia.LLAMADAS_A_LA_VEZ, 8): aunque estén todas
        # en curso, quedan hilos para el resto de peticiones.
        threads=16,
        # Algo por encima del límite de Flask, para que sea Flask quien conteste con su mensaje.
        max_request_body_size=archivos.MAXIMO_POR_PETICION + 1024 * 1024,
        **ajustes_de_proxy(config),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", help="Archivo de respaldo del registro, en UTF-8 (ADR 0008).")
    args = parser.parse_args(argv)
    if args.log:
        from app.a_archivo import main as a_archivo

        return a_archivo([args.log, "servir"])
    servir()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
