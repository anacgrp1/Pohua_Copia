"""
El buzón de avisos del Plant Manager (COT-77).

Qué hace esto que no haga ya la cola de revisión
------------------------------------------------
`GET /api/assistant/attention` responde "qué está esperando AHORA", deducido
del estado de cada RFQ. Sirve para trabajar, pero es una foto: en cuanto el PM
dictamina, el RFQ sale de la cola y no queda constancia de que se le avisó.

Aquí se guarda el HECHO: qué se avisó, de qué RFQ, por qué motivo, cuándo, y
cuándo se leyó. Eso es lo que permite responder después cuánto se tarda en
atender lo que sale a revisión, o qué motivo aparece más — y es parte del
histórico que COT-76 quiere conservar para entrenar.

Ninguna función de este módulo rompe el ciclo del buzón. Un aviso que no se
pudo escribir es un aviso perdido, no un RFQ perdido: se registra el fallo y
se sigue. El RFQ ya quedó en `RequiresReview`, así que el trabajo no se pierde
aunque el aviso sí.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import app.persistence.duplicates as duplicates

log = logging.getLogger("cotizador.notificaciones")

# Sin `commit()` en ninguna función: `duplicates.conectar_bd()` devuelve la
# conexión en `autocommit`. Y cuando el llamador pasa la suya, el commit es
# suyo — confirmar aquí la transacción de otro es de los errores que sólo se
# notan cuando ya escribiste a medias.

# Los tipos que admite el CHECK de la migración 014.
TIPO_FACTIBILIDAD = "factibilidad_revision"
TIPO_EXTRACCION = "extraccion_revision"
TIPO_DICTAMEN = "dictamen_pm"

# El mismo vocabulario de `rfq_banderas.nivel`, para poder ordenar avisos y
# banderas juntos sin traducir nada.
NIVELES = ("ok", "info", "warn", "crit")


def crear(
    tipo: str,
    rfq_id: str,
    titulo: str,
    detalle: str = "",
    datos: Optional[dict] = None,
    nivel: str = "warn",
    usuario_id: Optional[int] = None,
    conexion=None,
    clave: Optional[str] = None,
    titulo_datos: Optional[dict] = None,
) -> Optional[int]:
    """Registra un aviso y devuelve su id, o ``None`` si no se pudo.

    El fallo se traga a propósito (y se registra): ver el encabezado.
    """
    if not rfq_id or not titulo:
        raise ValueError("crear() requiere rfq_id y titulo.")
    if nivel not in NIVELES:
        nivel = "warn"

    propia = conexion is None
    conn = None
    try:
        conn = conexion or duplicates.conectar_bd()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO notificaciones
                    (tipo, rfq_id, titulo, detalle, datos_json, nivel, usuario_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
                """,
                (tipo, rfq_id, titulo, detalle or "",
                 json.dumps(datos or {}, ensure_ascii=False, default=str),
                 nivel, usuario_id),
            )
            nuevo = cur.fetchone()[0]
        log.info("Aviso %s creado para RFQ=%s (%s).", nuevo, rfq_id, tipo)
        _empujar(nuevo, tipo, rfq_id, titulo, detalle, nivel, usuario_id,
                 clave, titulo_datos)
        return nuevo
    except Exception as error:
        log.exception("No se pudo crear el aviso de RFQ=%s (%s): %s",
                      rfq_id, tipo, error)
        return None
    finally:
        if propia and conn is not None:
            conn.close()


def _empujar(aviso_id, tipo, rfq_id, titulo, detalle, nivel, usuario_id,
             clave=None, titulo_datos=None) -> None:
    """El mismo aviso, al teléfono (Web Push). Nunca frena a quien lo creó.

    ``clave``/``titulo_datos`` viajan hasta ``push`` sin tocarse: es allí donde
    se sabe en qué idioma está cada aparato, y por tanto el único sitio donde
    el título se puede escribir bien.
    """
    try:
        import app.notifications.push as push
        push.enviar_a_todos(titulo=titulo, cuerpo=detalle or "", rfq_id=rfq_id,
                            nivel=nivel, usuario_id=usuario_id,
                            clave=clave, titulo_datos=titulo_datos,
                            extra={"aviso_id": aviso_id, "tipo": tipo})
    except Exception as error:
        log.warning("Aviso %s: no se pudo empujar al teléfono: %s", aviso_id, error)


def listar(solo_sin_leer: bool = True, limite: int = 50,
           conexion=None) -> List[Dict[str, Any]]:
    """Los avisos, los más nuevos primero."""
    limite = max(1, min(int(limite or 50), 200))
    propia = conexion is None
    conn = None
    try:
        conn = conexion or duplicates.conectar_bd()
        filtro = "WHERE leida_en IS NULL" if solo_sin_leer else ""
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT id, tipo, rfq_id, titulo, detalle, datos_json, nivel,
                       creada_en, leida_en
                FROM notificaciones
                {filtro}
                ORDER BY creada_en DESC
                LIMIT %s;
                """,
                (limite,),
            )
            filas = cur.fetchall()
        return [
            {
                "id": f[0],
                "tipo": f[1],
                "rfq_id": f[2],
                "titulo": f[3],
                "detalle": f[4] or "",
                "datos": f[5] or {},
                "nivel": f[6],
                "creada_en": f[7].isoformat() if f[7] else None,
                "leida_en": f[8].isoformat() if f[8] else None,
            }
            for f in filas
        ]
    finally:
        if propia and conn is not None:
            conn.close()


def contar_sin_leer(conexion=None) -> Dict[str, int]:
    """Cuántos avisos sin leer hay, y cuántos de ellos son críticos."""
    propia = conexion is None
    conn = None
    try:
        conn = conexion or duplicates.conectar_bd()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*), COUNT(*) FILTER (WHERE nivel = 'crit')
                FROM notificaciones
                WHERE leida_en IS NULL;
                """
            )
            total, criticas = cur.fetchone()
        return {"total": int(total or 0), "criticas": int(criticas or 0)}
    finally:
        if propia and conn is not None:
            conn.close()


def marcar_leida(notificacion_id: int, usuario_id: Optional[int] = None,
                 correo: Optional[str] = None, conexion=None) -> bool:
    """Marca un aviso como leído. Devuelve si cambió algo.

    `leida_en IS NULL` en el WHERE: releer un aviso ya leído no debe mover su
    fecha, que es la que mide cuánto se tardó en atenderlo.
    """
    propia = conexion is None
    conn = None
    try:
        conn = conexion or duplicates.conectar_bd()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE notificaciones
                SET leida_en = now(), leida_por = %s, leida_por_correo = %s
                WHERE id = %s AND leida_en IS NULL;
                """,
                (usuario_id, correo, notificacion_id),
            )
            cambiadas = cur.rowcount
        return cambiadas > 0
    finally:
        if propia and conn is not None:
            conn.close()


def marcar_todas(usuario_id: Optional[int] = None,
                 correo: Optional[str] = None, conexion=None) -> int:
    """Marca como leídos todos los avisos pendientes. Devuelve cuántos."""
    propia = conexion is None
    conn = None
    try:
        conn = conexion or duplicates.conectar_bd()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE notificaciones
                SET leida_en = now(), leida_por = %s, leida_por_correo = %s
                WHERE leida_en IS NULL;
                """,
                (usuario_id, correo),
            )
            cambiadas = cur.rowcount
        return int(cambiadas or 0)
    finally:
        if propia and conn is not None:
            conn.close()


def cerrar_del_rfq(rfq_id: str, usuario_id: Optional[int] = None,
                   correo: Optional[str] = None, conexion=None) -> int:
    """Da por atendidos los avisos pendientes de un RFQ. Devuelve cuántos.

    Al aprobar o declinar un RFQ, sus avisos («espera dictamen», «datos con
    poca confianza»…) ya no piden nada a nadie, pero seguían en la campana
    hasta que alguien los marcara a mano. No se borran: quedan como leídos,
    con quién y cuándo, que es la constancia de que se atendieron.
    """
    if not rfq_id:
        return 0
    propia = conexion is None
    conn = None
    try:
        conn = conexion or duplicates.conectar_bd()
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE notificaciones
                SET leida_en = now(), leida_por = %s, leida_por_correo = %s
                WHERE rfq_id = %s AND leida_en IS NULL;
                """,
                (usuario_id, correo, rfq_id),
            )
            cambiadas = cur.rowcount
        return int(cambiadas or 0)
    finally:
        if propia and conn is not None:
            conn.close()
