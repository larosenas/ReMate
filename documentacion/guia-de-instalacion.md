# Guía de instalación de ReMate, paso a paso

Tutorial para instalar ReMate en un Windows Server de la red interna, de principio a fin y en orden. Cada paso dice **dónde** se hace (tu equipo o el servidor), **con qué consola** y **qué tienes que ver** para seguir. Al final están la actualización a una versión nueva y la restauración de una copia.

El porqué de cada decisión está en los ADR: [0006](../docs/adr/0006-despliegue-windows-sin-https.md) (Windows Server sin HTTPS), [0009](../docs/adr/0009-servicio-windows-con-winsw.md) (servicio con WinSW), [0011](../docs/adr/0011-ia-solo-para-leer-ofertas-con-la-api-de-openai.md) (IA) y [0014](../docs/adr/0014-caducidad-de-archivos-y-copias.md) (caducidad y copias).

## Antes de empezar

### Cómo queda instalado

```text
C:\ReMate\
├── app\        el código (backend\, scripts\, frontend\dist\) y el .env  → permiso necesario: leer y ejecutar
├── archivos\   adjuntos, correos y pedidos                             → permiso necesario: escribir
├── logs\       remate.log y recordatorios.log (respaldo del registro)   → permiso necesario: escribir
└── copias\     copias de seguridad (si no van a otra unidad)            → permiso necesario: escribir
```

- El código va en `C:\ReMate\app`, **no** en `C:\ReMate`: los scripts de `scripts\windows` y el servicio (`remate-servicio.xml`) buscan los logs en la carpeta de al lado (`C:\ReMate\logs`).
- `archivos\`, `logs\` y `copias\` no vienen en el código. Las creas tú como administrador, para poder dar a la cuenta de ReMate permiso de escritura **solo** en ellas (paso 3).
- **No se clona el repositorio en el servidor:** se copia un paquete preparado en tu equipo. La interfaz (`frontend\dist`) no está en el repositorio, se compila en tu equipo, y el servidor no necesita Git, Node.js ni acceso a GitHub.

### Dónde ejecutar los pasos

Los pasos indican si se hacen en tu equipo o en el servidor. `[Admin]` señala los que necesitan una consola elevada.

En PowerShell, un programa externo que falla no siempre detiene el bloque: los comandos de esta guía llevan `if ($LASTEXITCODE -ne 0) { throw ... }`. Si salta, **no sigas**: resuelve el error primero.

### Lo que tienes que pedir a sistemas

Apúntalo fuera del repositorio (son datos del servidor y contraseñas):

- [ ] Acceso de administrador al servidor, su nombre y que la zona horaria sea la correcta. Y la **dirección con la que entrarán los usuarios** (por ejemplo, `http://<ip_servidor>:2905`): va en `APP_URL` (paso 7), y ReMate solo atiende peticiones dirigidas a ella, a `localhost` y a los nombres de `HOSTS_PERMITIDOS`.
- [ ] La **cuenta de Windows** que ejecutará ReMate, con permiso para iniciar sesión como servicio y como trabajo por lotes, y su contraseña para configurar el servicio y las tareas.
- [ ] .NET Framework 4.8 para `WinSW.NET461.exe`, y la aprobación de ese binario (paso 13).
- [ ] PostgreSQL 18: si va en el mismo servidor o en otro; host, puerto y quién crea la base de datos.
- [ ] La **subred interna** que podrá entrar a ReMate y el perfil del cortafuegos.
- [ ] El **servidor de correo (SMTP)**: servidor, puerto, cifrado, remitente y usuario (o relé permitido).
- [ ] Salida a internet desde el servidor hacia la API de OpenAI (`api.openai.com`, HTTPS, 443) y hacia el índice de paquetes de Python para instalar las dependencias.
- [ ] Una **clave de API de OpenAI** para ReMate. Modelo recomendado: `gpt-5-mini` con `IA_RAZONAMIENTO=low`. La clave solo se escribe en el `.env` del servidor.
- [ ] Copias: destino (mejor fuera del servidor) y una hora en la que no se use ReMate.
- [ ] Que el antivirus analice en tiempo real `C:\ReMate\archivos` y la carpeta de las copias, y que el destino de las copias esté cifrado (BitLocker o equivalente).

Y de los usuarios: el **CSV con proveedores y peticionarios** (no se guarda en el repositorio).

### Cuenta que ejecutará ReMate

En una PowerShell normal de la sesión de esa cuenta:

```powershell
whoami
```

Anota el resultado, con formato `SERVIDOR\usuario` o `DOMINIO\usuario`. Ese nombre se pone en `$cuenta` en los pasos 3 y 13 y en **ReMate → Propiedades → Iniciar sesión** en `services.msc`. El servicio y las dos tareas usan esa misma cuenta, y Windows pide su contraseña para ejecutarlos aunque se cierre la sesión (el PIN del escritorio no la sustituye).

El servicio funciona sin mantener abierta la sesión de escritorio. Si cambia o caduca la contraseña, hay que actualizarla en el servicio y en las dos tareas. No se añaden permisos de administrador para ejecutar ReMate.

---

## Parte A. En tu equipo: preparar el paquete

### Paso 1. Sacar una copia limpia de la versión que vas a instalar [Tu equipo]

En una carpeta aparte, para no tocar tu copia de trabajo:

```powershell
git clone --branch main <url del repositorio> C:\entrega\ReMate
cd C:\entrega\ReMate
git rev-parse HEAD          # apunta este SHA: es la versión que instalas
```

Antes de seguir, pasa sobre esa versión las pruebas, los linters y el build del backend y del frontend (ver el [README](../README.es.md#pruebas-y-comprobaciones)). Si alguna comprobación falla, no se instala.

### Paso 2. Compilar la interfaz y montar el paquete [Tu equipo]

```powershell
cd C:\entrega\ReMate\frontend
npm ci
if ($LASTEXITCODE -ne 0) { throw 'npm ci ha fallado.' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'El build ha fallado.' }

$origen = 'C:\entrega\ReMate'
$paquete = 'C:\entrega\paquete-remate'
robocopy "$origen\backend" "$paquete\backend" /E /XD .venv __pycache__ .pytest_cache .ruff_cache htmlcov /XF .coverage *.pyc
robocopy "$origen\scripts" "$paquete\scripts" /E
robocopy "$origen\frontend\dist" "$paquete\frontend\dist" /E
New-Item -ItemType Directory -Force -Path "$paquete\documentacion" | Out-Null
Copy-Item "$origen\.env.example", "$origen\README.md" $paquete
Copy-Item "$origen\documentacion\guia-de-instalacion.md", "$origen\documentacion\manual-de-usuario.md" "$paquete\documentacion"
Compress-Archive -Path "$paquete\*" -DestinationPath "C:\entrega\remate-<SHA corto>.zip"
```

(`robocopy` devuelve códigos del 0 al 7 cuando va bien; 8 o más es un error.)

**Comprueba** que el zip tiene `backend\`, `scripts\`, `frontend\dist\index.html`, `.env.example` y `documentacion\`, y que **no** tiene `.env`, `.git`, `.venv`, `node_modules` ni ningún CSV.

Lleva el zip al servidor (carpeta compartida, escritorio remoto…).

---

## Parte B. En el servidor

### Paso 3. Crear las carpetas y darles permisos [Admin]

```powershell
New-Item -ItemType Directory -Force -Path C:\ReMate\app, C:\ReMate\archivos, C:\ReMate\logs, C:\ReMate\copias

$cuenta = '<resultado de whoami en la sesión de la cuenta de ReMate>'
icacls C:\ReMate\archivos /grant "${cuenta}:(OI)(CI)M"
icacls C:\ReMate\logs     /grant "${cuenta}:(OI)(CI)M"
icacls C:\ReMate\copias   /grant "${cuenta}:(OI)(CI)M"
icacls C:\ReMate\app      /grant "${cuenta}:(OI)(CI)RX"
```

`M` es modificar (leer y escribir); `RX`, leer y ejecutar. `/grant` **añade** permisos y no quita los heredados: revisa que otros usuarios no pueden leer `archivos\` ni `copias\`.

### Paso 4. Copiar el código [Admin]

```powershell
Expand-Archive -Path <ruta del zip> -DestinationPath C:\ReMate\app
Test-Path C:\ReMate\app\backend\app, C:\ReMate\app\frontend\dist\index.html, C:\ReMate\app\scripts\windows\remate-servicio.xml
```

**Tienes que ver** tres `True`. Si el zip dejó una carpeta intermedia (`C:\ReMate\app\paquete-remate\...`), mueve su contenido a `C:\ReMate\app`.

### Paso 5. Instalar Python 3.15 y PostgreSQL 18 [Admin]

1. **Python 3.15** desde python.org: marca «instalar para todos los usuarios» y el lanzador `py`.
2. **PostgreSQL 18** con el instalador oficial. Si la base de datos va en otro servidor, instala solo las herramientas de línea de órdenes (`psql`, `pg_dump`, `pg_restore`): las necesitan las copias.

Abre una consola [Admin] nueva y comprueba:

```powershell
py -3.15 --version
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' --version
```

### Paso 6. Crear la base de datos [Admin]

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h localhost -p 5432 -U postgres -d postgres
```

Dentro de `psql` (si PostgreSQL es remoto, cambia el host):

```sql
CREATE ROLE remate LOGIN;
\password remate
CREATE DATABASE remate OWNER remate ENCODING 'UTF8';
\q
```

`\password` pide la contraseña sin que quede escrita. Guárdala en un gestor de contraseñas: la necesitas en los pasos 7 y 8. Comprueba que el usuario nuevo entra:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\psql.exe' -h localhost -p 5432 -U remate -d remate -c "SELECT 1;"
```

### Paso 7. Crear el `.env` de producción [Admin]

```powershell
cd C:\ReMate\app
Copy-Item .env.example .env
notepad .env
```

Cambia estas variables (cada una lleva encima su explicación) y no dejes ningún valor de ejemplo:

| Variable | Valor |
| --- | --- |
| `APP_ENV` | `production` |
| `HOST`, `PORT` | IP local de escucha (`0.0.0.0` por defecto) y puerto (`2905` por defecto) |
| `DB_HOST`, `DB_PORT` | los de PostgreSQL (`localhost` y `5432` si está en el mismo servidor) |
| `DB_NAME`, `DB_USER` | `remate` |
| `DB_PASSWORD` | la del paso 6 |
| `ARCHIVOS_DIR` | `C:\ReMate\archivos` |
| `FRONTEND_DIST` | vacío |
| `IA_API_KEY` | la clave de API de OpenAI (vacía: ReMate funciona sin IA y los datos se escriben a mano) |
| `IA_MODELO` | el modelo de OpenAI, por ejemplo `gpt-5-mini` |
| `IA_RAZONAMIENTO` | `low` (o vacío, que es lo mismo). Con un valor que no sea `none`, `minimal`, `low`, `medium`, `high`, `xhigh` o `max`, ReMate no arranca |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_SECURE`, `SMTP_FROM` | los del servidor de correo |
| `APP_URL` | **Imprescindible en producción:** la dirección con la que entran los usuarios, por ejemplo `http://<ip_servidor>:2905`. Sirve para el enlace de los correos, y ReMate solo atiende peticiones dirigidas a esa dirección, a `localhost` y a las de `HOSTS_PERMITIDOS` (protección frente a DNS rebinding). Vacía, ReMate arranca, pero los correos van sin enlace y esa protección no se aplica |
| `HOSTS_PERMITIDOS` | Opcional: otros nombres o IP con los que se entre a ReMate (por ejemplo, el nombre del servidor), separados por comas y sin `http://` ni puerto |
| `PROXY_DE_CONFIANZA` | Opcional: la IP desde la que se conecta el proxy inverso, si se entra a través de uno (apartado «Entrar por un nombre con un proxy inverso»). Vacía: sin proxy |
| `EMPRESA_NOMBRE` | Opcional: el nombre de la empresa, que va en la firma de los correos a los proveedores. Vacío, la firma no lo lleva |
| `ADMIN_CLAVE_HASH` | Opcional: el hash de la contraseña del modo admin, entre comillas simples. Se genera con `flask --app app clave-admin`, mejor en otro equipo para que la contraseña no pase por el servidor. Vacía, el modo admin queda desactivado |
| `COPIAS_DIR` | Opcional: `C:\ReMate\copias`, para que el modo admin muestre la última copia |

Si eliges otro puerto, adapta `APP_URL` y la regla del cortafuegos. Si `HOST` es una IP concreta, prueba en esa IP en lugar de `localhost`. Los cambios se aplican al reiniciar el servicio; las variables del entorno tienen prioridad sobre el `.env`.

Guarda, cierra el Bloc de notas y protege el archivo (solo la cuenta de ReMate lo lee; Administradores y SYSTEM, control total):

```powershell
icacls C:\ReMate\app\.env /inheritance:r /grant:r "${cuenta}:R" "*S-1-5-32-544:F" "*S-1-5-18:F"
```

(Si cerraste la consola, vuelve a definir `$cuenta` como en el paso 3.) Para editarlo más adelante, abre el Bloc de notas como administrador.

### Paso 8. Salida hacia la IA y contraseña de las copias

Este paso se hace en una PowerShell normal de la **cuenta de ReMate** (comprueba `whoami`), porque la contraseña de las copias se guarda en su perfil.

**8.1 Salida hacia la API de OpenAI.** No se instala nada en el servidor: basta con la clave del paso 7 y salida a internet.

```powershell
Test-NetConnection api.openai.com -Port 443
```

**Tienes que ver** `TcpTestSucceeded : True`. La prueba de verdad (que la clave y el modelo funcionan) se hace en el paso 14.

**8.2 Contraseña para las copias.** El script de copia no lee el `.env`: `pg_dump` toma la contraseña de este archivo del perfil de la cuenta.

```powershell
New-Item -ItemType Directory -Force -Path "$env:APPDATA\postgresql" | Out-Null
notepad "$env:APPDATA\postgresql\pgpass.conf"
```

Escribe una sola línea (adapta host y puerto si PostgreSQL es remoto; escapa `:` y `\` con `\` si forman parte de un campo) y guarda:

```text
localhost:5432:remate:remate:<contraseña del paso 6>
```

Protégelo, porque PostgreSQL no lo hace en Windows:

```powershell
icacls "$env:APPDATA\postgresql\pgpass.conf" /inheritance:r /grant:r "${env:USERDOMAIN}\${env:USERNAME}:F" "*S-1-5-18:F"
```

Deja esta consola abierta: la usas en los pasos 10 y 11.

### Paso 9. Entorno de Python y tablas [Admin]

```powershell
cd C:\ReMate\app\backend
py -3.15 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Creación del entorno fallida.' }
.\.venv\Scripts\pip.exe install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Instalación de dependencias fallida.' }
.\.venv\Scripts\pip.exe check
if ($LASTEXITCODE -ne 0) { throw 'Dependencias incompatibles.' }
.\.venv\Scripts\alembic.exe upgrade head
if ($LASTEXITCODE -ne 0) { throw 'Migración fallida: no arrancar la aplicación.' }
.\.venv\Scripts\alembic.exe current
.\.venv\Scripts\alembic.exe heads
.\.venv\Scripts\pip.exe freeze > C:\ReMate\versiones-instaladas.txt
```

**Tienes que ver** que `current` y `heads` muestran la misma revisión. El `.venv` hereda de `app\` el permiso de lectura y ejecución de la cuenta de ReMate.

### Paso 10. Cargar proveedores y peticionarios

Copia el CSV a una carpeta que la cuenta pueda leer (por ejemplo `C:\ReMate\archivos\carga.csv`). Formato: UTF-8, separado por `;`, cabecera `tipo;nombre;correo`, tipo `proveedor` o `peticionario`.

```powershell
cd C:\ReMate\app\backend
.\.venv\Scripts\flask.exe --app app cargar-listas C:\ReMate\archivos\carga.csv
```

Revisa los contadores y las líneas con error. Una línea mal no deshace las demás: corrige el CSV y repite (los correos ya cargados se omiten). Cuando las listas estén bien en la interfaz (paso 11), **borra el CSV del servidor**.

Los avisados del pedido (quienes reciben el aviso cuando hay que emitir un pedido en el ERP) se dan de alta después, desde la pantalla de listas.

### Paso 11. Primera prueba, a mano

```powershell
cd C:\ReMate\app\backend
.\.venv\Scripts\python.exe -m app.servir --log C:\ReMate\logs\remate.log
```

La consola se queda «colgada» y sin mensajes: es normal. El registro de la aplicación se guarda en la base de datos, tabla `logs` ([ADR 0008](../docs/adr/0008-registro-en-la-base-de-datos.md)); lo que no se puede guardar allí, como un error al arrancar, va a `C:\ReMate\logs\remate.log`. En un navegador del servidor:

1. `http://localhost:2905/api/salud` → **tienes que ver** `{"estado": "ok", "base_de_datos": "ok"}`.
2. `http://localhost:2905` → el panel de ReMate.
3. `http://localhost:2905/listas` y recarga la página (F5) → sigue apareciendo, con los proveedores y peticionarios del paso 10.

Si algo falla, mira primero el final de `remate.log` (`Get-Content C:\ReMate\logs\remate.log -Tail 30`) y, si la aplicación llegó a arrancar, la tabla `logs`:

```sql
SELECT creado_en, nivel, origen, mensaje FROM logs ORDER BY id DESC LIMIT 20;
```

Para pararlo, Ctrl+C en la consola.

### Paso 12. Abrir el puerto solo a la red interna [Admin]

```powershell
New-NetFirewallRule -DisplayName 'ReMate (puerto 2905)' -Direction Inbound -Protocol TCP -LocalPort 2905 `
    -RemoteAddress '<subred interna, por ejemplo 10.0.0.0/16>' -Action Allow -Profile Domain
```

Revisa que no hay otra regla más amplia que ya abra el 2905 o `python.exe`. ReMate no tiene inicio de sesión: quien llegue al puerto, entra.

### Paso 13. Instalar el servicio y crear las dos tareas [Admin]

Antes, para la prueba del paso 11 (Ctrl+C).

#### Instalar el servicio de Windows [Admin]

1. En un equipo con acceso a internet, abre la [release oficial WinSW 2.12.0](https://github.com/winsw/winsw/releases/tag/v2.12.0) y descarga **WinSW.NET461.exe**. Comprueba que el servidor tiene **.NET Framework 4.8**. No uses los binarios x64/x86 de esa release, que incluyen otro runtime. Lleva también la [licencia MIT](https://github.com/winsw/winsw/blob/v2.12.0/LICENSE.txt).
2. Antes de ejecutarlo, comprueba su procedencia, su versión y los avisos de seguridad. Registra `Get-FileHash <ruta del exe> -Algorithm SHA256` y `(Get-Item <ruta del exe>).VersionInfo`.
3. Cópialo como `C:\ReMate\app\scripts\windows\remate-servicio.exe`, junto a `remate-servicio.xml`, con la licencia al lado como `WinSW-LICENSE.txt`. El ejecutable no va en el repositorio. La cuenta de ReMate necesita leer y ejecutar estos archivos, no escribirlos.
4. Instala el servicio, sin arrancarlo:

   ```powershell
   cd C:\ReMate\app\scripts\windows
   .\remate-servicio.exe install
   if ($LASTEXITCODE -ne 0) { throw 'Instalación del servicio fallida.' }
   services.msc
   ```

5. En **ReMate → Propiedades → Iniciar sesión**, elige la cuenta que anotaste con `whoami` y pon su contraseña de Windows. WinSW instala por defecto con LocalSystem: **no lo arranques así**.
6. En **General**, elige inicio **Automático (inicio retrasado)**. En **Recuperación**, elige «Reiniciar el servicio» en el primer error, el segundo y los siguientes, al minuto, y activa también la recuperación para detenciones con error. El XML instala en modo manual para poder hacer esto antes del primer inicio.
7. Inicia el servicio y comprueba la cuenta y el estado:

   ```powershell
   Start-Service -Name ReMate
   Get-CimInstance Win32_Service -Filter "Name='ReMate'" |
       Select-Object Name, State, StartName, StartMode
   ```

   Debe estar `Running`, con la cuenta de ReMate y arranque automático. Los mensajes del propio servicio quedan en `remate-servicio.wrapper.log`, en `C:\ReMate\logs`.

#### Crear las tareas de recordatorio y copia [Admin]

```powershell
$cuenta = '<resultado de whoami en la sesión de la cuenta de ReMate>'
$credencial = Get-Credential -UserName $cuenta -Message 'Cuenta de las tareas de ReMate'
$clave = $credencial.GetNetworkCredential().Password
$scripts = 'C:\ReMate\app\scripts\windows'
$ps = '-NoProfile -ExecutionPolicy Bypass -File'

# 1. Tarea diaria (recordatorio de entrega, avisos del pedido y caducidad), a las 9:00.
Register-ScheduledTask -TaskName 'ReMate - recordatorio' -User $cuenta -Password $clave -RunLevel Limited `
    -Action (New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "$ps $scripts\enviar-recordatorios.ps1") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 9:00) `
    -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew)

# 2. La copia de seguridad: se crea DESHABILITADA (paso 16). La hora es un ejemplo.
Register-ScheduledTask -TaskName 'ReMate - copia de seguridad' -User $cuenta -Password $clave -RunLevel Limited `
    -Action (New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "$ps $scripts\copia-de-seguridad.ps1") `
    -Trigger (New-ScheduledTaskTrigger -Daily -At 22:00) `
    -Settings (New-ScheduledTaskSettingsSet -Disable -StartWhenAvailable -MultipleInstances IgnoreNew)

Remove-Variable clave, credencial
```

- `Get-Credential` pide la contraseña en una ventana, para que no quede escrita en el comando ni en el historial; `Remove-Variable` la borra de la memoria al final.
- Las dos tareas se ejecutan con la cuenta de ReMate, sin privilegios elevados (`-RunLevel Limited`) y aunque nadie haya iniciado sesión. Si el servidor estaba apagado a su hora, se lanzan al encenderlo (`-StartWhenAvailable`).

**Comprueba:** `Get-Service ReMate` muestra `Running`, `Get-ScheduledTask -TaskName 'ReMate*'` muestra las dos tareas (la de copia, `Disabled`) y `http://localhost:2905/api/salud` vuelve a responder «ok».

### Paso 14. Comprobar que funciona de verdad

- [ ] **Desde el equipo de un usuario**, la dirección de `APP_URL` abre el panel; desde una red no autorizada, no. Con otro nombre o IP sale `{"error": "host_no_permitido"}`: si se quiere entrar también así, añádelo a `HOSTS_PERMITIDOS`.
- [ ] **Una necesidad de prueba:** créala, sube y descarga un adjunto y cancélala con el motivo «Prueba de instalación».
- [ ] **La IA, sin sesión abierta en el servidor:** redacta una solicitud de ofertas y lee una oferta de prueba con datos inventados. Si falla, el motivo está en la tabla `logs` (origen `app.integraciones.ia`); si funciona, cada llamada deja una línea con sus tokens.
- [ ] **Los `.eml`** se descargan y se abren y envían desde el programa de correo del usuario.
- [ ] **El registro:** la consulta del paso 11 muestra lo que acabas de hacer («Necesidad creada: …»).
- [ ] **Reinicio del servidor:** después, ReMate vuelve a estar en marcha sin hacer nada.
- [ ] **Caída:** en una ventana de mantenimiento, cierra el proceso de ReMate (el `python.exe` de `C:\ReMate\app\backend\.venv` con `-m app.servir`; comprueba el PID y la ruta, y no cierres procesos por nombre genérico). Tiene que volver en un minuto, con una sola instancia. Comprueba también que `Stop-Service ReMate` lo deja parado sin reinicio.

### Paso 15. Probar el recordatorio

```powershell
cd C:\ReMate\app\backend
.\.venv\Scripts\flask.exe --app app enviar-recordatorios --prueba
```

Con `--prueba` no envía nada: guarda los correos como `.eml` en `C:\ReMate\archivos\recordatorios-prueba\` (solo si hay necesidades en «Pendiente entrega» a 7 días o menos y sin aviso enviado) y cuenta lo que caducaría. El envío real por SMTP se prueba aparte, con un destinatario de prueba, y el resultado de cada día se ve en `C:\ReMate\logs\recordatorios.log`.

### Paso 16. Activar las copias de seguridad [Admin]

La tarea de copia está deshabilitada a propósito: el script copia primero la base de datos y luego los archivos **sin parar ReMate**, y si alguien sube algo entre medias, la copia no casa. Antes de activarla:

1. **Acuerda la hora** (cuando nadie use ReMate) y el destino (mejor fuera del servidor). Para una copia coherente, en esa ventana hay que deshabilitar y detener el servicio y la tarea diaria, hacer la copia y volver a arrancar.
2. **Si el destino u otros datos no son los de por defecto**, añade los parámetros al argumento de la tarea, porque el script no lee el `.env`: `-Servidor`, `-Puerto`, `-Usuario`, `-BaseDeDatos`, `-Archivos` y `-Destino` (por ejemplo, `-Destino "<destino acordado>"`). Lo que se guarda está fijado en el ADR 0014: 7 volcados diarios, 4 semanales y una copia espejo de los archivos (`-Diarias` y `-Semanales`).
3. **Haz una copia a mano y compruébala:**

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File C:\ReMate\app\scripts\windows\copia-de-seguridad.ps1
   if ($LASTEXITCODE -ne 0) { throw 'Copia fallida.' }
   ```

   **Tienes que ver** «Copia de seguridad hecha en C:\ReMate\copias\remate-AAAAMMDD-HHMMSS», con el `.dump` y el marcador `.remate-copia-completa` dentro; los archivos van en `C:\ReMate\copias\archivos-espejo`.
4. **Ensaya una restauración** en una base de datos y una carpeta de prueba, nunca encima de las de producción (ver [Restaurar una copia](#restaurar-una-copia)). Una copia que no se ha probado a restaurar no cuenta.
5. **[Admin]** Solo entonces: `Enable-ScheduledTask -TaskName 'ReMate - copia de seguridad'`.

### Paso 17. Dejarlo registrado

Fuera del repositorio, anota: el SHA de la versión instalada, la revisión de Alembic, la fecha, quién instala, `C:\ReMate\versiones-instaladas.txt`, el resultado de los pasos 14 a 16 y lo que quede pendiente.

---

## Entrar por un nombre con un proxy inverso (opcional)

Si el servidor tiene un proxy inverso como Caddy, se puede entrar por un nombre de la red interna (por ejemplo, `http://remate.empresa.local`) en lugar de la IP y el puerto ([ADR 0016](../docs/adr/0016-proxy-inverso-con-caddy.md)). Ejemplo con Caddy y Waitress escuchando en la IP del servidor (`HOST=<ip_servidor>`):

1. **Caddy.** Añade al `Caddyfile`:

   ```
   http://remate.empresa.local {
       reverse_proxy <ip_servidor>:2905
   }
   ```

   La IP tiene que ser una en la que escuche Waitress: con `127.0.0.1`, si `HOST` es la IP del servidor, sale un 502. Valida y recarga (la recarga no corta los demás sitios):

   ```powershell
   & "<carpeta de Caddy>\caddy.exe" validate --config "<carpeta de Caddy>\Caddyfile" --adapter caddyfile
   & "<carpeta de Caddy>\caddy.exe" reload --config "<carpeta de Caddy>\Caddyfile" --adapter caddyfile
   ```

2. **`.env`** (haz antes una copia). Cada variable una sola vez, porque si se repite gana la última:

   ```
   APP_URL=http://remate.empresa.local
   PROXY_DE_CONFIANZA=<ip_servidor>
   HOSTS_PERMITIDOS=<ip_servidor>
   ```

   `PROXY_DE_CONFIANZA` es la IP desde la que se conecta el proxy: si está en el mismo servidor, la de `HOST`. `HOSTS_PERMITIDOS` con la IP mantiene el acceso por `http://<ip_servidor>:2905`, por ejemplo para los enlaces de los correos ya enviados. Reinicia el servicio `ReMate`.

3. **Comprueba:** en el servidor, `curl.exe -i -H "Host: remate.empresa.local" http://127.0.0.1/api/salud` da `200 OK` con `Via: 1.1 Caddy` (justo después de reiniciar puede dar un 502 unos segundos); desde un equipo de la red, el nombre abre el panel y el modo admin deja entrar.
4. **Dejar de entrar por la IP**, cuando ya no haga falta: vacía `HOSTS_PERMITIDOS` y reinicia. ReMate responde `host_no_permitido` a lo que no llegue por el nombre.
5. **HTTPS**, si el proxy tiene certificado: quita el `http://` del bloque, pon `APP_URL=https://remate.empresa.local` y reinicia. La cookie del modo admin pasa a ser `Secure` sola.
6. **Volver atrás:** quita el bloque del `Caddyfile` y recarga; devuelve el `.env` de la copia y reinicia ReMate.

---

## Actualizar a una versión nueva

1. **Prepara el paquete** de la versión nueva (pasos 1 y 2). Revisa sus migraciones y sus variables nuevas en `.env.example`. Guarda la configuración actual del servicio (cuenta, inicio y recuperación), del XML y de las tareas.
2. **Para todo** y evita que se vuelva a lanzar durante el mantenimiento:

   ```powershell
   Set-Service -Name ReMate -StartupType Disabled
   Disable-ScheduledTask -TaskName 'ReMate - recordatorio'
   Disable-ScheduledTask -TaskName 'ReMate - copia de seguridad'
   Stop-Service -Name ReMate
   Stop-ScheduledTask -TaskName 'ReMate - recordatorio'
   ```

   Si hay una copia en curso, espera a que termine.
3. **Haz una copia a mano** con la cuenta de ReMate, en primer plano (paso 16.3), y comprueba el marcador, el `.dump` y los archivos.
4. **Guarda la versión anterior** fuera de `app`, con un nombre único (fecha o SHA): `backend`, `scripts`, `frontend\dist` y la documentación. El `.venv` no se puede mover: si hace falta volver, se recrea.
5. **Copia el paquete nuevo**, incluidos los scripts. Sustituye entero `frontend\dist` para no mezclar versiones. Añade al `.env` solo las variables nuevas, conservando sus valores y sus permisos.
6. **Recrea el entorno y aplica las migraciones** como en el paso 9, y comprueba que `current` coincide con `heads`. No ejecutes migraciones mientras quede algún proceso de la versión anterior.
7. **Arranca y comprueba:**

   ```powershell
   Set-Service -Name ReMate -StartupType Automatic
   Start-Service -Name ReMate
   # Solo después de comprobar la aplicación:
   Enable-ScheduledTask -TaskName 'ReMate - recordatorio'
   Enable-ScheduledTask -TaskName 'ReMate - copia de seguridad'
   ```

   Comprueba la salud, el panel, el detalle de una necesidad y la subida y descarga de archivos. Si era inicio retrasado, repónlo en `services.msc`.

**Volver atrás:** con el servicio y las tareas deshabilitados, recupera el paquete anterior y recrea su entorno. Si se aplicaron migraciones, restaura juntas la base de datos y los archivos de la copia del punto 3: no des por hecho que el código anterior entiende el esquema nuevo, ni ejecutes `alembic downgrade` sin haberlo probado. Restaurar descarta los cambios posteriores a la copia.

## Restaurar una copia

### Ensayo en destinos separados

Usa una copia completa y el paquete de código de su misma versión. Crea una **base de datos vacía de ensayo** (por ejemplo, `remate_restauracion`) y una carpeta nueva para sus archivos. No apuntes el ensayo a `remate` ni a `C:\ReMate\archivos`.

```powershell
$copia = 'C:\ReMate\copias\remate-<AAAAMMDD-HHMMSS>'
$volcado = Join-Path $copia 'remate-<AAAAMMDD-HHMMSS>.dump'
if (-not (Test-Path -LiteralPath (Join-Path $copia '.remate-copia-completa'))) { throw 'Copia sin marcador.' }
if (-not (Test-Path -LiteralPath $volcado -PathType Leaf)) { throw 'Falta el volcado.' }
$espejo = 'C:\ReMate\copias\archivos-espejo'
if (-not (Test-Path -LiteralPath $espejo -PathType Container)) { throw 'Faltan los archivos.' }
& 'C:\Program Files\PostgreSQL\18\bin\pg_restore.exe' -h localhost -p 5432 -U remate `
    -d remate_restauracion --exit-on-error --single-transaction --no-owner --no-privileges $volcado
if ($LASTEXITCODE -ne 0) { throw 'Restauración fallida: no continuar.' }
# La carpeta destino debe ser nueva; New-Item falla si ya existe.
New-Item -ItemType Directory -Path C:\ReMate\ensayo-restauracion
if (-not $?) { throw 'El destino de ensayo ya existe o no se puede crear.' }
robocopy $espejo C:\ReMate\ensayo-restauracion /E /R:2 /W:5 /NP /NFL /NDL
if ($LASTEXITCODE -ge 8) { throw 'Copia de archivos fallida: no continuar.' }
```

Comprueba la revisión en `alembic_version`, los recuentos de registros y que existen los archivos a los que apunta la base de datos (los adjuntos con `caducado_en` no tienen archivo: es lo esperado). El espejo es el de la última copia, no el del día del volcado: puede tener archivos de necesidades posteriores que la base restaurada no conoce. Si quieres probar la interfaz, usa una instalación aparte con su propio `.env`, la base y la carpeta de ensayo, otro puerto y el correo y la IA desactivados. Listar un `.dump` con `pg_restore --list` no sustituye este ensayo.

### Recuperación de producción

Sustituye el estado actual por el de la copia, así que se hace con la autorización de los responsables:

1. Acuerda el punto de recuperación y, si es posible, guarda antes el estado actual.
2. Deshabilita y detén el servicio y las dos tareas, como al actualizar.
3. Restaura en una **base de datos nueva y vacía** y en una **carpeta nueva de archivos**, con el procedimiento ya ensayado. Así no se mezclan tablas o archivos posteriores con la versión recuperada.
4. Recupera el código compatible y su entorno. Cambia `DB_NAME` y `ARCHIVOS_DIR` en el `.env` a los destinos recuperados, y también los parámetros de la tarea de copia y el `pgpass.conf`.
5. Arranca solo la aplicación y comprueba la conexión, la revisión del esquema, los listados, el detalle y los adjuntos. Habilita las tareas después, y comunica a los usuarios qué datos posteriores a la copia se han perdido.

No uses `robocopy /MIR` contra la carpeta activa: borra los archivos que no están en la copia. Tampoco basta `pg_restore --clean` para quitar las tablas de una versión posterior; por eso se restaura en una base vacía. No arranques tras un error de restauración.

---

## Lo que no hay que hacer

- No poner el código en `C:\ReMate` directamente, ni clonar el repositorio en el servidor.
- No copiar el `.env` ni el `.venv` de tu equipo.
- No añadir privilegios de administrador a la cuenta para ejecutar ReMate.
- No arrancar ReMate a mano mientras el servicio está en marcha: habría dos procesos peleando por el puerto.
- No ejecutar `pytest` ni `vaciar-listas` en producción.
- No pegar contraseñas en los comandos ni enseñar el contenido del `.env` o del `pgpass.conf`.
