"""ISC Drawing Parser v4 - servidor local.

    python app.py               -> http://127.0.0.1:8765

Endpoints (contrato estable, pensado para no romperse entre versiones de la
calculadora):

    GET  /api/status            estado, modo y version del motor
    GET  /api/testkey           comprueba la API key con una llamada minima
    POST /api/parse             multipart form-data, campo "file" -> payload
    GET  /api/crop/<id>         PNG del recorte o de la pagina
    GET  /api/spec/<job>        JSON de ingenieria completo de una lectura
    POST /api/quote-pdf         genera el PDF de oferta (compatibilidad V5)
    GET  /                      sirve el HTML de la calculadora si esta al lado
    GET  /<fichero>             sirve los ficheros hermanos del HTML (el iframe
                                del Spring Engineering Calculator los necesita)

    POST /api/veredicto        anota un veredicto de factibilidad
    GET  /api/veredictos       los ultimos (?pendientes=1 = sin avisar)
    POST /api/veredicto/<id>/aviso   marca uno como ya avisado

El payload de /api/parse mantiene las claves que ya usaba la calculadora
(ok, mode, springType, fields[], feasibility[], page, page_w, page_h) y anade
las nuevas (spec, title, warnings, pages[], severidad, code, box, page).
"""

import json
import os
import sys
import traceback
import uuid

from flask import (Flask, Response, abort, jsonify, request, send_file,
                   send_from_directory)

import isc_extractor
import quote_pdf
from isc_extractor import config, errores, locate

BASE = os.path.dirname(os.path.abspath(__file__))
PADRE = os.path.dirname(BASE)
CROPS = os.path.join(BASE, "_crops")
UPLOADS = os.path.join(BASE, "_uploads")
SPECS = os.path.join(BASE, "_specs")
QUOTES = os.path.join(PADRE, "Quotes")


def asegurar_carpetas():
    """Crea las carpetas de trabajo. Se llama al arrancar Y antes de escribir.

    El README le dice al usuario que `_uploads` y `_crops` son carpetas de
    trabajo que puede ignorar, asi que tarde o temprano alguien las borra para
    hacer limpieza con el lector abierto. Crearlas solo al importar convierte
    esa limpieza en un error 500 sin explicacion.
    """
    for d in (CROPS, UPLOADS, SPECS, QUOTES):
        os.makedirs(d, exist_ok=True)


asegurar_carpetas()

CONFIG = config.load_config(BASE)
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024      # 64 MB por plano


def api_key():
    return config.get_api_key(BASE)


def modo():
    if CONFIG.get("demo_mode") is True:
        return "demo"
    return "live" if api_key() else "demo"


@app.after_request
def cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "*"
    return resp


# ---------------------------------------------------------------- estado
@app.route("/api/status")
def status():
    return jsonify(
        ok=True,
        mode=modo(),
        has_key=bool(api_key()),
        stage="v4",
        engine="isc-extractor",
        version=isc_extractor.__version__,
        tipos=list(config.TIPOS_VALIDOS),
        model_router=CONFIG.get("model_router"),
        model_extractor=CONFIG.get("model_extractor"),
        jsonschema=isc_extractor.validate.disponible(),
        credito=isc_extractor.gasto.estado(BASE, CONFIG),
    )


@app.route("/api/testkey")
def testkey():
    k = api_key()
    if not k:
        return jsonify(ok=False, message="No API key found. Put it in "
                       "api_key.txt (see api_key.EJEMPLO.txt).")
    try:
        from isc_extractor import llm
        cli = llm.cliente(k)
        cli.messages.create(
            model=CONFIG.get("model_router") or config.MODEL_ROUTER,
            max_tokens=8,
            messages=[{"role": "user", "content": "Responde OK."}],
        )
        return jsonify(ok=True, message="The API key works - the parser is "
                       "ready for live reading.")
    except Exception as e:
        return jsonify(ok=False, message=errores.mensaje(e))


# ---------------------------------------------------------------- credito
@app.route("/api/credito", methods=["GET", "POST", "OPTIONS"])
def credito():
    """Estado del gasto, y alta de recargas.

    GET  -> cuanto lleva gastado este lector y cuanto se estima que queda.
    POST {"recarga": 50} -> apunta que se han cargado 50 USD.

    Es un contador, no una consulta de saldo: la API no expone el saldo. Ver
    isc_extractor/gasto.py para el porque.
    """
    if request.method == "OPTIONS":
        return ("", 204)
    if request.method == "POST":
        datos = request.get_json(silent=True) or {}
        est = isc_extractor.gasto.recargar(BASE, datos.get("recarga"))
        if est is None:
            return jsonify(ok=False,
                           error="Send a positive amount, e.g. "
                                 '{"recarga": 50}'), 400
        return jsonify(ok=True, credito=est,
                       message="Recorded a top-up. Estimated credit is now "
                               "$%.2f." % (est["restante_usd"] or 0))
    return jsonify(ok=True, credito=isc_extractor.gasto.estado(BASE, CONFIG))


# ---------------------------------------------------------------- lectura

def _recibir(peticion):
    """Guarda el fichero que llega y devuelve (job, ruta, tipo_forzado).

    El `job` es lo que ata todo lo de esta lectura: el nombre del fichero
    subido, el de cada recorte, el del spec y la URL con la que la calculadora
    los vuelve a pedir.
    """
    asegurar_carpetas()
    up = peticion.files["file"]
    job = uuid.uuid4().hex[:8]
    ext = os.path.splitext(up.filename)[1].lower() or ".pdf"
    guardado = os.path.join(UPLOADS, job + ext)
    up.save(guardado)
    tipo = (peticion.form.get("tipo") or "").strip() or None
    return job, guardado, tipo


def _recortar(payload, paginas, job):
    """Guarda las paginas enteras y un recorte por cada dato localizado.

    Los recortes son lo que deja comprobar de un vistazo que un numero salio de
    donde dice: sin ellos, revisar una lectura obliga a abrir el plano al lado.
    Devuelve los nombres de las paginas completas.
    """
    nombres = locate.guardar_paginas(paginas, CROPS, job)
    for col in ("fields", "feasibility"):
        for item in payload.get(col, []):
            if item.get("box") is None:
                continue
            n = locate.recortar(paginas,
                                {"pagina": item.get("page", 0), "nbox": item["box"]},
                                CROPS)
            if n:
                item["crop"] = "/api/crop/" + n
    return nombres


def _apuntar_gasto(payload):
    """Anota lo que costo esta lectura y avisa si queda poco saldo.

    Nunca tumba una lectura: el plano ya esta leido y pagado, y perderlo por un
    fallo del contador seria cobrar dos veces por lo mismo.
    """
    try:
        est = isc_extractor.gasto.registrar(
            BASE, payload.get("router"), payload.get("diagnostico"),
            CONFIG, payload.get("tipo"))
        linea = isc_extractor.gasto.aviso(est)
        if linea:
            # Sin saldo no hay lectura: va arriba del todo.
            payload["warnings"] = ([{"text": linea, "severity": "high"}]
                                   + list(payload.get("warnings", [])))
        payload["credito"] = est
    except Exception:
        app.logger.exception("contador de gasto")


def _archivar(payload, job, nombre_original):
    """Deja el spec junto al plano, en la carpeta compartida si la hay."""
    ruta = isc_extractor.archivo.archivar(
        CONFIG.get("carpeta_compartida"), payload.get("spec") or {},
        payload, job, nombre_original, CONFIG,
        coste_usd=isc_extractor.gasto.coste_lectura(
            payload.get("router"), payload.get("diagnostico"), CONFIG),
        log=lambda s: app.logger.info("[%s] %s", job, s))
    if ruta:
        payload["archivado"] = ruta


def _aviso_de_demo(payload):
    """Que nadie confunda datos de muestra con su plano.

    `avisos()` devuelve objetos {text, severity}; el filtro tiene que mirar el
    texto, no el objeto, o no quita nada y el aviso se duplica.
    """
    def _txt(w):
        return w if isinstance(w, str) else str((w or {}).get("text", ""))
    payload["warnings"] = (
        [{"text": "DEMO MODE: this is sample data. It was NOT read from "
                  "the drawing you uploaded.", "severity": "high"}]
        + [w for w in payload.get("warnings", []) if "DEMO" not in _txt(w)])


@app.route("/api/parse", methods=["POST", "OPTIONS"])
def parse():
    """Lee un plano y devuelve lo que dice, con sus recortes.

    El orden es el que se lee: recibir, leer, recortar, apuntar el gasto,
    archivar, limpiar lo viejo y contestar. Cada paso esta arriba con su
    nombre, para que se pueda entender uno sin leer los otros seis.
    """
    if request.method == "OPTIONS":
        return ("", 204)
    if "file" not in request.files or not request.files["file"].filename:
        return jsonify(ok=False, error="No file was uploaded."), 400

    m = modo()
    job, guardado, tipo_forzado = _recibir(request)
    if tipo_forzado and tipo_forzado not in config.TIPOS_VALIDOS:
        return jsonify(ok=False,
                       error="Invalid forced spring type: %s" % tipo_forzado), 400

    try:
        payload, paginas = isc_extractor.parse_drawing(
            guardado, cfg=CONFIG, api_key=api_key(),
            tipo_forzado=tipo_forzado, modo_demo=(m == "demo"),
            log=lambda s: app.logger.info("[%s] %s", job, s))
    except Exception as e:
        app.logger.error("[%s] %s", job, traceback.format_exc())
        return jsonify(ok=False, error=errores.mensaje(e)), 500

    nombres = _recortar(payload, paginas, job)

    # En demo no se llama a la API, asi que no hay nada que cobrar ni que
    # archivar: lo que se archivaria son datos de muestra.
    if m != "demo":
        _apuntar_gasto(payload)
        if CONFIG.get("carpeta_compartida"):
            _archivar(payload, job, request.files["file"].filename)

    # La retencion va aqui y no en un proceso aparte: es una pasada por dos
    # carpetas, cuesta milisegundos, y asi no depende de que alguien mantenga
    # una tarea programada que nadie recuerda haber creado.
    isc_extractor.archivo.purgar(BASE, CONFIG.get("retencion_dias"),
                                 log=lambda s: app.logger.info(s))

    if CONFIG.get("guardar_spec", True):
        with open(os.path.join(SPECS, job + ".json"), "w", encoding="utf-8") as f:
            json.dump(payload.get("spec", {}), f, indent=2, ensure_ascii=False)

    payload.update(
        ok=True,
        mode=m,
        job=job,
        archivo=request.files["file"].filename,
        page="/api/crop/" + nombres[0],
        pages=["/api/crop/" + n for n in nombres],
        page_w=paginas[0]["w"],
        page_h=paginas[0]["h"],
        specUrl="/api/spec/" + job,
    )
    if m == "demo":
        _aviso_de_demo(payload)
    return jsonify(payload)


@app.route("/api/crop/<cid>")
def crop(cid):
    p = os.path.join(CROPS, os.path.basename(cid))
    if not os.path.exists(p):
        abort(404)
    return send_file(p, mimetype="image/png")


@app.route("/api/spec/<job>")
def spec(job):
    p = os.path.join(SPECS, os.path.basename(job) + ".json")
    if not os.path.exists(p):
        abort(404)
    return send_file(p, mimetype="application/json")


# ---------------------------------------------------------------- oferta PDF
@app.route("/api/quote-pdf", methods=["POST", "OPTIONS"])
def generar_oferta():
    """Genera el PDF de oferta y lo guarda en la carpeta Quotes.

    La calculadora V6 ya no llama a este endpoint (genera la oferta por su
    cuenta), pero las versiones anteriores si: se mantiene para que actualizar
    el lector no obligue a actualizar la calculadora el mismo dia.
    """
    if request.method == "OPTIONS":
        return ("", 204)
    datos = request.get_json(silent=True) or {}
    cliente = (datos.get("customer") or "").strip()
    numero = (datos.get("quoteNo") or "").strip()
    if not cliente or not numero:
        return jsonify(ok=False,
                       error="Customer and quote number are required."), 400
    if not datos.get("lines"):
        return jsonify(ok=False, error="The quote has no line items."), 400
    try:
        asegurar_carpetas()
        nombre = quote_pdf.quote_filename(cliente, numero)
        destino = os.path.join(QUOTES, nombre)
        quote_pdf.build_quote_pdf(datos, destino)
    except Exception as e:
        app.logger.error("quote-pdf: %s", traceback.format_exc())
        return jsonify(ok=False, error="PDF build failed: %s" % e), 500
    try:
        os.startfile(destino)                    # Windows: abre la oferta
    except Exception:
        pass
    return jsonify(ok=True, file=nombre, path=destino, folder=QUOTES)


# ---------------------------------------------------------------- la app

# Donde puede estar la calculadora, en orden. Son las dos formas en que esto se
# despliega, y hay que aceptar las dos: en un puesto, `construir_distribucion.py`
# deja el HTML JUNTO a la carpeta del lector; en el repositorio, el lector vive
# en `apps/lector/` y la calculadora en `apps/calculadora/`. Mirando solo la
# primera, un clon recien hecho arrancaba y servia la pagina de "no encuentro
# ninguna calculadora", que parece que el lector esta roto.
DONDE_BUSCAR = [PADRE, os.path.join(PADRE, "calculadora")]


def buscar_html():
    """HTML de calculadora que se sirve en `/`.

    Se elige por nombre porque la calculadora cambia de nombre cada version y
    el lector no debe romperse por eso. Manda `html` de config.json si esta;
    si no, gana el que mas se parezca a la calculadora de produccion, y las
    copias DEMO / BACKUP / OLD se quedan las ultimas: en un puesto real, servir
    la demo en vez de la buena es un fallo silencioso y caro.
    """
    forzado = (CONFIG.get("html") or "").strip()
    if forzado:
        for carpeta in DONDE_BUSCAR:
            p = os.path.join(carpeta, forzado)
            if os.path.exists(p):
                return p

    candidatos = []
    for i, carpeta in enumerate(DONDE_BUSCAR):
        if not os.path.isdir(carpeta):
            continue
        for f in os.listdir(carpeta):
            if not f.lower().endswith(".html"):
                continue
            low = f.lower()
            prioridad = 0 if "parser" in low else (1 if "price calculator" in low else 3)
            if any(x in low for x in ("demo", "backup", "old", "copy", "copia")):
                prioridad += 10
            # `i` desempata: si el puesto tiene una copia junto al lector, esa
            # es la que se estaba usando y la que debe seguir ganando.
            candidatos.append((prioridad, i, os.path.join(carpeta, f)))
    if not candidatos:
        return None
    candidatos.sort()
    return candidatos[0][2]


def carpeta_calculadora():
    """La carpeta desde la que se sirven los hermanos del HTML.

    Es la del HTML elegido, no una fija: el Spring Engineering Calculator tiene
    que salir de al lado de la calculadora que se esta sirviendo, y no de otra
    copia que hubiera en la carpeta de arriba.
    """
    p = buscar_html()
    return os.path.dirname(p) if p else PADRE


# ------------------------------------------------------------- factibilidad
@app.route("/api/veredicto", methods=["POST", "OPTIONS"])
def veredicto():
    """Anota un veredicto de factibilidad. -> el registro guardado.

    Lo manda la calculadora en cuanto el Spring Calculator cierra el dictamen.
    Sale del navegador para que exista despues de cerrar la ventana: de aqui lo
    lee quien tenga que avisar al plant manager.

    Este endpoint NO manda ningun correo. Por que canal, desde que cuenta y a
    quien no son decisiones del lector; ademas, separar el envio del registro
    permite reintentarlo sin volver a leer el plano, y que un fallo de correo
    no pierda el dictamen.

    POST {"pn":"000134185", "verdict":"REQUIRES REVIEW",
          "reasons":["..."], "machine":{...}, "customer":"...", "score":28}
    """
    if request.method == "OPTIONS":
        return ("", 204)
    reg, error = isc_extractor.veredictos.registrar(
        BASE, request.get_json(silent=True) or {})
    if error:
        return jsonify(ok=False, error=error), 400
    return jsonify(ok=True, veredicto=reg, repetido=bool(reg.get("repetido")))


@app.route("/api/veredictos")
def veredictos_lista():
    """Los ultimos veredictos. `?pendientes=1` = los que esperan aviso."""
    pend = str(request.args.get("pendientes") or "").lower() in ("1", "true", "si")
    filas = isc_extractor.veredictos.listar(
        BASE, pendientes=pend, limite=request.args.get("limite") or 50)
    return jsonify(ok=True, total=len(filas), veredictos=filas)


@app.route("/api/veredicto/<ident>/aviso", methods=["POST", "OPTIONS"])
def veredicto_avisado(ident):
    """Marca que ya se aviso de este veredicto, para no avisar dos veces."""
    if request.method == "OPTIONS":
        return ("", 204)
    reg, error = isc_extractor.veredictos.marcar_notificado(BASE, ident)
    if error:
        return jsonify(ok=False, error=error), 404
    return jsonify(ok=True, veredicto=reg)


@app.route("/")
def home():
    p = buscar_html()
    if not p:
        return Response(
            "<h3>The ISC Drawing Parser v4 is running.</h3>"
            "<p>No calculator .html was found in <code>%s</code>. Open your "
            "calculator directly - the parser answers on "
            "<code>/api/parse</code>.</p>"
            "<p><a href='/api/status'>/api/status</a> &middot; "
            "<a href='/api/testkey'>/api/testkey</a></p>"
            % "</code> nor <code>".join(DONDE_BUSCAR),
            mimetype="text/html")
    with open(p, encoding="utf-8") as f:
        return _sin_cache(Response(f.read(), mimetype="text/html"))


def _sin_cache(resp):
    """Que el navegador no sirva una version vieja de la calculadora.

    Sin cabeceras ni validadores, un navegador aplica su propia heuristica y
    puede quedarse con la copia guardada: se edita el HTML, se reinicia la app
    y la ventana sigue ejecutando el codigo anterior, sin ningun error que lo
    delate. Es una pagina para una sola maquina por 127.0.0.1, asi que no
    cachear no cuesta nada y evita esa clase de fallo fantasma.
    """
    resp.headers["Cache-Control"] = "no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


EXT_SERVIBLES = (".html", ".htm", ".js", ".css", ".png", ".jpg", ".jpeg",
                 ".gif", ".svg", ".ico", ".webp", ".woff", ".woff2", ".ttf")


@app.route("/<path:fichero>")
def hermano(fichero):
    """Sirve los ficheros que hay junto al HTML de la calculadora.

    Hace falta porque la calculadora carga el Spring Engineering Calculator en
    un iframe con una ruta RELATIVA: si el HTML se sirve desde `/`, ese iframe
    pide `/Spring Engineering Calculator.html` a este servidor. Sin esta ruta,
    el boton de calculo de resorte abre un 404 y parece que el lector esta roto.

    Solo se sirven extensiones de front-end y `send_from_directory` rechaza los
    intentos de salirse de la carpeta: nadie puede pedir `../api_key.txt`.
    """
    if fichero.startswith("api/"):
        abort(404)
    if not fichero.lower().endswith(EXT_SERVIBLES):
        abort(404)
    try:
        return _sin_cache(send_from_directory(carpeta_calculadora(), fichero))
    except Exception:
        abort(404)


def comprobaciones_de_arranque():
    """Falla pronto y con un mensaje util, en vez de degradarse en silencio."""
    isc_extractor.validate.exigir()
    isc_extractor.archivo.purgar(BASE, CONFIG.get("retencion_dias"),
                                 log=lambda s: print("  " + s))


if __name__ == "__main__":
    try:
        comprobaciones_de_arranque()
    except RuntimeError as e:
        print("")
        print("=" * 66)
        print("  THE DRAWING PARSER CANNOT START")
        print("=" * 66)
        print(e)
        print("=" * 66)
        print("")
        raise SystemExit(1)

    puerto = int(CONFIG.get("port", 8765))
    m = modo()
    print("=" * 66)
    print("  ISC Drawing Parser v%s  (router + extractor especializado)"
          % isc_extractor.__version__)
    print("  Mode      : %s" % ("LIVE - drawings are read for real by AI"
                                if m == "live" else
                                "DEMO - sample data, the drawing is NOT read"))
    print("  Router    : %s" % CONFIG.get("model_router"))
    print("  Extractor : %s (effort=%s, max_tokens=%s)"
          % (CONFIG.get("model_extractor"), CONFIG.get("effort"), CONFIG.get("max_tokens")))
    print("  Validation: jsonschema active")
    _dias = CONFIG.get("retencion_dias")
    print("  Retention: crops and uploads deleted after %s"
          % ("%d days" % _dias if _dias else "never (disabled)"))
    _sh = CONFIG.get("carpeta_compartida")
    print("  Spec filing: %s"
          % (_sh if _sh else "off - set carpeta_compartida in config.json"))
    _cred = isc_extractor.gasto.estado(BASE, CONFIG)
    if _cred["restante_usd"] is None:
        print("  Credit    : %d drawings read, $%.2f spent (no top-up recorded;\n                POST /api/credito {\"recarga\": 50} to enable the low-credit "
              "warning)" % (_cred["lecturas"], _cred["gastado_usd"]))
    else:
        print("  Credit    : ~$%.2f left of $%.2f (estimate, %d drawings read)"
              % (_cred["restante_usd"], _cred["cargado_usd"], _cred["lecturas"]))
    print("  Open      : http://localhost:%d" % puerto)
    print("  Test key  : http://localhost:%d/api/testkey" % puerto)

    # --- recarga automatica, SOLO si se pide ------------------------------
    # Python lee el codigo al arrancar y no lo relee: cambiar un fichero no
    # afecta a un servidor ya en marcha. Costo dos vueltas averiguarlo -- se
    # corregian los recortes, se volvia a leer el plano y salian igual de mal,
    # porque el proceso seguia con el codigo viejo.
    #
    # No se activa sola. En un puesto, `launcher.py` abre una ventana y espera
    # a ESTE proceso; el recargador arranca un hijo y vigila ficheros, que ahi
    # no hace falta y puede confundir al lanzador. Se pide a mano:
    #
    #     python app.py --dev
    # SOLO NUESTRO CODIGO. El recargador vigila por defecto TODO lo que esta
    # importado, biblioteca estandar incluida, y en Windows eso salta solo: se
    # reinicio el servidor porque el sistema toco `urllib/response.py`, en
    # mitad de una lectura de plano. Desde el navegador se vio "Failed to
    # fetch"; se perdio la lectura y los 0,25 USD que costaba.
    #
    # Se excluye el arbol de Python entero -- interprete y paquetes -- y quedan
    # vigilados nuestros ficheros, que es lo unico que cambia mientras se
    # trabaja.
    dev = "--dev" in sys.argv
    extra = {}
    if dev:
        extra = {"exclude_patterns": [os.path.join(sys.prefix, "**"),
                                      os.path.join(sys.base_prefix, "**")]}
        print("  Reload    : ON - se reinicia al guardar un .py NUESTRO")
    print("=" * 66)
    app.run(host="127.0.0.1", port=puerto, debug=False, threaded=True,
            use_reloader=dev, **extra)
