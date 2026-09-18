# Operación del Cotizador

Guía de las cosas que hay que hacer a mano: puesta en marcha, despliegue, alta
de usuarios y las dos tareas urgentes de seguridad que quedaron pendientes.

---

## 1. URGENTE — Sacar del repositorio los datos de clientes

Los datos de clientes **ya están cargados en Neon**, que es donde tienen que
vivir. En el repositorio eran una segunda copia de la cartera comercial al
alcance de cualquiera con acceso al código.

Son cinco archivos:

| Archivo | Tamaño | Contenido |
|---|---|---|
| `sql/seed_contactos_isc.sql` | 2.4 MB | Contactos de clientes (nombres, correos, teléfonos) |
| `isc_customer_contacts.sql` | 2.3 MB | Contactos de clientes |
| `sql/seed_clientes_isc.sql` | 23 KB | Cartera de clientes |
| `sql/seed_clientes_top12.sql` | 2 KB | Razones sociales, condiciones de pago y dominios |
| `isc_schema_postgres.sql` | 119 KB | Esquema del sistema legado, ya superado por `sql/schema.sql` |

Ninguno lo carga el código: ni `scripts/db_init.sh`, ni el workflow de Neon, ni
ningún módulo de Python los referencia. Quitarlos no rompe nada.

Los tres pasos de abajo los tienes que ejecutar tú: el puente con tu equipo
permite escribir archivos pero no borrarlos, y tampoco ejecutar git en tu
máquina.

### Antes de borrar nada: respalda

Si los quitas del repositorio, **la única copia de esos datos queda en Neon**.
Haz un respaldo fuera del repositorio antes:

```bash
pg_dump "$DATABASE_URL" --data-only \
  -t clientes -t cliente_dominios -t cliente_contactos -t cliente_direcciones \
  -f respaldo_clientes_$(date +%Y%m%d).sql
```

Guárdalo donde guardas los respaldos de la empresa, **no** en la carpeta del
proyecto (si lo dejas ahí, `.gitignore` no lo cubre por el nombre).

### Paso 1 — Sacarlos del seguimiento de git

Esto los quita de los commits futuros, dejando los archivos en tu disco:

```bash
git rm --cached isc_customer_contacts.sql isc_schema_postgres.sql \
  sql/seed_contactos_isc.sql sql/seed_clientes_isc.sql sql/seed_clientes_top12.sql
git commit -m "chore: sacar del repositorio los datos de clientes (viven en Neon)"
```

Ya están todos en `.gitignore`, así que no volverán a entrar por accidente.

### Paso 2 — Borrarlos del disco

Una vez respaldados y fuera de git:

```bash
del isc_customer_contacts.sql isc_schema_postgres.sql
del sql\seed_contactos_isc.sql sql\seed_clientes_isc.sql sql\seed_clientes_top12.sql
```

Tras esto el repositorio no contiene ningún dato de clientes. Para trabajar en
local, carga en tu base de desarrollo el subconjunto que necesites desde el
respaldo del paso anterior, o desde Neon directamente. No se deja ningún juego
de datos de ejemplo en el repositorio: el sistema trabaja con los clientes
reales de ISC y unos ficticios sólo darían resultados que no significan nada.

### Paso 3 — Purga del historial

Los pasos anteriores no sacan los archivos de los **commits anteriores**:
cualquiera con acceso al repositorio los sigue teniendo.

**Cómo purgarlos.** Avisa antes al equipo: esto reescribe el historial y todos
tendrán que volver a clonar.

```bash
# 1. Respaldo completo, por si algo sale mal
git clone --mirror <url-del-repo> respaldo-cotizador.git

# 2. Instalar la herramienta (git filter-branch está desaconsejado)
pip install git-filter-repo

# 3. Desde un clon limpio del repositorio
git filter-repo \
  --path sql/seed_contactos_isc.sql \
  --path sql/seed_clientes_isc.sql \
  --path sql/seed_clientes_top12.sql \
  --path isc_customer_contacts.sql \
  --path isc_schema_postgres.sql \
  --invert-paths

# 4. Volver a apuntar al remoto y forzar
git remote add origin <url-del-repo>
git push --force --all
git push --force --tags
```

**Después de purgar:**

- Cada persona del equipo borra su clon y vuelve a clonar. Un `git pull` sobre
  un clon viejo reintroduce los objetos.
- Si el repositorio está en GitHub, abre un ticket de soporte para que purguen
  las vistas en caché de los commits viejos: siguen siendo accesibles por SHA
  aunque ya no estén en ninguna rama.
- Revisa si hay forks. Un fork conserva el historial completo.

---

## 2. URGENTE — Rotación de credenciales

Mientras existió el fallo de *path traversal* (`GET /%2e%2e/.env` devolvía el
`.env` entero), cualquiera que conociera la URL de Render podía leer:

- `DATABASE_URL` — el DSN de Neon **con la contraseña dentro**
- `ANTHROPIC_API_KEY`
- `IMAP_PASSWORD` o `AZURE_CLIENT_SECRET`

No hay forma de saber desde aquí si alguien lo explotó. Si la aplicación estuvo
publicada en internet, hay que rotarlas todas:

1. **Neon** — Dashboard → Roles → *Reset password*. Actualiza `DATABASE_URL` en
   Render y en tu `.env` local. Usa el endpoint con `-pooler` en el host.
2. **Anthropic** — [console.anthropic.com](https://console.anthropic.com) →
   API Keys → revoca la actual y crea otra.
3. **Correo** — cambia la contraseña de la cuenta IMAP, o rota el
   `AZURE_CLIENT_SECRET` en el portal de Azure si usas Graph.

Aprovecha para generar los dos secretos nuevos que pide la aplicación:

```bash
python -c "import secrets; print('JWT_SECRET=' + secrets.token_urlsafe(48))"
python -c "import secrets; print('WORKER_SECRET_KEY=' + secrets.token_urlsafe(32))"
```

Con `APP_ENV=prod` la aplicación **no arranca** si falta alguno de los dos. Es
deliberado: antes arrancaba con `JWT_SECRET` vacía, y firmar tokens con cadena
vacía significa que cualquiera puede fabricarse una sesión de administrador.

---

## 3. Puesta en marcha local

```bash
# Dependencias
pip install -r requirements.txt -r requirements-dev.txt

# Base de datos: levanta PostgreSQL, carga el esquema y todas las migraciones
make db-up


# Tu usuario (la contraseña se pide de forma interactiva, mínimo 12 caracteres)
make usuario CORREO=tu@cgr-international.com NOMBRE="Tu Nombre" ROL=admin

# Servidor
python run_web.py --reload
```

Copia `.env.example` a `.env` y rellena al menos `DATABASE_URL`, `JWT_SECRET` y
las variables de correo.

Roles disponibles:

| Rol | Puede |
|---|---|
| `admin` | Todo, incluido dar de alta usuarios y operar el worker |
| `pm` | Ver RFQs, aprobar/declinar, costear, operar el worker |
| `quoter` | Los mismos que `pm` |

`pm` y `quoter` llevan el mismo juego de permisos, pero se mantienen separados
para que la bitácora distinga quién dictaminó: Planta o quien cotiza.

Para añadir otro puesto, al final de `sql/migrations/006_auth_roles.sql` está el
SQL de ejemplo. Ya no hace falta tocar `scripts/crear_usuario.py` para el alta
del día a día: **Perfil → Usuarios** da de alta, cambia el rol y desactiva
personas desde la interfaz, y el desplegable de roles se lee de la base, así
que un rol nuevo aparece solo.

`scripts/crear_usuario.py` sigue siendo necesario para **el primer admin**: sin
nadie dentro, no hay quien use la pantalla.

### Roles que sobraban

La migración `009_limpiar_roles.sql` retira `ventas` y `consulta`, que sembró
una versión anterior de la 006 y no corresponden a ningún puesto de ISC. Sólo
los borra si **no hay usuarios con ellos**; si alguien los tiene, avisa por
consola y no toca nada: cambia a esa persona de rol desde Perfil → Usuarios y
vuelve a aplicarla.

### Fotos de perfil

`008_perfil_usuarios.sql` añade las columnas de la foto. Se guarda en la base de
datos, no en disco, porque en Render el sistema de ficheros se borra en cada
despliegue: una carpeta de subidas perdería las fotos cada vez que publiques.
El navegador la recorta a 256×256 antes de subirla, así que son unos 30 KB por
persona.

### La pantalla de sistema es de sólo lectura

**Perfil → System** enseña con qué configuración está corriendo el servidor,
con los secretos tapados. No se puede editar desde ahí, y no es una limitación
pendiente: en Render las variables se inyectan desde el panel del servicio y el
disco es efímero, así que un formulario de guardar habría dicho "guardado" sin
cambiar nada. Para cambiar un valor: Render → Environment, y volver a desplegar.

---

## 4. Ver los cambios antes de publicarlos

Render despliega desde `main`, así que sin esto la única forma de ver un cambio
es publicarlo en el sitio que usa la planta. Para trabajar sin eso:

**Doble clic en `ver_local.bat`.** Levanta el cotizador en
<http://localhost:8000> y abre el navegador. Guardas un archivo y el servidor se
reinicia solo; para CSS o JavaScript basta con refrescar con Ctrl+F5 (el Ctrl es
importante: fuerza recargar sin usar el caché).

Cuando la página se sirve desde `localhost` aparece una etiqueta **LOCAL** en la
esquina superior derecha. Está para que, con las dos pestañas abiertas, no
confundas la local con la de producción.

### Qué apaga el arranque local, y por qué

Si tu `.env` apunta a Neon, un servidor local sin cuidado haría dos cosas que se
notan fuera de tu computadora. El script las apaga siempre:

| Se apaga | Si no |
|---|---|
| `WORKER_AUTOSTART` | Tu equipo leería el **mismo buzón** que Render y marcaría los correos como leídos: producción dejaría de verlos |
| `ENVIO_AUTOMATICO` | Al declinar un RFQ para probar, saldría un **correo de verdad** a un comprador |

Lo que el script **no** puede evitar es que escribas en la base de producción:
si apruebas o declinas un RFQ apuntando a Neon, queda registrado ahí. Por eso el
arranque te dice en grande contra qué base estás trabajando.

Para quedar aislada del todo, levanta una base local y apunta ahí tu
`DATABASE_URL`:

```bash
make db-up
```

### Si no tienes Python

El `.bat` te lo dice y te manda a <https://www.python.org/downloads/>. En la
primera pantalla del instalador hay que marcar **"Add Python to PATH"**; si no,
Windows no lo encuentra después. Luego, una sola vez:

```bash
pip install -r requirements.txt
```

---

## 5. Despliegue en Render

El repositorio trae un `Dockerfile` porque la aplicación necesita tres cosas
que el runtime de Python de Render no incluye: **Node.js** (el motor de costeo
corre en un subproceso de Node), las librerías nativas de **WeasyPrint** para
el PDF, y el cliente de **PostgreSQL**.

En Render: *New → Web Service → Docker*, y define las variables de entorno de
`.env.example`. Como mínimo:

```
APP_ENV=prod
DATABASE_URL=...        (endpoint -pooler de Neon)
JWT_SECRET=...          (48+ caracteres aleatorios)
WORKER_SECRET_KEY=...
ANTHROPIC_API_KEY=...
IMAP_SERVER / IMAP_USER / IMAP_PASSWORD
APP_URL=https://isc-by-cgr.onrender.com
MAIL_FOLDER=TEST        (mientras se prueba; INBOX cuando entre en servicio)
VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY   (scripts/generar_vapid.py)
```

`APP_URL` es dónde vive Pohua de cara al mundo. Se usa en el enlace del correo
de recordatorio (`RECORDATORIO_HORAS`, sección 7): sin ella ese correo no sale,
porque el enlace apuntaría a `localhost`.

Deja `CORS_ORIGINS` **vacía**: la PWA se sirve desde el mismo servidor y no
necesita CORS. Con `APP_ENV=prod` no se admite `*`.

La sonda de vida es `GET /api/health` (no toca la base de datos a propósito,
para que un problema de base no reinicie el contenedor en bucle).

### Migraciones

El workflow `.github/workflows/update-neon.yml` aplica `sql/schema.sql` y
**todas** las migraciones de `sql/migrations/` en cada push a `main` que las
toque, cada una dentro de una transacción. Antes sólo corría `schema.sql`, y
por eso producción se quedaba sin el catálogo de costeo.

---

## 6. Capturar el catálogo de costeo

`POST /api/price` responde con dos campos que hay que mirar antes de mandar un
precio a un cliente:

- `completo` — `true` sólo si todos los insumos salieron del catálogo.
- `faltantes` — qué faltó, en lenguaje llano.
- `origen_datos` — de dónde salió cada número.

La migración `007_catalogo_costeo.sql` sembró las máquinas, materiales,
empaques y parámetros que estaban escritos dentro de `pricing/engine.js`. Falta
capturar, y hasta entonces todo costeo saldrá con `completo: false`:

| Tabla | Qué falta |
|---|---|
| `material_precios` | Precio por libra de cada calibre de alambre |
| `aleacion_surcharges` | Sobreprecio vigente de los inoxidables (SS, SS177, 316) |
| `subcontratistas` | Recubrimientos y servicios externos |

Ejemplo de captura de un precio:

```sql
INSERT INTO material_precios (material_id, diam_pulg, precio_lb, fecha_cotizado, origen)
SELECT id, 0.0630, 2.55, CURRENT_DATE, 'cotización proveedor X'
FROM materiales WHERE codigo = 'MW';
```

Los precios son históricos: el motor toma el del diámetro más cercano y, a
igualdad de diámetro, el más reciente. Nunca sobrescribas una fila; inserta una
nueva con la fecha del día.

Lo mismo con los parámetros (`param_juegos` / `param_valores`): para cambiar un
markup se crea un juego nuevo con `vigente_desde` futuro y se cierra el
anterior. Así una cotización vieja se puede reconstruir con los parámetros que
estaban vigentes ese día.

**Plazo de entrega:** la API devuelve `lead_time_weeks: null`. Antes devolvía 8
semanas fijas con un comentario `# Placeholder` al lado, y ese número salía en
el PDF que va al cliente. No hay plazos en el catálogo, así que lo pone
Planeación a mano.

---

## 7. Notas de operación

**Conexiones a Neon.** El código abre y cierra una conexión por operación. Se
corrigieron seis puntos donde no se cerraban (usaban la conexión de psycopg2
como context manager, que gestiona la transacción pero **no** cierra). Aun así,
usa el endpoint con `-pooler` de Neon: es lo que evita agotar el límite de
conexiones de la rama cuando entran varios correos a la vez.

**Un solo lector de correo.** Si la app de escritorio está corriendo, manda un
latido cada minuto y el worker del servidor se queda en espera, para que no
lean el mismo buzón los dos. Ese latido se autentica con `WORKER_SECRET_KEY`;
si la variable no está definida, el endpoint devuelve 503 en vez de aceptar un
secreto por defecto conocido.

**Logs.** Van a consola y a `app.log` (rotativo, 5 MB × 5 archivos). La
configuración la aplica cada punto de entrada — `app/main.py`, `api/server.py`,
`desktop_app/main.py` —, ya no un import con efectos secundarios.

---

## 8. Pendientes conocidos

Cosas detectadas y **no** resueltas, para que no se pierdan:

1. **Condición de carrera en `app/rfq/repository.py`.** `guardar_veredicto` y
   `guardar_veredicto_final` hacen SELECT y luego UPDATE. Si dos procesos
   dictaminan el mismo RFQ a la vez, uno pisa el `datos_json` del otro. La
   solución es un `SELECT ... FOR UPDATE` dentro de una transacción explícita,
   lo que exige revisar el `autocommit=True` de `conectar_bd()`.
2. **Peso del alambre en extensión y torsión.** El peso que se calcula cubre el
   cuerpo del resorte, no los ganchos ni las patas, así que el costo de
   material queda subestimado en esos dos tipos. Se avisa en `faltantes`.
3. **`mypy` no pasa limpio** sobre el código heredado. En CI está como
   informativo (`continue-on-error`) para no bloquear al equipo.
4. **Los contactos de clientes no tienen respaldo automático.** Al salir del
   repositorio, la única copia viva está en Neon. Neon guarda historial de la
   rama, pero conviene un `pg_dump` periódico a un lugar seguro.
