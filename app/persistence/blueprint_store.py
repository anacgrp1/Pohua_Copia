"""COT-56 [Flujo - Almacenamiento] Persistencia de planos en almacenamiento.

Propósito
---------
Guarda los planos (adjuntos del RFQ) en el almacenamiento físico según el
modo del sistema:

* ``<Local>`` → **disco local**.
* ``<Token>`` → **Azure Blob Storage**.

Sólo debe llamarse cuando la validación fue correcta (criterio OK): los
planos se persisten únicamente si el RFQ es válido.

Alcance
-------
* **Sí hace:** escribir los bytes de cada adjunto en disco o subirlos a Blob.
* **NO hace:** insertar el registro del RFQ (eso es ``repositorio_rfq``), ni
  decidir si el RFQ es válido (COT-54).

Función pública
---------------
``guardar_planos(rfq_id, adjuntos, modo=None, ...) -> list[str]``

``adjuntos`` es una lista de dicts ``{"nombre": str, "contenido": bytes}``
(el mismo formato que produce el proveedor de correo). Devuelve la lista de
ubicaciones donde quedó cada plano (rutas de disco o nombres de blob).
"""

from __future__ import annotations

import logging
import os
import re
from typing import List, Optional

log = logging.getLogger("cotizador.almacen_planos")

# "outlook" es el lector de escritorio: guarda en el disco de esa computadora,
# como "imap". Sin él, cada RFQ leído por Outlook dejaba un ERROR en el registro.
_MODOS_LOCAL = ("local", "imap", "dev", "outlook")
_MODOS_TOKEN = ("token", "graph", "prod")


class AlmacenPlanosError(Exception):
    """Error al persistir los planos."""


def _slug(texto: str) -> str:
    """Sanea un identificador para usarlo como carpeta/prefijo seguro."""
    limpio = re.sub(r"[^A-Za-z0-9._-]+", "_", str(texto or "sin_rfq"))
    return limpio.strip("_") or "sin_rfq"


def _modo_por_defecto() -> str:
    """Determina el modo desde la configuración (MAIL_MODE / AUTH_METHOD)."""
    import app.core.config as config
    modo = getattr(config, "MAIL_MODE", None) or getattr(config, "AUTH_METHOD", None) or "imap"
    return str(modo).lower()


# Lo que puede ser un plano y lo que no.
_EXT_PLANO = (".pdf", ".png", ".jpg", ".jpeg", ".stp", ".step")

# Una imagen más pequeña que esto no es un dibujo de ingeniería: es un logo.
# Los PDF no pasan por aquí —uno de una página pesa lo que pesa— y los planos
# de verdad, escaneados o exportados, no bajan de este tamaño.
_MINIMO_IMAGEN = 20 * 1024


def es_plano(adjunto: dict) -> bool:
    """¿Este adjunto es un plano, o es la firma del correo?

    Un correo de trabajo trae la firma con su logo como un adjunto más, y por
    nombre y extensión (image.png) es indistinguible de un dibujo. Colarla
    costaba caro: se guardaba como plano del RFQ, se le pasaba al modelo para
    que la leyera, y al abrir la cotización completa aparecía en la casilla
    del lector junto al plano de verdad —y al pulsar "AI Read Drawing", la
    calculadora abría un SEGUNDO número de parte con el logo dentro—.

    Se descarta por dos señales, en este orden:

    1. Va incrustada en el cuerpo (tiene Content-ID). Es la señal buena: el
       HTML la pinta con <img src="cid:...">, o sea que es parte de la firma,
       no un archivo que alguien adjuntó.
    2. Es una imagen diminuta. Respaldo para cuando el proveedor de correo no
       marca lo incrustado.
    """
    if adjunto.get("en_linea"):
        return False
    nombre = str(adjunto.get("nombre") or "").lower()
    ext = os.path.splitext(nombre)[1]
    if ext not in _EXT_PLANO:
        return False
    if ext in (".png", ".jpg", ".jpeg"):
        contenido = adjunto.get("contenido") or b""
        if len(contenido) < _MINIMO_IMAGEN:
            return False
    return True


def solo_planos(adjuntos) -> list:
    """Los adjuntos que sí son planos, en el mismo orden."""
    return [a for a in (adjuntos or []) if es_plano(a)]


def guardar_planos(
    rfq_id: str,
    adjuntos: Optional[list],
    modo: Optional[str] = None,
    *,
    base_dir: Optional[str] = None,
    cliente_blob=None,
) -> List[str]:
    """Persiste los planos según el modo (<Local> disco / <Token> Blob).

    Args:
        rfq_id: identificador del RFQ (agrupa los planos).
        adjuntos: lista de dicts ``{"nombre", "contenido"(bytes)}``.
        modo: ``"local"``/``"imap"`` o ``"token"``/``"graph"``. Si es None se
            toma de la configuración.
        base_dir: carpeta raíz para disco (sólo modo local). Inyección para
            pruebas; por defecto ``config.PLANOS_DIR`` o ``"planos"``.
        cliente_blob: contenedor de Blob ya creado (inyección para pruebas).

    Returns:
        Lista de ubicaciones (rutas de disco o nombres de blob). Vacía si no
        hay adjuntos.
    """
    # La firma del correo no es un plano: se queda fuera del almacén y, por
    # tanto, fuera de la casilla del lector cuando se abra la cotización.
    descartados = len(adjuntos or []) - len(solo_planos(adjuntos))
    adjuntos = solo_planos(adjuntos)
    if descartados:
        log.info("RFQ %s: %d adjunto(s) no son planos (firma o imagen "
                 "incrustada); no se guardan.", rfq_id, descartados)
    if not adjuntos:
        log.info("RFQ %s sin planos que persistir.", rfq_id)
        return []

    # Además del disco, a la base. El disco es de quien leyó el correo: si lo
    # leyó el lector de escritorio, el plano se queda en ESA computadora y la
    # web no lo tiene; si lo leyó el servidor, se borra en el siguiente
    # despliegue. En la base lo ve todo el mundo y dura lo que dure el RFQ,
    # que es lo que hace falta para abrir la cotización con el dibujo puesto.
    #
    # Va aparte y no puede tumbar el guardado de siempre: si la base no está,
    # el plano sigue yendo a disco como hasta ahora.
    guardar_en_base(rfq_id, adjuntos)

    modo = (modo or _modo_por_defecto()).lower()

    if modo in _MODOS_LOCAL:
        return _guardar_en_disco(rfq_id, adjuntos, base_dir)
    if modo in _MODOS_TOKEN:
        return _guardar_en_blob(rfq_id, adjuntos, cliente_blob)

    raise AlmacenPlanosError(f"Modo de almacenamiento desconocido: {modo!r}")


# --------------------------------------------------------------------------- #
# La base: el único sitio que ven los dos lados
# --------------------------------------------------------------------------- #

# Tope por fichero. Un plano de ingeniería son cientos de KB; por encima de
# esto casi siempre es un PDF con fotos dentro, y no compensa moverlo por la
# base cada vez. Ése se queda en disco y se sube a mano.
_MAX_BYTES = 8 * 1024 * 1024

_TIPOS = {".pdf": "application/pdf", ".png": "image/png",
          ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


def guardar_en_base(rfq_id: str, adjuntos: list) -> int:
    """Guarda (o sustituye) los planos de este RFQ en la base. Nunca lanza."""
    guardados = 0
    try:
        import app.persistence.duplicates as duplicates
        with duplicates.conexion_bd() as conexion:
            with conexion.cursor() as cur:
                for adjunto in (adjuntos or []):
                    contenido = adjunto.get("contenido") or b""
                    nombre = os.path.basename(adjunto.get("nombre") or "adjunto")
                    if not contenido or len(contenido) > _MAX_BYTES:
                        if contenido:
                            log.info("RFQ %s: %s pesa %d bytes y no va a la base.",
                                     rfq_id, nombre, len(contenido))
                        continue
                    ext = os.path.splitext(nombre)[1].lower()
                    cur.execute(
                        """
                        INSERT INTO rfq_planos (rfq_id, nombre, tipo, bytes, contenido)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (rfq_id, nombre) DO UPDATE
                           SET contenido = EXCLUDED.contenido,
                               bytes = EXCLUDED.bytes,
                               tipo = EXCLUDED.tipo,
                               guardado_en = NOW();
                        """,
                        (rfq_id, nombre, _TIPOS.get(ext, "application/octet-stream"),
                         len(contenido), memoryview(contenido)),
                    )
                    guardados += 1
        if guardados:
            log.info("RFQ %s: %d plano(s) guardado(s) en la base.", rfq_id, guardados)
    except Exception as error:
        log.warning("RFQ %s: no se pudieron guardar los planos en la base: %s",
                    rfq_id, error)
    return guardados


def listar_de_base(rfq_id: str) -> list:
    """Los planos de este RFQ que hay en la base: nombre, tipo y tamaño."""
    try:
        import app.persistence.duplicates as duplicates
        with duplicates.conexion_bd() as conexion:
            with conexion.cursor() as cur:
                cur.execute(
                    "SELECT nombre, tipo, bytes FROM rfq_planos "
                    "WHERE rfq_id = %s ORDER BY nombre;", (rfq_id,))
                return [{"nombre": n, "tipo": t, "bytes": int(b or 0)}
                        for n, t, b in cur.fetchall()]
    except Exception as error:
        log.warning("RFQ %s: no se pudieron listar los planos de la base: %s",
                    rfq_id, error)
        return []


def carpeta_de(rfq_id: str):
    """La carpeta de disco donde quedaron los planos de este RFQ, si existe.

    Vive aquí y no en la ruta de la API porque ya son tres los sitios que la
    necesitan —listar, descargar y releer el plano— y el saneado del nombre
    no puede tener tres copias: un ``rfq_id`` con ``..`` dentro apuntaría
    fuera de la carpeta base.
    """
    from pathlib import Path
    import app.core.config as config

    base = getattr(config.settings, "PLANOS_DIR", None) or "planos"
    carpeta = (Path(base) / _slug(rfq_id)).resolve()
    raiz = Path(base).resolve()
    if raiz not in carpeta.parents and carpeta != raiz:
        return None
    return carpeta if carpeta.is_dir() else None


def leer_plano(rfq_id: str, nombre: str):
    """Los bytes de un plano, venga de la base o del disco.

    La base manda: es lo único que ven a la vez el lector de escritorio y el
    servidor. El disco es el respaldo para lo que se guardó antes de que
    existiera ``rfq_planos``.
    """
    de_base = leer_de_base(rfq_id, nombre)
    if de_base:
        return de_base

    carpeta = carpeta_de(rfq_id)
    if carpeta is None:
        return None
    ruta = carpeta / os.path.basename(nombre or "")
    if not ruta.is_file():
        return None
    try:
        return ruta.read_bytes(), "application/octet-stream"
    except OSError as error:
        log.warning("RFQ %s: no se pudo leer el plano %s del disco: %s",
                    rfq_id, nombre, error)
        return None


def leer_de_base(rfq_id: str, nombre: str):
    """Un plano concreto: ``(bytes, tipo)``, o ``None`` si no está."""
    try:
        import app.persistence.duplicates as duplicates
        with duplicates.conexion_bd() as conexion:
            with conexion.cursor() as cur:
                cur.execute(
                    "SELECT contenido, tipo FROM rfq_planos "
                    "WHERE rfq_id = %s AND nombre = %s;",
                    (rfq_id, os.path.basename(nombre or "")))
                fila = cur.fetchone()
        if not fila:
            return None
        return bytes(fila[0]), (fila[1] or "application/octet-stream")
    except Exception as error:
        log.warning("RFQ %s: no se pudo leer el plano %s de la base: %s",
                    rfq_id, nombre, error)
        return None


# --------------------------------------------------------------------------- #
# <Local> — disco
# --------------------------------------------------------------------------- #

def _guardar_en_disco(rfq_id: str, adjuntos: list, base_dir: Optional[str]) -> List[str]:
    """Escribe cada adjunto en ``base_dir/<rfq_id>/<nombre>``."""
    if base_dir is None:
        import app.core.config as config
        base_dir = getattr(config, "PLANOS_DIR", None) or "planos"

    destino = os.path.join(base_dir, _slug(rfq_id))
    os.makedirs(destino, exist_ok=True)

    rutas: List[str] = []
    for adjunto in adjuntos:
        nombre = os.path.basename(adjunto.get("nombre") or "adjunto")
        contenido = adjunto.get("contenido") or b""
        ruta = os.path.join(destino, nombre)
        with open(ruta, "wb") as fh:
            fh.write(contenido)
        rutas.append(ruta)

    log.info("RFQ %s: %d plano(s) guardado(s) en disco (%s).",
             rfq_id, len(rutas), destino)
    return rutas


# --------------------------------------------------------------------------- #
# <Token> — Azure Blob Storage
# --------------------------------------------------------------------------- #

def _crear_contenedor_blob():
    """Crea el container client de Azure Blob desde la configuración.

    Import perezoso del SDK: sólo se exige ``azure-storage-blob`` cuando de
    verdad se usa el modo <Token>.
    """
    import app.core.config as config
    conn_str = getattr(config, "BLOB_CONNECTION_STRING", None)
    contenedor = getattr(config, "BLOB_CONTAINER", None) or "planos"
    if not conn_str:
        raise AlmacenPlanosError(
            "Falta BLOB_CONNECTION_STRING para el modo <Token>."
        )
    try:
        from azure.storage.blob import BlobServiceClient
    except ImportError as error:
        raise AlmacenPlanosError(
            "El paquete 'azure-storage-blob' no está instalado "
            "(pip install azure-storage-blob)."
        ) from error
    servicio = BlobServiceClient.from_connection_string(conn_str)
    return servicio.get_container_client(contenedor)


def _guardar_en_blob(rfq_id: str, adjuntos: list, cliente_blob) -> List[str]:
    """Sube cada adjunto a Blob bajo el prefijo ``<rfq_id>/<nombre>``."""
    contenedor = cliente_blob or _crear_contenedor_blob()

    nombres: List[str] = []
    for adjunto in adjuntos:
        nombre = os.path.basename(adjunto.get("nombre") or "adjunto")
        contenido = adjunto.get("contenido") or b""
        blob_name = f"{_slug(rfq_id)}/{nombre}"
        contenedor.upload_blob(name=blob_name, data=contenido, overwrite=True)
        nombres.append(blob_name)

    log.info("RFQ %s: %d plano(s) subido(s) a Blob.", rfq_id, len(nombres))
    return nombres
