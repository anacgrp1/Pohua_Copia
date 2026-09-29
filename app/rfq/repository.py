"""COT-56 [Flujo - Almacenamiento] Persistencia de RFQ en estado New.

Propósito
---------
Inserta en la base de datos el registro de un RFQ cuando la validación fue
correcta (criterio OK). Dos casos:

* **RFQ nuevo:** se crea un registro en estado ``New`` con ``version = 1``.
* **Seguimiento / actualización de un proyecto existente** (el análisis de
  hilos detectó que pertenece a un RFQ ya conocido): **no se duplica** el
  registro; se abre una **nueva versión** de cotización vinculada al mismo
  ``rfq_id``.

Quién decide el caso: el flujo (``flow.clasificar``) ya entrega el
``rfq_id`` y si es respuesta a un RFQ existente. Este módulo sólo persiste.

Alcance
-------
* **Sí hace:** calcular la siguiente versión e insertar el registro del RFQ.
* **NO hace:** guardar los planos (eso es ``almacen_planos``), validar los
  campos (COT-54), ni mapear el cliente (COT-55).

Funciones públicas
------------------
``guardar_rfq(rfq_id, datos, es_seguimiento=False, conexion=None) -> dict``
``guardar_veredicto(rfq_id, resultado, version=None, conexion=None) -> dict``
``guardar_veredicto_final(rfq_id, veredicto, version=None, ...) -> dict``
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import app.persistence.duplicates as duplicates

log = logging.getLogger("cotizador.repositorio_rfq")

ESTADO_NEW = "New"

# El modelo extrajo datos con confianza por debajo del umbral: el RFQ se
# registra igual, pero marcado para que lo valide una persona (COT-61 → COT-77).
ESTADO_REVISION = "RequiresReview"

# Niveles admitidos por el CHECK de `rfq_banderas.nivel` (migración 005).
NIVELES_BANDERA = ("ok", "info", "warn", "crit")

# Estados a los que llega un RFQ cuando el plant manager lo dictamina (COT-72).
ESTADO_APROBADO = "Approved"
ESTADO_DECLINADO = "Declined"

# Se evaluó, pero faltan datos para seguir: o no se sabe ni quién escribe y no
# vino plano (gate temprano), o el correo y el dibujo juntos no completaron los
# campos obligatorios. Se le pidió al comprador lo que falta y el RFQ espera su
# respuesta.
#
# Existe por COT-76: "dar de alta TODOS los RFQ evaluados para conservar el
# histórico y entrenar a futuro un modelo de predicción". Antes estos dos casos
# devolvían sin escribir nada, así que el histórico tenía justo el agujero de
# los casos que peor salen — que son los que más enseñan. No entra en la cola
# del PM: no hay nada que dictaminar mientras falten datos.
ESTADO_INCOMPLETO = "Incomplete"


def inicializar_bd() -> None:
    """Verifica que exista la tabla ``rfqs``.

    Ya no crea nada: el esquema lo aplica ``make db-up`` (COT-93).
    """
    import app.persistence.schema as schema
    schema.verificar_tablas(("rfqs",))


def _siguiente_version(rfq_id: str, conexion=None) -> int:
    """Devuelve la siguiente versión disponible para un rfq_id (1 si es nuevo)."""
    sql = """
    SELECT version FROM rfqs
    WHERE rfq_id = %s
    ORDER BY version DESC
    LIMIT 1;
    """
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (rfq_id,))
            fila = cur.fetchone()
            return (fila[0] + 1) if fila else 1
    finally:
        if propia:
            conn.close()


def _ultima_version_id(rfq_id: str, conexion=None) -> Optional[dict]:
    """Última versión de un RFQ: id, versión, estado, datos_json y notas.

    None si el RFQ no existe.
    """
    sql = """
    SELECT id, version, estado, datos_json, notas
    FROM rfqs
    WHERE rfq_id = %s
    ORDER BY version DESC
    LIMIT 1;
    """
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (rfq_id,))
            fila = cur.fetchone()
            if not fila:
                return None
            return {
                "id": fila[0],
                "version": fila[1],
                "estado": fila[2],
                "datos_json": fila[3],
                "notas": fila[4],
            }
    finally:
        if propia:
            conn.close()


def datos_anteriores(rfq_id: str, conexion=None) -> dict:
    """Lo que ya se sabía de ese RFQ: los datos de su última versión.

    Un RFQ es una conversación, no un correo suelto: el comprador manda el
    plano el lunes y el material el martes, y en el martes no vuelve a
    adjuntar nada. Sin esto, cada respuesta se juzga como si llegara sola y el
    sistema le pide otra vez lo que ya tiene guardado.

    Devuelve ``{}`` si el RFQ no existe o si no se pudo leer: quedarse sin
    memoria es peor atención, pero no puede tumbar el proceso del correo.
    """
    try:
        ultima = _ultima_version_id(rfq_id, conexion=conexion)
    except Exception as error:
        log.warning("RFQ=%s: no se pudo leer la versión anterior (%s).",
                    rfq_id, error)
        return {}
    if not ultima:
        return {}
    return _a_dict(ultima.get("datos_json")) or {}


def guardar_rfq(
    rfq_id: str,
    datos: dict,
    es_seguimiento: bool = False,
    conexion=None,
    estado: str = ESTADO_NEW,
) -> dict:
    if not rfq_id:
        raise ValueError("guardar_rfq requiere un rfq_id no vacío.")

    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()

    try:
        version = _siguiente_version(rfq_id, conexion=conn)
        volumen = datos.get("volumen")

        sql = """
        INSERT INTO rfqs (
            rfq_id, version, cliente_id, nombre_proyecto,
            part_number, volumen, material, estado, message_id, datos_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING id, version;
        """
        valores = (
            rfq_id,
            version,
            datos.get("cliente_id"),
            datos.get("nombre_proyecto"),
            datos.get("part_number"),
            None if volumen is None else str(volumen),
            datos.get("material"),
            estado,
            datos.get("message_id"),
            json.dumps(datos, ensure_ascii=False),
        )

        with conn.cursor() as cur:
            cur.execute(sql, valores)
            fila = cur.fetchone()
            nuevo_id = fila[0]
            version_insertada = fila[1]
    finally:
        if propia:
            conn.close()

    if es_seguimiento or version_insertada > 1:
        log.info("RFQ %s: nueva versión v%s (seguimiento) en estado %s.",
                 rfq_id, version_insertada, estado)
    else:
        log.info("RFQ %s: registro nuevo v%s en estado %s.",
                 rfq_id, version_insertada, estado)

    return {
        "id": nuevo_id,
        "rfq_id": rfq_id,
        "version": version_insertada,
        "estado": estado,
        "es_seguimiento": es_seguimiento or version_insertada > 1,
    }


def guardar_veredicto(
    rfq_id: str,
    resultado: dict,
    version: Optional[int] = None,
    conexion=None,
) -> dict:
    if not rfq_id:
        raise ValueError("guardar_veredicto requiere un rfq_id no vacío.")

    veredicto = (resultado or {}).get("veredicto")
    if not veredicto:
        raise ValueError("El resultado de factibilidad no trae veredicto.")

    motivos = list((resultado or {}).get("motivos") or [])
    for motivo in motivos:
        nivel = motivo.get("nivel")
        if nivel not in NIVELES_BANDERA:
            raise ValueError(
                f"Nivel de bandera no admitido: {nivel!r}. "
                f"rfq_banderas.nivel sólo acepta {', '.join(NIVELES_BANDERA)}.")

    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()

    try:
        # 1. Encontrar el registro correcto a actualizar
        if version is not None:
            sql_get = """
            SELECT id, version, datos_json FROM rfqs
            WHERE rfq_id = %s AND version = %s;
            """
            with conn.cursor() as cur:
                cur.execute(sql_get, (rfq_id, version))
                row = cur.fetchone()
                fila = {"id": row[0], "version": row[1], "datos_json": row[2]} if row else None
        else:
            fila = _ultima_version_id(rfq_id, conexion=conn)

        if not fila:
            raise ValueError(
                f"No existe el RFQ {rfq_id} "
                f"(versión {version if version is not None else 'última'}) "
                "para marcarle el veredicto.")

        rfq_row_id = fila["id"]
        version_marcada = fila["version"]

        # Combinar datos_json.
        # Se usa _a_dict (igual que guardar_veredicto_final) en lugar de
        # json.loads a pelo: si la columna traía texto que no es JSON, el
        # json.loads reventaba con una excepción sin controlar, y si traía una
        # lista, la asignación siguiente lanzaba TypeError. Los dos caminos del
        # módulo eran inconsistentes ante el mismo dato corrupto.
        datos_actuales = _a_dict(fila.get("datos_json"))
        datos_actuales["factibilidad"] = resultado

        notas = _notas_de_motivos(motivos)
        score = resultado.get("score")

        # 2. Actualizar rfqs
        sql_update = """
        UPDATE rfqs
        SET veredicto_sistema = %s,
            notas = %s,
            datos_json = %s
            {}
        WHERE id = %s;
        """.format(", score = %s" if score is not None else "")

        params = [veredicto, notas, json.dumps(datos_actuales, ensure_ascii=False)]
        if score is not None:
            params.append(score)
        params.append(rfq_row_id)

        with conn.cursor() as cur:
            cur.execute(sql_update, params)

            # 3. Limpiar y recrear banderas
            cur.execute("DELETE FROM rfq_banderas WHERE rfq_version_id = %s;",
                        (rfq_row_id,))

            if motivos:
                # El título se guarda como siempre —es el respaldo y lo que
                # lee cualquier versión anterior—, y con él el CÓDIGO del
                # motivo y los datos con los que se armó. Con eso la pantalla
                # puede decirlo en el idioma que tenga puesto en vez de
                # enseñar la frase en español dentro de una vista en inglés.
                sql_bandera = """
                INSERT INTO rfq_banderas (rfq_version_id, nivel, titulo, codigo, datos)
                VALUES (%s, %s, %s, %s, %s);
                """
                for motivo in motivos:
                    cur.execute(sql_bandera, (
                        rfq_row_id,
                        motivo["nivel"],
                        _titulo_de_motivo(motivo),
                        motivo.get("codigo"),
                        json.dumps(_datos_de_motivo(motivo), ensure_ascii=False),
                    ))
    finally:
        if propia:
            conn.close()

    log.info("RFQ %s v%s: veredicto del sistema '%s' (score %s) con %d bandera(s).",
             rfq_id, version_marcada, veredicto, resultado.get("score"),
             len(motivos))

    return {
        "id": rfq_row_id,
        "rfq_id": rfq_id,
        "version": version_marcada,
        "veredicto": veredicto,
        "score": resultado.get("score"),
        "banderas": len(motivos),
    }


def guardar_veredicto_final(
    rfq_id: str,
    veredicto: str,
    version: Optional[int] = None,
    nota: Optional[str] = None,
    estado: Optional[str] = None,
    conexion=None,
) -> dict:
    if not rfq_id:
        raise ValueError("guardar_veredicto_final requiere un rfq_id no vacío.")
    if not veredicto:
        raise ValueError("guardar_veredicto_final requiere un veredicto.")

    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()

    try:
        if version is not None:
            sql_get = """
            SELECT id, version, estado, notas, datos_json FROM rfqs
            WHERE rfq_id = %s AND version = %s;
            """
            with conn.cursor() as cur:
                cur.execute(sql_get, (rfq_id, version))
                row = cur.fetchone()
                fila = {"id": row[0], "version": row[1], "estado": row[2],
                        "notas": row[3], "datos_json": row[4]} if row else None
        else:
            fila = _ultima_version_id(rfq_id, conexion=conn)

        if not fila:
            raise ValueError(
                f"No existe el RFQ {rfq_id} "
                f"(versión {version if version is not None else 'última'}) "
                "para registrar el veredicto final.")

        rfq_row_id = fila["id"]
        version_marcada = fila["version"]

        # Sin nota nueva se conserva el valor tal cual (NULL incluido): antes
        # `or ""` convertía un NULL en cadena vacía y el UPDATE escribía ese
        # cambio en la base aunque nadie hubiera añadido ninguna nota.
        notas_actuales = fila.get("notas")
        if nota:
            notas_actuales = f"{notas_actuales}\n{nota}" if notas_actuales else nota

        estado_final = estado if estado is not None else fila.get("estado")
        datos = fila.get("datos_json")

        sql_update = """
        UPDATE rfqs
        SET veredicto_final = %s, estado = %s, notas = %s
        WHERE id = %s;
        """
        with conn.cursor() as cur:
            cur.execute(sql_update, (veredicto, estado_final, notas_actuales,
                                     rfq_row_id))
    finally:
        if propia:
            conn.close()

    log.info("RFQ %s v%s: el PM resolvió '%s' (estado %s).",
             rfq_id, version_marcada, veredicto, estado_final)

    return {
        "id": rfq_row_id,
        "rfq_id": rfq_id,
        "version": version_marcada,
        "veredicto_final": veredicto,
        "estado": estado_final,
        "datos": datos if isinstance(datos, dict) else _a_dict(datos),
    }


def deshacer_aprobacion(rfq_id: str, nota: str, conexion=None) -> dict:
    """Devuelve a revisión un RFQ aprobado sin querer, si su oferta no salió.

    Aprobar no manda nada al cliente; la oferta sale después, con «Enviar
    oferta». Mientras no haya salido (ni esté en la bandeja de salida) una
    aprobación se puede deshacer sin que el cliente note nada: el RFQ vuelve
    a ``RequiresReview``, sin veredicto final, y la nota deja constancia.

    Lanza ``ValueError`` si no existe, si no está aprobado o si la oferta ya
    salió (o está en cola): eso ya no se deshace desde aquí.
    """
    if not rfq_id or not nota:
        raise ValueError("deshacer_aprobacion requiere rfq_id y nota.")
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        fila = _ultima_version_id(rfq_id, conexion=conn)
        if not fila:
            raise ValueError(f"No existe el RFQ {rfq_id}.")
        if fila.get("estado") != ESTADO_APROBADO:
            raise ValueError(f"El RFQ {rfq_id} no está aprobado.")
        oferta = _a_dict(fila.get("datos_json")).get("oferta") or {}
        if oferta.get("enviada") or oferta.get("encolada"):
            raise ValueError(f"La oferta de {rfq_id} ya salió (o está en la bandeja "
                             "de salida): la aprobación ya no se puede deshacer.")
        notas = fila.get("notas")
        notas = f"{notas}\n{nota}" if notas else nota
        with conn.cursor() as cur:
            cur.execute("UPDATE rfqs SET estado = %s, veredicto_final = NULL, notas = %s "
                        "WHERE id = %s;", (ESTADO_REVISION, notas, fila["id"]))
        log.info("RFQ %s v%s: aprobación deshecha; vuelve a revisión.", rfq_id, fila["version"])
        return {"id": fila["id"], "rfq_id": rfq_id, "version": fila["version"],
                "estado": ESTADO_REVISION, "notas": notas}
    finally:
        if propia:
            conn.close()


def _a_dict(datos_json) -> dict:
    if not datos_json:
        return {}
    if isinstance(datos_json, dict):
        return datos_json
    try:
        cargado = json.loads(datos_json)
    except (TypeError, ValueError):
        return {}
    return cargado if isinstance(cargado, dict) else {}


def _datos_de_motivo(motivo: dict) -> dict:
    """Los datos con los que se armó el motivo, para rearmarlo en otro idioma.

    Sólo lo que hace falta para escribir la frase: el campo, el valor y el
    límite. La nota larga y la penalización no se pintan, así que no viajan.
    """
    return {clave: motivo.get(clave)
            for clave in ("campo", "valor", "limite", "unidad")
            if motivo.get(clave) is not None}


def _titulo_de_motivo(motivo: dict) -> str:
    return (motivo.get("texto") or motivo.get("codigo") or "sin detalle").strip()


def _notas_de_motivos(motivos) -> Optional[str]:
    if not motivos:
        return None
    return "\n".join(
        f"[{motivo.get('nivel')}] {_titulo_de_motivo(motivo)}" for motivo in motivos)


if __name__ == "__main__":
    inicializar_bd()
    print("Tabla 'rfqs' lista.")


def agregar_nota(rfq_id: str, nota: str, estado: Optional[str] = None,
                 conexion=None) -> dict:
    """Añade una nota a la última versión del RFQ sin tocar el veredicto.

    Es lo que hace "devolver" (send back): el PM no dictamina, pide que se
    corrija algo. La nota se acumula debajo de las que hubiera —cada
    devolución deja rastro— y el estado sólo cambia si se pide.
    """
    if not rfq_id or not nota:
        raise ValueError("agregar_nota requiere rfq_id y nota.")
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        fila = _ultima_version_id(rfq_id, conexion=conn)
        if not fila:
            raise ValueError(f"No existe el RFQ {rfq_id} para anotarlo.")
        notas = fila.get("notas")
        notas = f"{notas}\n{nota}" if notas else nota
        with conn.cursor() as cur:
            if estado:
                cur.execute("UPDATE rfqs SET notas = %s, estado = %s WHERE id = %s;",
                            (notas, estado, fila["id"]))
            else:
                cur.execute("UPDATE rfqs SET notas = %s WHERE id = %s;",
                            (notas, fila["id"]))
        return {"id": fila["id"], "rfq_id": rfq_id, "version": fila["version"],
                "estado": estado or fila.get("estado"), "notas": notas}
    finally:
        if propia:
            conn.close()


def anotar_datos(rfq_id: str, cambios: dict, conexion=None) -> dict:
    """Escribe claves sueltas en ``datos_json`` de la última versión del RFQ.

    ``cambios`` es clave → valor; ``None`` quita la clave. Lo usan las
    versiones de la cotización del PM (``app/rfq/versiones_pm.py``), que
    tocan varias claves a la vez y tienen que quedar juntas.
    """
    if not rfq_id:
        raise ValueError("anotar_datos requiere rfq_id.")
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        fila = _ultima_version_id(rfq_id, conexion=conn)
        if not fila:
            raise ValueError(f"No existe el RFQ {rfq_id}.")
        datos = _a_dict(fila.get("datos_json"))
        for clave, valor in (cambios or {}).items():
            if valor is None:
                datos.pop(clave, None)
            else:
                datos[clave] = valor
        with conn.cursor() as cur:
            cur.execute("UPDATE rfqs SET datos_json = %s WHERE id = %s;",
                        (json.dumps(datos, ensure_ascii=False, default=str), fila["id"]))
        return {"id": fila["id"], "rfq_id": rfq_id, "version": fila["version"],
                "datos": datos}
    finally:
        if propia:
            conn.close()


def anotar_cotizacion_pm(rfq_id: str, cotizacion: Optional[dict],
                         conexion=None) -> dict:
    """Guarda (o borra, con ``None``) la cotización que el PM dejó en la calculadora.

    ``datos_json.cotizacion_pm`` lleva el PN tal como quedó en la hoja, el
    resultado del motor con el que el PM lo vio (tramos y banderas), su
    contribución objetivo, la cabecera de la cotización y quién y cuándo. La
    ventana de revisión y la oferta costean CON ESTO cuando existe: lo que el
    PM corrigió en la calculadora es lo que se aprueba y lo que sale al
    cliente, no el costeo que el sistema hizo al entrar el correo.
    """
    if not rfq_id:
        raise ValueError("anotar_cotizacion_pm requiere rfq_id.")
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        fila = _ultima_version_id(rfq_id, conexion=conn)
        if not fila:
            raise ValueError(f"No existe el RFQ {rfq_id}.")
        datos = _a_dict(fila.get("datos_json"))
        if cotizacion is None:
            datos.pop("cotizacion_pm", None)
        else:
            datos["cotizacion_pm"] = cotizacion
        with conn.cursor() as cur:
            cur.execute("UPDATE rfqs SET datos_json = %s WHERE id = %s;",
                        (json.dumps(datos, ensure_ascii=False, default=str), fila["id"]))
        return {"id": fila["id"], "rfq_id": rfq_id, "version": fila["version"],
                "datos": datos}
    finally:
        if propia:
            conn.close()


def anotar_oferta(rfq_id: str, oferta: dict, nota: Optional[str] = None,
                  conexion=None) -> dict:
    """Deja constancia de la oferta al cliente en la última versión del RFQ.

    ``datos_json.oferta`` guarda qué salió y cuándo —archivo, destinatario,
    si de verdad se envió, quién lo mandó— y la nota va debajo de las demás.
    El estado no cambia: la oferta es la respuesta a un RFQ ya aprobado, y
    ``Approved`` sigue diciendo la verdad.
    """
    if not rfq_id or not isinstance(oferta, dict):
        raise ValueError("anotar_oferta requiere rfq_id y el dict de la oferta.")
    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        fila = _ultima_version_id(rfq_id, conexion=conn)
        if not fila:
            raise ValueError(f"No existe el RFQ {rfq_id} para anotar la oferta.")
        datos = _a_dict(fila.get("datos_json"))
        datos["oferta"] = oferta
        notas = fila.get("notas")
        if nota:
            notas = f"{notas}\n{nota}" if notas else nota
        with conn.cursor() as cur:
            cur.execute("UPDATE rfqs SET datos_json = %s, notas = %s WHERE id = %s;",
                        (json.dumps(datos, ensure_ascii=False, default=str), notas, fila["id"]))
        return {"id": fila["id"], "rfq_id": rfq_id, "version": fila["version"],
                "estado": fila.get("estado"), "datos": datos, "notas": notas}
    finally:
        if propia:
            conn.close()
