"""
COT-36 [Flujo] Orquestación del RFQ.

Bifurcación lógica: avanzar al parsing si el correo cumple con los criterios
de RFQ, o descartar el procesamiento si es trash.

Cadena completa (cableado COT-36)
---------------------------------
    1. html_cleaner      (COT-53)  limpiar el cuerpo del correo
       mapeo_cliente     (COT-55)  resolver el dominio del remitente -> cliente
       extraer_datos_correo (COT-61)  datos comerciales del cuerpo [PENDIENTE]
    2. field_validator   (COT-54)  gate temprano, antes de gastar la visión
    3. vision_pipeline   (COT-62)  leer los dibujos adjuntos
       extractor_resorte (COT-69)  interpretar el JSON del modelo
    4. fusionar          (COT-36)  una sola fuente de verdad, correo + dibujo
    5. field_validator   (COT-54)  validación final sobre el dict fusionado
       motor_factibilidad (COT-75) dictamen contra las directrices de la planta
    6. repositorio_rfq   (COT-56)  alta del RFQ en estado New
       almacen_planos    (COT-56)  persistencia de los planos
       repositorio_rfq   (COT-72)  veredicto del sistema + banderas del RFQ
    7. email_templates   (COT-59)  redactar la respuesta de datos faltantes
       smtp_sender       (COT-57)  despachar en modo <Local>
       graph_sender      (COT-58)  despachar en modo <Token>

El orden respeta la regla definida en COT-36: ``part_number`` y ``material``
pueden venir del cuerpo del correo **o** del dibujo, así que el flujo no
puede declararlos faltantes mirando sólo el correo — la validación completa
se corre después de fusionar ambas fuentes.

El gate temprano de la etapa 2 es la optimización de dos etapas del mismo
comentario: ``customer``, ``volumen`` y ``tiene_adjunto`` vienen sólo del
correo, así que se rechaza antes de gastar la llamada de visión. Mientras la
etapa 1 no exista (COT-61), el gate corre degradado — ver
``campos_gate_temprano``.

Cada etapa posterior a la clasificación está aislada en su propio
``try/except``: un fallo de BD, de visión o de correo saliente registra el
error pero no rompe el ciclo de lectura del buzón.
"""
import logging
import uuid
from typing import Any

import app.rfq.detector as detector
import app.rfq.thread_validator as thread_validator

log = logging.getLogger("cotizador.flujo")

# Clasificaciones posibles
RFQ_NUEVO = "RFQ_NUEVO"
RESPUESTA_RFQ = "RESPUESTA_RFQ"
TRASH = "TRASH"

# Campos que sólo puede llenar la extracción del cuerpo (etapa 1, COT-61).
# Mientras esa etapa no exista, el gate temprano los omite: exigirlos sin
# tener quién los extraiga rechazaría todos los RFQ antes de mirar el dibujo.
# En cuanto extraer_datos_correo() devuelva datos, el gate pasa solo a usar
# field_validator.CAMPOS_SOLO_CORREO completo, sin tocar este módulo.
CAMPOS_DEPENDIENTES_EXTRACCION = ("volumen",)


def clasificar(correo):
    """
    Clasifica el correo entrante:
      - RESPUESTA_RFQ: pertenece al hilo de un RFQ existente (Subtarea 2)
      - RFQ_NUEVO:     contiene patrones clave de RFQ (Subtarea 1)
      - TRASH:         no cumple ningun criterio
    Retorna (clasificacion, rfq_id).
    """
    # Es respuesta de un RFQ existente?
    rfq_id = thread_validator.validar_respuesta(correo)
    if rfq_id:
        return RESPUESTA_RFQ, rfq_id

    # Es un RFQ nuevo? (patrones en asunto y cuerpo)
    if detector.es_rfq(correo.get("asunto", ""), correo.get("cuerpo", "")):
        # Usar el ID del asunto si existe; si no, generar uno interno
        rfq_id = (detector.extraer_id_rfq(correo.get("asunto", ""))
                  or f"INT-{uuid.uuid4().hex[:8].upper()}")
        return RFQ_NUEVO, rfq_id

    return TRASH, None


# --------------------------------------------------------------------------- #
# Etapa 1-2: cuerpo legible y cliente
# --------------------------------------------------------------------------- #

def limpiar_cuerpo(correo):
    """
    Devuelve el cuerpo del correo como texto plano legible (COT-53).

    Los proveedores entregan texto plano cuando existe y HTML como fallback
    (dev_provider) o directamente HTML (Graph), así que la limpieza se aplica
    sólo si el cuerpo trae marcado. Ante cualquier fallo se devuelve el cuerpo
    original: un RFQ no se pierde por no poder limpiarlo.
    """
    cuerpo = correo.get("cuerpo_html") or correo.get("cuerpo") or ""
    if "<" not in cuerpo:
        return cuerpo

    try:
        import app.shared.html_cleaner as html_cleaner
        limpio = html_cleaner.limpiar_html(cuerpo)
        return limpio or cuerpo
    except Exception as error:
        log.warning("No se pudo limpiar el HTML del correo: %s", error)
        return cuerpo


def resolver_cliente(remitente):
    """
    Mapea el remitente a un cliente maestro por su dominio (COT-55).

    Devuelve ``(cliente | None, dominio | None)``. Que no haya cliente no es
    un error: significa que el dominio aún no está dado de alta (fase 2 de
    COT-71). El dominio se conserva para poder identificar al comprador.
    """
    try:
        import app.clients.mapper as mapper
        dominio = mapper.extraer_dominio(remitente)
        cliente = mapper.mapear_cliente(remitente)
        return cliente, dominio
    except Exception as error:
        log.error("Fallo al mapear el cliente de %r: %s", remitente, error)
        return None, None


def preparar_datos_correo(correo, rfq_id):
    """
    Construye el dict de datos del RFQ con lo que se puede saber del correo.

    ``customer`` sale del cliente maestro si el dominio está dado de alta, y
    si no del dominio mismo (según COT-54: "Customer <- Email domain or
    signature", siempre obtenible). Los campos comerciales que hoy nadie
    extrae del cuerpo (``part_number``, ``volumen``, ``material``) quedan en
    ``None`` a la espera de COT-61 o del dibujo.
    """
    cliente, dominio = resolver_cliente(correo.get("remitente"))
    adjuntos = correo.get("adjuntos") or []

    datos = {
        "rfq_id": rfq_id,
        "message_id": correo.get("message_id", ""),
        "remitente": correo.get("remitente", ""),
        "asunto": correo.get("asunto", ""),
        # La fecha del correo se quedaba en `correos_procesados` y no llegaba al
        # RFQ. Es el dato con el que se ordena un histórico, así que va aquí.
        "fecha_correo": correo.get("fecha", ""),
        "cuerpo": limpiar_cuerpo(correo),
        "tiene_adjunto": bool(adjuntos),
        "customer": (cliente or {}).get("razon_social") or dominio,
        "cliente_id": (cliente or {}).get("cliente_id"),
        "dominio": dominio,
        "part_number": None,
        "volumen": None,
        "material": None,
    }
    return datos


def extraer_datos_correo(datos):
    """
    Etapa 1 del orden definido en COT-36: extraer los datos comerciales del
    cuerpo del correo con el modelo de lenguaje (COT-61 / COT-66 / COT-67).

    Devuelve el dict de ``email_extractor.extraer``:
    ``{campos, en_revision, confianzas, requiere_revision, umbral}``. Los
    campos por debajo del umbral **no se usan ni se declaran faltantes**: se
    apartan en ``en_revision`` para que los valide el PM.

    Un fallo del modelo (sin API key, sin red, JSON irrecuperable) no rompe el
    RFQ: se registra y el flujo sigue buscando los datos en el dibujo, que es
    exactamente el comportamiento que había antes de COT-61.
    """
    cuerpo = datos.get("cuerpo")
    if not cuerpo or not cuerpo.strip():
        log.info("Cuerpo vacío; no hay nada que extraer con el modelo.")
        return {}

    try:
        import app.extraction.email_extractor as email_extractor
        return email_extractor.extraer(cuerpo, asunto=datos.get("asunto"))
    except Exception as error:
        log.error("Fallo la extracción del cuerpo (%s); se continúa con el "
                  "dibujo como única fuente.", error)
        return {}


# --------------------------------------------------------------------------- #
# Etapas 3 y 5: validación
# --------------------------------------------------------------------------- #

def campos_gate_temprano(extraccion_correo):
    """
    Campos exigibles en el gate temprano (COT-54).

    Con la etapa 1 funcionando son los tres de ``CAMPOS_SOLO_CORREO``. Sin
    ella, se omiten los que dependen de esa extracción: el gate sigue
    filtrando lo que sí se puede saber (quién escribe y si vino plano) sin
    rechazar RFQ por un dato que nadie está leyendo todavía.
    """
    import app.shared.field_validator as field_validator
    campos = field_validator.CAMPOS_SOLO_CORREO
    if extraccion_correo:
        return campos
    return tuple(c for c in campos if c not in CAMPOS_DEPENDIENTES_EXTRACCION)


# Lo que una respuesta hereda del RFQ al que contesta. Es una lista cerrada a
# propósito: el asunto, el cuerpo, el remitente o los adjuntos son de ESTE
# correo y no se heredan nunca; lo que se arrastra son los datos de la pieza,
# que es lo que la conversación va reuniendo.
_SE_HEREDA_DEL_HILO = (
    "cliente_id", "customer", "nombre_proyecto",
    "part_number", "volumen", "material", "escalones_cantidad",
    "tiene_adjunto", "resorte",
    "moneda", "incoterm", "fecha_entrega_requerida",
    "contacto_nombre", "contacto_correo",
)


def heredar_del_hilo(datos: dict, rfq_id: str) -> list:
    """Rellena lo que la respuesta no trae con lo que el RFQ ya sabía.

    El comprador manda el plano el lunes y el material el martes, y en el
    martes no vuelve a adjuntar nada —los clientes de correo ni siquiera
    adjuntan el original al responder—. Sin memoria, esa respuesta se juzgaba
    sola: sin plano y sin volumen, así que el sistema volvía a pedir lo que ya
    tenía guardado y la conversación no avanzaba nunca.

    Lo que trae el correo nuevo MANDA: si el comprador corrige el material,
    vale el nuevo. Lo de antes sólo rellena huecos.

    Devuelve los nombres de los campos que se heredaron, para el registro.
    """
    import app.rfq.repository as repository

    previos = repository.datos_anteriores(rfq_id) or {}
    heredados = []
    for clave in _SE_HEREDA_DEL_HILO:
        if datos.get(clave) not in (None, "", [], False):
            continue
        valor = previos.get(clave)
        if valor in (None, "", [], False):
            continue
        datos[clave] = valor
        heredados.append(clave)
    return heredados


def volumen_de_escalones(campos):
    """El EAU cuando el comprador mandó una escalera y ningún volumen suelto.

    "The volumes are: 10000, 22000, 50000" es un RFQ con precio por escalones,
    que en resortes es lo normal: no es un correo al que le falte el volumen.
    El modelo lo lee bien y lo guarda en ``escalones_cantidad``; el que se
    ponía estricto era el validador, que exigía ``volumen`` y mandaba al
    comprador a dar un dato que ya había dado.

    Se toma el **escalón mayor** como estimación anual: es el techo de la
    escalera y lo que suele significar el último peldaño. El costeo no se
    entera de nada —ése ya cotizaba la escalera entera, no este número—, así
    que esto sólo llena el hueco del validador y la ficha del RFQ.

    Devuelve ``None`` si ya hay volumen o si no hay escalera que leer.
    """
    if not campos:
        return None
    if campos.get("volumen") not in (None, ""):
        return None
    import app.rfq.costeo as costeo
    # El mismo lector que usa el costeo: aguanta listas, y también cadenas
    # como "10,000, 25000 y 50.000".
    cantidades = costeo.cantidades_del_rfq(campos)
    if not cantidades:
        return None
    mayor = max(cantidades)
    # El lector del costeo trabaja con decimales; una cantidad de piezas no
    # se enseña como "50000.0" en la ficha del RFQ.
    return int(mayor) if float(mayor).is_integer() else mayor


def validar(datos, campos_requeridos=None):
    """Valida los campos obligatorios del RFQ (COT-54)."""
    import app.shared.field_validator as field_validator
    return field_validator.validar_campos_rfq(datos, campos_requeridos)


# --------------------------------------------------------------------------- #
# Etapa 4: dibujos
# --------------------------------------------------------------------------- #

def procesar_dibujos(correo, rfq_id, informe=None):
    """
    Si el correo trae dibujos adjuntos soportados (.pdf/.png/.jpg; .stp/.step
    se omiten por ahora), los envia al modelo de vision, interpreta el JSON y
    persiste las variables fisicas del resorte.

    ``informe`` es un dict opcional que se rellena con POR QUÉ no salió nada:
    sin adjuntos, adjuntos en un formato que no se lee, o una lectura que
    falló. Esa respuesta acaba en la ficha del RFQ, donde antes sólo había
    seis rayas y nadie podía saber si el correo no traía plano o si traía uno
    y ni se miró.

    Espera correo["adjuntos"] = [{"nombre": str, "contenido": bytes}, ...],
    que es lo que ya entregan dev_provider (walk del MIME) y token_provider
    (/attachments de Graph).

    Los imports son perezosos para no exigir anthropic al importar
    este modulo, y para que un fallo de vision no rompa el ciclo de correos.
    """
    anotar = informe.update if isinstance(informe, dict) else (lambda _d: None)

    adjuntos = correo.get("adjuntos") or []
    if not adjuntos:
        log.info("RFQ=%s sin dibujos adjuntos; nada que analizar.", rfq_id)
        anotar({"estado": "sin_adjunto"})
        return []

    # Import perezoso (solo cuando hay algo que analizar)
    import app.persistence.spring_repository as spring_repository
    import app.vision.pipeline as pipeline
    import app.vision.spring_extractor as spring_extractor

    # Lo que el modelo puede leer Y que además es un plano: la firma del
    # correo llega como un adjunto más y por nombre no se distingue de un
    # dibujo, pero mandársela al modelo cuesta una llamada y devuelve un
    # resorte inventado a partir de un logo.
    import app.persistence.blueprint_store as almacen

    soportados = [
        a for a in almacen.solo_planos(adjuntos)
        if (a.get("nombre", "").lower().endswith(pipeline.EXTENSIONES_SOPORTADAS))
    ]
    if not soportados:
        nombres_todos = [a.get("nombre", "?") for a in adjuntos]
        log.info("RFQ=%s: adjuntos presentes pero ninguno es un plano legible (%s).",
                 rfq_id, ", ".join(nombres_todos))
        anotar({"estado": "formato_no_leido", "ficheros": nombres_todos,
                "soportados": list(pipeline.EXTENSIONES_SOPORTADAS)})
        return []

    resultados = []
    nombres = ", ".join(a.get("nombre", "?") for a in soportados)
    try:
        analisis = pipeline.analizar_dibujos(soportados)
        datos = spring_extractor.interpretar(analisis["texto"])
        spring_repository.guardar(
            rfq_id, correo.get("message_id", ""), nombres, datos)
        resultados.append(datos)
        anotar({"estado": "leido", "ficheros": [a.get("nombre", "?") for a in soportados]})
        log.info("RFQ=%s: resorte extraido (listo_para_cotizar=%s).",
                 rfq_id, datos.get("listo_para_cotizar"))
    except Exception as error:  # no romper el ciclo de correos por un dibujo
        log.error("RFQ=%s: fallo al procesar dibujos (%s): %s",
                  rfq_id, nombres, error)
        anotar({"estado": "fallo", "ficheros": [a.get("nombre", "?") for a in soportados],
                "motivo": str(error)})
    return resultados


def fusionar(datos_correo, resortes):
    """
    Fusiona los datos del correo con los del dibujo (COT-36).

    El correo manda: sólo se rellena desde el dibujo lo que el correo no trae.
    ``volumen`` se toma de ``cantidad`` porque es la misma magnitud (EAU)
    vista desde el plano.
    """
    datos = dict(datos_correo)
    if not resortes:
        return datos

    resorte = resortes[0] or {}
    equivalencias = {
        "material": "material",
        "volumen": "cantidad",
        "part_number": "num_parte",
    }
    for campo, origen in equivalencias.items():
        if datos.get(campo) in (None, "") and resorte.get(origen) not in (None, ""):
            datos[campo] = resorte[origen]

    datos["resorte"] = resorte
    datos["listo_para_cotizar"] = resorte.get("listo_para_cotizar")
    return datos


# --------------------------------------------------------------------------- #
# Etapa 5c: factibilidad (COT-72 / COT-74 / COT-75)
# --------------------------------------------------------------------------- #

def dictaminar_factibilidad(datos, rfq_id):
    """Dictamina si el resorte es fabricable, con las directrices vigentes.

    Devuelve el dict de ``engine.evaluar_factibilidad`` o ``None``
    si no se pudo dictaminar (directrices ilegibles, por ejemplo).

    Un fallo aquí **no frena el RFQ**: se registra el error y el RFQ se da de
    alta con ``veredicto_sistema`` en NULL, que es justamente la señal de "sin
    dictaminar" para la pantalla del PM. Dejar de procesar RFQs porque un
    archivo de configuración está roto sería peor que darlos de alta sin
    veredicto.
    """
    try:
        import app.feasibility.engine as engine
        return engine.evaluar_factibilidad(datos)
    except Exception as error:
        log.error("RFQ=%s: no se pudo dictaminar la factibilidad: %s", rfq_id, error)
        return None


def _requiere_revision_de_factibilidad(factibilidad):
    """True si el motor mandó el RFQ al plant manager."""
    if not factibilidad:
        return False
    import app.feasibility.engine as engine
    return factibilidad.get("veredicto") == engine.VEREDICTO_REVISION


def registrar_veredicto(rfq_id, factibilidad, registro):
    """Guarda el veredicto y sus motivos en ``rfqs`` / ``rfq_banderas``.

    Se llama después de ``persistir``: el registro tiene que existir para
    poder marcarlo. Como el resto de las etapas, un fallo de BD se registra
    pero no rompe el ciclo del buzón — el RFQ ya quedó dado de alta.
    """
    if not factibilidad or registro is None:
        return None
    try:
        import app.rfq.repository as repository
        return repository.guardar_veredicto(
            rfq_id, factibilidad, version=registro.get("version"))
    except Exception as error:
        # `exception` y no `error`: esto escribe en columnas concretas de `rfqs`
        # y en `rfq_banderas`, así que cuando falla suele ser el esquema —una
        # migración sin aplicar— y sin la traza no hay forma de saber cuál.
        # Se registró el RFQ pero se perdió su veredicto: es exactamente el dato
        # que COT-76 quiere conservar para entrenar, así que no puede pasar
        # inadvertido en el log.
        log.exception(
            "RFQ=%s: NO SE GUARDÓ EL VEREDICTO (%s). El RFQ quedó dado de alta "
            "sin dictamen; revisa que las migraciones estén aplicadas.",
            rfq_id, error)
        return None


def _nivel_de_motivos(motivos):
    """El nivel del aviso es el del motivo más grave que lo provocó."""
    niveles = {(m.get("nivel") or "").lower() for m in motivos}
    if "crit" in niveles:
        return "crit"
    if "warn" in niveles:
        return "warn"
    return "info"


def _avisar(tipo, rfq_id, titulo, detalle, datos, nivel):
    """Escribe el aviso en el buzón del PM. Devuelve si se pudo.

    Un fallo aquí no frena nada: el RFQ ya quedó en ``RequiresReview`` y sigue
    apareciendo en la cola de revisión, que se deduce del estado. Lo que se
    pierde es la constancia de que se avisó, no el trabajo.
    """
    try:
        import app.notifications.repository as notificaciones
        return notificaciones.crear(
            tipo=tipo, rfq_id=rfq_id, titulo=titulo, detalle=detalle,
            datos=datos, nivel=nivel) is not None
    except Exception as error:
        log.exception("RFQ=%s: no se pudo dejar el aviso para el PM: %s",
                      rfq_id, error)
        return False


def _texto_aviso(cual, cliente):
    """El título del aviso, tal y como lo dice el machote.

    Está en `app/email/templates.py`, junto a los correos: es el mismo texto
    dicho por el otro canal —campana y teléfono en vez de correo—, y cuando la
    empresa cambie el machote no puede quedarse uno de los dos sin cambiar.
    """
    try:
        import app.email.templates as textos
        return (textos.aviso_revision_factibilidad(cliente) if cual == 'revision'
                else textos.aviso_validacion(cliente))
    except Exception:
        return ('Feasibility review required' if cual == 'revision'
                else 'Quote validation required')


def notificar_factibilidad_pm(rfq_id, factibilidad, cliente=None):
    """
    Avisa que un RFQ no pasó las directrices y lo tiene que dictaminar el PM.

    El aviso se guarda en ``notificaciones`` (COT-77) y lo recoge la campana de
    la aplicación. Se guarda además del estado del RFQ, no en vez de él: la
    cola de revisión dice qué espera AHORA, y esto deja constancia de que se
    avisó, cuándo y por qué, que es lo que se puede medir después.

    El sistema nunca declina por su cuenta: si el PM resuelve que no es
    factible, es esa decisión (``rfqs.veredicto_final``) la que dispara el
    correo de declinación al cliente, no este aviso.
    """
    motivos = factibilidad.get("motivos") or []
    detalle = "; ".join(motivo.get("texto", "") for motivo in motivos)
    score = factibilidad.get("score")
    banda = factibilidad.get("banda") or "-"

    log.warning("RFQ=%s A REVISIÓN del PM — score %s (%s), directrices v%s — %s",
                rfq_id, score, banda, factibilidad.get("reglas_version"), detalle)

    notificado = _avisar(
        tipo="factibilidad_revision",
        rfq_id=rfq_id,
        titulo=_texto_aviso('revision', cliente or rfq_id),
        detalle=f"{rfq_id} · {detalle}" if detalle else rfq_id,
        datos={"score": score, "banda": banda, "motivos": motivos,
               "reglas_version": factibilidad.get("reglas_version")},
        nivel=_nivel_de_motivos(motivos),
    )
    return {"rfq_id": rfq_id, "motivos": motivos, "notificado": notificado}


# --------------------------------------------------------------------------- #
# Etapa 6: persistencia (criterio OK)
# --------------------------------------------------------------------------- #

def _estado_revision():
    """Estado con el que se registran los RFQ que debe validar el PM."""
    import app.rfq.repository as repository
    return repository.ESTADO_REVISION


def _estado_incompleto():
    """Estado de los RFQ que se evaluaron pero se quedaron sin datos."""
    import app.rfq.repository as repository
    return repository.ESTADO_INCOMPLETO


def notificar_revision_pm(datos, en_revision, rfq_id):
    """
    Avisa que un RFQ necesita validación humana antes de cotizarse.

    Es el otro aviso de COT-77: aquí el dato existe pero el modelo no se fía de
    él. Va al PM antes de pedirle nada al comprador, porque podría estar
    pidiéndole justo lo que ya mandó.
    """
    detalle = ", ".join(
        f"{campo}={info.get('valor')!r} (confianza {info.get('confianza'):.2f})"
        for campo, info in sorted(en_revision.items())
    )
    log.warning("RFQ=%s REQUIERE REVISIÓN del PM — %s", rfq_id, detalle)

    notificado = _avisar(
        tipo="extraccion_revision",
        rfq_id=rfq_id,
        titulo=f"{rfq_id}: {len(en_revision)} dato(s) extraídos con poca confianza",
        detalle=detalle,
        datos={"campos": en_revision, "customer": datos.get("customer")},
        # `warn` y no `crit`: hay dato, sólo que hay que confirmarlo. Lo crítico
        # se reserva para lo que no se puede fabricar.
        nivel="warn",
    )
    return {"rfq_id": rfq_id, "campos": en_revision, "notificado": notificado}


def persistir(datos, correo, rfq_id, es_seguimiento, estado=None):
    """
    Da de alta el RFQ y guarda los planos (COT-56).

    Se llama cuando la validación fue correcta ("criterio OK") o cuando el
    RFQ va a revisión del PM: en ambos casos el registro debe existir, lo que
    cambia es el ``estado``. El esquema de la BD lo crea ``make db-up``
    (COT-93): este módulo no ejecuta DDL.
    """
    registro = None
    try:
        import app.rfq.repository as repository
        extra = {} if estado is None else {"estado": estado}
        registro = repository.guardar_rfq(
            rfq_id, datos, es_seguimiento=es_seguimiento, **extra)
    except Exception as error:
        # Perder el alta es perder el RFQ entero del histórico, no un campo.
        log.exception("RFQ=%s: NO SE PUDO DAR DE ALTA EN LA BD (%s).",
                      rfq_id, error)

    try:
        import app.persistence.blueprint_store as blueprint_store
        ubicaciones = blueprint_store.guardar_planos(
            rfq_id, correo.get("adjuntos"))
        if registro is not None:
            registro["planos"] = ubicaciones
    except Exception as error:
        log.error("RFQ=%s: no se pudieron guardar los planos: %s", rfq_id, error)

    return registro


# --------------------------------------------------------------------------- #
# Etapa 7: respuesta al comprador
# --------------------------------------------------------------------------- #

# El interruptor y el transporte viven en `correo_saliente`, compartidos con
# la declinación que dispara el PM (COT-72): un solo ENVIO_AUTOMATICO para
# todo lo que sale hacia el cliente.

def _envio_habilitado():
    """Interruptor del envío real de correo (ver ``correo_saliente``)."""
    import app.email.outbound as outbound
    return outbound.envio_habilitado()


def _nombre_comprador(datos):
    """Nombre de cortesía para el saludo, derivado del correo del remitente."""
    import app.email.outbound as outbound
    return outbound.nombre_comprador(datos)


def _despachar(contenido):
    """Envía el correo por el canal del modo activo: SMTP o Graph."""
    import app.email.outbound as outbound
    return outbound.enviar(contenido)


def responder_datos_faltantes(datos, faltantes, rfq_id):
    """
    Construye (COT-59) y despacha (COT-57/58) la petición de datos faltantes.

    Devuelve ``True`` si el correo salió, ``False`` si sólo se construyó
    (envío deshabilitado) o si falló el despacho.
    """
    if not datos.get("remitente"):
        log.warning("RFQ=%s: sin remitente al que responder.", rfq_id)
        return False

    try:
        import app.email.templates as templates
        contenido = templates.construir_correo("datos_faltantes", {
            "destinatario": datos["remitente"],
            "asunto_original": datos.get("asunto") or f"RFQ {rfq_id}",
            # Va en el asunto para que su respuesta se reconozca como parte
            # de este RFQ (app/rfq/thread_validator.py).
            "rfq_id": rfq_id,
            "nombre_comprador": _nombre_comprador(datos),
            "campos_faltantes": list(faltantes),
        })
    except Exception as error:
        log.error("RFQ=%s: no se pudo construir la respuesta: %s", rfq_id, error)
        return False

    if not _envio_habilitado():
        log.info("RFQ=%s: correo de datos faltantes LISTO pero no enviado "
                 "(ENVIO_AUTOMATICO apagado). Para: %s | Faltan: %s",
                 rfq_id, contenido["destinatario"], ", ".join(faltantes))
        return False

    try:
        enviado = _despachar(contenido)
        log.info("RFQ=%s: solicitud de datos faltantes enviada a %s (%s).",
                 rfq_id, contenido["destinatario"], ", ".join(faltantes))
        return bool(enviado)
    except Exception as error:
        log.error("RFQ=%s: fallo al enviar la solicitud de datos: %s",
                  rfq_id, error)
        return False


# --------------------------------------------------------------------------- #
# Orquestación
# --------------------------------------------------------------------------- #

def avanzar_a_parsing(correo, clasificacion, rfq_id):
    """
    Recorre la cadena completa del RFQ y devuelve el resultado del proceso:

    ``{rfq_id, clasificacion, etapa, es_valido, campos_faltantes, cliente_id,
    registro, resorte, en_revision, factibilidad}``.

    ``etapa`` indica dónde terminó:

    * ``"gate_temprano"``    — rechazado antes de gastar la visión.
    * ``"datos_faltantes"``  — faltó información tras leer el dibujo.
    * ``"requiere_revision"`` — se extrajo todo, pero algún dato quedó por
      debajo del umbral de confianza: se da de alta marcado para el PM.
    * ``"revision_factibilidad"`` — los datos son buenos, pero el resorte no
      pasa las directrices de la planta: se da de alta marcado para el PM,
      que es quien dictamina si se declina.
    * ``"alta"``             — el RFQ quedó registrado en estado New.

    La revisión gana sobre los datos faltantes: si el modelo leyó un campo con
    poca confianza, pedirle al comprador un dato que quizá ya mandó es peor
    que hacer que una persona lo confirme.

    Por lo mismo, la factibilidad **no se dictamina** en la rama de confianza
    baja: dictaminar sobre medidas que el propio modelo marcó como dudosas
    produciría motivos que nadie puede defender frente al cliente.
    """
    log.info("PARSING [%s] RFQ=%s | %s | %s",
             clasificacion, rfq_id, correo.get("remitente"),
             correo.get("asunto"))

    # Asociar el correo al historial del RFQ
    thread_validator.registrar_en_historial(
        rfq_id, correo.get("message_id", ""), correo.get("asunto", ""))

    resultado: dict[str, Any] = {
        "rfq_id": rfq_id,
        "clasificacion": clasificacion,
        "etapa": None,
        "es_valido": False,
        "campos_faltantes": [],
        "cliente_id": None,
        "registro": None,
        "resorte": None,
        "en_revision": {},
        "factibilidad": None,
    }

    # 1-2. Cuerpo legible + cliente + extracción de datos del correo (COT-61)
    datos = preparar_datos_correo(correo, rfq_id)
    resultado["cliente_id"] = datos.get("cliente_id")

    extraccion = extraer_datos_correo(datos)
    campos_correo = extraccion.get("campos") or {}
    en_revision = extraccion.get("en_revision") or {}
    datos.update({k: v for k, v in campos_correo.items() if v not in (None, "")})
    if en_revision:
        datos["en_revision"] = en_revision
        resultado["en_revision"] = en_revision

    escalera = volumen_de_escalones(datos)
    if escalera:
        datos["volumen"] = escalera
        log.info("RFQ=%s: el correo trae escalones y ningún volumen suelto; "
                 "se toma el mayor (%s) como EAU.", rfq_id, escalera)

    # Si esto es una respuesta, el RFQ ya sabe cosas: el plano que vino el
    # primer día, las cantidades, el número de parte. Se heredan antes de
    # juzgar si falta algo.
    if clasificacion == RESPUESTA_RFQ:
        heredados = heredar_del_hilo(datos, rfq_id)
        if heredados:
            log.info("RFQ=%s: la respuesta hereda del hilo: %s.",
                     rfq_id, ", ".join(heredados))

    # 3. Gate temprano: no gastar la llamada de visión si ni siquiera sabemos
    #    quién escribe, no vino un plano, o (con COT-61 listo) falta el volumen.
    campos = campos_gate_temprano(campos_correo)
    temprano = validar(datos, campos)
    if not temprano["es_valido"]:
        faltantes = temprano["campos_faltantes"]
        log.info("RFQ=%s rechazado en el gate temprano; faltan: %s",
                 rfq_id, ", ".join(faltantes))
        resultado["etapa"] = "gate_temprano"
        resultado["campos_faltantes"] = faltantes
        # Se da de alta igual (COT-76). Un RFQ que no llegó a evaluarse del todo
        # sigue siendo un RFQ que entró, y su desenlace —qué faltaba, de qué
        # cliente, con qué asunto— es justo lo que necesita el modelo de
        # predicción de factibilidad para aprender a olerlos antes.
        datos["campos_faltantes"] = faltantes
        datos["motivo_incompleto"] = "gate_temprano"
        resultado["registro"] = persistir(
            datos, correo, rfq_id,
            es_seguimiento=(clasificacion == RESPUESTA_RFQ),
            estado=_estado_incompleto())
        responder_datos_faltantes(datos, faltantes, rfq_id)
        return resultado

    # 4. Dibujos + fusión de ambas fuentes
    lectura_plano = {}
    resortes = procesar_dibujos(correo, rfq_id, lectura_plano)
    datos = fusionar(datos, resortes)
    # Por qué el resorte salió (o no) del plano. Se guarda con el RFQ para que
    # la ficha lo pueda decir en vez de enseñar seis rayas.
    if lectura_plano:
        datos["lectura_plano"] = lectura_plano
    resultado["resorte"] = datos.get("resorte")

    # 5. Validación completa (correo + dibujo)
    completa = validar(datos)
    resultado["es_valido"] = completa["es_valido"]
    resultado["campos_faltantes"] = completa["campos_faltantes"]

    # 5b. Confianza baja: el dato existe pero no es de fiar. Va al PM antes de
    #     pedirle nada al comprador (podría estar pidiéndole lo que ya mandó).
    if en_revision:
        resultado["etapa"] = "requiere_revision"
        resultado["registro"] = persistir(
            datos, correo, rfq_id,
            es_seguimiento=(clasificacion == RESPUESTA_RFQ),
            estado=_estado_revision())
        notificar_revision_pm(datos, en_revision, rfq_id)
        return resultado

    if not completa["es_valido"]:
        log.info("RFQ=%s incompleto tras el dibujo; faltan: %s",
                 rfq_id, ", ".join(completa["campos_faltantes"]))
        resultado["etapa"] = "datos_faltantes"
        datos["campos_faltantes"] = completa["campos_faltantes"]
        datos["motivo_incompleto"] = "datos_faltantes"
        resultado["registro"] = persistir(
            datos, correo, rfq_id,
            es_seguimiento=(clasificacion == RESPUESTA_RFQ),
            estado=_estado_incompleto())
        responder_datos_faltantes(datos, completa["campos_faltantes"], rfq_id)
        return resultado

    # 5c. Factibilidad: el resorte se puede fabricar con las directrices de la
    #     planta (COT-74/75). Si no pasa, el RFQ igual se da de alta, pero
    #     marcado para que lo dictamine el plant manager. El sistema no declina.
    factibilidad = dictaminar_factibilidad(datos, rfq_id)
    resultado["factibilidad"] = factibilidad
    a_revision = _requiere_revision_de_factibilidad(factibilidad)

    # 6. Alta del RFQ y persistencia de planos
    resultado["etapa"] = "revision_factibilidad" if a_revision else "alta"
    resultado["registro"] = persistir(
        datos, correo, rfq_id,
        es_seguimiento=(clasificacion == RESPUESTA_RFQ),
        estado=_estado_revision() if a_revision else None)

    # 6b. El veredicto y sus motivos, donde los va a leer la pantalla del PM.
    registrar_veredicto(rfq_id, factibilidad, resultado["registro"])

    if a_revision:
        notificar_factibilidad_pm(
            rfq_id, factibilidad,
            cliente=datos.get("cliente_id") or datos.get("customer")
                    or datos.get("dominio"))
        return resultado

    log.info("RFQ=%s dado de alta (cliente=%s).",
             rfq_id, datos.get("cliente_id") or datos.get("dominio"))
    # Pasó las directrices, pero sigue esperando al PM: nada sale al cliente
    # sin su aprobación. Que la campana lo diga, igual que cuando no pasa.
    notificar_alta_pm(rfq_id, datos, factibilidad)
    return resultado


def notificar_alta_pm(rfq_id, datos, factibilidad):
    """Avisa que un RFQ factible quedó en ``New`` y espera la aprobación del PM.

    Es el mismo buzón que el de la revisión; el nivel es ``info`` porque no
    hay nada que corregir, sólo que aprobar y ofertar.
    """
    factibilidad = factibilidad or {}      # el motor pudo fallar: se avisa igual
    pn = datos.get("part_number") or "-"
    cliente = datos.get("customer") or datos.get("dominio") or "-"
    return _avisar(
        tipo="factibilidad_revision",
        rfq_id=rfq_id,
        titulo=_texto_aviso('validacion', cliente),
        detalle=f"{rfq_id} · PN {pn} · score {factibilidad.get('score')} "
                f"({factibilidad.get('banda') or '-'})",
        datos={"score": factibilidad.get("score"), "banda": factibilidad.get("banda"),
               "motivos": factibilidad.get("motivos") or []},
        nivel="info",
    )


def descartar(correo):
    """Descarta el procesamiento: el correo no es un RFQ (trash)."""
    log.info("TRASH descartado | %s | %s",
             correo.get("remitente"), correo.get("asunto"))


def procesar(correo):
    """
    ===== BIFURCACION LOGICA =====
    Si cumple criterios de RFQ -> avanzar al parsing.
    Si es trash               -> descartar el procesamiento.
    Retorna la clasificacion aplicada.
    """
    clasificacion, rfq_id = clasificar(correo)

    if clasificacion in (RFQ_NUEVO, RESPUESTA_RFQ):
        avanzar_a_parsing(correo, clasificacion, rfq_id)
    else:
        descartar(correo)

    return clasificacion
