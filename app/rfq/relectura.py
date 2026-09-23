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
        #
        # El motivo se traduce a algo accionable: el error crudo de la
        # librería es un volcado JSON que llenaba la tarjeta de ruido sin
        # decir si hay que recargar saldo, cambiar la clave o sólo esperar.
        import app.core.modelo_errores as modelo_errores
        motivo = modelo_errores.explicar(error)
        log.exception("RFQ=%s: falló la relectura del plano (%s, %s): %s",
                      rfq_id, ", ".join(nombres), motivo["codigo"], error)
        return {"estado": "fallo", "resorte": None, "ficheros": nombres,
                "motivo": motivo["texto"], "codigo": motivo["codigo"],
                "reintentar": motivo["reintentar"]}


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


# Lo ya intentado en este proceso, y si tiene sentido repetirlo. Vive en
# memoria a propósito: al reiniciar se vuelve a intentar una vez, que es
# justo lo que se quiere después de recargar saldo o cambiar la clave.
_INTENTADO: Dict[str, str] = {}


def olvidar_intentos() -> None:
    """Para las pruebas, y para cuando alguien pulsa «releer» a mano."""
    _INTENTADO.clear()


def leer_en_segundo_plano(rfq_id: str, resorte: Optional[dict],
                          message_id: str = "") -> bool:
    """Lanza la lectura del plano SIN esperarla. Devuelve si se lanzó.

    Por qué
    -------
    La ficha del RFQ leía el plano dentro de la propia petición, así que la
    pantalla se quedaba en blanco lo que tardara el modelo —y leer un plano
    con un modelo de visión son segundos, no milésimas—. Peor: esa espera se
    pagaba al ABRIR la ficha, que es la pantalla más visitada, y para ver unos
    datos que el 90% de las veces ya estaban en la base.

    Así que la ficha ya no espera. Pinta al instante lo que hay guardado y
    manda leer por detrás; cuando alguien vuelva a entrar —o abra la ventana
    de revisión, que sí espera porque ahí se decide— las cotas están.

    La ventana de revisión conserva la lectura SÍNCRONA a propósito: ahí el PM
    va a aprobar o declinar, y dictaminar sobre un plano sin leer es
    dictaminar sobre seis rayas. Esa espera está justificada; la de la ficha
    no lo estaba.
    """
    if not falta_geometria(resorte):
        return False
    if _INTENTADO.get(rfq_id) in ("definitivo", "corriendo"):
        return False

    import threading

    # "corriendo" evita que dos pestañas abiertas a la vez manden dos
    # lecturas del mismo plano: son dos llamadas cobradas para guardar lo
    # mismo, y la segunda además pisaría a la primera.
    _INTENTADO[rfq_id] = "corriendo"

    def _trabajo():
        try:
            lectura = releer(rfq_id, message_id=message_id)
            if lectura["estado"] == "leido" and lectura["resorte"]:
                _INTENTADO.pop(rfq_id, None)
            else:
                _INTENTADO[rfq_id] = ("pasajero" if lectura.get("reintentar")
                                      else "definitivo")
        except Exception:
            # Nadie está esperando esto: si revienta, se apunta y ya.
            _INTENTADO[rfq_id] = "pasajero"
            log.exception("RFQ=%s: falló la lectura en segundo plano.", rfq_id)

    threading.Thread(target=_trabajo, name=f"plano-{rfq_id}",
                     daemon=True).start()
    return True


def asegurar_resorte_una_vez(rfq_id: str, resorte: Optional[dict],
                             message_id: str = "", cliente=None) -> Dict[str, Any]:
    """Como ``asegurar_resorte``, pero sin reintentar lo que no se va a arreglar.

    Por qué hace falta
    ------------------
    La ficha del RFQ se repinta cada vez que alguien la abre. Leer el plano ahí
    es lo correcto —los datos que enseña salen del dibujo, y quien la abre no
    tiene por qué saber que el día del correo la lectura falló ni ir a buscar
    otra pantalla para arreglarlo—, pero cada lectura es una llamada de pago.

    Un plano ilegible o una clave revocada fallan igual las cien veces. Sin
    freno, abrir la misma ficha diez veces son diez llamadas cobradas para
    obtener diez veces el mismo error.

    Así que se distingue lo pasajero de lo definitivo, con el mismo criterio
    que ya usa ``modelo_errores.explicar``: si el error se arregla solo
    —saturación, límite de ritmo, un corte de red—, se vuelve a intentar; si
    no, se intenta UNA vez y después se deja el botón de releer, que es una
    persona decidiendo gastar la llamada.
    """
    if not falta_geometria(resorte):
        return {"resorte": resorte, "lectura": None}

    if _INTENTADO.get(rfq_id) == "definitivo":
        # Ya se intentó y no va a salir distinto. No se dice que no se
        # intentó: se dice que se intentó y falló, que es lo que la pantalla
        # necesita para enseñar el motivo y el botón.
        return {"resorte": resorte, "lectura": None, "agotado": True}

    lectura = releer(rfq_id, message_id=message_id, cliente=cliente)

    if lectura["estado"] == "leido" and lectura["resorte"]:
        _INTENTADO.pop(rfq_id, None)
        return {"resorte": lectura["resorte"], "lectura": lectura}

    # `reintentar` sólo viene en los fallos del modelo. Un plano que no existe
    # o que está en un formato que no se abre tampoco mejora solo.
    pasajero = bool(lectura.get("reintentar"))
    _INTENTADO[rfq_id] = "pasajero" if pasajero else "definitivo"
    return {"resorte": resorte, "lectura": lectura}


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
