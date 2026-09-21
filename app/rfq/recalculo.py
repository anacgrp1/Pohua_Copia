"""Rehacer el dictamen con lo que el plant manager corrija.

Por qué existe
-------------
El veredicto de factibilidad se calculaba UNA vez, cuando entraba el correo, y
se quedaba grabado. Eso dejaba dos situaciones incómodas en la misma pantalla:

* El plano se lee después —porque aquel día falló, o porque el PM pulsa ahora
  «Leer el plano con IA»— y aparecen cotas que antes no estaban. El costeo se
  rehace al vuelo, pero el veredicto seguía siendo el de cuando no había nada:
  un RFQ marcado «requiere revisión» por falta de datos que ya están leídos.

* El PM mira el dibujo, ve que el modelo leyó 1.6 donde dice 1.8, y lo corrige.
  Antes esa corrección no tenía dónde ir: o se dictaminaba sobre un dato que se
  sabe malo, o se corregía a mano en la calculadora y el RFQ se quedaba con el
  valor viejo.

Aquí el PM ajusta, recalcula, y **el dictamen sale de lo recalculado**. Es lo
que hace que la decisión sea sobre lo que hay, no sobre lo que había.

Qué queda escrito
-----------------
Un valor corregido por una persona no puede parecer un valor leído por el
modelo. El resorte ajustado se guarda como una lectura más —la última gana—,
pero con el origen diciendo quién lo tocó, y con ``ajustado_por`` dentro. Así
la ficha puede distinguir «esto lo leyó la IA» de «esto lo corrigió el PM», y
el historial queda: las lecturas anteriores no se borran.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, Optional

log = logging.getLogger("cotizador.recalculo")

# Lo que el PM puede corregir desde la ventana de revisión. Es una lista
# cerrada a propósito: por aquí entra lo que escribe alguien en un formulario,
# y no se deja que eso reescriba campos que no son suyos —la confianza del
# modelo, el número de parte, las advertencias— ni que meta claves nuevas.
CAMPOS_NUMERICOS = (
    "diametro_alambre_mm",
    "diametro_exterior_mm",
    "diametro_interior_mm",
    "diametro_medio_mm",
    "longitud_libre_mm",
    "longitud_cuerpo_mm",
    "numero_espiras_totales",
    "numero_espiras_activas",
    "paso_mm",
    "angulo_brazos_grados",
    "longitud_gancho_mm",
    "constante_resorte_N_mm",
)

CAMPOS_TEXTO = ("tipo_resorte", "material", "acabado", "tolerancias")

CAMPOS = CAMPOS_NUMERICOS + CAMPOS_TEXTO


def _numero(valor) -> Optional[float]:
    """Texto de un formulario a número. Vacío es vacío, no cero.

    Un campo que el PM deja en blanco significa "no lo sé", y eso NO es lo
    mismo que 0: un diámetro de alambre en cero haría que el motor calculara
    con cero en vez de decir que falta.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    texto = str(valor).strip().replace(",", ".")
    if not texto:
        return None
    try:
        return float(texto)
    except ValueError:
        return None


def fusionar_ajustes(resorte: Optional[dict], ajustes: Optional[dict]) -> Dict[str, Any]:
    """El resorte con lo que el PM haya corregido encima.

    Sólo pisa lo que venga con valor: mandar el formulario entero no borra las
    cotas que el PM no tocó. Para vaciar un campo a propósito se manda la
    cadena ``"-"``, que es explícito y no se confunde con "no lo mandé".
    """
    fusionado = dict(resorte or {})
    ajustes = ajustes or {}
    tocados = []

    for campo in CAMPOS:
        if campo not in ajustes:
            continue
        crudo = ajustes[campo]

        if isinstance(crudo, str) and crudo.strip() == "-":
            if fusionado.get(campo) is not None:
                fusionado[campo] = None
                tocados.append(campo)
            continue

        if campo in CAMPOS_NUMERICOS:
            valor = _numero(crudo)
        else:
            valor = str(crudo).strip() or None

        if valor is None:
            continue
        if fusionado.get(campo) != valor:
            fusionado[campo] = valor
            tocados.append(campo)

    return {"resorte": fusionado, "tocados": tocados}


def recalcular(rfq_id: str,
               resorte: Optional[dict],
               ajustes: Optional[dict] = None,
               usuario: Optional[str] = None,
               version: Optional[int] = None,
               message_id: str = "") -> Dict[str, Any]:
    """Vuelve a dictaminar con el resorte ajustado y lo deja escrito.

    Devuelve ``{resorte, tocados, factibilidad, guardado, error}``. Nunca
    lanza por el motor ni por la base: la ventana tiene que seguir abriéndose
    aunque el recálculo falle, y el error se dice en vez de tumbarla.
    """
    fusion = fusionar_ajustes(resorte, ajustes)
    ajustado = fusion["resorte"]
    tocados = fusion["tocados"]

    # Lo que tocó una persona se marca como tal. Sin esto, un 1.8 escrito a
    # mano y un 1.8 leído del plano serían indistinguibles para siempre.
    if tocados:
        ajustado["ajustado_por"] = usuario or "pm"
        ajustado["ajustado_en"] = _dt.datetime.now(
            _dt.timezone.utc).isoformat(timespec="seconds")
        ajustado["campos_ajustados"] = tocados

    factibilidad, error = None, None
    try:
        import app.feasibility.engine as engine
        factibilidad = engine.evaluar_factibilidad(ajustado)
    except Exception as err:
        log.exception("RFQ=%s: no se pudo volver a dictaminar: %s", rfq_id, err)
        error = str(err)

    guardado = False
    if tocados:
        # El resorte ajustado, como una lectura más. Las anteriores no se
        # borran: el historial de qué decía el plano y qué corrigió quién es
        # justo lo que hace falta para discutir un precio meses después.
        try:
            import app.persistence.spring_repository as spring_repository
            origen = f"Ajustado por {usuario}" if usuario else "Ajustado en revisión"
            spring_repository.guardar(rfq_id, message_id or "", origen, ajustado)
            guardado = True
        except Exception as err:
            log.error("RFQ=%s: no se pudo guardar el resorte ajustado: %s",
                      rfq_id, err)
            error = error or str(err)

    if factibilidad:
        try:
            import app.rfq.repository as repository
            repository.guardar_veredicto(rfq_id, factibilidad, version=version)
            log.info("RFQ=%s: dictamen rehecho por %s (%s). Veredicto: %s, "
                     "score %s, %d motivo(s).",
                     rfq_id, usuario or "?",
                     ", ".join(tocados) if tocados else "sin cambios",
                     factibilidad.get("veredicto"), factibilidad.get("score"),
                     len(factibilidad.get("motivos") or []))
        except Exception as err:
            log.error("RFQ=%s: se recalculó pero no se pudo guardar el "
                      "veredicto: %s", rfq_id, err)
            error = error or str(err)

    return {"resorte": ajustado, "tocados": tocados,
            "factibilidad": factibilidad, "guardado": guardado, "error": error}
