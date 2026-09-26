"""Traduccion de fallos de la API a mensajes que entienda quien cotiza.

El SDK de la API de IA lanza excepciones correctas pero ilegibles para alguien que
no programa: `AuthenticationError(...)` no le dice a nadie que tiene que abrir
`api_key.txt`. El Drawing Parser de V6 tenia esto resuelto a mano sobre urllib
(401 -> "revisa api_key.txt", 429 -> "sin credito"); aqui se recupera esa idea,
pero cubriendo tambien los casos que el SDK distingue y urllib no: modelo
inexistente, sobrecarga temporal, peticion demasiado grande.

Regla: el mensaje dice QUE ha pasado y QUE hacer. El detalle tecnico va detras,
entre parentesis, para quien tenga que diagnosticar. Van en ingles porque salen
en el modal de la calculadora, que esta integramente en ingles.
"""


def _detalle(e, limite=200):
    t = " ".join(str(e).split())
    return t if len(t) <= limite else t[:limite - 3] + "..."


def _codigo(e):
    """Codigo HTTP de la excepcion, si lo lleva."""
    for attr in ("status_code", "code"):
        v = getattr(e, attr, None)
        if isinstance(v, int):
            return v
    resp = getattr(e, "response", None)
    v = getattr(resp, "status_code", None)
    return v if isinstance(v, int) else None


# El saldo agotado NO llega como 429. Llega como 400 invalid_request_error, con
# este texto dentro. Se reconoce por el texto porque no hay codigo propio.
PISTAS_SALDO = ("credit balance", "credit balance is too low", "purchase credits",
                "plans & billing", "insufficient credit")

SIN_SALDO = ("The AI account has run out of credit. Nothing is wrong with "
             "the drawing or with this program: go to the AI provider's console -> "
             "Plans & Billing and top up, then try again.")


def _es_saldo(texto):
    t = (texto or "").lower()
    return any(p in t for p in PISTAS_SALDO)


MENSAJES = {
    401: "The API key was rejected (401). Check api_key.txt: it must be ONE "
         "line starting with sk-ant-, with no quotes and no spaces.",
    403: "This API key is not allowed to use this model (403). Check in "
         "the AI provider's console that your organisation has access.",
    404: "The configured model does not exist (404). Check model_extractor "
         "and model_router in config.json.",
    413: "The drawing is too large to send (413). Lower dpi or max_pages in "
         "config.json, or upload fewer sheets.",
    429: "Too many requests too quickly (429). Wait a minute and try again. "
         "If it keeps happening, check the rate limits in the AI provider's console.",
    500: "Internal API error (500). Nothing to do with your drawing: retry in "
         "a few seconds.",
    529: "The API is overloaded (529). Retry in a minute.",
}


def mensaje(e):
    """Excepcion -> texto llano para la interfaz (en ingles, como la calculadora)."""
    nombre = type(e).__name__

    if nombre == "APIConnectionError" or "Connection" in nombre:
        return ("Could not reach the AI API. Check the internet "
                "connection and the company proxy or firewall. (%s)"
                % _detalle(e))

    if nombre == "APITimeoutError" or "Timeout" in nombre:
        return ("The API took too long to answer. This is usually a very large "
                "drawing: lower max_pages or dpi in config.json and retry.")

    # Se mira antes que el codigo: el saldo agotado viaja dentro de un 400 y de
    # un 429, y en los dos casos lo que hay que hacer es recargar.
    if _es_saldo(str(e)):
        return SIN_SALDO

    cod = _codigo(e)
    if cod in MENSAJES:
        return MENSAJES[cod] + " (%s)" % _detalle(e, 120)
    if cod == 400:
        return ("The API rejected the request (400). Usually a parameter the "
                "model chosen in config.json does not support. (%s)"
                % _detalle(e))
    if isinstance(cod, int) and cod >= 500:
        return ("API server error (%d). Retry in a few seconds. (%s)"
                % (cod, _detalle(e, 120)))
    if isinstance(cod, int):
        return "API error (%d): %s" % (cod, _detalle(e))

    return _detalle(e)


def traducir(e):
    """Devuelve un RuntimeError con el mensaje legible, conservando la causa.

    Se usa como `raise errores.traducir(e) from e` para que el traceback siga
    apuntando al fallo original en el log del servidor.
    """
    if isinstance(e, RuntimeError) and not _codigo(e):
        return e                      # ya es un mensaje nuestro, no lo envolvemos
    return RuntimeError(mensaje(e))
