"""ISC Extractor v4 - lector de planos de resorte.

Pipeline:
    1. render      : PDF/imagen -> paginas PNG + capa de texto (PyMuPDF, sin poppler)
    2. router      : claude-haiku-4-5   -> compresion | tension | torsion | wireform
    3. extractor   : claude-opus-5 (thinking adaptativo, effort high) -> JSON v4
    4. validacion  : jsonschema + una reparacion dirigida si no conforma
    5. localizacion: word_indices/nbox -> cajas reales sobre la pagina
    6. adapter     : JSON de ingenieria -> campos planos que consume la calculadora

Uso desde otro programa:

    from isc_extractor import parse_drawing
    payload, paginas = parse_drawing("plano.pdf")
    payload["fields"]        # para rellenar la calculadora
    payload["spec"]          # JSON completo de ingenieria
"""

from . import (adapter, archivo, coherencia, config, errores, gasto, locate,
               normalizar, render, validate, veredictos)

__version__ = "4.0.0"

__all__ = ["parse_drawing", "adapter", "archivo", "coherencia", "config",
           "veredictos",
           "errores", "gasto", "locate", "normalizar", "render", "validate",
           "__version__"]


def parse_drawing(path, cfg=None, api_key=None, tipo_forzado=None,
                  log=None, modo_demo=False):
    """Lee un plano y devuelve (payload, paginas).

    payload : dict listo para servir por HTTP (ver adapter.adaptar).
    paginas : lista de paginas rasterizadas, para generar recortes.
    """
    cfg = cfg or config.load_config()
    paginas, avisos_render = render.cargar(
        path, dpi=cfg.get("dpi"), max_pages=cfg.get("max_pages"))
    listado, mapa = render.listado_palabras(paginas)

    if modo_demo:
        from . import demo
        spec, tipo, router, diag = demo.cargar()
        avisos_render.insert(
            0, "DEMO MODE: this data does NOT come from the drawing you uploaded.")
    else:
        from . import llm
        cli = llm.cliente(api_key or config.get_api_key())
        bloques = render.bloques_imagen(paginas)      # base64 una sola vez

        if tipo_forzado:
            tipo = tipo_forzado
            router = {"tipo": tipo, "confianza": "alta", "razon": "forzado por el usuario"}
        else:
            router = llm.clasificar(cli, bloques, cfg, listado_palabras=listado, log=log)
            tipo = router.get("tipo")

        if tipo not in config.TIPOS_VALIDOS:
            raise RuntimeError(
                "The classifier returned a spring type this parser does not "
                "know (%r). Valid types are: %s. Detail: %s"
                % (tipo, ", ".join(config.TIPOS_VALIDOS), router))

        spec, diag = llm.extraer(cli, bloques, tipo, listado, cfg, log=log)

        # El extractor ha visto el plano entero y puede contradecir al router.
        # Si lo hace, se relee con el prompt y el schema correctos: una lectura
        # con el tipo equivocado no sirve para nada.
        detectado = spec.get("tipo_detectado")
        discrepa = (detectado in config.TIPOS_VALIDOS and detectado != tipo
                    and not tipo_forzado)
        if discrepa and cfg.get("reintento_si_tipo_discrepa",
                                config.REINTENTO_SI_TIPO_DISCREPA):
            if log:
                log("El extractor dice %s, el router dijo %s: releyendo."
                    % (detectado, tipo))
            spec_2, diag_2 = llm.extraer(cli, bloques, detectado, listado, cfg, log=log)
            diag_2["relectura_por_tipo"] = {"router": tipo, "extractor": detectado}
            diag_2["uso"] = list(diag.get("uso", [])) + list(diag_2.get("uso", []))
            spec, diag, tipo = spec_2, diag_2, detectado
            router["tipo_corregido_por_extractor"] = detectado
            avisos_render.insert(
                0, "The classifier said '%s' but the parser saw '%s', so the "
                   "drawing was read again with the right prompt. Confirm the type."
                   % (router.get("tipo"), detectado))
        elif discrepa:
            avisos_render.insert(
                0, "SPRING TYPE WARNING: the classifier said '%s' and the parser "
                   "thinks it is '%s'. This reading may not be valid."
                   % (tipo, detectado))

        spec["tipo_resorte"] = tipo          # coherencia con lo que se acabo usando
        avisos_render += normalizar.aplicar(spec)
        spec.setdefault("metadatos_extraccion", {})
        if isinstance(spec["metadatos_extraccion"], dict):
            spec["metadatos_extraccion"]["router"] = {
                k: v for k, v in router.items() if not k.startswith("_")}

    ubic = locate.resolver(spec, mapa, len(paginas))
    payload = adapter.adaptar(spec, tipo, ubic, diag, router, avisos_render)
    payload["engine"] = "isc-extractor-v%s" % __version__
    payload["localizadas"] = len(ubic)
    return payload, paginas
