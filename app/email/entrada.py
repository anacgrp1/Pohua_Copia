"""¿Puede este proceso abrir el buzón? Y si no, qué le falta.

Por qué existe
-------------
El reparto elegido es que lee la aplicación de escritorio —tiene el Outlook de
ISC abierto— y el servidor se aparta. Pero el worker del servidor seguía
intentándolo en cada ciclo, y como no tiene credenciales, cada intento dejaba
tres líneas de ERROR con su traza en el registro.

En dos horas y media eso son 84 errores por una configuración que es
DELIBERADA y correcta. El problema no es el intento fallido: es que entierra
lo que sí hay que ver. Quien abría el registro buscando por qué no salió una
oferta tenía que apartar ochenta y cuatro tracebacks idénticos primero.

Una configuración que no puede funcionar no se reintenta a ciegas: se dice
una vez, claro, y se deja de intentar.

Es el gemelo de ``outbound.diagnostico_envio()``: mismo formato de respuesta,
misma idea. Leer y mandar son dos permisos distintos y cada uno se contesta
por separado.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

log = logging.getLogger("cotizador.buzon")

_MODOS_TOKEN = ("graph", "token", "prod")
_MODOS_OUTLOOK = ("outlook", "com", "escritorio")
# «Este proceso NO lee el buzón», dicho a propósito. No es lo mismo que una
# configuración a medias: es una decisión. Hoy la lectura la hace la
# aplicación de escritorio con el Outlook de ISC abierto, y el servidor no
# tiene por qué fingir que lo intenta.
_MODOS_SIN_LECTURA = ("ninguno", "ninguna", "none", "off", "apagado", "no")

# Lo ya dicho, para no repetirlo en cada ciclo. Vive en memoria del proceso:
# al reiniciar se vuelve a decir una vez, que es justo lo que se quiere.
_YA_AVISADO: Dict[str, bool] = {}


def _puesto(c, *nombres) -> bool:
    return any((getattr(c, n, "") or "").strip() for n in nombres)


def diagnostico_lectura() -> Dict[str, Any]:
    """``{modo, canal, puede, faltan, nota}``. No toca la red ni el buzón."""
    import app.core.config as config
    c = config.settings
    modo = str(getattr(c, "MAIL_MODE", "imap") or "imap").lower()

    if modo in _MODOS_SIN_LECTURA:
        # `faltan` vacío a propósito: no falta nada. Está apagado.
        return {"modo": modo, "canal": "ninguno", "puede": False,
                "faltan": [], "apagado": True,
                "nota": "La lectura del correo está apagada en este proceso "
                        "(MAIL_MODE=ninguno). La hace la aplicación de "
                        "escritorio."}

    if modo in _MODOS_OUTLOOK:
        import sys
        en_windows = sys.platform == "win32"
        if en_windows:
            # En Windows, además, tiene que poder usarse pywin32: sin él no hay
            # forma de hablar con Outlook, y cada intento fallaba en silencio.
            from app.email.outlook_provider import comando_de_instalacion, falta_pywin32
            motivo = falta_pywin32()
            if motivo:
                return {
                    "modo": modo, "canal": "outlook", "apagado": False,
                    "puede": False, "faltan": ["pywin32"],
                    "nota": (f"pywin32 no se puede usar en este Python ({motivo}). "
                             f"Instálalo con: {comando_de_instalacion()}"),
                }
        return {
            "modo": modo, "canal": "outlook", "apagado": False,
            "puede": en_windows, "faltan": [] if en_windows else ["Outlook"],
            "nota": ("Lee el Outlook de escritorio de esta computadora."
                     if en_windows else
                     "MAIL_MODE=outlook necesita el Outlook de escritorio, y "
                     "este proceso no corre en Windows."),
        }

    if modo in _MODOS_TOKEN:
        faltan = [n for n in ("AZURE_TENANT_ID", "AZURE_CLIENT_ID",
                              "AZURE_CLIENT_SECRET")
                  if not _puesto(c, n)]
        if not _puesto(c, "GRAPH_USER", "IMAP_USER"):
            faltan.append("GRAPH_USER")
        return {"modo": modo, "canal": "graph", "puede": not faltan,
                "faltan": faltan, "apagado": False,
                "nota": "La aplicación de Entra ID necesita permiso de lectura "
                        "sobre ese buzón."}

    faltan = [n for n in ("IMAP_SERVER", "IMAP_USER", "IMAP_PASSWORD")
              if not _puesto(c, n)]
    return {"modo": modo, "canal": "imap", "puede": not faltan,
            "faltan": faltan, "apagado": False,
            "nota": "En Microsoft 365 la autenticación básica está retirada: "
                    "IMAP con usuario y contraseña ya no entra."}


def avisar_una_vez(diag: Dict[str, Any], quien: str = "servidor") -> str:
    """Escribe el porqué la primera vez y lo resume las siguientes.

    Devuelve la frase, para que quien llame la pueda poner también en el
    resultado del ciclo —la pantalla la enseña sin que nadie abra el registro—.

    Apagado a propósito no es lo mismo que mal configurado: lo primero se dice
    en INFO y una vez, lo segundo en WARNING. Marcar como aviso algo que
    alguien eligió es la forma de que nadie vuelva a leer los avisos.
    """
    if diag.get("apagado"):
        clave = f"{quien}:apagado"
        frase = (f"La lectura del correo está apagada en el {quien} "
                 f"(MAIL_MODE={diag['modo']}).")
        if not _YA_AVISADO.get(clave):
            _YA_AVISADO[clave] = True
            log.info("%s %s", frase, diag["nota"])
        return frase

    clave = f"{quien}:{diag['modo']}:{','.join(diag['faltan'])}"
    frase = (f"El {quien} no puede abrir el buzón en modo "
             f"{diag['modo'].upper()}: falta {', '.join(diag['faltan'])}.")

    if not _YA_AVISADO.get(clave):
        _YA_AVISADO[clave] = True
        log.warning("%s %s Si la lectura la hace la aplicación de escritorio, "
                    "esto es lo esperado y no hace falta arreglar nada: el "
                    "servidor dejará de intentarlo en vez de dejar un error "
                    "por ciclo.", frase, diag["nota"])
    else:
        log.debug("%s (ya avisado)", frase)
    return frase


def olvidar_avisos() -> None:
    """Para las pruebas: vuelve a considerar todo como no avisado."""
    _YA_AVISADO.clear()
