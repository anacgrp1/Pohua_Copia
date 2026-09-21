"""Volver a leer con la IA el plano que ya está guardado.

Por qué existe
--------------
Un plano se lee UNA vez, cuando el correo entra (``flow.procesar_dibujos``).
Si en ese momento falló algo —el formato no estaba soportado, la firma del
correo se coló como si fuera el dibujo, el modelo devolvió un JSON a medias,
o sencillamente el servidor todavía no tenía el arreglo— el RFQ se queda para
siempre sin cotas: sin diámetro de alambre no hay máquina, no hay peso de
alambre y el costeo sale orientativo aunque el correo viniera completo.

Volver a mandar el correo no es una opción: el adjunto ya se guardó y el
message-id ya está registrado. Este módulo lee de nuevo el plano guardado —el
mismo archivo, la misma API de visión, el mismo extractor— y persiste el
resultado, que es lo que luego usan la ventana de revisión y la calculadora.

Nunca lanza. Devuelve siempre un dict con ``estado``, del mismo vocabulario
que ``datos["lectura_plano"]`` del flujo:

``sin_adjunto``       no hay ningún plano guardado para este RFQ.
``formato_no_leido``  los hay, pero ninguno en un formato que el modelo lea.
``leido``             se leyó; ``resorte`` trae las variables físicas.
``fallo``             se intentó y reventó; ``motivo`` dice por qué.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

log = logging.getLogger("cotizador.relectura")


def planos_guardados(rfq_id: str) -> List[Dict[str, Any]]:
    """Los planos de este RFQ con su contenido, listos para el modelo.

    Devuelve ``[{"nombre": str, "contenido": bytes}, ...]``. Un plano cuyo
    contenido no se pueda recuperar se omite en lugar de viajar vacío: un
    bloque de cero bytes gasta la llamada y no enseña nada.
    """
    import app.persistence.blueprint_store as almacen

    fichas = almacen.listar_de_base(rfq_id)
    if not fichas:
        carpeta = almacen.carpeta_de(rfq_id)
        if carpeta is not None:
            fichas = [{"nombre": h.name} for h in sorted(carpeta.iterdir())
                      if h.is_file()]

    planos = []
    for ficha in fichas:
        nombre = ficha.get("nombre") or ""
        leido = almacen.leer_plano(rfq_id, nombre)
        if not leido or not leido[0]:
            log.warning("RFQ %s: el plano %s está listado pero no se pudo leer.",
                        rfq_id, nombre)
            continue
        planos.append({"nombre": nombre, "contenido": leido[0]})
    return planos


def legibles(planos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Los que el modelo de visión sabe abrir (.pdf/.png/.jpg)."""
    import app.vision.pipeline as pipeline
    return [p for p in planos
            if (p.get("nombre") or "").lower().endswith(pipeline.EXTENSIONES_SOPORTADAS)]


def releer(rfq_id: str, message_id: str = "", cliente=None) -> Dict[str, Any]:
    """Lee otra vez el plano guardado y persiste el resorte.

    ``cliente`` es el cliente de Anthropic; se inyecta en las pruebas y en
    producción lo crea el pipeline. El resultado se guarda en
    ``resortes_cotizacion`` como si viniera del correo, porque para todo lo
    que hay aguas abajo —la ficha, el costeo, la calculadora— es exactamente
    lo mismo: lo que dice el dibujo de esta pieza.
    """
    planos = planos_guardados(rfq_id)
    if not planos:
        log.info("RFQ=%s: no hay ningún plano guardado que releer.", rfq_id)
        return {"estado": "sin_adjunto", "resorte": None, "ficheros": []}

    utiles = legibles(planos)
    if not utiles:
        nombres = [p["nombre"] for p in planos]
        log.info("RFQ=%s: hay planos guardados pero ninguno legible (%s).",
                 rfq_id, ", ".join(nombres))
        import app.vision.pipeline as pipeline
        return {"estado": "formato_no_leido", "resorte": None,
                "ficheros": nombres,
                "soportados": list(pipeline.EXTENSIONES_SOPORTADAS)}

    nombres = [p["nombre"] for p in utiles]
    try:
        import app.persistence.spring_repository as spring_repository
        import app.vision.pipeline as pipeline
        import app.vision.spring_extractor as spring_extractor

        analisis = pipeline.analizar_dibujos(utiles, cliente=cliente)
        datos = spring_extractor.interpretar(analisis["texto"])
        spring_repository.guardar(rfq_id, message_id or "", ", ".join(nombres), datos)
        log.info("RFQ=%s: plano releído con la IA (%s); listo_para_cotizar=%s.",
                 rfq_id, ", ".join(nombres), datos.get("listo_para_cotizar"))
        return {"estado": "leido", "resorte": datos, "ficheros": nombres}
    except Exception as error:
        # Releer es una mejora, no un requisito: que falle no puede tumbar
        # ni la ficha ni la apertura de la calculadora.
        log.exception("RFQ=%s: falló la relectura del plano (%s): %s",
                      rfq_id, ", ".join(nombres), error)
        return {"estado": "fallo", "resorte": None, "ficheros": nombres,
                "motivo": str(error)}


def falta_geometria(resorte: Optional[dict]) -> bool:
    """¿Al resorte le falta lo mínimo para costear?

    El diámetro de alambre es el dato del que cuelga todo lo demás: sin él no
    se elige máquina, no se busca el precio del material en su calibre y el
    peso del alambre sale en cero. Si está, el resorte se considera leído
    aunque falten cotas menores; si no, no hay nada que costear.
    """
    if not resorte:
        return True
    valor = resorte.get("diametro_alambre_mm")
    try:
        return valor is None or float(valor) <= 0
    except (TypeError, ValueError):
        return True


def asegurar_resorte(rfq_id: str, resorte: Optional[dict],
                     message_id: str = "", cliente=None) -> Dict[str, Any]:
    """Si al resorte le falta geometría y hay plano guardado, léelo ahora.

    Es lo que hace que "abrir la cotización completa" abra completa: el PM no
    tiene por qué saber que el día que entró el correo la lectura del dibujo
    falló, ni volver a subir un archivo que el sistema ya tiene.

    Devuelve ``{"resorte": <el de siempre o el releído>, "lectura": <dict|None>}``.
    ``lectura`` es ``None`` cuando no hizo falta releer, para que quien llame
    distinga "no se intentó" de "se intentó y no salió".
    """
    if not falta_geometria(resorte):
        return {"resorte": resorte, "lectura": None}

    lectura = releer(rfq_id, message_id=message_id, cliente=cliente)
    if lectura["estado"] == "leido" and lectura["resorte"]:
        return {"resorte": lectura["resorte"], "lectura": lectura}
    return {"resorte": resorte, "lectura": lectura}
