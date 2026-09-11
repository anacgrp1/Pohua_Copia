"""COT-55 [Lógica] Mapeo de cliente existente por dominio del remitente.

Propósito
---------
Dado el remitente de un correo entrante, busca en la base de datos si su
**dominio** corresponde a un cliente ya registrado y, de ser así, devuelve
sus **datos maestros** (incluido el ID de cliente) para asociar el nuevo RFQ
a ese cliente. Si el dominio no existe en la BD, devuelve ``None`` (cliente
no encontrado / potencialmente nuevo).

Según la tarjeta "Check basic data", el **Customer** se obtiene del *dominio
del correo o la firma*. Este módulo cubre la vía del **dominio**.

Modelo de datos (DER COT-86/87)
-------------------------------
Un cliente puede tener varios dominios (filiales, marcas). Se modela con dos
tablas:

* ``clientes``          — una fila por cliente (datos maestros).
* ``cliente_dominios``  — una fila por (cliente, dominio); FK a ``clientes``.

La búsqueda por dominio hace un JOIN directo vía psycopg2.

Alcance
-------
* **Sí hace:** extraer el dominio del remitente y consultarlo.
* **NO hace:** crear el RFQ ni versiones (COT-56), extraer datos comerciales
  del cuerpo (COT-61), ni dar de alta clientes nuevos.

Funciones públicas
------------------
* ``extraer_dominio(remitente) -> str | None``
* ``buscar_cliente_por_dominio(dominio, conexion=None) -> dict | None``
* ``mapear_cliente(remitente, conexion=None) -> dict | None``
"""

from __future__ import annotations

import logging
from email.utils import parseaddr
from typing import Optional

import app.persistence.duplicates as duplicates

log = logging.getLogger("cotizador.mapeo_cliente")


def inicializar_bd() -> None:
    """Verifica que existan ``clientes`` y ``cliente_dominios``.

    Modelo del DER (COT-86/87): una fila por cliente en ``clientes`` y una
    fila por (cliente, dominio) en ``cliente_dominios`` (multi-dominio).
    Ya no crea nada: el esquema lo aplica ``make db-up`` (COT-93).
    """
    import app.persistence.schema as schema
    schema.verificar_tablas(("clientes", "cliente_dominios"))


def extraer_dominio(remitente: Optional[str]) -> Optional[str]:
    """Extrae el dominio (en minúsculas) del remitente de un correo.

    Acepta tanto ``"Nombre <user@dominio.com>"`` como ``"user@dominio.com"``.
    Devuelve ``None`` si no se puede determinar un dominio válido.
    """
    if not remitente:
        return None

    # parseaddr separa el nombre de la dirección: ("Nombre", "user@dominio.com")
    direccion = parseaddr(remitente)[1] or remitente
    if "@" not in direccion:
        return None

    dominio = direccion.rsplit("@", 1)[1].strip().lower()
    # Un dominio válido tiene al menos un punto (evita "user@localhost" suelto).
    if not dominio or "." not in dominio:
        return None
    return dominio


def buscar_cliente_por_dominio(
    dominio: Optional[str], conexion=None
) -> Optional[dict]:
    """Busca el cliente dueño de un dominio con un JOIN directo.

    Args:
        dominio: dominio a buscar (p. ej. ``"neogen.com"``).
        conexion: conexión psycopg2 abierta (opcional, para reutilizar).

    Returns:
        dict con los datos maestros del cliente, o ``None`` si no existe.
    """
    if not dominio:
        return None

    sql = """
    SELECT cd.dominio,
           c.cliente_id, c.razon_social, c.rfc,
           c.correo_principal, c.payment_terms, c.estatus
    FROM cliente_dominios cd
    JOIN clientes c ON c.cliente_id = cd.cliente_id
    WHERE LOWER(cd.dominio) = LOWER(%s)
    LIMIT 1;
    """

    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, (dominio.lower(),))
            fila = cur.fetchone()
    finally:
        if propia:
            conn.close()

    if not fila:
        log.info("Dominio %r sin cliente asociado.", dominio)
        return None

    cliente = {
        "cliente_id": fila[1],
        "razon_social": fila[2],
        "dominio": fila[0],
        "rfc": fila[3],
        "correo_principal": fila[4],
        "payment_terms": fila[5],
        "estatus": fila[6],
    }

    log.info("Dominio %r mapeado a cliente %s.", dominio, cliente.get("cliente_id"))
    return cliente


def mapear_cliente(remitente: Optional[str], conexion=None) -> Optional[dict]:
    """Mapea el remitente de un correo a un cliente existente por su dominio.

    Combina ``extraer_dominio`` + ``buscar_cliente_por_dominio``.

    Returns:
        dict con datos maestros del cliente, o ``None`` si el remitente no
        tiene dominio válido o el dominio no corresponde a un cliente.
    """
    dominio = extraer_dominio(remitente)
    if not dominio:
        log.info("Remitente %r sin dominio válido; no se puede mapear.", remitente)
        return None
    return buscar_cliente_por_dominio(dominio, conexion=conexion)


if __name__ == "__main__":
    inicializar_bd()
    print("Tablas 'clientes' y 'cliente_dominios' listas.")
