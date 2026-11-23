"""Sirve el frontend compilado (dist/) desde Flask, en el mismo puerto que la API (ADR 0004)."""

from pathlib import Path

from flask import Flask, abort, send_from_directory

from app.api.errores import respuesta_error


def registrar_frontend(app: Flask, carpeta_dist: Path) -> None:
    """Las rutas que no son de la API devuelven el archivo pedido o, si no existe,
    `index.html`, para que funcione la navegación de React."""

    def frontend(ruta: str = ""):
        if ruta.startswith("api/"):
            abort(404)
        if not (carpeta_dist / "index.html").is_file():
            return (
                "No se encuentra el frontend compilado. Ejecuta `npm run build` en "
                "frontend/ o indica su carpeta en la variable FRONTEND_DIST.",
                404,
            )
        if ruta and (carpeta_dist / ruta).is_file():
            return send_from_directory(carpeta_dist, ruta)
        return send_from_directory(carpeta_dist, "index.html")

    # Se usa add_url_rule de Flask (no app.get de flask-openapi3) para que la ruta
    # reciba el parámetro `ruta` y no aparezca en la documentación de la API.
    app.add_url_rule("/", "frontend", frontend, defaults={"ruta": ""})
    app.add_url_rule("/<path:ruta>", "frontend", frontend)

    def api_inexistente(ruta: str):
        # Sin esta ruta, un POST a una dirección de la API que no existe caía en la del
        # frontend (solo GET) y devolvía un 405 confuso, por ejemplo con el servidor sin
        # reiniciar tras añadir rutas nuevas.
        return respuesta_error(
            404,
            "ruta_no_encontrada",
            "Esa dirección de la API no existe. Si se acaba de actualizar la aplicación, "
            "reinicia el servidor.",
        )

    app.add_url_rule(
        "/api/<path:ruta>",
        "api_inexistente",
        api_inexistente,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    )
