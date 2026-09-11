"""Validación de presencia de campos del RFQ en memoria.

Propósito
---------
Este módulo es **una estructura condicional** que verifica si un diccionario
con datos de un RFQ trae presentes los campos mínimos obligatorios para
poder continuar con el pipeline de cotización. Es un chequeo puramente
sintáctico de presencia, no una validación semántica.

Alcance
-------
* **Sí hace:** revisa que ciertas claves existan en el dict y tengan un
  valor no vacío (no ``None``, no cadena vacía).
* **NO hace:** extraer datos del correo, parsear el cuerpo HTML, leer
  adjuntos, enviar correos de notificación al cliente, inferir valores
  faltantes, ni interpretar el contenido de los campos.

Datos básicos para cotizar (tarjeta "Check basic data")
-------------------------------------------------------
Los campos obligatorios y su ORIGEN (de dónde los toma el pipeline):

    Campo (clave)     Etiqueta oficial   Origen
    ----------------  -----------------  -----------------------------------
    tiene_adjunto     Drawing            Adjunto (PDF/PNG/...)
    customer          Customer           Dominio del correo o firma
    part_number       Part number        Cuerpo del correo *o* dibujo
    volumen           Volume / EAU       Cuerpo del correo
    material          Material spec      Cuerpo del correo *o* dibujo

Este módulo valida sólo PRESENCIA; no le importa de qué fuente vino el
valor. El flujo (COT-36) es responsable de **fusionar** los datos del correo
(COT-61) y del dibujo (visión) ANTES de validar los campos multi-fuente
(``part_number``, ``material``). Por eso ``validar_campos_rfq`` acepta un
subconjunto de campos: permite una validación temprana con los campos que
sólo vienen del correo (``customer``, ``volumen``, ``tiene_adjunto``) antes
de gastar la extracción de visión, y una validación final con todos.

Campos del dibujo fuera de alcance
----------------------------------
``spring_type``, ``key_dimensions`` y ``tolerancias`` **no** se validan
aquí: se infieren/extraen del dibujo en una fase posterior (visión), y son
responsabilidad de ese módulo, no de esta validación comercial.

Función pública
---------------
``validar_campos_rfq(email_data: dict, campos_requeridos=None) -> dict``

Devuelve ``{"es_valido": bool, "campos_faltantes": list[str]}``.
"""

from __future__ import annotations

from typing import Iterable, Optional

# Campos mínimos obligatorios para considerar un RFQ como procesable, según la
# tarjeta "Check basic data". Los campos del dibujo (spring_type,
# key_dimensions, tolerancias) NO van aquí: se validan tras la visión.
_CAMPOS_OBLIGATORIOS = ("tiene_adjunto", "customer", "part_number", "volumen", "material")

# Subconjunto que puede resolverse SÓLO con el correo (sin necesidad del
# dibujo). Útil para una validación temprana que ahorre la llamada de visión.
CAMPOS_SOLO_CORREO = ("tiene_adjunto", "customer", "volumen")


def validar_campos_rfq(
    email_data: dict,
    campos_requeridos: Optional[Iterable[str]] = None,
) -> dict:
    """Valida la presencia de los campos obligatorios del RFQ.

    Un campo se considera **ausente** si:

    * no existe como clave en ``email_data``, o
    * su valor es ``None``, o
    * su valor es una cadena vacía (``""``).

    Caso especial: ``tiene_adjunto`` debe ser ``True``. Cualquier otro
    valor (``False``, ``None``, ausente) lo marca como faltante.

    Args:
        email_data: diccionario con los datos del RFQ ya fusionados
            (correo + dibujo, según corresponda).
        campos_requeridos: iterable opcional con los nombres de campos a
            validar. Si es ``None`` se validan todos los obligatorios
            (``_CAMPOS_OBLIGATORIOS``). Se puede pasar ``CAMPOS_SOLO_CORREO``
            para una validación temprana.

    Returns:
        ``{"es_valido": bool, "campos_faltantes": list[str]}``. La lista
        está vacía si todos los campos requeridos están presentes.
    """
    campos = tuple(campos_requeridos) if campos_requeridos is not None else _CAMPOS_OBLIGATORIOS

    campos_faltantes: list[str] = []

    for campo in campos:
        valor = email_data.get(campo)

        if campo == "tiene_adjunto":
            # Único campo con regla específica: debe ser exactamente True.
            if valor is not True:
                campos_faltantes.append(campo)
            continue

        # Resto de campos: ausentes si None o cadena vacía.
        if valor is None or valor == "":
            campos_faltantes.append(campo)

    return {
        "es_valido": not campos_faltantes,
        "campos_faltantes": campos_faltantes,
    }
