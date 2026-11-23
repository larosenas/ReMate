# 0016 — Entrada por un nombre con un proxy inverso (Caddy)

- **Estado:** Aceptada
- **Fecha:** 2026-11-19
- **Relacionado con:** sustituye en parte a [0006](0006-despliegue-windows-sin-https.md) (cómo se entra). Completa [0009](0009-servicio-windows-con-winsw.md) sin cambiarlo: Waitress sigue como servicio y con la misma escucha (`HOST`, `PORT`). Ver también [0015](0015-modo-admin-con-contrasena.md) (modo admin) y `backend/app/origen.py`.

## Contexto y problema

Con el ADR 0006 se entra a ReMate por `http://<ip_servidor>:2905`. Es habitual que el servidor tenga ya un proxy inverso, como Caddy, que da a cada aplicación un nombre de la red interna (por ejemplo, `http://remate.empresa.local`). Con el proxy delante, el navegador habla con el proxy y el proxy reenvía las peticiones a Waitress.

Esto tiene un efecto en la aplicación: todas las peticiones llegan desde la IP del proxy. Hay dos cosas que dependen de la IP o del esquema reales:

- **El bloqueo del modo admin** cuenta los fallos por equipo (ADR 0015). Si todo llega desde una sola IP, cinco contraseñas mal puestas por cualquiera bloquearían a todos durante 15 minutos.
- **La cookie del modo admin** solo lleva `Secure` si la petición es HTTPS (`request.is_secure`).

## Decisión

1. **El proxy reenvía** el nombre de ReMate hacia Waitress. Con Caddy:

   ```
   http://remate.empresa.local {
       reverse_proxy <ip_servidor>:2905
   }
   ```

   La IP del `reverse_proxy` tiene que ser una en la que escuche Waitress (`HOST`): si Waitress escucha en la IP del servidor, con `127.0.0.1` el proxy da un 502.
2. **Nueva variable `PROXY_DE_CONFIANZA`**, con la IP desde la que se conecta el proxy (si está en el mismo servidor, la misma de `HOST`). Con ella, Waitress toma la IP del equipo de `X-Forwarded-For` y el esquema de `X-Forwarded-Proto`, con sus propias opciones `trusted_proxy`, `trusted_proxy_count=1` y `trusted_proxy_headers`, configuradas en `backend/app/servir.py`.
   - Solo se fía de esas cabeceras si la conexión viene de esa IP; en cualquier otro caso las borra (`clear_untrusted_proxy_headers`, activo por defecto).
   - Tiene que ser una IP concreta: no se admiten nombres ni `*`, porque cualquiera podría poner otra IP en `X-Forwarded-For` y saltarse el bloqueo.
   - `X-Forwarded-Host` no se usa, porque el proxy deja pasar el `Host` tal cual. Por eso las comprobaciones de `origen.py` siguen valiendo con `APP_URL` igual al nombre.
3. **Acceso por la IP:** se puede mantener mientras haga falta (por ejemplo, para los enlaces de correos ya enviados) poniendo la IP en `HOSTS_PERMITIDOS`. Al quitarla, ReMate rechaza con `host_no_permitido` lo que no llegue por el nombre.
4. **HTTPS:** si el proxy tiene certificado, basta con quitar el `http://` del bloque y poner `APP_URL=https://…`. El código ya está preparado: la cookie del modo admin pasa a ser `Secure` sola.

## Alternativas consideradas

- **`ProxyFix` de Werkzeug:** se fía de las cabeceras venga de donde venga la conexión. Las opciones de Waitress comprueban la IP del proxy por sí solas.
- **Cambiar `HOST` a `127.0.0.1`** y que el proxy se conecte ahí: también funciona, pero cierra de golpe el acceso directo por la IP.

## Consecuencias

**Positivas:**

- Se entra por un nombre en lugar de una IP y un puerto.
- El bloqueo del modo admin sigue siendo por equipo.
- Con HTTPS en el proxy, la cookie del modo admin es `Secure` sin tocar el código.
- No hay dependencias nuevas, y sin `PROXY_DE_CONFIANZA` todo funciona como antes.

**Negativas:**

- Hay una pieza más en el camino: si el proxy se para, solo queda la IP.
- Si el proxy solo sirve HTTP, los datos siguen viajando sin cifrar por la red interna, como con el ADR 0006.
- Con `HOST` en la IP del servidor, para dejar de entrar por la IP no basta con cambiar `HOST`: hay que quitarla de `HOSTS_PERMITIDOS`.
