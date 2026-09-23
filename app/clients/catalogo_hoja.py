# -*- coding: utf-8 -*-
"""El catálogo de clientes de la hoja, servido desde la tabla de Pohua.

El problema
-----------
Había DOS catálogos de clientes y ninguno de los dos lo sabía.

Uno es la tabla ``clientes``: los datos maestros: razón social, términos de
pago, RFC, estado fiscal. Ahí entra un cliente cuando se registra su dominio,
y es contra ella contra la que Pohua resuelve el remitente de cada correo.

El otro vivía DENTRO del documento de la calculadora —``dbs.customers``, un
``{code, name, terms}`` por cliente— dentro del blob JSON de
``cotizador_estado``. Se llenaba a mano, o copiando desde el primero cuando
alguien abría un RFQ y el cliente no estaba.

El resultado era el que se ve en pantalla: un cliente que Pohua conoce
perfectamente aparece sin resolver en la hoja, con la casilla "Customer"
vacía, y sin cliente una cotización no se puede ni numerar ni aprobar. Había
que teclear a mano un nombre que el sistema ya tenía guardado.

Dos copias de lo mismo divergen SIEMPRE. No es cuestión de disciplina: la
segunda copia sólo se actualiza cuando alguien pasa por el sitio exacto que la
actualiza.

La solución
-----------
La tabla manda. ``dbs.customers`` deja de ser un catálogo y pasa a ser una
PROYECCIÓN suya, armada al servir el documento. Para la calculadora no cambia
nada —recibe la misma lista con la misma forma— pero la lista ya no se queda
vieja, porque no se guarda en ningún sitio: se calcula cada vez.

Y al revés: un cliente dado de alta dentro de la hoja sube a ``clientes``, que
es donde va a hacer falta la próxima vez que llegue un correo suyo.

Lo que NO se hace
-----------------
No se borra la copia del blob. Se ignora al leer —la proyección la pisa— pero
se sigue guardando tal cual. Es redundante y da igual: pesa poco, y significa
que el día que esto falle la hoja sigue teniendo su lista de siempre en vez de
quedarse sin clientes. Un catálogo vacío para todo el mundo es mucho peor que
uno un poco viejo.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger("cotizador.catalogo_hoja")

# Lo que la hoja espera en cada cliente. Es lo que consume `fillCustomers()`
# del núcleo, así que estos tres nombres no se tocan sin tocar la calculadora.
CLAVES = ("code", "name", "terms")

TERMINOS_POR_DEFECTO = "Net 30"


def _codigo(cliente_id: Any, razon_social: Any) -> str:
    """El código corto con el que la hoja nombra al cliente.

    Se prefiere el ``cliente_id`` de Pohua: ya es corto, ya es único y ya es
    el que aparece en el RFQ, así que los dos sistemas dicen lo mismo. Sólo si
    faltara se apaña uno con las primeras letras de la razón social.
    """
    corto = str(cliente_id or "").strip()
    if corto:
        return corto[:20]
    limpio = re.sub(r"[^A-Za-z0-9]+", "", str(razon_social or "")).upper()
    return limpio[:8] or "CLIENTE"


def proyectar(conexion) -> Optional[List[Dict[str, str]]]:
    """La lista de clientes tal y como la quiere la hoja, desde ``clientes``.

    Devuelve ``None`` —y no una lista vacía— cuando no se puede leer la tabla.
    La diferencia importa: vacío significaría "no hay clientes" y dejaría la
    hoja sin catálogo; ``None`` significa "no se pudo saber" y quien llama se
    queda con lo que hubiera en el documento.
    """
    try:
        with conexion.cursor() as cur:
            cur.execute("""
                SELECT cliente_id, razon_social, payment_terms
                  FROM clientes
                 WHERE estatus = 'Activo'
                 ORDER BY cliente_id
            """)
            filas = cur.fetchall()
    except Exception as error:
        log.warning("No se pudo leer el catálogo de clientes: %s", error)
        return None

    lista = []
    vistos = set()
    for cliente_id, razon_social, terminos in filas:
        codigo = _codigo(cliente_id, razon_social)
        if codigo in vistos:          # dos clientes no pueden compartir código
            continue
        vistos.add(codigo)
        lista.append({
            "code": codigo,
            "name": str(razon_social or codigo)[:80],
            "terms": str(terminos or TERMINOS_POR_DEFECTO),
        })
    return lista


def aplicar(documento: Dict[str, Any], conexion) -> bool:
    """Pisa ``dbs.customers`` del documento con la proyección. Devuelve si pudo.

    Nunca lanza: servir el documento es más importante que servirlo con el
    catálogo al día.
    """
    if not isinstance(documento, dict):
        return False
    try:
        lista = proyectar(conexion)
        if lista is None:
            return False
        dbs = documento.get("dbs")
        if not isinstance(dbs, dict):
            dbs = {}
            documento["dbs"] = dbs
        # Si la tabla está vacía —el primer día— se deja lo que hubiera: mejor
        # el catálogo viejo de la hoja que ninguno.
        if not lista and dbs.get("customers"):
            return False
        dbs["customers"] = lista
        return True
    except Exception as error:
        log.warning("No se pudo aplicar el catálogo de clientes: %s", error)
        return False


def recoger(documento: Dict[str, Any], conexion) -> int:
    """Sube a ``clientes`` los que sólo existan dentro de la hoja.

    Alguien puede dar de alta un cliente en la calculadora —tiene su pantalla
    para ello— y ese cliente tiene que acabar en la tabla: es donde se va a
    buscar cuando llegue su primer correo. Si se quedara sólo en el blob,
    volveríamos a tener dos catálogos, esta vez al revés.

    Devuelve cuántos se dieron de alta. Nunca lanza: perder un alta es malo,
    perder el guardado entero de la calculadora es peor.
    """
    try:
        dbs = documento.get("dbs") if isinstance(documento, dict) else None
        lista = (dbs or {}).get("customers")
        if not isinstance(lista, list) or not lista:
            return 0

        with conexion.cursor() as cur:
            cur.execute("SELECT cliente_id FROM clientes")
            conocidos = {str(f[0]).strip() for f in cur.fetchall()}

            nuevos = 0
            for c in lista:
                if not isinstance(c, dict):
                    continue
                codigo = str(c.get("code") or "").strip()
                nombre = str(c.get("name") or "").strip()
                if not codigo or codigo in conocidos:
                    continue
                cur.execute("""
                    INSERT INTO clientes
                        (cliente_id, razon_social, payment_terms, origen_datos)
                    VALUES (%s, %s, %s, 'calculadora')
                    ON CONFLICT (cliente_id) DO NOTHING
                """, (codigo[:20], (nombre or codigo)[:200],
                      str(c.get("terms") or TERMINOS_POR_DEFECTO)))
                conocidos.add(codigo)
                nuevos += 1

        if nuevos:
            log.info("Catálogo: %d cliente(s) dados de alta desde la hoja.", nuevos)
        return nuevos
    except Exception as error:
        log.warning("No se pudieron recoger los clientes de la hoja: %s", error)
        return 0
