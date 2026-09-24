"""Adaptador de costeo — traduce los datos del resorte al esquema PN del motor.

Antes este módulo rellenaba el PN con constantes: precio de alambre 2.50 USD/lb
(con un ``TODO`` al lado), máquina «AIM 3000», 6 h de setup, 327 piezas/hora y
5 % de scrap, para **cualquier** resorte. El precio que salía de ahí no era el
de la pieza, era el de esa máquina imaginaria.

Ahora todo eso se lee del catálogo (``pricing/repository.py``) y lo que no está
en la base no se inventa: se reporta en ``faltantes`` y el precio se marca como
incompleto.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import pricing.mensajes as mensajes
from pricing import espiras as espiras_mod
from pricing import reglas, repository

log = logging.getLogger("cotizador.pricing.adapter")

# Descripción que espera el motor JS según el tipo de resorte.
_TIPO_A_DESC = {
    "compresion": "Compression Spring",
    "compression": "Compression Spring",
    "extension": "Tension Spring",
    "tension": "Tension Spring",
    "torsion": "Torsion Spring",
    "wireform": "Wire Form",
    "alambre": "Wire Form",
}

# Escalón vacío: el motor espera siempre cinco.
_TIER_VACIO = {"qty": None, "routing": [], "tooling": {}, "sub": {}, "packing": {}}


def _num(valor: Any) -> Optional[float]:
    """Convierte a float lo que se pueda; None si no es un número utilizable."""
    if valor is None or isinstance(valor, bool):
        return None
    try:
        numero = float(valor)
    except (TypeError, ValueError):
        return None
    return numero if numero == numero else None  # descarta NaN


# Densidad del alambre en lb/pulg³, por código de material.
#
# Copia EXACTA de WIRE_DENS de pricing/engine.js — mismas claves y mismos
# valores. No se añade ninguna que el motor no tenga: si aquí hubiera un
# material de más, el peso que calculamos y el que el motor habría calculado
# dejarían de coincidir para ese material, y el costo de materia prima saldría
# distinto según por dónde se mirara.
#
# (SS177 y 316 no están, igual que en el motor: caen al valor por defecto.
# Si en ISC miden una densidad distinta para los inoxidables, hay que
# añadirlas en LOS DOS sitios a la vez.)
#
# Tampoco está INCX750, y es a propósito: la calculadora de ISC cotiza el
# Inconel X-750 con el código del Hastelloy ("codigo": "HAST" en su entrada
# "inconel"), así que `reglas/factibilidad.json` hace lo mismo y un RFQ de
# Inconel se pesa con .321. Si algún día ISC le da código propio, hay que
# sembrar la fila en `materiales` con 8250 kg/m³ y añadir INCX750: .298 en
# CUATRO sitios a la vez: aquí, pricing/engine.js, el HTML de la calculadora
# y la tabla `materiales`.
_DENSIDAD_LB_IN3 = {
    "MW": .284, "CSI": .284, "HD": .284, "OT": .284, "GMW": .284,
    "GHD": .284, "SG": .284, "BB": .284,
    "SS": .286,
    "PHOSB": .320, "BRASS": .308, "HAST": .321,
}
_DENSIDAD_POR_DEFECTO = .284  # acero al carbono, igual que el motor


def falta_para_el_peso(spring_data: Dict[str, Any]) -> Optional[str]:
    """Qué cota concreta impide calcular el peso del alambre.

    El peso es ``π · Dm · Nt`` por la sección del alambre, así que hacen falta
    TRES cosas y cada una puede venir de varios sitios. Decir «faltan diámetro,
    diámetro medio o número de espiras» las nombra las tres aunque sólo falle
    una, y quien lee no sabe cuál escribir: el diámetro medio casi nunca está
    impreso en un plano —se deduce del exterior menos un calibre— así que
    mencionarlo manda a buscar una cota que no existe.

    Devuelve el nombre del campo que hay que conseguir, o ``None`` si no falta
    ninguno.
    """
    d = _num(spring_data.get("diametro_alambre_mm"))
    if not d or d <= 0:
        return "diametro_alambre_mm"

    # El medio sale del exterior o del interior; basta con cualquiera.
    if not (_num(spring_data.get("diametro_medio_mm"))
            or _num(spring_data.get("diametro_exterior_mm"))
            or _num(spring_data.get("diametro_interior_mm"))):
        return "diametro_exterior_mm"

    # Las totales pueden venir del plano o salir de las activas más las
    # espiras muertas del tipo de extremo (`pricing/espiras.py`). Se pregunta
    # ahí y no aquí para que esta función y el cálculo del desarrollo no puedan
    # discrepar: decir "no falta nada" y luego devolver un peso nulo es peor
    # que decir que falta.
    totales, _ = espiras_mod.espiras_totales(spring_data)
    if not totales:
        return "numero_espiras_totales"

    return None


def longitud_desarrollada_pulg(spring_data: Dict[str, Any]) -> Optional[float]:
    """Longitud de alambre desarrollada, en pulgadas.

    Es ``π · Dm · Nt / cos(α)`` — el diámetro medio por el número total de
    espiras, corregido por el ángulo de hélice.  El diámetro medio se obtiene
    del que haya: medio, exterior menos un calibre, o interior más un calibre.

    Por qué el coseno
    -----------------
    ``π · Dm · Nt`` es la longitud si el alambre diera vueltas planas. No las
    da: avanza un paso en cada vuelta, así que cada espira es la hipotenusa de
    un triángulo cuyos catetos son la circunferencia y el paso. Ignorarlo
    dejaba el alambre —y con él el peso, el costo de material y el precio— por
    DEBAJO de lo que es.

    En el 004-222 son 5.8° de hélice: 0.00573 lb contra 0.00576, medio por
    ciento. Poco, pero es medio por ciento en el sentido de cotizar barato, y
    en un resorte de paso largo crece deprisa —a 20° ya es un 6 %—.

    Es la fórmula del núcleo (`resortes.js`: ``PI*D*Nt/Math.cos(helix)``), que
    es lo que hace que el peso de aquí y el de la calculadora coincidan.

    Sin paso no se puede calcular el ángulo, así que se devuelve la longitud
    plana: quedarse corto por medio por ciento es mejor que no dar peso.

    Devuelve None si falta geometría.  No se estima: un peso inventado se
    convierte directamente en un costo de material inventado.

    Ojo: es la longitud del CUERPO.  En extensión no incluye los ganchos y en
    torsión no incluye las patas; ``build_pn_for_engine`` lo anota como
    faltante para esos dos tipos.
    """
    d = _num(spring_data.get("diametro_alambre_mm"))
    if not d or d <= 0:
        return None

    dm = _num(spring_data.get("diametro_medio_mm"))
    if not dm:
        od = _num(spring_data.get("diametro_exterior_mm"))
        idd = _num(spring_data.get("diametro_interior_mm"))
        if od:
            dm = od - d
        elif idd:
            dm = idd + d
    if not dm or dm <= 0:
        return None

    # Igual que arriba: la conversión de activas a totales vive en un solo
    # sitio, con la tabla de espiras muertas por tipo de extremo. Antes aquí
    # se sumaban 2 sin mirar los extremos, que sólo vale para los cerrados: a
    # unos extremos planos les inventaba dos espiras de alambre.
    espiras, _ = espiras_mod.espiras_totales(spring_data)
    if not espiras or espiras <= 0:
        return None

    import math
    circunferencia = math.pi * dm                     # mm, una vuelta plana
    paso = _paso_mm(spring_data, espiras)
    if paso and paso > 0:
        # La hipotenusa: una vuelta de circunferencia avanzando un paso.
        por_espira = math.hypot(circunferencia, paso)
    else:
        por_espira = circunferencia
    return (por_espira * espiras) / 25.4


def _paso_mm(spring_data: Dict[str, Any], espiras: float) -> Optional[float]:
    """El paso entre espiras, acotado o deducido de la longitud libre.

    Sólo en compresión: en extensión las espiras van juntas —el paso es el
    calibre— y en torsión la geometría es otra. Devolver None ahí deja la
    longitud plana, que es la convención del núcleo para esos dos tipos.
    """
    tipo = str(spring_data.get("tipo_resorte") or "").strip().lower()
    if not tipo.startswith("compres"):
        return None

    paso = _num(spring_data.get("paso_mm"))
    if paso and paso > 0:
        return paso

    # Deducido: la longitud libre menos lo que ocupan los extremos cerrados,
    # repartido entre las espiras activas.
    l0 = _num(spring_data.get("longitud_libre_mm"))
    d = _num(spring_data.get("diametro_alambre_mm"))
    if not l0 or not d or l0 <= 0 or d <= 0:
        return None
    muertas, _ = espiras_mod.espiras_muertas(spring_data)
    activas = espiras - muertas
    if activas <= 0:
        return None
    extremos = 2 * d if muertas >= 2 else 0
    paso = (l0 - extremos) / activas
    return paso if paso > d else None      # menos que el calibre no es un paso


def peso_alambre_lb(longitud_pulg: Optional[float], diametro_mm: Optional[float],
                    codigo_material: Optional[str]) -> Optional[float]:
    """Peso del alambre en libras: ``π/4 · d² · L · densidad``.

    Réplica exacta de ``wireFormWeight`` del motor JS, para que el peso que
    manda el adaptador sea el que el motor habría calculado.
    """
    if not longitud_pulg or not diametro_mm or longitud_pulg <= 0 or diametro_mm <= 0:
        return None
    import math
    d_pulg = diametro_mm / 25.4
    densidad = _DENSIDAD_LB_IN3.get(
        str(codigo_material or "").upper(), _DENSIDAD_POR_DEFECTO)
    return math.pi / 4 * d_pulg * d_pulg * longitud_pulg * densidad


def _cantidades(lista: Any, unica: Optional[float]) -> List[float]:
    """Las cantidades a costear, limpias, únicas, de menor a mayor, máximo 5."""
    fuera: List[float] = []
    for v in (lista if isinstance(lista, (list, tuple)) else []):
        n = _num(v)
        if n and n > 0 and n not in fuera:
            fuera.append(n)
    if not fuera and unica and unica > 0:
        fuera = [unica]
    return sorted(fuera)[:5]


def _tramo(cantidad: float, routing: List[Dict[str, Any]],
           empaque: Dict[str, Any],
           caja: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Un tramo del motor con su ruta y su empaque; lo demás en blanco.

    `caja` es lo que contestaron las reglas del taller para ESTE tramo. Manda
    sobre el empaque del catálogo porque la caja la decide el peso total del
    tramo, y eso cambia de un tramo a otro: 10.000 piezas de un resorte
    pequeño van en cajas y 50.000 ya son tambores. El catálogo, en cambio,
    sólo sabe dar una caja para todo el PN.
    """
    empaque = empaque or {}
    return {
        "qty": cantidad,
        # Copia por tramo: el motor escribe dentro (`scrapWarn`, lotes) y dos
        # tramos compartiendo la misma lista se pisarían.
        "routing": [dict(op) for op in routing],
        "tooling": {"desc": "", "cost": None, "amortQty": None},
        "sub": {"supplier": "", "service": "", "minUsd": None, "perLb": None,
                "perPc": None, "partsPerBatch": None, "shareSkid": "NO"},
        "packing": {
            "id": (caja or {}).get("id") or empaque.get("codigo"),
            "qtyPerBox": (caja or {}).get("ppb") or empaque.get("piezas_por_caja"),
        },
    }


# El transporte del alambre. Es una constante de ISC que nadie ha revisado,
# pero es la que usa la calculadora de la planta, y alrededor del 7 % del
# costo de material.
TRANSPORTE_POR_DEFECTO = 0.30


def _transporte(params: Dict[str, Any], catalogo) -> float:
    """El transporte del alambre, en $/lb.

    Si el catálogo no lo trae se usa la constante de ISC y se anota, en vez de
    dejarlo en cero y que el material salga barato sin que nadie lo note.
    """
    v = _num(params.get("transpPerLb"))
    if v is not None:
        return v
    catalogo.faltantes.append(
        "El catálogo no tiene el transporte del alambre: se usó la constante de "
        "ISC de %.2f $/lb. Es alrededor del 7 %% del costo de material."
        % TRANSPORTE_POR_DEFECTO)
    return TRANSPORTE_POR_DEFECTO


HORNO = "Stationary Oven"


def _con_relevado(secundarias, desc, catalogo):
    """Añade el horno a toda compresión, si la casa lo tiene puesto así.

    El taller contestó que el horno NO va en toda compresión —«only very big
    springs and 17-7 SS material»— y la regla del núcleo lo respeta. Pero en
    las cotizaciones de referencia el horno está, puesto a mano.

    Así que no se decide aquí: lo decide `RELEVADO_SIEMPRE_COMPRESION` en la
    configuración. Encendido, el horno entra y se DICE que entró por esa
    política y no porque el plano lo pidiera; quien aprueba ve la diferencia
    entre una operación que pide el dibujo y una que pone la casa.

    Con el interruptor apagado esto no toca nada.
    """
    if secundarias is None or desc != "Compression Spring":
        return secundarias
    try:
        import app.core.config as config
        if not getattr(config.settings, "RELEVADO_SIEMPRE_COMPRESION", False):
            return secundarias
    except Exception:
        return secundarias
    if any(op.get("m") == HORNO for op in secundarias):
        return secundarias          # el plano ya lo pedía
    catalogo.faltantes.append(
        "El horno de relevado se añadió por política de la casa "
        "(RELEVADO_SIEMPRE_COMPRESION), no porque el plano lo pida: el dato "
        "del taller dice que sólo va en resortes muy grandes y en 17-7.")
    return list(secundarias) + [
        {"m": HORNO, "why": "stress relief on all compression (ISC policy)"}]


def _fmt_mm(v) -> str:
    return ("%g" % v) if v is not None else "?"


def _fuera_de_capacidad(cap: Dict[str, Any], diam_mm, od_mm) -> Optional[str]:
    """Por qué esa máquina no da la talla para esta pieza, o ``None`` si da.

    Un límite sin capturar (``None``) no descarta: significa que no se sabe, y
    inventarse que no hay límite es justo el error que esto evita. Sólo se
    afirma sobre lo que la planta capturó.
    """
    minimo = cap.get("alambre_min_mm")
    maximo = cap.get("alambre_max_mm")
    od_max = cap.get("od_max_mm")
    if diam_mm is not None and minimo is not None and diam_mm < minimo:
        return ("toma alambre desde %s mm y la pieza es de %s"
                % (_fmt_mm(minimo), _fmt_mm(diam_mm)))
    if diam_mm is not None and maximo is not None and diam_mm > maximo:
        return ("toma alambre hasta %s mm y la pieza es de %s"
                % (_fmt_mm(maximo), _fmt_mm(diam_mm)))
    if od_mm is not None and od_max is not None and od_mm > od_max:
        return ("llega a un exterior de %s mm y la pieza mide %s"
                % (_fmt_mm(od_max), _fmt_mm(od_mm)))
    return None


def build_pn_for_engine(
    rfq_id: str,
    spring_data: Dict[str, Any],
    conexion=None,
) -> Tuple[Dict[str, Any], repository.Catalogo]:
    """Construye el PN para el motor y devuelve también el catálogo consultado.

    Devuelve la tupla ``(pn, catalogo)``: el catálogo lleva la trazabilidad
    (``origen``) y la lista de datos que faltaban (``faltantes``), que la ruta
    HTTP adjunta a la respuesta para que quien la lea sepa cuánto se puede fiar
    del número.
    """
    tipo = str(spring_data.get("tipo_resorte") or "").strip().lower()

    # Un tipo que no reconocemos NO se convierte en el más parecido. Antes caía
    # por defecto en "Compression Spring", así que un resorte de torsión mal
    # leído se costeaba como uno de compresión —con otra máquina y otras
    # operaciones— sin que nada lo dijera.
    desc = _TIPO_A_DESC.get(tipo)
    tipo_desconocido = desc is None
    if tipo_desconocido:
        desc = spring_data.get("tipo_resorte") or ""

    diam_mm = _num(spring_data.get("diametro_alambre_mm"))
    od_mm = _num(spring_data.get("diametro_exterior_mm"))
    cantidad = _num(spring_data.get("cantidad"))
    material_codigo = (spring_data.get("material") or "").strip() or None

    # Los tramos de cantidad. Un RFQ real casi nunca trae UNA cantidad: trae
    # "10,000, 25,000 y 50,000" y quiere precio para cada una. Se admiten
    # hasta cinco —los que tiene el motor— y se ordenan de menor a mayor,
    # que es como los lee el PM. Sin lista, se usa `cantidad` como único tramo.
    cantidades = _cantidades(spring_data.get("cantidades"), cantidad)

    catalogo = repository.cargar_catalogo(
        tipo_resorte=tipo or "compresion",
        material_codigo=material_codigo,
        diametro_alambre_mm=diam_mm,
        diametro_exterior_mm=od_mm,
        empaque_codigo=spring_data.get("empaque"),
        conexion=conexion,
    )

    if not cantidades:
        mensajes.falta(catalogo, "SIN_CANTIDAD")

    if tipo_desconocido:
        catalogo.faltantes.append(
            "El tipo de resorte %r no es uno de los que sabemos costear "
            "(compresión, extensión, torsión o wire form): la ruta y la máquina "
            "hay que ponerlas a mano." % (spring_data.get("tipo_resorte"),))

    maquina = catalogo.maquina or {}
    material = catalogo.material or {}
    empaque = catalogo.empaque or {}
    params = catalogo.parametros or {}

    # ¿Puede esa máquina, en concreto, con esta pieza?
    #
    # No se cambia la que eligió el catálogo —cuál PREFIERE el taller es otra
    # discusión, y no se decide aquí—, pero sí se dice cuando la elegida
    # FÍSICAMENTE no puede. Eso no es preferencia: es un dato, y hasta ahora no
    # llegaba a nadie.
    #
    # Son dos comprobaciones distintas y ninguna cubre a la otra:
    if maquina.get("nombre") and diam_mm:
        # 1. El rango de alambre y el OD que la planta capturó para esa
        #    máquina. Caso real: el 004-222 se costeó en una NUCOIL HX-60, que
        #    toma alambre desde 1.0 mm, con un alambre de 0.991. La consulta de
        #    selección ya filtra por esto, así que si aun así sale una máquina
        #    fuera de rango es que la fila de capacidades no está o no coincide
        #    con la que se usó al elegir — y eso hay que verlo, no suponerlo.
        cap = repository.capacidad_de_maquina(maquina["nombre"], conexion=conexion)
        if cap is None:
            catalogo.faltantes.append(
                "No hay capacidades capturadas para %s: no se pudo comprobar si "
                "puede con un alambre de %s mm. Se cotizó con ella de todas "
                "formas." % (maquina["nombre"], _fmt_mm(diam_mm)))
        else:
            fuera = _fuera_de_capacidad(cap, diam_mm, od_mm)
            if fuera:
                catalogo.faltantes.append(
                    "La máquina elegida (%s) no puede con esta pieza: %s. Hay "
                    "que cambiarla a mano antes de cotizar."
                    % (maquina["nombre"], fuera))

        # 2. El tope por material, que baja el diámetro máximo de una máquina
        #    para ciertos alambres. La SIMPLEX MC 50 llega a .198" y en temple
        #    en aceite sólo a .165". La que sí puede cuesta cuatro veces más por
        #    pieza, así que callarlo es cotizar muy por debajo del costo.
        tope = repository.tope_de_maquina(maquina["nombre"], conexion=conexion)
        if tope is None:
            catalogo.faltantes.append(
                "No se pudo comprobar el tope por material: la tabla `maquinas` "
                "todavía no tiene `tope_material` ni `tope_alambre_max_mm`. Están "
                "en maquinas_valores.csv del extracto del catálogo.")
        else:
            motivo = reglas.tope_por_material(
                maquina["nombre"], tope, material.get("nombre"), diam_mm)
            if motivo:
                catalogo.faltantes.append(
                    "La máquina elegida (%s) no puede con este material: %s. "
                    "Hay que cambiarla a mano antes de cotizar."
                    % (maquina["nombre"], motivo))

    # scrap y markup salen de los parámetros versionados; si no hay juego
    # vigente se dejan en None y el motor aplica los suyos, pero queda anotado.
    scrap_pct = _num(params.get("scrapDefault"))
    markup_material = _num(params.get("matMk"))

    # Peso de alambre: sin él el motor calcula el material en 0 y el precio
    # sale sin la materia prima dentro, que suele ser el grueso del costo.
    dev_len = longitud_desarrollada_pulg(spring_data)
    peso_lb = peso_alambre_lb(dev_len, diam_mm, material.get("codigo") or material_codigo)
    if peso_lb is None:
        que_falta = falta_para_el_peso(spring_data)
        if que_falta:
            # `campo` va con la clave —la web la traduce al idioma puesto— y
            # `nombre` con el texto llano, para el mensaje del servidor.
            mensajes.falta(catalogo, "SIN_PESO_POR", campo=que_falta,
                           nombre=mensajes.etiqueta_campo(que_falta))
        else:
            mensajes.falta(catalogo, "SIN_PESO_ALAMBRE")
    elif tipo.startswith(("extension", "tension", "torsion")):
        mensajes.falta(catalogo, "PESO_SOLO_CUERPO")

    # Las operaciones que van DESPUÉS de la bobinadora: rectificado si el plano
    # pide extremos rectificados, horno por 17-7 o por tratamiento térmico,
    # looping en extensión y doblado en torsión.
    #
    # No se deciden aquí: se preguntan a las reglas del taller, que viven en el
    # núcleo. Reimplementarlas en Python sería tener dos versiones de la misma
    # regla, y acabarían discrepando. Si el núcleo no está disponible se dice,
    # en vez de entregar una ruta de una sola operación que parece completa.
    secundarias = None
    if not tipo_desconocido:
        # El tratamiento térmico viene suelto o dentro del bloque de material,
        # según de dónde salga la extracción.
        _mat = spring_data.get("material")
        tratamiento = spring_data.get("tratamiento_termico")
        if not tratamiento and isinstance(_mat, dict):
            tratamiento = _mat.get("tratamiento_termico")

        secundarias = reglas.operaciones_secundarias(
            desc,
            tipo_extremos=spring_data.get("tipo_extremos"),
            tratamiento_termico=tratamiento,
            material_codigo=(material.get("codigo") or material_codigo),
        )
        secundarias = _con_relevado(secundarias, desc, catalogo)
        if secundarias is None:
            catalogo.faltantes.append(
                "No se pudieron consultar las reglas del taller, así que la ruta "
                "lleva sólo la bobinadora: faltan rectificado, horno, looping o "
                "doblado según la pieza. El costo de proceso sale por debajo.")

    routing = []
    if maquina:
        # `machH` es lo que la máquina CUESTA por hora; `tgtH` es lo que se
        # espera que DEJE por hora. Son dos números distintos y en el catálogo
        # viven en dos columnas distintas: `costo_hora` y `ccv_objetivo_h`.
        #
        # Aquí iban los dos al objetivo. En la NUCOIL HX-60 eso mandaba 89.29
        # USD/h a la casilla "Machine $/h" en vez de 29.76 —el objetivo es el
        # triple del costo en todas las filas del catálogo—, y el costo de
        # máquina salía por tres. En el 004-222 eso fue $1.234 la pieza contra
        # $0.3946: la cotización entera al triple, con todas las líneas del
        # P&L cuadrando entre sí, porque el error entra antes de que empiecen
        # los porcentajes.
        #
        # Si no hay tarifa vigente se manda `None` y la hoja lo enseña vacío,
        # que es lo correcto: es una tarifa que hay que capturar, no un cero.
        routing.append({
            "machine": maquina.get("nombre"),
            "family": maquina.get("familia") or "COILER",
            "setupH": maquina.get("horas_setup"),
            "pph": maquina.get("pph"),
            "laborH": maquina.get("horas_labor"),
            "machH": maquina.get("costo_hora"),
            "tgtH": maquina.get("ccv_objetivo_h"),
            # El ratio (máquinas por operario) se deja SIN VALOR a propósito.
            #
            # El motor tiene la escalera que validó Miguel Rodea: puesta a punto
            # y primeras 4 h con máquina dedicada, luego 2, 3 y hasta 4 según
            # duren las horas de tirada. Mandar aquí el multiplicador de la
            # familia —que es una constante y no sabe cuántas horas dura esta
            # tirada— anulaba esa escalera en TODAS las cotizaciones. Medido en
            # la calculadora, eso son hasta un 40 % más de mano de obra en un
            # tramo largo.
            #
            # Si `familias_maquina.multiplicador` significa otra cosa que
            # máquinas por operario, ésta es la línea que hay que revisar.
            "ratio": None,
            "scrapPct": scrap_pct,
        })

    # Cada secundaria es una operación más en la ruta. Importa más de lo que
    # parece: el número de operaciones alimenta la escalera de overheads y el
    # suelo de ISC, que es 800 + 200 por cada operación de más, así que faltaba
    # costo por tres caminos a la vez.
    for op in (secundarias or []):
        m = repository.maquina_por_nombre(op.get("m"), conexion=conexion)
        if not m:
            catalogo.faltantes.append(
                "La operación «%s» que pide el plano (%s) no está en el catálogo "
                "de máquinas: no se pudo costear." % (op.get("m"), op.get("why")))
            continue
        routing.append({
            "machine": m.get("nombre"),
            "family": m.get("familia") or "SECONDARY",
            "setupH": m.get("horas_setup"),
            "pph": m.get("pph"),
            "laborH": m.get("horas_labor"),
            # Lo mismo que arriba: el COSTO por hora, no el objetivo de CCV.
            # En el Grinder A son 11.16 contra 55.80: cinco veces.
            "machH": m.get("costo_hora"),
            "tgtH": m.get("ccv_objetivo_h"),
            "ratio": None,
            "scrapPct": scrap_pct,
        })

    # Las cajas que existen, una vez para todos los tramos: la regla elige
    # entre ellas según el peso de cada tramo.
    lista_cajas = repository.cajas(conexion=conexion) if not tipo_desconocido else []

    pn: Dict[str, Any] = {
        "pn": rfq_id,
        "desc": desc,
        "notes": "",
        "unit": "pc",
        "material": {
            # Sin material en catálogo se manda el código tal cual vino, para
            # que el motor lo señale, en lugar de sustituirlo por "MW".
            "code": material.get("codigo") or material_codigo,
            "diaIn": (diam_mm / 25.4) if diam_mm else None,
            # A cinco decimales, como lo guarda la calculadora en todos sus
            # caminos (`Math.round(w*100000)/100000`): es el peso con el que
            # se cotiza en la planta. Sin redondear, el tramo de 50.000 piezas
            # del 004-222 compraba 335.8 lb en vez de 335.9 y la oferta salía
            # un dólar por debajo de la de la calculadora.
            "weightLb": (round(peso_lb, 5) if peso_lb is not None else None),
            "devLenIn": dev_len,
            "basePerLb": material.get("precio_lb"),
            "surchPerLb": material.get("surcharge_lb") or 0,
            # `or 0` convertía "el catálogo no lo tiene" en "cuesta cero", y el
            # transporte del alambre es alrededor del 7 % del material.
            "transpPerLb": _transporte(params, catalogo),
            "mkPct": markup_material,
            "moqLb": None,
        },
        "components": [{"desc": "", "usd": None}, {"desc": "", "usd": None}],
        "consumable": {"desc": "", "usd": None},
        # Un tramo por cantidad, todos con la misma ruta: el RFQ no dice que
        # a 50,000 piezas se use otra máquina, así que no se inventa. Los que
        # sobran hasta cinco van vacíos, que es como el motor los ignora.
        "tiers": [
            _tramo(q, routing, empaque,
                   reglas.empaque(peso_lb, desc, q, lista_cajas)
                   if not tipo_desconocido else None)
            if q is not None else dict(_TIER_VACIO)
            for q in (cantidades + [None] * 5)[:5]
        ],
        "selTier": 0,
        "opsTier": 0,
        "ohOverride": None,
        "remarks": "",
        "rev": "",
        "drawing": None,
        "springFeas": None,
    }

    if catalogo.faltantes:
        log.info("Costeo de %s incompleto (%d datos faltantes): %s",
                 rfq_id, len(catalogo.faltantes), "; ".join(catalogo.faltantes))

    return pn, catalogo


def overrides_de_parametros(parametros: Dict[str, Any],
                            representante: Optional[str] = None) -> Dict[str, Any]:
    """Traduce los parámetros de la base al ``ctx_overrides`` del motor JS.

    Sólo se mandan las claves que existan en la base: las demás las pone el
    motor con sus valores por omisión.

    ``representante`` es el vendedor asignado a la cuenta; el motor lo usa para
    decidir si aplica comisión. Antes venía escrito a mano en ``runner.js``, así
    que todas las cotizaciones salían a nombre de la misma persona.
    """
    overrides: Dict[str, Any] = {}
    if parametros:
        overrides["params"] = dict(parametros)
    if representante:
        overrides["rep"] = representante
    return overrides
