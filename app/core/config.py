import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, get_type_hints
from urllib.parse import urlparse

from app.core.exceptions import ConfigurationError

# NOTA: este módulo NO llama a logging.basicConfig().  La configuración de
# logs (consola + archivo rotativo) vive en app/core/logging.py y la aplican
# los puntos de entrada (app.main, api.server, desktop_app.main).  Configurar
# el logging aquí, como efecto secundario de un import, pisaba esa config.
logger = logging.getLogger("ConfigLoader")


class Settings:
    """Clase centralizada para gestionar las variables de entorno de la aplicación.

    Carga variables desde el entorno del sistema y, en su defecto, desde un archivo .env.
    Realiza conversión de tipos y validación de variables críticas según el tipo de entorno
    (dev/prod) y el método de autenticación seleccionado (local/token).
    """

    # --- Variables de Control ---
    APP_ENV: str = "dev"
    AUTH_METHOD: str = "local"
    MAIL_MODE: str = "imap"

    # --- Configuración IMAP / SMTP (Método Local / imap) ---
    IMAP_SERVER: Optional[str] = None
    IMAP_HOST: Optional[str] = None
    IMAP_PORT: int = 993
    IMAP_USER: Optional[str] = None
    IMAP_PASSWORD: Optional[str] = None
    IMAP_FOLDER: str = "INBOX"
    # La carpeta del buzón que se lee. Vale para los dos proveedores —IMAP y
    # Graph—, por eso no lleva prefijo; `IMAP_FOLDER` se conserva como alias.
    #
    # Existe para poder probar el flujo entero con una carpeta aparte (TEST) sin
    # que el sistema se coma la bandeja de entrada de ventas mientras se afina:
    # se mueve un correo a esa carpeta, se corre el ciclo, y lo que pasa pasa
    # ahí. Cuando el flujo esté validado, se quita la variable y vuelve a INBOX.
    MAIL_FOLDER: str = "INBOX"

    # Con MAIL_MODE=outlook: qué buzón de los que tiene abiertos el Outlook de
    # escritorio hay que leer (sales.isc@cgr-international.com). Vacío = el
    # primero, que en una computadora con un solo buzón es el correcto.
    OUTLOOK_BUZON: str = ""
    SMTP_SERVER: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USE_TLS: bool = True

    # --- Configuración Azure AD / OAuth2 (Método Token / graph) ---
    AZURE_CLIENT_ID: Optional[str] = None
    AZURE_TENANT_ID: Optional[str] = None
    AZURE_CLIENT_SECRET: Optional[str] = None
    GRAPH_CLIENT_ID: Optional[str] = None
    GRAPH_TENANT_ID: Optional[str] = None
    GRAPH_CLIENT_SECRET: Optional[str] = None
    GRAPH_USER: Optional[str] = None

    # --- PostgreSQL ---
    DATABASE_URL: str = ""  # URL completa (Neon/Railway/Render la inyectan)
    PG_HOST: str = "localhost"
    PG_PORT: int = 5432
    PG_DATABASE: str = "cotizador"
    PG_USER: str = "postgres"
    PG_PASSWORD: str = ""
    POSTGREST_URL: str = "http://localhost:3000"  # Solo para dev local con Docker

    # --- Lectura del buzón ---
    # Dentro del horario de atención el buzón se lee de forma continua: un
    # ciclo cada pocos segundos, no cada cinco minutos (ventas, 2026-09-30).
    # Un ciclo sin correos nuevos es una consulta a Outlook y nada más.
    INTERVALO_SEGUNDOS: int = 20

    # --- Horario de atención ---------------------------------------------
    # Cuándo contesta Pohua. Fuera de esta ventana el ciclo no abre el buzón:
    # el correo se queda sin leer y entra en el primer ciclo de la apertura
    # siguiente, así que nada se pierde y de madrugada no se gasta el modelo.
    #
    # La ventana se define en UNA zona —la planta, Kansas City— porque el
    # ciclo es un solo proceso y no puede tener tres horarios. La pantalla lo
    # enseña en la ciudad del idioma de quien mira (js/reloj.js), que es otra
    # cosa: la misma hora dicha en su huso.
    HORARIO_ACTIVO: bool = True
    HORARIO_ZONA: str = "America/Chicago"      # Kansas City, la planta (7-17, ventas 2026-09-30)
    HORARIO_DESDE: int = 7                     # 7:00 (ventas, 2026-09-26)
    HORARIO_HASTA: int = 17                    # 17:00 (a las 17:00 en punto, cerrado)
    HORARIO_DIAS: str = "1-5"                  # lunes a viernes (1=lunes, 7=domingo)

    # --- El relevado de esfuerzos en compresión ---
    #
    # El taller contestó esto (en el núcleo, `taller_2026.json`), y lo contestó CORRIGIENDO
    # una suposición anterior: «not all compression — only very big springs and
    # 17-7 SS material (aging); otherwise only when the drawing requires it».
    # Por eso la regla del núcleo no pone el horno en un Music Wire corriente.
    #
    # Pero en las cotizaciones de referencia el horno SÍ está, puesto a mano.
    # Las dos cosas pueden ser ciertas: que la regla general sea «sólo cuando
    # el plano lo pida» y que en la práctica estas piezas se relajen igual.
    #
    # Esto no se decide en el código. Con el interruptor encendido, todo
    # resorte de compresión lleva horno y se dice de dónde salió esa decisión;
    # apagado, manda la regla del taller. Lo que no hace ninguno de los dos es
    # meter una operación de tapadillo: el motivo viaja hasta la pantalla.
    RELEVADO_SIEMPRE_COMPRESION: bool = False

    # --- El recordatorio de lo que espera dictamen ---
    # El aviso principal es la campana y el teléfono. Si un RFQ lleva más de
    # estas horas esperando a una persona, sale además UN correo a quien puede
    # dictaminar (app/rfq/recordatorios.py). 0 lo apaga.
    RECORDATORIO_HORAS: int = 4
    # Dónde vive Pohua de cara al mundo, para el enlace de ese correo:
    # https://isc-by-cgr.onrender.com. Sin esto el enlace sería a localhost y
    # el recordatorio no se manda.
    APP_URL: str = ""

    # --- Local Worker / Failover ---
    # Sin valor por defecto a proposito: en prod _validate() exige que este
    # definida.  En dev, si se deja vacia, el endpoint de heartbeat se apaga
    # en vez de aceptar un secreto conocido por todo el mundo.
    WORKER_SECRET_KEY: str = ""
    WEB_SERVER_URL: str = "http://localhost:8000"

    # --- Autenticación de la API (COT-100) ---
    # Clave con la que se firman los tokens de sesión (JWT HS256).
    # Obligatoria en prod.  Generar con:
    #   python -c "import secrets;print(secrets.token_urlsafe(48))"
    JWT_SECRET: str = ""
    JWT_ALGORITHM: str = "HS256"
    # Duración de la sesión en minutos (8 h por defecto = una jornada).
    JWT_EXPIRE_MINUTES: int = 480
    # Orígenes permitidos por CORS, separados por coma.
    # Vacío = mismo origen únicamente (la PWA se sirve desde el propio FastAPI).
    CORS_ORIGINS: str = ""

    # --- Multimodal Vision Model ---
    ANTHROPIC_API_KEY: str = ""
    # El más capaz para leer planos: es el que tiene que sacar una cota
    # borrosa de un dibujo escaneado sin inventarse el número. Aquí no se
    # ahorra: una cota mal leída se convierte en un precio mal cotizado.
    VISION_MODEL: str = "claude-opus-5"
    # 2048 se quedaba corto desde que al lector se le pide que anote lo que
    # supone: seis advertencias razonadas más el esquema entero pasan del
    # tope, la respuesta se corta a media frase y el JSON llega sin cerrar.
    # Se veía como un fallo intermitente —mismo plano, mismo modelo, unas
    # veces sí y otras no—, que es la clase de fallo que más cuesta atar.
    # Con 4096 cabe de sobra; y si aun así se cortara, el extractor rescata
    # lo que llegó en vez de tirar la llamada entera.
    VISION_MAX_TOKENS: int = 4096
    # Vacía a propósito: los modelos recientes RECHAZAN `temperature` con un
    # 400 («is deprecated for this model») y se llevan por delante la llamada
    # entera. Para lo que se les pide aquí —devolver JSON de un plano, leer
    # cifras— el comportamiento por defecto es el que se quiere. Ponerle un
    # número la vuelve a mandar, y `app/core/modelo.py` la quitará sola si el
    # modelo la rechaza.
    VISION_TEMPERATURE: Optional[float] = None

    # --- Modelo de lenguaje: extracción del cuerpo del correo (COT-61) ---
    # Si se deja vacío se usa VISION_MODEL.
    # Para el texto —el cuerpo del correo, el chat del asistente—. No hace
    # falta el de arriba: aquí se leen cifras que ya vienen contadas y frases
    # de un correo, no dibujos.
    LLM_MODEL: str = "claude-sonnet-5"
    # Confianza mínima para dar por bueno un campo extraído del correo.
    # Por debajo, el campo no se usa ni se pide al cliente: lo valida el PM.
    UMBRAL_CONFIANZA: float = 0.7

    # --- Almacenamiento de planos (COT-56) ---
    # <Local>: carpeta en disco. <Token>: contenedor de Azure Blob Storage.
    PLANOS_DIR: str = "planos"
    BLOB_CONNECTION_STRING: str = ""
    BLOB_CONTAINER: str = "planos"

    # --- Factibilidad (COT-74) ---
    # Nota: el motor de factibilidad tiene su propio umbral de confianza en
    # reglas/factibilidad.json. No es este: aquel decide cuanto pesa una
    # lectura dudosa en el dictamen, este decide que campos se aceptan.
    # Archivo con las directrices de la planta que lee el motor de COT-75.
    # Ruta relativa a la raiz del proyecto, o absoluta.
    REGLAS_FACTIBILIDAD: str = "reglas/factibilidad.json"

    # --- Web Push: los avisos en el teléfono ---
    # Par de claves VAPID (scripts/generar_vapid.py). Sin ellas la campana
    # sigue funcionando dentro de la app; sólo no llega nada al teléfono.
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    # A quién puede escribir el servicio de push si algo falla (mailto:...).
    # Vacío = el buzón configurado (IMAP_USER / GRAPH_USER).
    VAPID_SUBJECT: str = ""

    # --- Correo saliente (COT-36) ---
    # Dos interruptores, porque son dos cosas distintas y se decidían con una.
    #
    # ENVIO_AUTOMATICO — lo que el sistema manda SOLO: la petición de datos al
    # comprador, la declinación, los recordatorios. Apagado por defecto: es un
    # buzón de clientes reales y el robot no escribe por arrastre del cableado.
    #
    # ENVIO_MANUAL — lo que manda UNA PERSONA pulsando un botón, con el
    # destinatario y las condiciones delante: hoy, la oferta. Encendido por
    # defecto, porque ahí ya hay alguien decidiendo. Con los dos apagados no
    # sale un solo correo, que es lo que hace falta para ensayar el recorrido.
    #
    # Estaban juntos bajo ENVIO_AUTOMATICO, así que para que la oferta llegara
    # había que encender también las respuestas automáticas del robot: o no
    # sale nada, o sale todo.
    ENVIO_AUTOMATICO: bool = False
    ENVIO_MANUAL: bool = True

    # Volver a procesar un correo que ya se procesó (mismo Message-ID).
    #
    # Apagado siempre, salvo en una prueba de flujo. Normalmente, que un
    # correo se procese dos veces significaría dos RFQ del mismo pedido y dos
    # respuestas al mismo comprador; por eso el sistema se lo salta y lo
    # apunta como "duplicado omitido". Pero al probar el recorrido entero se
    # quiere justo lo contrario: repetir el MISMO correo de prueba las veces
    # que haga falta sin tener que mandar uno nuevo cada vez.
    REPROCESAR_REPETIDOS: bool = False

    # La carpeta vigilada es la de las peticiones de cotización (COT, 2026-09):
    # todo correo que una persona deje ahí ES una petición, diga o no «RFQ» o
    # «quote». Un «Hola, test» sin plano y sin cantidades se da de alta como
    # incompleto y se le contesta pidiendo el plano y los volúmenes, en vez de
    # tirarse a la basura por no llevar una palabra clave. Sólo se descartan
    # los remitentes automáticos (no-reply, mailer-daemon, respuestas de
    # ausencia). Apagado, vuelve el filtro por palabras clave.
    CARPETA_SOLO_RFQ: bool = True
    # Cuarentena de adjuntos (app/email/cuarentena.py). APAGADA por defecto
    # (2026-09-25): el análisis con Defender daba «amenaza» en todo en la
    # computadora del lector y los correos se quedaban sin leer.
    CUARENTENA_ADJUNTOS: bool = False

    # Logo de la firma de los correos al cliente. Vacío = el que trae el
    # proyecto (app/email/assets/firma.png, el logo de la casa a 320 px).
    # Se manda incrustado en el mensaje, no enlazado.
    FIRMA_IMAGEN: str = ""

    def __init__(self, env_file_path: Optional[str] = None) -> None:
        """Inicializa las configuraciones cargando el archivo .env si existe."""
        # Ruta del archivo .env (por defecto el directorio actual de ejecución o raíz del proyecto)
        if env_file_path is None:
            # Las pruebas no leen el .env de quien las corre (tests/conftest.py):
            # con el de la máquina de desarrollo heredaban el buzón, la carpeta
            # y el modo de correo reales, y fallaban unas u otras según lo que
            # tuviera cada uno. Un fichero pedido a propósito sí se lee.
            env_file_path = ("" if os.environ.get("POHUA_SIN_DOTENV")
                             else os.path.join(os.getcwd(), ".env"))

        # 1. Cargar archivo .env en os.environ si no está definido en el sistema
        self._load_dotenv(env_file_path)

        # 2. Asignar y convertir tipos
        self._populate_settings()

        # 2b. Sincronizar DATABASE_URL ↔ PG_* (prioridad: DATABASE_URL)
        self._sync_database_url()

        # 3. Validar consistencia de los datos
        self._validate()

    def _load_dotenv(self, file_path: str) -> None:
        """Lee un archivo .env y carga las variables a os.environ si no existen en el sistema."""
        if not file_path:          # las pruebas: no se lee ninguno
            return
        path = Path(file_path)
        if not path.is_file():
            logger.warning(
                f"No se encontró el archivo .env en: {path.absolute()}. "
                "Se usarán variables del sistema."
            )
            return

        logger.info(f"Cargando variables de entorno desde: {path.absolute()}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Ignorar comentarios y líneas vacías
                    if not line or line.startswith("#"):
                        continue

                    # Dividir solo por el primer signo '='
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()

                        # Limpiar comillas si existen
                        if (val.startswith('"') and val.endswith('"')) or (
                            val.startswith("'") and val.endswith("'")
                        ):
                            val = val[1:-1]

                        # El entorno del sistema (os.environ) tiene prioridad sobre el archivo .env
                        if key not in os.environ:
                            os.environ[key] = val
        except Exception as e:
            logger.error(f"Error al leer el archivo .env: {e}")

    def _populate_settings(self) -> None:
        """Puebla las propiedades de la clase extrayendo de os.environ con tipos correctos."""
        # Obtener las anotaciones de tipo declaradas en la clase
        type_hints = get_type_hints(self.__class__)

        # 1. Resolver alias mutuos en os.environ antes de poblar
        # MAIL_MODE <-> AUTH_METHOD
        mail_mode = os.environ.get("MAIL_MODE")
        auth_method = os.environ.get("AUTH_METHOD")
        if mail_mode and not auth_method:
            os.environ["AUTH_METHOD"] = "token" if mail_mode.lower() == "graph" else "local"
        elif auth_method and not mail_mode:
            os.environ["MAIL_MODE"] = "graph" if auth_method.lower() == "token" else "imap"

        # MAIL_FOLDER <-> IMAP_FOLDER: el mismo dato con el nombre viejo y el nuevo.
        mail_folder = os.environ.get("MAIL_FOLDER")
        imap_folder = os.environ.get("IMAP_FOLDER")
        if mail_folder and not imap_folder:
            os.environ["IMAP_FOLDER"] = mail_folder
        elif imap_folder and not mail_folder:
            os.environ["MAIL_FOLDER"] = imap_folder

        # IMAP_HOST <-> IMAP_SERVER
        imap_host = os.environ.get("IMAP_HOST")
        imap_server = os.environ.get("IMAP_SERVER")
        if imap_host and not imap_server:
            os.environ["IMAP_SERVER"] = imap_host
        elif imap_server and not imap_host:
            os.environ["IMAP_HOST"] = imap_server

        # GRAPH_TENANT_ID <-> AZURE_TENANT_ID
        graph_tenant = os.environ.get("GRAPH_TENANT_ID")
        azure_tenant = os.environ.get("AZURE_TENANT_ID")
        if graph_tenant and not azure_tenant:
            os.environ["AZURE_TENANT_ID"] = graph_tenant
        elif azure_tenant and not graph_tenant:
            os.environ["GRAPH_TENANT_ID"] = azure_tenant

        # GRAPH_CLIENT_ID <-> AZURE_CLIENT_ID
        graph_client = os.environ.get("GRAPH_CLIENT_ID")
        azure_client = os.environ.get("AZURE_CLIENT_ID")
        if graph_client and not azure_client:
            os.environ["AZURE_CLIENT_ID"] = graph_client
        elif azure_client and not graph_client:
            os.environ["GRAPH_CLIENT_ID"] = azure_client

        # GRAPH_CLIENT_SECRET <-> AZURE_CLIENT_SECRET
        graph_secret = os.environ.get("GRAPH_CLIENT_SECRET")
        azure_secret = os.environ.get("AZURE_CLIENT_SECRET")
        if graph_secret and not azure_secret:
            os.environ["AZURE_CLIENT_SECRET"] = graph_secret
        elif azure_secret and not graph_secret:
            os.environ["GRAPH_CLIENT_SECRET"] = azure_secret

        for key, expected_type in type_hints.items():
            # Obtener valor de os.environ o usar el valor por defecto definido en la clase
            raw_val = os.environ.get(key)
            if raw_val is None:
                continue

            try:
                # Conversión de tipos
                converted_val = self._convert_type(raw_val, expected_type)
                setattr(self, key, converted_val)
            except Exception as e:
                raise ConfigurationError(
                    f"Error de conversión de tipos para la variable '{key}' "
                    f"(valor: '{raw_val}', tipo esperado: {expected_type}): {e}"
                )

    def _convert_type(self, value: str, expected_type: Any) -> Any:
        """Helper para convertir strings a tipos nativos de Python."""
        # Manejar tipos Optional (ej. Optional[str], que se representa
        # internamente como Union[str, None])
        # En Python 3.8+, los tipos de Union tienen __origin__ y __args__
        origin = getattr(expected_type, "__origin__", None)
        if origin is not None:
            # Extraer los tipos reales de la unión (por ejemplo, str y NoneType en Optional[str])
            args = getattr(expected_type, "__args__", ())
            # Filtrar NoneType
            non_none_types = [t for t in args if t is not type(None)]
            if non_none_types:
                expected_type = non_none_types[0]

        # Convertir a booleanos de forma segura
        if expected_type is bool:
            return value.lower() in ("true", "1", "yes", "on")

        # Convertir a enteros
        if expected_type is int:
            return int(value)

        # Convertir a float
        if expected_type is float:
            return float(value)

        # Por defecto tratar como string
        return value

    def _sync_database_url(self) -> None:
        """Sincroniza DATABASE_URL con las variables PG_* individuales.

        Si DATABASE_URL está definida (Neon, Railway, Render, etc.), extrae
        host/port/dbname/user/password y los escribe en los atributos PG_*
        para que todo el código los pueda usar de forma uniforme.

        Si DATABASE_URL no está definida pero las PG_* sí, construye la URL
        sintetizada para que ``database_dsn`` siempre funcione.
        """
        if self.DATABASE_URL:
            try:
                parsed = urlparse(self.DATABASE_URL)
                self.PG_HOST = parsed.hostname or self.PG_HOST
                self.PG_PORT = parsed.port or self.PG_PORT
                self.PG_DATABASE = (parsed.path or "").lstrip("/") or self.PG_DATABASE
                self.PG_USER = parsed.username or self.PG_USER
                self.PG_PASSWORD = parsed.password or self.PG_PASSWORD
                logger.info("DATABASE_URL detectada → host=%s, db=%s",
                            self.PG_HOST, self.PG_DATABASE)
            except Exception as e:
                raise ConfigurationError(
                    f"DATABASE_URL no se pudo parsear: {e}")
        else:
            # Sintetizar desde PG_* individuales
            pwd = self.PG_PASSWORD
            self.DATABASE_URL = (
                f"postgresql://{self.PG_USER}:{pwd}"
                f"@{self.PG_HOST}:{self.PG_PORT}"
                f"/{self.PG_DATABASE}"
            )

    @property
    def database_dsn(self) -> str:
        """Devuelve la URL de conexión lista para psycopg2.

        Añade ``sslmode=require`` si el host no es localhost (clouds lo exigen).
        """
        url = self.DATABASE_URL
        is_remote = self.PG_HOST not in ("localhost", "127.0.0.1", "db")
        if is_remote and "sslmode" not in url:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}sslmode=require"
        return url

    def _validate(self) -> None:
        """Valida que no falten variables críticas según el tipo de entorno y el modo híbrido."""
        # Validar APP_ENV
        if self.APP_ENV not in ("dev", "prod"):
            raise ConfigurationError(
                f"APP_ENV inválido: '{self.APP_ENV}'. Debe ser 'dev' o 'prod'."
            )

        # Validar AUTH_METHOD
        if self.AUTH_METHOD not in ("local", "token"):
            raise ConfigurationError(
                f"AUTH_METHOD inválido: '{self.AUTH_METHOD}'. Debe ser 'local' o 'token'."
            )

        # Validaciones de Seguridad y Robustez en PRODUCCIÓN
        if self.APP_ENV == "prod":
            logger.warning(
                "INICIANDO EN ENTORNO DE PRODUCCIÓN. "
                "Se aplicarán políticas estrictas de seguridad."
            )
            self._validate_prod_secrets()

        # Validar configuración según método de autenticación híbrido
        if self.AUTH_METHOD == "local":
            self._validate_local_auth()
        elif self.AUTH_METHOD == "token":
            self._validate_token_auth()

        logger.info("Configuración cargada y validada exitosamente.")

    def _validate_prod_secrets(self) -> None:
        """Exige en producción los secretos que en dev pueden faltar.

        Sin esto la app arrancaba en Render con JWT_SECRET vacío (tokens
        firmados con cadena vacía = cualquiera podía fabricarse una sesión) y
        con el secreto del worker en su valor de plantilla.
        """
        if not self.JWT_SECRET:
            raise ConfigurationError(
                "SEGURIDAD: JWT_SECRET es obligatoria con APP_ENV=prod. "
                "Genérala con: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        if len(self.JWT_SECRET) < 32:
            raise ConfigurationError(
                "SEGURIDAD: JWT_SECRET es demasiado corta (mínimo 32 caracteres)."
            )
        if self.JWT_SECRET in ("cambiame", "changeme", "secret", "default_secret_for_dev"):
            raise ConfigurationError(
                "SEGURIDAD: JWT_SECRET tiene un valor de plantilla. Genera una real."
            )
        if not self.WORKER_SECRET_KEY:
            raise ConfigurationError(
                "SEGURIDAD: WORKER_SECRET_KEY es obligatoria con APP_ENV=prod "
                "(la usa la app de escritorio para su heartbeat)."
            )
        if self.WORKER_SECRET_KEY == "default_secret_for_dev":
            raise ConfigurationError(
                "SEGURIDAD: WORKER_SECRET_KEY conserva el valor por defecto de desarrollo."
            )
        if not self.DATABASE_URL:
            raise ConfigurationError(
                "DATABASE_URL es obligatoria con APP_ENV=prod."
            )
        if "*" in self.cors_origins:
            raise ConfigurationError(
                "SEGURIDAD: CORS_ORIGINS no puede ser '*' en producción. "
                "Enumera los orígenes concretos, o déjala vacía para permitir solo el mismo origen."
            )

    def _validate_local_auth(self) -> None:
        """Valida las variables del entorno @Local@."""
        critical_vars = {
            "IMAP_SERVER": self.IMAP_SERVER,
            "IMAP_USER": self.IMAP_USER,
            "IMAP_PASSWORD": self.IMAP_PASSWORD
        }

        # Validar presencia
        for var_name, var_val in critical_vars.items():
            if not var_val:
                logger.warning(
                    "Falta variable crítica para AUTH_METHOD='local': "
                    f"'{var_name}' no está definida en el entorno. El correo no funcionará."
                )

        # En producción, validar que no se usen valores por defecto de la plantilla
        if self.APP_ENV == "prod":
            if self.IMAP_PASSWORD == "tu_contraseña_segura":
                raise ConfigurationError(
                    "SEGURIDAD: No se permite usar la contraseña por defecto de IMAP "
                    "en el entorno de producción."
                )
            if self.IMAP_USER == "usuario@example.com":
                raise ConfigurationError(
                    "SEGURIDAD: No se permite usar el usuario por defecto de IMAP "
                    "en el entorno de producción."
                )

    def _validate_token_auth(self) -> None:
        """Valida las variables del entorno @Token@ (Azure AD)."""
        critical_vars = {
            "AZURE_CLIENT_ID": self.AZURE_CLIENT_ID,
            "AZURE_TENANT_ID": self.AZURE_TENANT_ID,
            "AZURE_CLIENT_SECRET": self.AZURE_CLIENT_SECRET
        }

        # Validar presencia
        for var_name, var_val in critical_vars.items():
            if not var_val:
                raise ConfigurationError(
                    "Falta variable crítica para AUTH_METHOD='token': "
                    f"'{var_name}' no está definida en el entorno."
                )

        # En producción, validar que no se usen valores por defecto de la plantilla
        if self.APP_ENV == "prod":
            if self.AZURE_CLIENT_SECRET == "tu_client_secret_seguro_de_azure":
                raise ConfigurationError(
                    "SEGURIDAD: No se permite usar el AZURE_CLIENT_SECRET por defecto "
                    "en el entorno de producción."
                )
            # Chequeo rápido de GUIDs por defecto
            default_guid = "00000000-0000-0000-0000-000000000000"
            if self.AZURE_CLIENT_ID == default_guid or self.AZURE_TENANT_ID == default_guid:
                raise ConfigurationError(
                    "SEGURIDAD: Los identificadores de Azure (ClientID/TenantID) "
                    "no pueden ser el valor GUID por defecto en producción."
                )

    @property
    def cors_origins(self) -> List[str]:
        """Lista de orígenes permitidos por CORS, ya limpia.

        Vacía significa "solo mismo origen": la PWA se sirve desde este mismo
        FastAPI, así que no hace falta abrir CORS salvo en desarrollo con el
        frontend en otro puerto.
        """
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    # Nombres cuyo VALOR nunca debe aparecer en un log o en una respuesta.
    # Se compara por subcadena, así que cubre las variantes (GRAPH_/AZURE_...).
    _CLAVES_SENSIBLES = (
        "PASSWORD", "SECRET", "TOKEN", "API_KEY", "APIKEY",
        "DATABASE_URL", "CONNECTION_STRING", "DSN",
    )

    @classmethod
    def es_sensible(cls, clave: str) -> bool:
        """True si el valor de esa variable no debe mostrarse nunca."""
        arriba = clave.upper()
        return any(marca in arriba for marca in cls._CLAVES_SENSIBLES)

    def to_dict(self) -> Dict[str, Any]:
        """Valores actuales, con los secretos tapados.

        Antes solo se redactaba PASSWORD y SECRET, así que DATABASE_URL (que
        lleva la contraseña de Neon dentro del DSN) y ANTHROPIC_API_KEY salían
        en claro en cualquier volcado de configuración.
        """
        return {
            k: ("[REDACTED]" if self.es_sensible(k) else v)
            for k, v in self.__dict__.items()
            if not k.startswith("_") and not callable(v)
        }


# Instancia única (Singleton) para ser importada por toda la aplicación
try:
    settings = Settings()
    # Exportar los atributos de settings a nivel de módulo para compatibilidad
    # con import config; config.VAR
    for _key in dir(settings):
        if not _key.startswith("_"):
            _value = getattr(settings, _key)
            if not callable(_value):
                globals()[_key] = _value
except ConfigurationError as err:
    logger.critical(f"ERROR DE CONFIGURACIÓN CRÍTICO: {err}")
    # En entornos de script o aplicación en ejecución, lanzar el error detiene el inicio incorrecto
    raise err


def intervalo_segundos() -> int:
    """Cada cuánto se lee el buzón, en segundos (mínimo 5)."""
    try:
        return max(5, int(getattr(settings, "INTERVALO_SEGUNDOS", 20) or 20))
    except (TypeError, ValueError):
        return 20


# La aplicación de escritorio manda su latido cada minuto. El servidor se
# aparta mientras el último tenga menos de esto: dos latidos y medio, para que
# un latido que llega tarde no ponga a los dos a leer el mismo buzón.
TOLERANCIA_LATIDO_S = 150
