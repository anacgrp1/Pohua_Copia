"""El horario de atención: cuándo contesta Pohua.

Los RFQ llegan a cualquier hora —un comprador en Alemania escribe a las 3 de
la madrugada en Kansas— pero contestarlos es un acto de la empresa, y la
empresa tiene horario: de lunes a viernes, de 6:00 a 18:00.

QUÉ HACE FUERA DE HORA. Nada, y esa es la decisión. El ciclo ni siquiera abre
el buzón: el correo se queda sin leer donde está y entra en el primer ciclo de
la apertura siguiente. Así nada se pierde —el buzón es la cola—, no se gasta
el modelo de madrugada, y sobre todo no se manda una oferta a las 2 a.m., que
es algo que un cliente nota y no para bien.

EN QUÉ RELOJ. En uno solo: el de la planta (Kansas City), porque el ciclo es
un proceso y no puede tener tres horarios a la vez. Es configurable con
``HORARIO_ZONA``.

Lo que sí es de cada quien es cómo se LEE ese horario: la pantalla lo enseña
en la ciudad del idioma que tenga puesto —Kansas City en inglés, Querétaro en
español, Sevran en francés—, igual que el reloj de arriba. Una misma ventana,
dicha en tres husos. ``estado()`` devuelve los instantes en UTC para que el
navegador los pinte en su hora sin que aquí haya que saber nada de idiomas.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger("cotizador.horario")

# La ciudad de cada zona, para poder decirlo en una frase.
CIUDADES = {
    "America/Chicago": "Kansas City",
    "America/Mexico_City": "Querétaro",
    "Europe/Paris": "Sevran",
}


def _config():
    import app.core.config as config
    return config.settings


def _zona(nombre: str):
    """La zona horaria, o UTC si el sistema no la conoce.

    Una zona mal escrita no puede tumbar el ciclo: se avisa y se sigue con UTC,
    que al menos es determinista.
    """
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(nombre)
    except Exception as error:
        log.warning("Zona horaria desconocida (%s): %s. Se usa UTC.", nombre, error)
        from datetime import timezone
        return timezone.utc


def dias_laborables(texto: str) -> List[int]:
    """Convierte "1-5" o "1,2,3,4,5" en [1,2,3,4,5]. Lunes = 1, domingo = 7."""
    dias: List[int] = []
    for trozo in str(texto or "").split(","):
        trozo = trozo.strip()
        if not trozo:
            continue
        if "-" in trozo:
            try:
                desde, hasta = [int(x) for x in trozo.split("-", 1)]
            except ValueError:
                continue
            paso = 1 if hasta >= desde else -1
            dias.extend(range(desde, hasta + paso, paso))
        else:
            try:
                dias.append(int(trozo))
            except ValueError:
                continue
    limpios = sorted({d for d in dias if 1 <= d <= 7})
    return limpios or [1, 2, 3, 4, 5]


def _ventana() -> Tuple[Any, List[int], int, int, bool]:
    c = _config()
    zona = _zona(getattr(c, "HORARIO_ZONA", "America/Chicago"))
    dias = dias_laborables(getattr(c, "HORARIO_DIAS", "1-5"))
    desde = max(0, min(23, int(getattr(c, "HORARIO_DESDE", 6))))
    hasta = max(1, min(24, int(getattr(c, "HORARIO_HASTA", 18))))
    activo = bool(getattr(c, "HORARIO_ACTIVO", True))
    if hasta <= desde:      # una ventana vacía sería un sistema apagado a ciegas
        log.warning("HORARIO_HASTA (%s) no es mayor que HORARIO_DESDE (%s); "
                    "se ignora el horario.", hasta, desde)
        activo = False
    return zona, dias, desde, hasta, activo


def abierto(ahora: Optional[datetime] = None) -> bool:
    """¿Es horario de atención en este momento?

    Con ``HORARIO_ACTIVO`` apagado siempre es que sí: el horario es una
    restricción que se puede quitar, no un requisito para funcionar.
    """
    zona, dias, desde, hasta, activo = _ventana()
    if not activo:
        return True
    local = (ahora or datetime.now(zona)).astimezone(zona)
    if local.isoweekday() not in dias:
        return False
    return desde <= local.hour < hasta


def proxima_apertura(ahora: Optional[datetime] = None) -> Optional[datetime]:
    """Cuándo vuelve a abrir, en la zona del horario. None si ya está abierto."""
    zona, dias, desde, hasta, activo = _ventana()
    if not activo:
        return None
    local = (ahora or datetime.now(zona)).astimezone(zona)
    if local.isoweekday() in dias and desde <= local.hour < hasta:
        return None

    # Hoy, si aún no ha abierto; si no, el primer día laborable que venga.
    if local.isoweekday() in dias and local.hour < desde:
        return local.replace(hour=desde, minute=0, second=0, microsecond=0)
    for salto in range(1, 8):
        dia = local + timedelta(days=salto)
        if dia.isoweekday() in dias:
            return dia.replace(hour=desde, minute=0, second=0, microsecond=0)
    return None


def proximo_cierre(ahora: Optional[datetime] = None) -> Optional[datetime]:
    """Cuándo cierra hoy. None si ahora mismo está cerrado."""
    zona, dias, desde, hasta, activo = _ventana()
    if not activo:
        return None
    local = (ahora or datetime.now(zona)).astimezone(zona)
    if local.isoweekday() not in dias or not (desde <= local.hour < hasta):
        return None
    if hasta >= 24:
        base = local.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        return base
    return local.replace(hour=hasta, minute=0, second=0, microsecond=0)


def estado(ahora: Optional[datetime] = None) -> Dict[str, Any]:
    """Lo que necesita la pantalla para contarlo, sin saber de zonas.

    Los instantes van en ISO con su huso: el navegador los pinta en la ciudad
    del idioma que tenga puesto, que es justo lo que hace el reloj de arriba.
    """
    zona, dias, desde, hasta, activo = _ventana()
    c = _config()
    nombre_zona = getattr(c, "HORARIO_ZONA", "America/Chicago")
    local = (ahora or datetime.now(zona)).astimezone(zona)
    esta_abierto = abierto(local)
    apertura = proxima_apertura(local)
    cierre = proximo_cierre(local)
    return {
        "activo": activo,
        "abierto": esta_abierto,
        "zona": nombre_zona,
        "ciudad": CIUDADES.get(nombre_zona, nombre_zona.split("/")[-1].replace("_", " ")),
        "desde": desde,
        "hasta": hasta,
        "dias": dias,
        "ahora_local": local.isoformat(timespec="seconds"),
        "proxima_apertura": apertura.isoformat(timespec="seconds") if apertura else None,
        "proximo_cierre": cierre.isoformat(timespec="seconds") if cierre else None,
    }


def motivo_cerrado(ahora: Optional[datetime] = None) -> str:
    """Una línea para el registro: por qué no se abrió el buzón."""
    e = estado(ahora)
    apertura = e["proxima_apertura"] or "la próxima apertura"
    return (f"Fuera del horario de atención ({e['desde']}:00–{e['hasta']}:00 "
            f"{e['ciudad']}, lunes a viernes). Los correos esperan a {apertura}.")
