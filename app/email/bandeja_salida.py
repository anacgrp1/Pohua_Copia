"""La bandeja de salida: quien arma el correo no siempre es quien lo manda.

El reparto
----------
El buzón de ISC se abre por el Outlook de escritorio de una computadora. Leer
ya estaba repartido —lee la aplicación de escritorio y el worker del servidor
se aparta, porque los dos hablan con la misma base en Neon—. Mandar no lo
estaba: la oferta la arma el proceso web en Render cuando el plant manager
pulsa el botón, y Render no tiene cuenta emisora.

El resultado era el peor posible: el PDF se generaba, se archivaba, y el correo
moría con «No hay cuenta emisora configurada». La oferta existía para todos
menos para el cliente.

Aquí el correo redactado espera en la base a que pase por él quien sí tiene
Outlook. No es un reintento ni una cola de trabajo genérica: es el mismo
reparto que ya se usa para leer, aplicado a mandar.

Lo que viaja y lo que no
------------------------
El PDF de la oferta viaja **en bytes**: lo escribe Render en su disco, y esa
ruta no existe en la computadora que va a mandar el correo. Guardar la ruta
sería guardar una promesa que el otro lado no puede cumplir.

Las imágenes de la firma NO viajan: son del repositorio, están en los dos
lados, y cada uno resuelve las suyas al mandar. Meter las rutas de Render en
la fila dejaría la firma rota en Windows.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

log = logging.getLogger("cotizador.bandeja_salida")

# Cuántas veces se reintenta antes de dejarlo en 'fallo' y no volver a
# intentarlo solo. Outlook puede estar cerrándose, la computadora suspendida o
# el buzón pidiendo contraseña: eso se arregla solo en el siguiente ciclo. Lo
# que no puede pasar es que un correo imposible se reintente para siempre y
# tape a los que sí podrían salir.
MAX_INTENTOS = 5


@contextmanager
def _conexion(conexion=None):
    """La conexión que toca: la que nos pasen, o una propia que se cierra sola.

    `duplicates.conexion_bd()` ya es un context manager que CIERRA —Neon tiene
    tope de conexiones— y viene con autocommit, así que aquí no se hace commit
    a mano.
    """
    if conexion is not None:
        yield conexion
        return
    import app.persistence.duplicates as duplicates
    with duplicates.conexion_bd() as conn:
        yield conn


# --------------------------------------------------------------------------- #
# Encolar
# --------------------------------------------------------------------------- #

def encolar(contenido: Dict[str, Any], rfq_id: Optional[str] = None,
            clase: str = "oferta", por: Optional[str] = None,
            conexion=None) -> int:
    """Deja el correo esperando a quien pueda mandarlo. Devuelve su id.

    ``contenido`` es el dict de ``templates.construir_correo``. Sus adjuntos
    se leen a bytes AQUÍ, mientras el fichero todavía existe y este proceso lo
    puede ver: quien lo despache estará en otra computadora.
    """
    adjuntos = []
    for ruta in (contenido.get("adjuntos") or []):
        try:
            with open(ruta, "rb") as fichero:
                datos = fichero.read()
            adjuntos.append((os.path.basename(ruta), _tipo_de(ruta), datos))
        except OSError as error:
            # Un adjunto ilegible no cancela el correo: es peor que la oferta
            # no salga a que salga sin el PDF, y el registro lo dice.
            log.error("No se pudo leer el adjunto %s para la bandeja de "
                      "salida: %s", ruta, error)

    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO correos_salida
                    (rfq_id, clase, destinatario, asunto, cuerpo_html,
                     cuerpo_texto, creado_por)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (rfq_id, clase, contenido.get("destinatario"),
                 contenido.get("asunto"), contenido.get("cuerpo_html"),
                 contenido.get("cuerpo_texto"), por))
            salida_id = cur.fetchone()[0]

            for nombre, tipo, datos in adjuntos:
                cur.execute(
                    """
                    INSERT INTO correos_salida_adjuntos
                        (salida_id, nombre, tipo, bytes, contenido)
                    VALUES (%s, %s, %s, %s, %s);
                    """,
                    (salida_id, nombre, tipo, len(datos), psycopg_binario(datos)))

    log.info("Correo para %s encolado (id=%s, rfq=%s, %d adjunto/s).",
             contenido.get("destinatario"), salida_id, rfq_id, len(adjuntos))
    return salida_id


def psycopg_binario(datos: bytes):
    """Los bytes tal como los quiere psycopg2 para una columna ``bytea``."""
    import psycopg2
    return psycopg2.Binary(datos)


def _tipo_de(ruta: str) -> str:
    import mimetypes
    return mimetypes.guess_type(ruta)[0] or "application/octet-stream"


# --------------------------------------------------------------------------- #
# Leer
# --------------------------------------------------------------------------- #

def pendientes(limite: int = 20, conexion=None) -> List[Dict[str, Any]]:
    """Lo que espera a que alguien lo mande, lo más viejo primero.

    Los que ya agotaron los intentos no salen: se quedan en la tabla para que
    se vean y se puedan reintentar a mano, pero no vuelven a tapar la cola.
    """
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, rfq_id, clase, destinatario, asunto,
                       cuerpo_html, cuerpo_texto, intentos
                FROM correos_salida
                WHERE estado = 'pendiente' AND intentos < %s
                ORDER BY id
                LIMIT %s;
                """,
                (MAX_INTENTOS, limite))
            filas = cur.fetchall()

            correos = []
            for f in filas:
                cur.execute(
                    "SELECT nombre, tipo, contenido FROM correos_salida_adjuntos "
                    "WHERE salida_id = %s ORDER BY id;", (f[0],))
                adjuntos = [{"nombre": a[0], "tipo": a[1], "contenido": bytes(a[2])}
                            for a in cur.fetchall()]
                correos.append({
                    "id": f[0], "rfq_id": f[1], "clase": f[2],
                    "destinatario": f[3], "asunto": f[4],
                    "cuerpo_html": f[5], "cuerpo_texto": f[6],
                    "intentos": f[7], "adjuntos": adjuntos,
                })
    return correos


def hay_pendientes(conexion=None) -> int:
    """Cuántos correos esperan. Para decirlo en la pantalla sin traerlos."""
    try:
        with _conexion(conexion) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM correos_salida "
                            "WHERE estado = 'pendiente' AND intentos < %s;",
                            (MAX_INTENTOS,))
                return int(cur.fetchone()[0])
    except Exception as error:
        # Contar no puede tumbar una pantalla.
        log.debug("No se pudo contar la bandeja de salida: %s", error)
        return 0


# --------------------------------------------------------------------------- #
# Marcar
# --------------------------------------------------------------------------- #

def marcar_enviado(salida_id: int, conexion=None) -> None:
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE correos_salida "
                "SET estado = 'enviado', enviado_en = NOW(), "
                "    intentos = intentos + 1, ultimo_error = NULL "
                "WHERE id = %s;", (salida_id,))


def marcar_fallo(salida_id: int, error: str, conexion=None) -> None:
    """Suma un intento. Al agotarlos, el correo pasa a 'fallo' y para.

    Un fallo casi siempre es pasajero —Outlook cerrándose, la computadora
    suspendida— y se arregla solo en el siguiente ciclo. Por eso sigue
    'pendiente' mientras queden intentos.
    """
    with _conexion(conexion) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE correos_salida
                SET intentos = intentos + 1,
                    ultimo_error = %s,
                    estado = CASE WHEN intentos + 1 >= %s THEN 'fallo'
                                  ELSE 'pendiente' END
                WHERE id = %s;
                """,
                (str(error)[:2000], MAX_INTENTOS, salida_id))


# --------------------------------------------------------------------------- #
# Despachar
# --------------------------------------------------------------------------- #

def drenar(limite: int = 20, enviar=None) -> Dict[str, int]:
    """Manda lo que esté esperando. La llama el ciclo del lector de escritorio.

    ``enviar`` se inyecta en las pruebas; en producción es el proveedor de
    Outlook, que despacha desde el buzón compartido (``OUTLOOK_BUZON``) y no
    desde la cuenta personal de quien tenga Outlook abierto.

    Nunca lanza: un correo que no sale no puede tumbar el ciclo de lectura, que
    es lo que hace entrar los RFQ.
    """
    resumen = {"enviados": 0, "fallidos": 0, "pendientes": 0, "omitidos": 0}

    # Si ESTE proceso tampoco puede mandar, no se toca la cola. Intentarlo
    # gastaría los cinco intentos de cada correo en segundos y los dejaría en
    # 'fallo' para siempre, por una configuración que se arregla poniendo una
    # variable. Los correos se quedan quietos esperando a quien sí pueda.
    if enviar is None:
        try:
            import app.email.outbound as outbound
            diag = outbound.diagnostico_envio()
        except Exception as error:
            log.warning("No se pudo comprobar si se puede mandar: %s", error)
            return resumen
        if not diag["puede"]:
            resumen["omitidos"] = hay_pendientes()
            if resumen["omitidos"]:
                log.warning("Bandeja de salida: %d correo/s esperando, pero "
                            "este proceso no puede mandar (modo %s, falta %s). "
                            "No se tocan.",
                            resumen["omitidos"], diag["modo"],
                            ", ".join(diag["faltan"]))
            return resumen

    try:
        cola = pendientes(limite)
    except Exception as error:
        log.warning("No se pudo leer la bandeja de salida: %s", error)
        return resumen

    if not cola:
        return resumen

    despachar = enviar or _despachar_por_outlook
    for correo in cola:
        try:
            if despachar(correo):
                marcar_enviado(correo["id"])
                resumen["enviados"] += 1
                _apuntar_en_el_rfq(correo)
                log.info("Bandeja de salida: enviado a %s (id=%s, rfq=%s).",
                         correo["destinatario"], correo["id"], correo["rfq_id"])
            else:
                marcar_fallo(correo["id"], "El proveedor devolvió False.")
                resumen["fallidos"] += 1
        except Exception as error:
            log.error("Bandeja de salida: falló el id=%s: %s", correo["id"], error)
            try:
                marcar_fallo(correo["id"], str(error))
            except Exception:
                log.debug("Tampoco se pudo apuntar el fallo.", exc_info=True)
            resumen["fallidos"] += 1

    try:
        resumen["pendientes"] = hay_pendientes()
    except Exception:
        pass
    return resumen


def _despachar_por_outlook(correo: Dict[str, Any]) -> bool:
    """Un correo de la cola, por el Outlook de esta computadora.

    La firma se vuelve a resolver AQUÍ: sus imágenes son del repositorio y las
    rutas de quien encoló no valen en esta máquina.
    """
    from app.email.base_provider import EmailAttachment
    from app.email.factory import EmailProviderFactory

    adjuntos = [EmailAttachment(filename=a["nombre"], content=a["contenido"])
                for a in (correo.get("adjuntos") or [])]

    import app.email.templates as templates
    for imagen in (templates._imagenes_de_la_firma() or []):
        ruta = imagen.get("ruta")
        if not ruta:
            continue
        try:
            with open(ruta, "rb") as fichero:
                adjuntos.append(EmailAttachment(filename=os.path.basename(ruta),
                                                content=fichero.read(),
                                                content_id=imagen.get("cid")))
        except OSError as error:
            # Sin logo el correo sale igual, con la firma en texto.
            log.warning("No se pudo incrustar %s: %s", ruta, error)

    proveedor = EmailProviderFactory.get_provider()
    return bool(proveedor.send_email(
        to=correo["destinatario"],
        subject=correo["asunto"],
        body=correo.get("cuerpo_html") or correo.get("cuerpo_texto") or "",
        attachments=adjuntos,
    ))


def _apuntar_en_el_rfq(correo: Dict[str, Any]) -> None:
    """Deja dicho en el RFQ que la oferta ya salió.

    Sin esto, la pantalla seguiría enseñando «pendiente de enviar» después de
    que el correo saliera de verdad, y el embudo no contaría la oferta en
    «Quote sent» —que mira ``datos_json->'oferta'->>'enviada'``—.
    """
    if not correo.get("rfq_id") or correo.get("clase") != "oferta":
        return
    try:
        with _conexion() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE rfqs
                    SET datos_json = jsonb_set(
                            jsonb_set(COALESCE(datos_json, '{}'::jsonb),
                                      '{oferta,enviada}', 'true'::jsonb, true),
                            '{oferta,fecha_envio}',
                            to_jsonb(NOW()::text), true)
                    WHERE rfq_id = %s;
                    """,
                    (correo["rfq_id"],))
    except Exception as error:
        # El correo ya salió: no apuntarlo es feo, pero deshacerlo sería peor.
        log.warning("La oferta de %s salió pero no se pudo apuntar en el RFQ: %s",
                    correo.get("rfq_id"), error)
