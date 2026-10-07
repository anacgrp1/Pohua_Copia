"""El lector de planos, montado dentro del Cotizador.

El lector no es una API que haya que reimplementar aquí: es un programa Flask
completo que ya sirve la calculadora de precios en `/`, sus ficheros hermanos
—entre ellos el Spring Engineering Calculator, que la calculadora abre en un
iframe por ruta relativa— y los tres endpoints del contrato (`/api/parse`,
`/api/veredicto`, `/api/quote-pdf`). Vive en `apps/lector/` del núcleo.

Así que no se copia nada: se **monta** tal cual bajo `/quoting/lector`, y con
él entran las tres caras de una vez. Copiar sus rutas al Cotizador habría sido
una segunda versión que mantener, que es justo lo que el núcleo existe para
evitar.

Tres cosas hay que resolver al montarlo, y las tres se hacen aquí y no tocando
el núcleo, que es otro repositorio:

1. **El nombre del módulo.** `apps/lector/app.py` se llama `app`, igual que el
   paquete `app/` del Cotizador. Un `import app` desde aquí devolvería el
   paquete del Cotizador, que ya está en `sys.modules`. Se carga por ruta con
   un nombre propio, `isc_lector_app`.

2. **Dónde busca el lector su parser.** La calculadora, servida por http,
   apunta a `location.origin` — o sea, a la raíz del Cotizador, donde no está.
   Lleva una salida prevista, `window.ISC_PARSER_URL`, y se le inyecta el
   prefijo del montaje en cada respuesta HTML.

3. **La sesión.** Un iframe no manda cabecera Authorization, así que la puerta
   la guarda `api/routes/quoting.py` con una cookie de sesión atada a esta
   ruta. Aquí no se decide nada de eso: este módulo sólo entrega la aplicación.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import re
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Tuple

from pricing import nucleo

if TYPE_CHECKING:
    from app.auth.tokens import UsuarioSesion

log = logging.getLogger("cotizador.api.lector")

# Dónde se monta, qué cookie abre la puerta y qué permiso hace falta.
#
# La cookie se ata a `/quoting`, no al montaje: bajo ese prefijo cuelgan dos
# cosas que necesitan la misma llave y las dos las pide la calculadora desde
# dentro del iframe, sin cabeceras nuestras —el lector montado y la API de
# estado que sustituye a la carpeta compartida—. Atarla más abajo obligaría a
# repartir dos cookies para la misma sesión.
RAIZ_QUOTING = "/quoting"
PREFIJO = RAIZ_QUOTING + "/lector"
COOKIE = "cgr_lector"
PERMISO = "precio:calcular"

# Cómo fue el montaje, para que el diagnóstico lo pueda contar. Se rellena una
# vez al arrancar: si el lector no cargó, no va a cargar solo más tarde, y
# reintentarlo en cada petición sólo repetiría la misma excepción.
_MONTADO = False
_MOTIVO = "El lector todavía no se ha intentado montar."

# La cabecera por la que la puerta le pasa el usuario al inyector. Se limpia
# de lo que venga de fuera antes de ponerla: si no, cualquiera podría entrar
# diciendo que es admin con sólo mandar la cabecera.
CABECERA_USUARIO = b"x-isc-user"

# Los dos scripts que el Cotizador le añade a la calculadora. El orden y el
# `defer` no son un detalle:
#
#   isc-tema.js  SIN defer, porque frena el parseo hasta que termina y así el
#                color queda decidido ANTES del primer pintado. Con defer, el
#                navegador pintaba la calculadora en blanco y un instante
#                después se volvía oscura: ese salto se veía en cada recarga.
#
#   isc-nube.js  CON defer, porque tiene que correr DESPUÉS de que la
#                calculadora arranque: lo que hace es adoptar el documento de
#                Neon, y para eso ella ya tiene que existir.
_TEMA = "/js/isc-tema.js"
_ADAPTADOR = "/js/isc-nube.js"
# El idioma de Pohua dentro de la calculadora (traduce lo que pinta), CON
# defer: traduce lo que ya hay al cargar y vigila lo que se repinta después.
_IDIOMA = "/js/isc-idioma.js"
#
#   isc-contrato.js  CON defer, DESPUÉS de que la calculadora exista: publica
#                    `window.ISC_SC`, el contrato con los datos del resorte,
#                    envolviendo su `render()`. Sólo hace algo en la de
#                    resortes (la de precios no tiene `STATE.comp`).
#
#   isc-visor3d.js   CON defer y DETRÁS del contrato: comprueba `ISC_SC` nada
#                    más cargar, así que el orden no es opcional. El resorte
#                    de compresión en 3D, en la casilla del dibujo.
_CONTRATO = "/js/isc-contrato.js"
_VISOR = "/js/isc-visor3d.js"
_APROBACION = "/js/isc-aprobacion.js"
_SELECTS = "/js/isc-selects.js"
# El plano del cliente a la vista: «Ver» en la casilla de planos y la pestaña
# «Plano del cliente» (sólo hace algo en la de precios, que tiene #q-drawing).
_PLANO = "/js/isc-plano.js"


def carpeta() -> Optional[Path]:
    """Dónde está el lector, o None si no está.

    Se mira primero la copia de `vendor/lector/` y sólo después el clon: en
    Render no hay clon —el núcleo es privado y el build no tiene sesión de
    GitHub— y en local con el núcleo delante interesa que la copia mande
    igualmente, para trabajar contra lo mismo que se va a desplegar. Quien
    quiera apuntar al clon a propósito tiene `ISC_LECTOR_DIR`.
    """
    variable = os.environ.get("ISC_LECTOR_DIR")
    if variable:
        ruta = Path(variable)
        return ruta if (ruta / "app.py").is_file() else None
    for ruta in (nucleo.RAIZ / "vendor" / "lector",
                 nucleo.CLON / "apps" / "lector"):
        if (ruta / "app.py").is_file():
            return ruta
    return None


def _preparar_rutas(dir_lector: Path) -> None:
    """Deja importables `quote_pdf` e `isc_extractor`.

    Se **añaden al final** de sys.path, nunca al principio: `apps/lector`
    contiene un `app.py`, y ponerlo delante haría que un `import app` de
    cualquier módulo del Cotizador cargado más tarde encontrara ese fichero en
    vez del paquete de negocio.

    `isc_extractor` se busca primero en la copia de `vendor/` y luego en el
    clon; si está instalado con `pip`, manda el paquete, porque Python mira
    antes lo instalado que lo que se añade al final de la ruta.
    """
    for ruta in (dir_lector,
                 nucleo.RAIZ / "vendor",                      # la copia
                 nucleo.CLON / "nucleo" / "extraccion"):      # el clon
        texto = str(ruta)
        if ruta.is_dir() and texto not in sys.path:
            sys.path.append(texto)


def _cargar_flask(dir_lector: Path) -> Any:
    """Importa `apps/lector/app.py` con nombre propio y devuelve su Flask."""
    if "isc_lector_app" in sys.modules:
        return sys.modules["isc_lector_app"].app

    spec = importlib.util.spec_from_file_location(
        "isc_lector_app", dir_lector / "app.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"No se pudo preparar la carga de {dir_lector/'app.py'}")
    modulo = importlib.util.module_from_spec(spec)
    # En sys.modules ANTES de ejecutarlo: el módulo se importa a sí mismo por
    # nombre en alguna ruta y sin esto se cargaría dos veces.
    sys.modules["isc_lector_app"] = modulo
    try:
        spec.loader.exec_module(modulo)
    except BaseException:
        del sys.modules["isc_lector_app"]
        raise
    return modulo.app


class _InyectarParserURL:
    """Middleware WSGI que le dice a la calculadora dónde está su lector.

    Sólo toca respuestas `text/html`, y sólo para meter una línea detrás de
    `<head>`. Todo lo demás —los PNG de los recortes, el JSON de `/api/parse`,
    el PDF de la oferta— pasa sin mirarlo.

    Reescribe `Content-Length` porque el cuerpo crece: dejarlo corto hace que
    el navegador trunque el HTML por la mitad, y una calculadora a medias no
    da error, simplemente no funcionan la mitad de los botones.
    """

    def __init__(self, wsgi_app: Any, prefijo: str) -> None:
        self.wsgi_app = wsgi_app
        self.prefijo = prefijo

    def _marca(self, environ) -> bytes:
        """Las tres líneas que convierten la calculadora en parte de Pohua.

        1. ``ISC_PARSER_URL`` — dónde está su lector, que ya no es 127.0.0.1.
        2. ``ISC_USER`` — quién entró. La calculadora lo mira al arrancar
           (``usuarioDelAnfitrion``) y, si viene, **no enseña su pantalla de
           acceso**: es su forma prevista de que no se entre dos veces a la
           misma aplicación. El rol se traduce aquí: quien puede dictaminar
           RFQs es ADMIN para ella; el resto, QUOTE.
        3. El tema de Pohua, **sin** ``defer``: tiene que estar puesto antes
           del primer pintado o se ve la calculadora en blanco un instante.
        4. El adaptador de almacenamiento, **con** ``defer``: tiene que correr
           DESPUÉS de que la calculadora arranque, porque lo que hace es
           adoptar el documento de Neon, y eso es justo lo que ella hacía al
           conectar la carpeta compartida.
        """
        import json

        usuario = environ.get("HTTP_X_ISC_USER")
        partes = ["window.ISC_PARSER_URL=%s;" % json.dumps(self.prefijo)]
        if usuario:
            partes.append("window.ISC_USER=%s;" % usuario)
        return ("<script>%s</script>"
                "<script src=\"%s\"></script>"
                "<script defer src=\"%s\"></script>"
                "<script defer src=\"%s\"></script>"
                "<script defer src=\"%s\"></script>"
                "<script defer src=\"%s\"></script>"
                "<script defer src=\"%s\"></script>"
                "<script defer src=\"%s\"></script>"
                "<script defer src=\"%s\"></script>"
                % ("".join(partes), _TEMA, _ADAPTADOR, _IDIOMA, _CONTRATO, _VISOR,
                   _APROBACION, _SELECTS, _PLANO)).encode("utf-8")

    def __call__(self, environ, start_response):
        captura: dict = {}

        def _start(estado, cabeceras, exc_info=None):
            captura["estado"] = estado
            captura["cabeceras"] = cabeceras
            captura["exc_info"] = exc_info
            return lambda _: None      # nadie usa el write() antiguo de WSGI

        cuerpo = b"".join(self.wsgi_app(environ, _start))

        # Los recortes del plano, a prueba de despliegues (ver _recorte).
        cuerpo, captura = _recorte(environ, captura, cuerpo)
        # El JSON de ingeniería, igual (ver _spec).
        cuerpo, captura = _spec(environ, captura, cuerpo)
        # Y la lectura entera, a Neon y fuera del disco (ver _tras_lectura).
        _tras_lectura(environ, captura, cuerpo)

        tipo = ""
        for nombre, valor in captura["cabeceras"]:
            if nombre.lower() == "content-type":
                tipo = valor.lower()
                break

        if "text/html" in tipo:
            corte = _tras_head(cuerpo)
            cuerpo = cuerpo[:corte] + self._marca(environ) + cuerpo[corte:]

        cabeceras = [(n, v) for n, v in captura["cabeceras"]
                     if n.lower() != "content-length"]
        cabeceras.append(("Content-Length", str(len(cuerpo))))

        start_response(captura["estado"], cabeceras, captura["exc_info"])
        return [cuerpo]


# --------------------------------------------------------------------------- #
# Los recortes del plano
# --------------------------------------------------------------------------- #

# Tope de lo que se guarda por recorte. Un recuadro de un plano ronda los
# 40 KB; medio mega ya sería una página entera y no es lo que esto guarda.
MAX_BYTES_RECORTE = 512 * 1024


def _recorte(environ, captura, cuerpo):
    """Guarda el PNG en la base la primera vez, y lo sirve cuando el disco ya no lo tiene.

    El lector escribe los recortes en `vendor/lector/_crops`, en disco. En la
    planta eso dura; en Render el disco se vacía en cada despliegue, así que
    una cotización de ayer se abría hoy con todos sus recortes rotos — el
    icono de imagen partida dentro de "On the drawing", sin explicación.

    Aquí se resuelve donde se puede resolver sin tocar el lector, que es del
    núcleo: se mira el PNG al pasar. Si el lector lo sirvió, se copia a Neon
    (una vez, en un hilo aparte: nadie espera por esto). Si el lector contesta
    404 y en Neon está, se devuelve desde ahí. La cotización vive en la base;
    sus recortes también.
    """
    ruta = environ.get("PATH_INFO", "") or ""
    if "/api/crop/" not in ruta:
        return cuerpo, captura
    cid = ruta.rsplit("/", 1)[-1].strip()
    if not cid:
        return cuerpo, captura

    estado = str(captura.get("estado", ""))

    if estado.startswith("200") and cuerpo and len(cuerpo) <= MAX_BYTES_RECORTE:
        _guardar_recorte_en_segundo_plano(cid, cuerpo)
        return cuerpo, captura

    # 500 también: si el fichero se borra justo entre que el lector mira que
    # existe y lo abre (lo acaba de llevar a Neon _tras_lectura), falla así.
    if estado.startswith("404") or estado.startswith("500"):
        png = _leer_recorte(cid)
        if png:
            log.info("Recorte %s recuperado de la base (el disco ya no lo tenía).", cid)
            return png, {
                "estado": "200 OK",
                "cabeceras": [("Content-Type", "image/png"),
                              ("Cache-Control", "private, max-age=600")],
                "exc_info": None,
            }
    return cuerpo, captura


def _guardar_recorte_en_segundo_plano(cid: str, png: bytes) -> None:
    import threading

    def _trabajo():
        try:
            import psycopg2

            import app.persistence.duplicates as duplicates
            with duplicates.conexion_bd() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO lector_recortes (cid, png, bytes)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (cid) DO UPDATE SET ultimo_uso = now();
                        """,
                        (cid, psycopg2.Binary(png), len(png)),
                    )
        except Exception as error:      # guardar nunca puede romper la imagen
            log.debug("No se pudo guardar el recorte %s: %s", cid, error)

    threading.Thread(target=_trabajo, name="recorte-plano", daemon=True).start()


def _leer_recorte(cid: str):
    try:
        import app.persistence.duplicates as duplicates
        with duplicates.conexion_bd() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT png FROM lector_recortes WHERE cid = %s;", (cid,))
                fila = cur.fetchone()
                if fila:
                    cur.execute("UPDATE lector_recortes SET ultimo_uso = now() "
                                "WHERE cid = %s;", (cid,))
        return bytes(fila[0]) if fila else None
    except Exception as error:
        log.debug("No se pudo leer el recorte %s: %s", cid, error)
        return None


# --------------------------------------------------------------------------- #
# La lectura entera, a Neon
# --------------------------------------------------------------------------- #
#
# El lector escribe en disco, por cada plano que lee, el fichero subido
# (`_uploads`), un PNG por página y por cota (`_crops`) y el JSON de ingeniería
# (`_specs`). Son dibujos y datos de clientes de ISC: en la planta se quedaban
# en esa computadora, y en Render en un disco que se vacía en cada despliegue.
#
# Nada más contestar `/api/parse`, Pohua se lleva lo que la calculadora va a
# volver a pedir —los PNG y el spec— a Neon (`lector_recortes`, `lector_specs`)
# y borra los tres del disco. Si la base no está, no se borra nada: el lector
# sigue como siempre y su propia retención limpia a los 7 días.
#
# Va en un hilo: la calculadora no espera por esto. Mientras el hilo trabaja,
# el disco sigue sirviendo; cuando termina, sirve la base (_recorte, _spec).

# Un recorte o una página entera. Las páginas a 200 ppp rondan 1-3 MB.
MAX_BYTES_LECTURA = 8 * 1024 * 1024

_JOB_VALIDO = re.compile(r"^[0-9A-Za-z_-]{4,64}$")
_FICHERO_VALIDO = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,127}$")


def _carpetas_lector() -> Optional[dict]:
    """Las carpetas de trabajo del lector cargado, o None si no está."""
    modulo = sys.modules.get("isc_lector_app")
    if modulo is None:
        return None
    carpetas = {}
    for clave in ("CROPS", "UPLOADS", "SPECS"):
        valor = getattr(modulo, clave, None)
        if not valor:
            return None
        carpetas[clave] = Path(valor)
    return carpetas


def _nombre_de_url(url: Any) -> Optional[str]:
    if not isinstance(url, str) or "/api/crop/" not in url:
        return None
    nombre = url.rsplit("/", 1)[-1].split("?", 1)[0]
    return nombre if _FICHERO_VALIDO.match(nombre) and ".." not in nombre else None


def recortes_de(datos: dict) -> list:
    """Los PNG que la respuesta de `/api/parse` le dice a la calculadora que pida."""
    urls = [datos.get("page")] + list(datos.get("pages") or [])
    for columna in ("fields", "feasibility"):
        for item in datos.get(columna) or []:
            if isinstance(item, dict):
                urls.append(item.get("crop"))
    vistos: list = []
    for url in urls:
        nombre = _nombre_de_url(url)
        if nombre and nombre not in vistos:
            vistos.append(nombre)
    return vistos


def _tras_lectura(environ, captura, cuerpo) -> None:
    ruta = environ.get("PATH_INFO", "") or ""
    if (environ.get("REQUEST_METHOD") or "").upper() != "POST" or not ruta.endswith("/api/parse"):
        return
    if not str(captura.get("estado", "")).startswith("200"):
        return
    try:
        datos = json.loads(cuerpo or b"{}")
    except ValueError:
        return
    if not isinstance(datos, dict) or not datos.get("ok"):
        return
    job = datos.get("job")
    if not isinstance(job, str) or not _JOB_VALIDO.match(job):
        return
    hilo = threading.Thread(target=llevar_lectura_a_neon,
                            args=(job, datos.get("spec"), recortes_de(datos)),
                            name="lectura-a-neon", daemon=True)
    hilo.start()


def llevar_lectura_a_neon(job: str, spec: Any, recortes: list,
                          carpetas: Optional[dict] = None) -> dict:
    """Guarda en Neon los PNG y el spec de una lectura y borra del disco lo suyo.

    Nunca lanza. Devuelve un resumen (lo usan las pruebas y el registro).
    """
    resumen = {"recortes": 0, "spec": False, "borrados": 0, "error": None}
    carpetas = carpetas or _carpetas_lector()
    if carpetas is None or not _JOB_VALIDO.match(job or ""):
        resumen["error"] = "sin lector"
        return resumen

    guardados: list = []
    try:
        import psycopg2

        import app.persistence.duplicates as duplicates
        with duplicates.conexion_bd() as conn:
            with conn.cursor() as cur:
                for nombre in recortes:
                    ruta = carpetas["CROPS"] / nombre
                    if not ruta.is_file():
                        continue
                    png = ruta.read_bytes()
                    if not png or len(png) > MAX_BYTES_LECTURA:
                        continue
                    cur.execute(
                        """
                        INSERT INTO lector_recortes (cid, png, bytes)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (cid) DO UPDATE SET ultimo_uso = now();
                        """,
                        (nombre, psycopg2.Binary(png), len(png)))
                    guardados.append(ruta)
                resumen["recortes"] = len(guardados)

                ruta_spec = carpetas["SPECS"] / (job + ".json")
                if spec is None and ruta_spec.is_file():
                    spec = json.loads(ruta_spec.read_text(encoding="utf-8"))
                if spec is not None:
                    cur.execute(
                        """
                        INSERT INTO lector_specs (job, spec) VALUES (%s, %s)
                        ON CONFLICT (job) DO UPDATE SET spec = EXCLUDED.spec,
                                                        ultimo_uso = now();
                        """,
                        (job, json.dumps(spec, ensure_ascii=False)))
                    resumen["spec"] = True
    except Exception as error:
        # Sin base no se borra NADA: lo que no está en Neon sigue en disco.
        resumen["error"] = str(error)
        log.info("La lectura %s se queda en disco (no se pudo llevar a Neon: %s).",
                 job, error)
        return resumen

    # La conexión va en autocommit: lo de arriba ya está en la base.
    borrar = list(guardados)
    if resumen["spec"]:
        borrar.append(carpetas["SPECS"] / (job + ".json"))
    # El plano subido sólo servía para leerlo: ya está leído.
    if carpetas["UPLOADS"].is_dir():
        borrar.extend(p for p in carpetas["UPLOADS"].glob(job + ".*") if p.is_file())
    for ruta in borrar:
        try:
            ruta.unlink()
            resumen["borrados"] += 1
        except FileNotFoundError:
            pass
        except OSError as error:        # en Windows, un fichero abierto
            log.debug("No se pudo borrar %s: %s", ruta, error)
    log.info("Lectura %s llevada a Neon: %d imagen(es)%s; %d fichero(s) fuera del disco.",
             job, resumen["recortes"], " y su spec" if resumen["spec"] else "",
             resumen["borrados"])
    return resumen


def _spec(environ, captura, cuerpo):
    """Sirve el JSON de ingeniería desde Neon cuando el disco ya no lo tiene."""
    ruta = environ.get("PATH_INFO", "") or ""
    if "/api/spec/" not in ruta:
        return cuerpo, captura
    job = ruta.rsplit("/", 1)[-1].strip()
    if not _JOB_VALIDO.match(job):
        return cuerpo, captura
    estado = str(captura.get("estado", ""))
    if not (estado.startswith("404") or estado.startswith("500")):
        return cuerpo, captura
    spec = _leer_spec(job)
    if spec is None:
        return cuerpo, captura
    return json.dumps(spec, ensure_ascii=False, indent=2).encode("utf-8"), {
        "estado": "200 OK",
        "cabeceras": [("Content-Type", "application/json"),
                      ("Cache-Control", "private, max-age=600")],
        "exc_info": None,
    }


def _leer_spec(job: str):
    try:
        import app.persistence.duplicates as duplicates
        with duplicates.conexion_bd() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT spec FROM lector_specs WHERE job = %s;", (job,))
                fila = cur.fetchone()
                if fila:
                    cur.execute("UPDATE lector_specs SET ultimo_uso = now() "
                                "WHERE job = %s;", (job,))
        if not fila:
            return None
        valor = fila[0]
        return json.loads(valor) if isinstance(valor, str) else valor
    except Exception as error:
        log.debug("No se pudo leer el spec %s: %s", job, error)
        return None


def _tras_head(cuerpo: bytes) -> int:
    """Posición justo después de `<head ...>`; el principio si no hay head.

    Se busca sólo en los primeros kilobytes: en un HTML de 400 KB el `<head>`
    está al principio o no está, y recorrerlo entero por si acaso sería medir
    todo el fichero para no encontrar nada.
    """
    bajo = cuerpo[:4096].lower()
    i = bajo.find(b"<head")
    if i < 0:
        return 0
    cierre = cuerpo.find(b">", i)
    return cierre + 1 if cierre > 0 else 0


def _envoltorio_asgi(wsgi_app: Any) -> Any:
    """WSGI → ASGI. `a2wsgi` si está; si no, el de Starlette, que está de salida."""
    try:
        from a2wsgi import WSGIMiddleware  # type: ignore
        return WSGIMiddleware(wsgi_app)
    except ImportError:
        pass
    from fastapi.middleware.wsgi import WSGIMiddleware as WSGIStarlette  # type: ignore
    log.warning("a2wsgi no está instalado; se usa el puente WSGI de Starlette, "
                "que está deprecado. Añade a2wsgi a requirements.txt.")
    return WSGIStarlette(wsgi_app)


def cargar(prefijo: str) -> Tuple[Optional[Any], Optional[str]]:
    """La aplicación ASGI del lector, o ``(None, motivo)`` si no se pudo.

    No lanza: que falte el lector no puede impedir que arranque el Cotizador.
    El motivo se enseña en el diagnóstico de la pantalla de Cotización, que es
    donde alguien lo va a leer.
    """
    dir_lector = carpeta()
    if dir_lector is None:
        return None, ("No se encontró apps/lector del núcleo. Se buscó en "
                      f"{nucleo.CLON / 'apps' / 'lector'} (o ISC_LECTOR_DIR).")

    _preparar_rutas(dir_lector)
    try:
        flask_app = _cargar_flask(dir_lector)
    except Exception as err:                       # noqa: BLE001
        log.exception("No se pudo cargar el lector desde %s", dir_lector)
        return None, f"{type(err).__name__}: {err}"

    return _envoltorio_asgi(_InyectarParserURL(flask_app, prefijo)), None


def estado() -> Tuple[bool, str]:
    """``(montado, motivo)``. El motivo sólo importa cuando no está montado."""
    return _MONTADO, _MOTIVO


def usuario_de_cookie(peticion: Any) -> UsuarioSesion:
    """El usuario de la cookie del lector, o 401/403.

    Es la misma comprobación que hace la puerta del montaje, escrita una vez
    para que la use también la API de estado: las dos las llama la calculadora
    desde dentro del iframe, donde no hay cabecera ``Authorization`` que valga.

    Se usa como dependencia de FastAPI:

        usuario: UsuarioSesion = Depends(lector.usuario_de_cookie)
    """
    from fastapi import HTTPException, status

    from app.auth.tokens import TokenInvalido
    from app.auth.tokens import leer as leer_token

    token = peticion.cookies.get(COOKIE)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Abre la pantalla de Cotización para entrar.")
    try:
        usuario = leer_token(token)
    except TokenInvalido as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="La sesión caducó. Vuelve a abrir Cotización.") from err
    if not usuario.puede(PERMISO):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Tu rol ({usuario.rol or 'sin rol'}) no puede cotizar.")
    return usuario


class _Guardia:
    """La puerta del lector: sin sesión no se pasa.

    Es una envoltura ASGI y no una dependencia de FastAPI porque lo que hay
    detrás es una aplicación montada entera, y `mount` no admite `Depends`.

    Comprueba una cookie y no la cabecera ``Authorization``: quien llama aquí
    es un iframe pidiendo su página, o la propia calculadora pidiendo un
    recorte, y ninguno de los dos manda cabeceras nuestras. La cookie la
    reparte ``POST /api/quoting/sesion`` y lleva dentro el token de sesión de
    siempre, así que caduca cuando caduca la sesión.

    Detrás de esta puerta hay dos cosas que no pueden quedar abiertas: la
    calculadora, que lleva incrustada la cartera de clientes y los precios de
    proveedor, y ``/api/parse``, que gasta crédito del modelo en cada llamada.
    """

    def __init__(self, interna: Any) -> None:
        self.interna = interna

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self._cortar(scope, receive, send, 400,
                               "El lector sólo atiende HTTP.")
            return

        from starlette.requests import Request

        from app.auth.tokens import TokenInvalido
        from app.auth.tokens import leer as leer_token

        token = Request(scope).cookies.get(COOKIE)
        if not token:
            await self._cortar(scope, receive, send, 401,
                               "Abre la pantalla de Cotización para entrar al lector.")
            return
        try:
            usuario = leer_token(token)
        except TokenInvalido:
            await self._cortar(scope, receive, send, 401,
                               "La sesión del lector caducó. Vuelve a abrir Cotización.")
            return
        if not usuario.puede(PERMISO):
            await self._cortar(scope, receive, send, 403,
                               f"Tu rol ({usuario.rol or 'sin rol'}) no puede usar el lector.")
            return

        await self.interna(self._con_usuario(scope, usuario), receive, send)

    @staticmethod
    def _con_usuario(scope, usuario) -> dict:
        """El scope con el usuario dentro, y sin el que trajera el cliente.

        Se filtra ANTES de añadir el nuestro. Sin ese filtro, bastaría con
        mandar `X-ISC-User: {"role":"ADMIN"}` a mano para entrar a la
        calculadora como administrador: la cabecera llegaría al inyector tal
        cual y la calculadora se la creería.

        El JSON sale en ASCII puro porque una cabecera HTTP no admite otra
        cosa; los acentos viajan escapados y `JSON.parse` los devuelve enteros.
        """
        import json

        datos = json.dumps({
            "name": usuario.nombre or usuario.correo,
            "email": usuario.correo,
            # `rfq:dictaminar` es el permiso de aprobar o declinar un RFQ. Es
            # el mismo poder que ADMIN en la calculadora —aprobar una oferta—
            # así que la correspondencia es esa y no el nombre del rol, que en
            # los dos sitios se llama distinto.
            "role": "ADMIN" if usuario.puede("rfq:dictaminar") else "QUOTE",
        }, ensure_ascii=True)

        cabeceras = [(n, v) for n, v in scope["headers"]
                     if n.lower() != CABECERA_USUARIO]
        cabeceras.append((CABECERA_USUARIO, datos.encode("ascii")))
        return dict(scope, headers=cabeceras)

    @staticmethod
    async def _cortar(scope, receive, send, codigo: int, texto: str) -> None:
        from starlette.responses import PlainTextResponse
        await PlainTextResponse(texto, status_code=codigo)(scope, receive, send)


def montar(app_fastapi: Any) -> Tuple[bool, str]:
    """Monta el lector en la aplicación, detrás de la puerta.

    Nunca lanza. Que falte el núcleo, que falte Flask o que el lector reviente
    al importarse son cosas que tienen que salir en el diagnóstico de la
    pantalla de Cotización, no impedir que arranque el Cotizador entero: el
    correo, los RFQs y el costeo no dependen de esto.
    """
    global _MONTADO, _MOTIVO

    interna, motivo = cargar(PREFIJO)
    if interna is None:
        _MONTADO, _MOTIVO = False, motivo or "Motivo desconocido."
        log.warning("El lector no se montó: %s", _MOTIVO)
        return _MONTADO, _MOTIVO

    app_fastapi.mount(PREFIJO, _Guardia(interna), name="lector")
    _MONTADO, _MOTIVO = True, ""
    log.info("Lector montado en %s (desde %s).", PREFIJO, carpeta())
    return _MONTADO, _MOTIVO
