"""Comandos de Flask de ReMate (se ejecutan con `flask --app app <comando>`)."""

import csv
from pathlib import Path

import click
from flask import current_app
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.security import generate_password_hash

from app import fechas
from app.integraciones.correo_saliente import ErrorCorreo
from app.modelos.listas import Peticionario, Proveedor
from app.modelos.necesidades import Necesidad
from app.servicios import avisos_pedido_sap, caducidad, listas, prueba_ia, recordatorios
from app.servicios.listas import CorreoDuplicado, DatosNoValidos

TIPOS = {"proveedor": Proveedor, "peticionario": Peticionario}


def cargar_listas(sesion, ruta: Path) -> dict:
    """CU-003 — Carga inicial de proveedores y peticionarios desde un CSV `tipo;nombre;correo`.

    Omite los correos que ya existen (no modifica nada) y sigue con las demás líneas
    si alguna tiene errores. Se puede ejecutar varias veces sin crear duplicados.
    """
    resumen = {"creados": 0, "omitidos": 0, "errores": []}
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        for numero, fila in enumerate(csv.reader(archivo, delimiter=";"), start=1):
            if not fila or not "".join(fila).strip():
                continue
            if numero == 1 and fila[0].strip().lower() == "tipo":
                continue  # cabecera
            if len(fila) != 3:
                resumen["errores"].append((numero, "Debe tener 3 columnas: tipo;nombre;correo."))
                continue
            tipo, nombre, email = (campo.strip() for campo in fila)
            modelo = TIPOS.get(tipo.lower())
            if modelo is None:
                resumen["errores"].append((numero, f"Tipo «{tipo}» no válido."))
                continue
            try:
                listas.crear(sesion, modelo, nombre, email)
                resumen["creados"] += 1
            except CorreoDuplicado:
                resumen["omitidos"] += 1
            except DatosNoValidos as e:
                resumen["errores"].append((numero, str(e)))
    return resumen


def registrar_comandos(app) -> None:
    @app.cli.command("cargar-listas")
    @click.argument("ruta", type=click.Path(exists=True, dir_okay=False, path_type=Path))
    def cargar_listas_comando(ruta: Path):
        """Carga inicial de proveedores y peticionarios desde un CSV fuera del repositorio."""
        with current_app.extensions["remate.sesiones"]() as sesion:
            resumen = cargar_listas(sesion, ruta)
        click.echo(
            f"Creados: {resumen['creados']}  ·  Omitidos (ya existían): {resumen['omitidos']}"
        )
        for numero, motivo in resumen["errores"]:
            click.echo(f"Línea {numero}: {motivo}", err=True)
        if resumen["errores"]:
            raise SystemExit(1)

    @app.cli.command("enviar-recordatorios")
    @click.option(
        "--prueba",
        is_flag=True,
        help="No envía: guarda los correos como .eml en ARCHIVOS_DIR/recordatorios-prueba.",
    )
    def enviar_recordatorios_comando(prueba: bool):
        """CU-009 — Recordatorio de entrega a una semana, avisos del paso 5 (pedido
        en SAP) que fallaron y su recordatorio semanal, y caducidad de los archivos y de `logs`
        (ADR 0014). Se ejecuta a diario (ADR 0004)."""
        config = current_app.config["REMATE"]
        with current_app.extensions["remate.sesiones"]() as sesion:
            # Cada tarea con su propio error: si fallan los avisos, los recordatorios enviados se
            # siguen contando.
            fallo = False
            try:
                resumen = recordatorios.enviar_recordatorios(
                    sesion, config, fechas.hoy(), prueba=prueba
                )
            except (ErrorCorreo, SQLAlchemyError) as e:
                sesion.rollback()
                click.echo(f"No se ha enviado ningún recordatorio: {_motivo(e)}", err=True)
                current_app.logger.error("No se ha enviado ningún recordatorio: %s", _motivo(e))
                resumen, fallo = None, True
            try:
                avisos = avisos_pedido_sap.enviar_pendientes(
                    sesion, config, fechas.hoy(), prueba=prueba
                )
            except (ErrorCorreo, SQLAlchemyError) as e:
                sesion.rollback()
                click.echo(f"No se ha enviado ningún aviso del pedido SAP: {_motivo(e)}", err=True)
                current_app.logger.error(
                    "No se ha enviado ningún aviso del pedido SAP: %s", _motivo(e)
                )
                avisos, fallo = None, True
            # Caducidad (ADR 0014): archivos de necesidades cerradas y `logs` antiguos.
            try:
                caducado = caducidad.caducar(
                    sesion, config.archivos_dir, fechas.hoy(), prueba=prueba
                )
            except SQLAlchemyError as e:
                sesion.rollback()
                click.echo(f"No se ha podido aplicar la caducidad: {type(e).__name__}", err=True)
                current_app.logger.exception("No se ha podido aplicar la caducidad")
                caducado, fallo = None, True
        if resumen is not None:
            fallo = _informar_recordatorios(resumen, config, prueba) or fallo
        if avisos is not None:
            fallo = _informar_avisos(avisos, prueba) or fallo
        if caducado is not None:
            _informar_caducidad(caducado, prueba)
        if fallo:
            raise SystemExit(1)

    @app.cli.command("probar-ia")
    @click.argument("carpeta", type=click.Path(exists=True, file_okay=False, path_type=Path))
    def probar_ia_comando(carpeta: Path):
        """Lee con la IA real las ofertas de prueba de CARPETA (fuera del repositorio) y compara
        lo que sale con su esperado.json. Cada oferta se paga y se envía a OpenAI."""
        resultados = prueba_ia.probar(current_app.config["REMATE"], carpeta)
        if not resultados:
            click.echo("No hay casos: cada subcarpeta necesita un esperado.json.", err=True)
            raise SystemExit(1)
        for resultado in resultados:
            if resultado.bien:
                click.echo(f"BIEN   {resultado.caso}")
                continue
            click.echo(f"FALLA  {resultado.caso}")
            for linea in [resultado.error] if resultado.error else resultado.diferencias:
                click.echo(f"       - {linea}")
        bien = sum(r.bien for r in resultados)
        click.echo(f"{bien} de {len(resultados)} casos bien.")
        if bien < len(resultados):
            raise SystemExit(1)

    @app.cli.command("clave-admin")
    def clave_admin_comando():
        """Modo admin (ADR 0015): pide la contraseña dos veces y escribe la línea
        ADMIN_CLAVE_HASH para el .env. La contraseña no se guarda en ningún sitio."""
        clave = click.prompt("Contraseña del modo admin", hide_input=True, confirmation_prompt=True)
        if len(clave) < 12:
            click.echo("La contraseña tiene que tener al menos 12 caracteres.", err=True)
            raise SystemExit(1)
        click.echo("Copia esta línea en el .env (con las comillas simples):")
        click.echo(f"ADMIN_CLAVE_HASH='{generate_password_hash(clave)}'")

    @app.cli.command("vaciar-listas")
    @click.option("--si", is_flag=True, help="No pedir confirmación.")
    def vaciar_listas_comando(si: bool):
        """Solo desarrollo: borra todos los proveedores y peticionarios y reinicia los id."""
        if current_app.config["REMATE"].entorno != "development":
            click.echo("Este comando solo se puede usar con APP_ENV=development.", err=True)
            raise SystemExit(1)
        if not si:
            click.confirm(
                "Se borrarán TODOS los proveedores y peticionarios de la base de datos "
                "de desarrollo. ¿Seguir?",
                abort=True,
            )
        with current_app.extensions["remate.sesiones"]() as sesion:
            # Las necesidades apuntan a los peticionarios: no se vacían las listas por debajo.
            if sesion.scalar(select(func.count()).select_from(Necesidad)):
                click.echo(
                    "Hay necesidades guardadas que usan estas listas; no se vacían.", err=True
                )
                raise SystemExit(1)
            # PostgreSQL exige truncar a la vez las tablas que las referencian (ya vacías).
            sesion.execute(
                text(
                    "TRUNCATE peticionarios, proveedores, necesidades, adjuntos, cambios_estado, "
                    "cambios_peticionario, "
                    "proveedores_solicitados, ofertas, lineas_oferta, retrasos "
                    "RESTART IDENTITY"
                )
            )
            sesion.commit()
        click.echo("Listas vaciadas.")


def _informar_recordatorios(resumen, config, prueba: bool) -> bool:
    """Salida y registro del recordatorio de entrega (CU-009). True si alguno ha fallado."""
    if prueba:
        carpeta = config.archivos_dir / recordatorios.CARPETA_PRUEBA
        click.echo(f"Prueba: {len(resumen.enviados)} recordatorio(s) guardados en {carpeta}")
    else:
        click.echo(f"Recordatorios enviados: {len(resumen.enviados)}")
    for codigo, motivo in resumen.omitidos:
        click.echo(f"Aviso: {codigo} no se ha avisado ({motivo}).", err=True)
    for codigo, motivo in resumen.fallidos:
        click.echo(f"{codigo}: no enviado ({motivo})", err=True)
    # En el registro de la aplicación, solo los códigos (ADR 0008).
    current_app.logger.info(
        "Recordatorio de entrega%s: enviados %s; omitidos %s; fallidos %s",
        " (prueba)" if prueba else "",
        ", ".join(resumen.enviados) or "ninguno",
        ", ".join(c for c, _ in resumen.omitidos) or "ninguno",
        ", ".join(c for c, _ in resumen.fallidos) or "ninguno",
    )
    return bool(resumen.fallidos)


def _informar_avisos(avisos, prueba: bool) -> bool:
    """Salida y registro de los avisos del pedido SAP (CU-006). True si alguno ha fallado."""
    click.echo(f"Avisos del pedido SAP: {len(avisos.enviados)}")
    if avisos.sin_avisados:
        click.echo(
            "Aviso: hay necesidades pendientes del pedido SAP, pero la lista «Avisados del "
            "pedido SAP» está vacía.",
            err=True,
        )
    for codigo, motivo in avisos.fallidos:
        click.echo(f"{codigo}: aviso del pedido SAP no enviado ({motivo})", err=True)
    for codigo, motivo in avisos.rechazados:
        click.echo(f"Aviso: {codigo}: aviso del pedido SAP enviado, pero con {motivo}.", err=True)
    current_app.logger.info(
        "Avisos del pedido SAP%s: enviados %s; fallidos %s%s",
        " (prueba)" if prueba else "",
        ", ".join(avisos.enviados) or "ninguno",
        ", ".join(c for c, _ in avisos.fallidos) or "ninguno",
        "; lista de avisados vacía" if avisos.sin_avisados else "",
    )
    return bool(avisos.fallidos)


def _informar_caducidad(caducado, prueba: bool) -> None:
    """Salida y registro de la caducidad (ADR 0014)."""
    megas = caducado.bytes / 1_000_000
    verbo = "Se borrarían" if prueba else "Borrados"
    click.echo(
        f"Caducidad: {verbo} {caducado.archivos} archivo(s) ({megas:.1f} MB) y "
        f"{caducado.logs} mensaje(s) de la tabla logs"
    )
    if caducado.reintentados:
        click.echo(
            f"Caducidad: borrados ahora {caducado.reintentados} archivo(s) de días anteriores"
        )
    if caducado.no_borrados:
        click.echo(
            f"Aviso: {caducado.no_borrados} archivo(s) caducado(s) no se han podido borrar del "
            "disco.",
            err=True,
        )
    current_app.logger.info(
        "Caducidad%s: archivos %s (%.1f MB); logs %s; no borrados %s",
        " (prueba)" if prueba else "",
        caducado.archivos,
        megas,
        caducado.logs,
        caducado.no_borrados,
    )


def _motivo(error: Exception) -> str:
    """El texto de un fallo del correo; de la base de datos, solo su tipo (sin datos de la consulta,
    ADR 0008)."""
    return str(error) if isinstance(error, ErrorCorreo) else type(error).__name__
