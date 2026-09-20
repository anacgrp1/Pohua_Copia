"""Web Push: los avisos de la campana, también en el teléfono.

La campana (``app.notifications.repository``) guarda cada aviso y lo recoge
quien tiene Pohua abierta. Esto es la otra puerta: el mismo aviso, entregado
por el servicio de push del navegador al centro de notificaciones del
teléfono (o de la compu), con la aplicación cerrada.

Cómo funciona, en tres pasos:

1. El navegador, tras pedirle permiso a la persona, entrega una suscripción:
   una URL del servicio de push (Google, Apple, Mozilla…) y dos claves. Se
   guarda una fila por dispositivo en ``push_suscripciones``.
2. Cuando se crea un aviso, ``enviar_a_todos()`` lo cifra para cada
   suscripción y lo entrega a esa URL (``pywebpush``). El envío va en un hilo
   aparte: el ciclo de correo no espera a Google.
3. El service worker de la app (``frontend/sw.js``) recibe el push, pinta la
   notificación, y al tocarla abre Pohua en ``#/rfq/<id>``: la ventana de
   revisión.

El servidor se identifica ante el servicio de push con un par de claves VAPID
(``VAPID_PUBLIC_KEY`` / ``VAPID_PRIVATE_KEY``, ``scripts/generar_vapid.py``).
Sin ellas todo lo demás sigue igual: ``habilitado()`` da False, la campana
funciona dentro de la app y no se manda nada.

Una suscripción que el servicio rechaza como muerta (404 / 410) se borra al
momento: es el navegador diciendo que ese dispositivo ya no la tiene.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Dict, List, Optional

import app.persistence.duplicates as duplicates

log = logging.getLogger("cotizador.push")

# Cuánto tiempo guarda el servicio de push el aviso si el teléfono está sin
# red. Un día: un dictamen de RFQ que llega al día siguiente todavía sirve.
TTL_SEGUNDOS = 24 * 3600


# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

def _config():
    import app.core.config as config
    return config


def clave_publica() -> str:
    return (getattr(_config(), "VAPID_PUBLIC_KEY", "") or "").strip()


def habilitado() -> bool:
    c = _config()
    return bool((getattr(c, "VAPID_PUBLIC_KEY", "") or "").strip()
                and (getattr(c, "VAPID_PRIVATE_KEY", "") or "").strip())


def _sujeto() -> str:
    c = _config()
    sujeto = (getattr(c, "VAPID_SUBJECT", "") or "").strip()
    if sujeto:
        return sujeto
    buzon = (getattr(c, "GRAPH_USER", None) or getattr(c, "IMAP_USER", None)
             or getattr(c, "SMTP_USER", None) or "")
    return f"mailto:{buzon}" if buzon else "mailto:pohua@localhost"


# ---------------------------------------------------------------------------
# Suscripciones
# ---------------------------------------------------------------------------

def _validar(suscripcion: Dict[str, Any]) -> Dict[str, str]:
    """Lo que manda ``PushSubscription.toJSON()``: endpoint + keys.{p256dh,auth}."""
    if not isinstance(suscripcion, dict):
        raise ValueError("La suscripción tiene que ser un objeto.")
    endpoint = str(suscripcion.get("endpoint") or "").strip()
    claves = suscripcion.get("keys") or {}
    p256dh = str(claves.get("p256dh") or "").strip()
    auth = str(claves.get("auth") or "").strip()
    if not endpoint.startswith("https://") or not p256dh or not auth:
        raise ValueError("Suscripción incompleta: hacen falta endpoint y las claves p256dh y auth.")
    return {"endpoint": endpoint, "p256dh": p256dh, "auth": auth}


def suscribir(usuario_id: int, correo: Optional[str], suscripcion: Dict[str, Any],
              navegador: Optional[str] = None, conexion=None) -> int:
    """Guarda (o renueva) la suscripción de un dispositivo. Devuelve su id."""
    s = _validar(suscripcion)
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO push_suscripciones
                    (usuario_id, usuario_correo, endpoint, p256dh, auth, navegador)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (endpoint) DO UPDATE
                    SET usuario_id = EXCLUDED.usuario_id,
                        usuario_correo = EXCLUDED.usuario_correo,
                        p256dh = EXCLUDED.p256dh,
                        auth = EXCLUDED.auth,
                        navegador = EXCLUDED.navegador,
                        fallos = 0
                RETURNING id, (xmax = 0) AS es_nuevo;
                """,
                (usuario_id, correo, s["endpoint"], s["p256dh"], s["auth"],
                 (navegador or "")[:200] or None),
            )
            nuevo, es_nuevo = cur.fetchone()
        # Cada vez que alguien abre Pohua, su dispositivo se vuelve a
        # registrar: así sobrevive un cambio de usuario en el mismo teléfono o
        # una suscripción renovada por el navegador. Eso está bien, pero
        # anunciarlo como novedad en cada recarga llenaba el registro de líneas
        # idénticas y tapaba lo que sí pasa. Alta nueva: se cuenta. Refresco de
        # una que ya estaba: se apunta, pero abajo.
        if es_nuevo:
            log.info("Push: dispositivo %s suscrito para %s.", nuevo,
                     correo or usuario_id)
        else:
            log.debug("Push: dispositivo %s ya estaba suscrito (%s); se refresca.",
                      nuevo, correo or usuario_id)
        return nuevo
    finally:
        if propia:
            conn.close()


def desuscribir(endpoint: str, usuario_id: Optional[int] = None, conexion=None) -> bool:
    """Borra la suscripción de un dispositivo (la suya: se filtra por usuario)."""
    if not endpoint:
        return False
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        with conn.cursor() as cur:
            if usuario_id is None:
                cur.execute("DELETE FROM push_suscripciones WHERE endpoint = %s;", (endpoint,))
            else:
                cur.execute("DELETE FROM push_suscripciones WHERE endpoint = %s AND usuario_id = %s;",
                            (endpoint, usuario_id))
            return cur.rowcount > 0
    finally:
        if propia:
            conn.close()


def listar(usuario_id: Optional[int] = None, conexion=None) -> List[Dict[str, Any]]:
    """Las suscripciones (todas, o las de una persona)."""
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        with conn.cursor() as cur:
            sql = ("SELECT id, usuario_id, usuario_correo, endpoint, p256dh, auth, navegador, "
                   "creada_en, ultimo_envio, fallos FROM push_suscripciones")
            if usuario_id is None:
                cur.execute(sql + " ORDER BY id;")
            else:
                cur.execute(sql + " WHERE usuario_id = %s ORDER BY id;", (usuario_id,))
            filas = cur.fetchall()
        claves = ("id", "usuario_id", "usuario_correo", "endpoint", "p256dh", "auth",
                  "navegador", "creada_en", "ultimo_envio", "fallos")
        return [dict(zip(claves, f)) for f in filas]
    finally:
        if propia:
            conn.close()


def _anotar_resultado(sub_id: int, ok: bool, muerta: bool, conexion=None) -> None:
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        with conn.cursor() as cur:
            if muerta:
                cur.execute("DELETE FROM push_suscripciones WHERE id = %s;", (sub_id,))
            elif ok:
                cur.execute("UPDATE push_suscripciones SET ultimo_envio = now(), fallos = 0 "
                            "WHERE id = %s;", (sub_id,))
            else:
                cur.execute("UPDATE push_suscripciones SET fallos = fallos + 1 WHERE id = %s;",
                            (sub_id,))
    except Exception as error:      # la constancia no puede romper el envío
        log.warning("Push: no se pudo anotar el resultado de %s: %s", sub_id, error)
    finally:
        if propia:
            conn.close()


# ---------------------------------------------------------------------------
# Envío
# ---------------------------------------------------------------------------

def _carga(titulo: str, cuerpo: str, rfq_id: Optional[str], nivel: str,
           extra: Optional[Dict[str, Any]] = None) -> str:
    """Lo que lee el service worker. Pequeño a propósito: el límite es 4 KB."""
    datos = {
        "titulo": titulo,
        "cuerpo": (cuerpo or "")[:300],
        "rfq_id": rfq_id,
        "nivel": nivel,
        # A dónde va al tocarla: la ventana de revisión del RFQ, o la app.
        "url": f"/#/rfq/{rfq_id}" if rfq_id else "/",
        "tag": f"rfq-{rfq_id}" if rfq_id else "pohua",
    }
    if extra:
        datos.update(extra)
    return json.dumps(datos, ensure_ascii=False, default=str)


def _mandar_una(sub: Dict[str, Any], carga: str) -> bool:
    """Un push a un dispositivo. Devuelve si salió; borra la suscripción si murió."""
    from pywebpush import WebPushException, webpush

    info = {"endpoint": sub["endpoint"],
            "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}}
    try:
        webpush(
            subscription_info=info,
            data=carga,
            vapid_private_key=_config().VAPID_PRIVATE_KEY.strip(),
            vapid_claims={"sub": _sujeto()},
            ttl=TTL_SEGUNDOS,
            timeout=10,
        )
        _anotar_resultado(sub["id"], ok=True, muerta=False)
        return True
    except WebPushException as error:
        respuesta = getattr(error, "response", None)
        codigo = getattr(respuesta, "status_code", None)
        muerta = codigo in (404, 410)
        if muerta:
            log.info("Push: el dispositivo %s ya no existe (%s); se da de baja.", sub["id"], codigo)
        else:
            log.warning("Push: no se pudo entregar a %s (%s): %s", sub["id"], codigo, error)
        _anotar_resultado(sub["id"], ok=False, muerta=muerta)
        return False
    except Exception as error:
        log.warning("Push: fallo inesperado con %s: %s", sub["id"], error)
        _anotar_resultado(sub["id"], ok=False, muerta=False)
        return False


def enviar_a_todos(titulo: str, cuerpo: str = "", rfq_id: Optional[str] = None,
                   nivel: str = "info", usuario_id: Optional[int] = None,
                   extra: Optional[Dict[str, Any]] = None,
                   en_segundo_plano: bool = True) -> int:
    """Manda el aviso a todos los dispositivos suscritos (o a los de una persona).

    Devuelve cuántos dispositivos había. Con ``en_segundo_plano`` el envío
    corre en un hilo y esta función vuelve enseguida: quien crea el aviso
    —el ciclo de correo, el dictamen del PM— no tiene por qué esperar.
    """
    if not habilitado():
        return 0
    try:
        subs = listar(usuario_id)
    except Exception as error:
        log.warning("Push: no se pudieron leer las suscripciones: %s", error)
        return 0
    if not subs:
        return 0

    carga = _carga(titulo, cuerpo, rfq_id, nivel, extra)

    def _trabajo():
        entregados = sum(1 for s in subs if _mandar_una(s, carga))
        log.info("Push: %s de %s dispositivos recibieron «%s».", entregados, len(subs), titulo)

    if en_segundo_plano:
        threading.Thread(target=_trabajo, name="push-avisos", daemon=True).start()
    else:
        _trabajo()
    return len(subs)


def enviar_a_persona(usuario_id: int, titulo: str, cuerpo: str = "", *,
                     url: str = "/", tag: str = "pohua",
                     nivel: str = "info") -> Dict[str, int]:
    """Un aviso a los dispositivos de UNA persona, esperando el resultado.

    Devuelve ``{"dispositivos": n, "entregados": m}``: quien lo pide (el
    administrador mandando una contraseña temporal) necesita saber si llegó
    a algún sitio o si tiene que dársela en persona. Por eso va en el hilo
    de la petición y no en segundo plano.
    """
    if not habilitado():
        return {"dispositivos": 0, "entregados": 0}
    subs = listar(usuario_id)
    if not subs:
        return {"dispositivos": 0, "entregados": 0}
    carga = _carga(titulo, cuerpo, None, nivel, {"url": url, "tag": tag})
    entregados = sum(1 for s in subs if _mandar_una(s, carga))
    log.info("Push: %s de %s dispositivos de la persona %s recibieron «%s».",
             entregados, len(subs), usuario_id, titulo)
    return {"dispositivos": len(subs), "entregados": entregados}
