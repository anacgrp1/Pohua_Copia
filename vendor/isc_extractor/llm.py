"""Llamadas al modelo: router barato + extractor especializado con validacion.

Paso 1  router     : modelo router     -> {tipo, confianza, razon}
Paso 2  extractor  : modelo extractor  -> JSON conforme a schemas/<tipo>.json
Paso 3  reparacion : si el JSON no valida, se le devuelven los errores al modelo.
"""

from . import config, errores, validate


def cliente(api_key):
    try:
        from anthropic import Anthropic
    except ImportError:
        raise RuntimeError(
            "The 'anthropic' package is missing. Run "
            "\"Setup - install packages.bat\" in this folder.")
    if not api_key:
        raise RuntimeError(
            "No API key. Put it in api_key.txt (one line starting with sk-) "
            "or in the ANTHROPIC_API_KEY environment variable.")
    return Anthropic(api_key=api_key)


def _texto(msg):
    """Concatena solo los bloques de texto (ignora los bloques de thinking)."""
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")


def _uso(msg):
    """Tokens de una llamada, incluida la actividad de cache.

    `in` es SOLO el resto no cacheado: el tamano real del prompt es
    in + cache_w + cache_r. Sin esas dos claves, un `in` bajo parece un ahorro
    cuando en realidad es un acierto de cache, y al reves.
    """
    u = getattr(msg, "usage", None)
    if not u:
        return {}
    d = {"in": getattr(u, "input_tokens", None),
         "out": getattr(u, "output_tokens", None)}
    cw = getattr(u, "cache_creation_input_tokens", None)
    cr = getattr(u, "cache_read_input_tokens", None)
    if cw:
        d["cache_w"] = cw
    if cr:
        d["cache_r"] = cr
    return d


# ---------------------------------------------------------------- paso 1
def _soporta_effort(modelo):
    """Haiku 4.5 rechaza output_config.effort y el thinking adaptativo."""
    return "haiku" not in (modelo or "").lower()


def _recorta_palabras(listado, tope):
    """Primeras N palabras del plano: para clasificar no hacen falta todas."""
    if not listado:
        return ""
    lineas = listado.splitlines()
    return "\n".join(lineas[:tope]) + ("\n... (lista recortada)" if len(lineas) > tope else "")


def _una_clasificacion(cli, modelo, contenido, cfg, log=None):
    kwargs = {
        "model": modelo,
        "max_tokens": config.MAX_TOKENS_ROUTER,
        "system": config.leer_prompt("router.md"),
        "messages": [{"role": "user", "content": contenido}],
    }
    if _soporta_effort(modelo):
        kwargs["thinking"] = config.THINKING
        kwargs["output_config"] = {
            "effort": cfg.get("effort_router") or config.EFFORT_ROUTER}
    try:
        msg = cli.messages.create(**kwargs)
    except Exception as e:
        raise errores.traducir(e) from e
    info = validate.extraer_json(_texto(msg))
    info["_uso"] = _uso(msg)
    info["_modelo"] = modelo
    if log:
        log("Router[%s] -> %s (confianza %s) %s"
            % (modelo, info.get("tipo"), info.get("confianza"), info["_uso"]))
    return info


def clasificar(cli, bloques_img, cfg, listado_palabras=None, log=None):
    """Router: hoja 1 + las primeras palabras de la capa de texto.

    Si la clasificacion sale con confianza baja se reintenta con un modelo mas
    capaz: equivocarse aqui invalida la extraccion entera, que cuesta mucho mas
    que este reintento.
    """
    texto = "Clasifica este plano."
    recorte = _recorta_palabras(listado_palabras, int(cfg.get("palabras_router")
                                                      or config.PALABRAS_ROUTER))
    if recorte:
        texto += ("\n\nPALABRAS DEL PLANO (capa de texto del PDF):\n" + recorte)
    contenido = bloques_img[:1] + [{"type": "text", "text": texto}]

    modelo = cfg.get("model_router") or config.MODEL_ROUTER
    info = _una_clasificacion(cli, modelo, contenido, cfg, log=log)

    escalado = cfg.get("model_router_escalado") or config.MODEL_ROUTER_ESCALADO
    if info.get("confianza") == "baja" and escalado and escalado != modelo:
        if log:
            log("Confianza baja: escalando el router a %s" % escalado)
        try:
            info2 = _una_clasificacion(cli, escalado, contenido, cfg, log=log)
            info2["_escalado_desde"] = {"modelo": modelo, "tipo": info.get("tipo"),
                                        "razon": info.get("razon")}
            return info2
        except Exception as e:                       # el escalado nunca debe romper
            if log:
                log("El escalado del router fallo (%s): sigo con la 1a lectura." % e)
    return info


# ---------------------------------------------------------------- pasos 2 y 3
def _cache_control(cfg):
    """-> el cache_control que toca, o None si esta desactivado."""
    modo = config.PROMPT_CACHE if cfg is None else cfg.get("prompt_cache",
                                                           config.PROMPT_CACHE)
    if not modo:
        return None
    if str(modo) == "1h":
        return {"type": "ephemeral", "ttl": "1h"}
    return {"type": "ephemeral"}


def _mensaje_usuario(bloques_img, tipo, listado_palabras, cfg=None):
    """Contenido del turno de usuario, ordenado por ESTABILIDAD.

    El orden importa tanto como el contenido: el cacheo es por prefijo, asi que
    lo que no cambia entre planos tiene que ir fisicamente delante de lo que si.

      1. schema del tipo   -> identico para todos los planos de ese tipo  [CACHE]
      2. imagenes          -> cambian en cada plano
      3. palabras + cierre -> cambian en cada plano

    Antes el schema iba al final, detras de las imagenes, y por eso no se podia
    cachear nada: la primera imagen ya rompia el prefijo. La instruccion de
    cierre sigue siendo lo ultimo que lee el modelo, que es donde mas pesa.
    """
    fence = "```"
    bloque_schema = {
        "type": "text",
        "text": ("Schema al que debe conformar EXACTAMENTE la respuesta "
                 "(additionalProperties:false - una clave inventada invalida "
                 "todo):\n\n"
                 + fence + "json\n" + config.leer_schema_texto(tipo) + "\n" + fence),
    }
    cc = _cache_control(cfg)
    if cc:
        # Un solo punto de corte: cachea tools + system + este bloque.
        bloque_schema["cache_control"] = cc

    cola = []
    if listado_palabras:
        cola.append(
            "PALABRAS OCR del plano (indice global: texto). Usa estos indices en "
            "el campo word_indices de localizacion:\n\n" + listado_palabras)
    else:
        cola.append(
            "Este plano NO tiene capa de texto. En localizacion usa nbox "
            "(fracciones 0..1) en vez de word_indices.")
    cola.append("Devuelve UNICAMENTE el JSON.")

    return [bloque_schema] + list(bloques_img) + [
        {"type": "text", "text": "\n\n".join(cola)}]


def _evaluar(texto, tipo):
    """-> (spec, errores). spec None si el texto ni siquiera es JSON valido."""
    try:
        spec = validate.extraer_json(texto)
    except Exception as e:
        return None, ["The reply is not valid JSON: %s" % e]
    return spec, validate.errores(spec, tipo)


def _peticion_reparacion(ilegible, errs):
    if ilegible:
        return (
            "Tu respuesta no es un JSON valido. Error del parser:\n\n"
            + validate.texto_errores(errs)
            + "\n\nVuelve a emitir el MISMO contenido como JSON estrictamente "
              "valido. Repasa sobre todo:\n"
              "- comillas dobles dentro de una cadena: hay que escaparlas (\\\").\n"
              "- saltos de linea dentro de una cadena: usa \\n, nunca un salto real.\n"
              "- barras invertidas: escapalas (\\\\).\n"
              "- comas: ni de mas al final de un objeto o lista, ni de menos entre "
              "elementos.\n"
              "- texto en japones, aleman o con simbolos (Ø, ±, grados): va dentro de "
              "las comillas, correctamente escapado.\n"
              "Devuelve UNICAMENTE el objeto JSON, sin explicaciones ni code fences.")
    return (
        "Tu JSON no conforma al schema. Errores del validador:\n\n"
        + validate.texto_errores(errs)
        + "\n\nCorrigelos SIN inventar datos nuevos: si una clave sobra eliminala, "
          "si el tipo es incorrecto conviertelo, si falta ponla a null. "
          "Devuelve el JSON completo corregido, nada mas.")


def _guardar_fallo(texto, tipo):
    """Deja la respuesta cruda en _fallos/ para poder diagnosticar sin repetir."""
    try:
        import time
        d = config.ROOT / "_fallos"
        d.mkdir(exist_ok=True)
        (d / ("%s_%d.txt" % (tipo, int(time.time())))).write_text(
            texto or "", encoding="utf-8")
    except Exception:
        pass


def _crear(cli, cfg, system, messages, max_tokens):
    """Llamada al extractor. Streaming porque max_tokens es alto y hay thinking."""
    modelo = cfg.get("model_extractor") or config.MODEL_EXTRACTOR
    kwargs = {
        "model": modelo,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
        "thinking": config.THINKING,
        "output_config": {"effort": cfg.get("effort") or config.EFFORT},
    }
    try:
        with cli.messages.stream(**kwargs) as s:
            msg = s.get_final_message()
    except Exception as e:
        raise errores.traducir(e) from e
    # Se comprueba aqui y no en extraer() para que cubra tambien las llamadas
    # de reparacion: el modelo puede negarse en cualquiera de ellas, y antes
    # una negativa en la segunda se trataba como "JSON ilegible".
    if getattr(msg, "stop_reason", None) == "refusal":
        raise RuntimeError("The model declined to read this drawing "
                           "(stop_reason=refusal).")
    return msg


def extraer(cli, bloques_img, tipo, listado_palabras, cfg, log=None):
    """Devuelve (spec, diagnostico). Nunca lanza por un JSON que no valide."""
    system = config.leer_prompt("%s.md" % tipo) + "\n\n" + config.leer_prompt("_comun.md")
    messages = [{"role": "user",
                 "content": _mensaje_usuario(bloques_img, tipo, listado_palabras,
                                             cfg)}]
    max_tokens = int(cfg.get("max_tokens") or config.MAX_TOKENS_EXTRACTOR)

    if log:
        log("Extractor %s: %s (effort=%s, max_tokens=%d, cache=%s)"
            % (tipo, cfg.get("model_extractor") or config.MODEL_EXTRACTOR,
               cfg.get("effort") or config.EFFORT, max_tokens,
               cfg.get("prompt_cache", config.PROMPT_CACHE) or "off"))

    msg = _crear(cli, cfg, system, messages, max_tokens)

    usos = [_uso(msg)]
    reparaciones = 0
    truncado = msg.stop_reason == "max_tokens"
    texto = _texto(msg)
    spec, errs = _evaluar(texto, tipo)

    # --- truncado: no hay reparacion posible -------------------------------
    # Si la respuesta se corto por max_tokens, el JSON esta partido a la mitad.
    # Pedirle al modelo que "arregle la sintaxis" le hace re-emitir lo mismo,
    # que se vuelve a truncar: una llamada entera del extractor tirada. Y el
    # mensaje generico mandaba a inspeccionar _fallos/ cuando lo que hay que
    # hacer es subir max_tokens.
    if truncado and spec is None:
        _guardar_fallo(texto, tipo)
        raise RuntimeError(
            "The model ran out of room before it finished the JSON "
            "(max_tokens = %d). This drawing carries more annotation than the "
            "limit allows - it is not a fault in the drawing or the key. Raise "
            "max_tokens in config.json and read it again. The partial reply was "
            "saved in _fallos/." % max_tokens)

    # --- reparacion dirigida ----------------------------------------------
    # Cubre los DOS modos de fallo: JSON que no parsea (comillas sin escapar,
    # texto de sobra) y JSON que parsea pero no conforma al schema.
    intentos = int(cfg.get("reintentos_validacion", config.REINTENTOS_VALIDACION))
    while errs and intentos > 0:
        if log:
            log("%s (%d). Reparando..."
                % ("JSON ilegible" if spec is None else "JSON no conforma", len(errs)))
        messages = messages + [
            {"role": "assistant", "content": texto},
            {"role": "user", "content": _peticion_reparacion(spec is None, errs)},
        ]
        msg = _crear(cli, cfg, system, messages, max_tokens)
        usos.append(_uso(msg))
        reparaciones += 1
        truncado = truncado or msg.stop_reason == "max_tokens"
        texto = _texto(msg)
        spec_nuevo, errs_nuevo = _evaluar(texto, tipo)

        # aceptamos la reparacion si arregla el parseo o reduce los errores
        if spec_nuevo is not None and (spec is None or errs_nuevo is None
                                       or len(errs_nuevo) < len(errs)):
            spec, errs = spec_nuevo, errs_nuevo
            if not errs:
                break
        else:
            break
        intentos -= 1

    if spec is None:
        _guardar_fallo(texto, tipo)
        raise RuntimeError(
            "The model did not return readable JSON, even after a retry. "
            "Detail: %s. The raw reply was saved in _fallos/ so it can be "
            "inspected." % ("; ".join(errs or []))[:200])

    if errs is None:
        jsonschema_diag = "no instalado"
    else:
        jsonschema_diag = "errores" if errs else "ok"

    diag = {
        "uso": usos,
        "reparaciones": reparaciones,
        "truncado": truncado,
        "jsonschema": jsonschema_diag,
        "errores_schema": errs or [],
    }
    return spec, diag
