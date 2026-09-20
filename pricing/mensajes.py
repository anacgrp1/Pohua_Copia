"""Los motivos de un costeo incompleto, con un código para poder traducirlos.

POR QUÉ EXISTE
--------------
Estos textos los escribe el servidor y los lee una persona en la pantalla: en
la franja ámbar de la ventana de revisión, en el aviso de "mandar con precio
orientativo" y en las notas del PM. El servidor no sabe en qué idioma tiene
puesta Pohua quien mira —y el mismo RFQ lo abren personas distintas—, así que
el texto salía siempre en español dentro de una pantalla en inglés.

La traducción tiene que pasar en el navegador, y para eso hace falta algo que
traducir: un CÓDIGO y sus datos, no una frase ya armada. Aquí viven los dos:

    falta(cat, "MATERIAL_SIN_CATALOGO", material="ASTM A228")

apunta en ``cat.faltantes`` la frase de siempre —que es la que va al registro
y a quien no tenga traducción— y en ``cat.faltantes_i18n`` el par
``{"codigo": ..., "datos": {...}}`` con el que el navegador arma la frase en
el idioma que toque (frontend/js/i18n.js, claves ``costeo.*``).

Las dos listas se llenan SIEMPRE juntas, desde esta única función, que es lo
que impide que se queden desparejadas.
"""

from __future__ import annotations

# El texto en español de cada motivo. Es el que se registra en el log y el que
# se enseña si el navegador no conoce el código (una versión más nueva del
# servidor con una más vieja de la web).
TEXTOS = {
    "PARAMETROS_SIN_JUEGO":
        "No hay un juego de parámetros vigente en param_juegos/param_valores; "
        "se usan los del motor.",
    "PARAMETROS_ILEGIBLES":
        "Parámetros de costeo ilegibles: {error}",
    "SIN_DIAMETRO_ALAMBRE":
        "Falta el diámetro de alambre: sin él no se puede elegir máquina "
        "ni buscar el precio del material.",
    "SIN_MAQUINA_CAPAZ":
        "Ninguna máquina activa del catálogo puede hacer un resorte de "
        "{tipo} con alambre de {diametro} mm.",
    "MAQUINA_SIN_TARIFA":
        "La máquina {maquina} no tiene tarifa vigente en maquina_tarifas.",
    "MAQUINA_FALLO":
        "Selección de máquina fallida: {error}",
    "MATERIAL_SIN_CATALOGO":
        "El material '{material}' no está en el catálogo de materiales.",
    "MATERIAL_SIN_PRECIO":
        "El material '{material}' no tiene precio en material_precios.",
    "MATERIAL_ILEGIBLE":
        "Precio de material ilegible: {error}",
    "SIN_MATERIAL":
        "No se indicó material: no se puede costear el alambre.",
    "SIN_EMPAQUES":
        "No hay empaques activos en el catálogo.",
    "EMPAQUE_ILEGIBLE":
        "Empaque ilegible: {error}",
    "SIN_CANTIDAD":
        "No se indicó cantidad: el costeo por escalones necesita un volumen.",
    "SIN_PESO_ALAMBRE":
        "No se pudo calcular el peso del alambre (faltan diámetro, diámetro "
        "medio o número de espiras): el costo de material saldría en cero.",
    "PESO_SOLO_CUERPO":
        "El peso sólo cubre el cuerpo del resorte; faltan ganchos o patas por "
        "capturar, así que el material está subestimado.",
    "SIN_CANTIDADES_RFQ":
        "El RFQ no trae ninguna cantidad: no hay tramos que costear.",
    # Los de la oferta al cliente (app/rfq/oferta.py). Llevan dentro los de
    # arriba: "El costeo es orientativo: <motivos>".
    "OFERTA_NO_APROBADA":
        "El RFQ está en '{estado}': sólo se oferta un RFQ aprobado.",
    "OFERTA_SIN_TRAMOS":
        "No hay tramos costeados: {detalle}",
    "OFERTA_ORIENTATIVA":
        "El costeo es orientativo: {detalle}",
    "OFERTA_SIN_DESTINO":
        "No hay a quién mandarla: el RFQ no trae remitente.",
    "SIN_MATERIAL_NI_DIAMETRO":
        "Sin material ni diámetro de alambre no se puede costear: "
        "hay que capturarlos en la cotización completa.",
}


def texto(codigo: str, **datos) -> str:
    """La frase en español de un motivo, con sus datos dentro."""
    plantilla = TEXTOS.get(codigo)
    if not plantilla:
        return codigo
    try:
        return plantilla.format(**datos)
    except (KeyError, IndexError):
        # Un dato que falta no puede tumbar un costeo: sale la plantilla.
        return plantilla


def entrada(codigo: str, **datos) -> dict:
    """El motivo en la forma que viaja a la web: código, datos y respaldo."""
    return {"codigo": codigo, "datos": {k: v for k, v in datos.items()},
            "texto": texto(codigo, **datos)}


def falta(catalogo, codigo: str, **datos) -> None:
    """Apunta un motivo en el catálogo, en las dos listas a la vez."""
    catalogo.faltantes.append(texto(codigo, **datos))
    try:
        catalogo.faltantes_i18n.append(entrada(codigo, **datos))
    except AttributeError:
        # Un catálogo de una versión anterior no tiene la lista nueva; el
        # costeo no se detiene por eso.
        pass
