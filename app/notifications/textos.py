# -*- coding: utf-8 -*-
"""Los avisos, dichos en el idioma de quien los va a leer.

Por qué existe
--------------
Pohua entero está traducido, pero las notificaciones salían siempre en
español: el título se armaba con una f-string en el servidor y viajaba ya
escrito hasta el teléfono. Quien tiene la aplicación en inglés recibía
«INT-738D9B2B: 1 dato(s) extraídos con poca confianza» en la pantalla de
bloqueo.

No se arregla traduciendo en la pantalla, porque una notificación push la
pinta el sistema operativo con lo que el servidor le mandó: cuando llega ya no
hay dónde traducirla. Hay que mandarla bien escrita de origen.

Y "de origen" no es un idioma, son varios: el mismo aviso va a todos los
dispositivos suscritos, y dos personas pueden tener Pohua en idiomas
distintos. Por eso el idioma se guarda POR DISPOSITIVO —lo dice el navegador
al suscribirse— y el texto se arma una vez por idioma, no una vez y ya.

Qué NO se traduce
-----------------
El cuerpo del aviso (el detalle) lleva datos: nombres de campo, números,
códigos de RFQ, la nota que escribió el PM. Eso se manda tal cual. Traducir un
identificador es peor que dejarlo en inglés.
"""

from __future__ import annotations

from typing import Any, Dict

IDIOMA_POR_DEFECTO = "en"

# Clave → texto por idioma. Los huecos son `str.format`: si falta uno, se deja
# el texto sin rellenar en vez de reventar el aviso (ver `titulo`).
TEXTOS: Dict[str, Dict[str, str]] = {
    "extraccion_revision": {
        "en": "{rfq}: {n} field(s) extracted with low confidence",
        "es": "{rfq}: {n} dato(s) extraídos con poca confianza",
        "fr": "{rfq} : {n} donnée(s) extraite(s) avec peu de confiance",
    },
    "extraccion_faltan": {
        "en": "{rfq}: {n} field(s) missing from the email",
        "es": "{rfq}: faltan {n} dato(s) en el correo",
        "fr": "{rfq} : il manque {n} donnée(s) dans le courrier",
    },
    "factibilidad_revision": {
        "en": "{cliente}: quote needs review before it can be sent",
        "es": "{cliente}: la cotización necesita revisión antes de salir",
        "fr": "{cliente} : le devis doit être vérifié avant l'envoi",
    },
    "factibilidad_validacion": {
        "en": "{cliente}: quote ready for your approval",
        "es": "{cliente}: cotización lista para tu aprobación",
        "fr": "{cliente} : devis prêt pour votre approbation",
    },
    "dictamen_devuelto": {
        "en": "{rfq}: sent back by the plant manager",
        "es": "{rfq}: devuelto por el PM",
        "fr": "{rfq} : renvoyé par le plant manager",
    },
}


def idiomas_de(clave: str) -> tuple:
    """Los idiomas en los que existe ese aviso."""
    return tuple((TEXTOS.get(clave) or {}).keys())


def titulo(clave: str, idioma: str = IDIOMA_POR_DEFECTO, **datos: Any) -> str:
    """El título del aviso en ese idioma, o ``''`` si la clave no existe.

    Devolver cadena vacía y no lanzar es deliberado: quien llama tiene un
    título ya escrito de respaldo, y un aviso en el idioma equivocado es mucho
    mejor que un aviso que no sale porque faltaba un hueco.
    """
    textos = TEXTOS.get(clave)
    if not textos:
        return ""
    plantilla = textos.get(idioma) or textos.get(IDIOMA_POR_DEFECTO) or ""
    try:
        return plantilla.format(**datos)
    except (KeyError, IndexError, ValueError):
        # Falta un dato. Se manda la plantilla sin rellenar antes que nada.
        return plantilla


def normalizar_idioma(idioma: Any) -> str:
    """"es-MX" → "es". Lo que no se reconozca, al idioma por defecto."""
    corto = str(idioma or "").strip().lower().replace("_", "-").split("-")[0]
    return corto if corto in ("en", "es", "fr") else IDIOMA_POR_DEFECTO
