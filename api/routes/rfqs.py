"""API routes — RFQ CRUD and PM decision endpoints.

GET   /api/rfqs              → list all RFQs
GET   /api/rfqs/{rfq_id}     → detail with datos_json, banderas, resorte
POST  /api/rfqs/{rfq_id}/approve  → PM approves
POST  /api/rfqs/{rfq_id}/decline  → PM declines
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_db
from api.models.schemas import (
    OfertaRequest,
    PMDecisionRequest,
    PMDecisionResponse,
    RecalculoRequest,
    RFQDetail,
    RFQListResponse,
    RFQSummary,
)
from api.security import exige
from app.auth.tokens import UsuarioSesion
from app.rfq import costeo as costeo_rfq

log = logging.getLogger("cotizador.api.rfqs")

router = APIRouter(prefix="/api/rfqs", tags=["rfqs"])


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("", response_model=RFQListResponse)
def list_rfqs(
    estado: Optional[str] = Query(None, description="Filter by estado"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """Lists RFQs ordered by most recent first."""
    conditions = []
    params = []

    if estado:
        conditions.append("r.estado = %s")
        params.append(estado)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql_count = f"SELECT COUNT(*) FROM rfqs r {where};"
    sql_list = f"""
        SELECT r.id, r.rfq_id, r.version, r.cliente_id, r.nombre_proyecto,
               r.part_number, r.volumen, r.material, r.estado, r.message_id,
               r.veredicto_sistema, r.veredicto_final, r.score,
               r.fecha_registro::text
        FROM rfqs r
        {where}
        ORDER BY r.fecha_registro DESC
        LIMIT %s OFFSET %s;
    """

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_count, params)
            total = cur.fetchone()[0]

            cur.execute(sql_list, params + [limit, offset])
            rows = cur.fetchall()

    columns = [
        "id", "rfq_id", "version", "cliente_id", "nombre_proyecto",
        "part_number", "volumen", "material", "estado", "message_id",
        "veredicto_sistema", "veredicto_final", "score", "fecha_registro",
    ]

    rfqs = [RFQSummary(**dict(zip(columns, row))) for row in rows]
    return RFQListResponse(rfqs=rfqs, total=total)


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------

@router.get("/{rfq_id}", response_model=RFQDetail)
def get_rfq(
    rfq_id: str,
    version: Optional[int] = None,
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """Returns the detail of a specific RFQ (latest version by default)."""
    version_clause = "AND r.version = %s" if version else ""
    order = "" if version else "ORDER BY r.version DESC LIMIT 1"

    sql = f"""
        SELECT r.id, r.rfq_id, r.version, r.cliente_id, r.nombre_proyecto,
               r.part_number, r.volumen, r.material, r.estado, r.message_id,
               r.veredicto_sistema, r.veredicto_final, r.score,
               r.fecha_registro::text, r.datos_json, r.notas
        FROM rfqs r
        WHERE r.rfq_id = %s {version_clause}
        {order};
    """
    params = [rfq_id] + ([version] if version else [])

    sql_banderas = """
        SELECT b.nivel, b.titulo, b.codigo, b.datos
        FROM rfq_banderas b
        WHERE b.rfq_version_id = %s
        ORDER BY b.id;
    """

    sql_resorte = """
        SELECT datos_json
        FROM resortes_cotizacion
        WHERE rfq_id = %s
        ORDER BY id DESC
        LIMIT 1;
    """

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"RFQ {rfq_id} not found")

            columns = [
                "id", "rfq_id", "version", "cliente_id", "nombre_proyecto",
                "part_number", "volumen", "material", "estado", "message_id",
                "veredicto_sistema", "veredicto_final", "score",
                "fecha_registro", "datos_json", "notas",
            ]
            data = dict(zip(columns, row))
            rfq_row_id = data["id"]

            # Banderas
            banderas = []
            try:
                cur.execute(sql_banderas, (rfq_row_id,))
                # `codigo` y `datos` pueden venir vacíos: son de las banderas
                # guardadas a partir de la migración 022. Sin ellos la
                # pantalla usa el título, que es el de siempre.
                banderas = [{"nivel": r[0], "titulo": r[1],
                             "codigo": r[2], "datos": r[3] or {}}
                            for r in cur.fetchall()]
            except Exception:
                pass  # Table might not have rfq_banderas yet

            # Resorte
            resorte = None
            try:
                cur.execute(sql_resorte, (rfq_id,))
                resorte_row = cur.fetchone()
                if resorte_row and resorte_row[0]:
                    crudo = resorte_row[0]
                    resorte = crudo if isinstance(crudo, dict) else json.loads(crudo)
            except Exception:
                pass

    # datos_json may already be a dict (psycopg2 auto-parses JSONB)
    datos = data.get("datos_json")
    if datos and not isinstance(datos, dict):
        try:
            datos = json.loads(datos)
        except (TypeError, ValueError):
            datos = {}
    data["datos_json"] = datos

    return RFQDetail(**data, banderas=banderas, resorte=resorte)


# ---------------------------------------------------------------------------
# PM Decisions
# ---------------------------------------------------------------------------

@router.post("/{rfq_id}/approve", response_model=PMDecisionResponse)
def approve_rfq(
    rfq_id: str,
    body: PMDecisionRequest,
    usuario: UsuarioSesion = Depends(exige("rfq:dictaminar")),
):
    """El Plant Manager aprueba un RFQ y sigue a cotización.

    Quién aprueba sale del token, no del cuerpo de la petición: antes el
    navegador mandaba el nombre y la bitácora registraba lo que quisiera poner
    quien llamara al endpoint.
    """
    log.info("RFQ %s aprobado por %s.", rfq_id, usuario.correo)
    try:
        import app.feasibility.pm_decision as pm_decision
        result = pm_decision.aprobar(
            rfq_id,
            nota=body.nota,
            usuario=usuario.correo,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("Failed to approve RFQ %s", rfq_id)
        raise HTTPException(status_code=500, detail=str(e))

    return PMDecisionResponse(**result)


@router.post("/{rfq_id}/decline", response_model=PMDecisionResponse)
def decline_rfq(
    rfq_id: str,
    body: PMDecisionRequest,
    usuario: UsuarioSesion = Depends(exige("rfq:dictaminar")),
):
    """El Plant Manager declina un RFQ y se envía el correo de declinación.

    Este es el endpoint con consecuencias hacia fuera de la empresa: manda un
    correo al comprador. Sin sesión estaba abierto a cualquiera con la URL.
    """
    log.info("RFQ %s declinado por %s (enviar_correo=%s).",
             rfq_id, usuario.correo, body.enviar_correo)
    try:
        import app.feasibility.pm_decision as pm_decision
        result = pm_decision.declinar(
            rfq_id,
            nota=body.nota,
            usuario=usuario.correo,
            destinatario=body.destinatario,
            enviar_correo=body.enviar_correo,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        log.exception("Failed to decline RFQ %s", rfq_id)
        raise HTTPException(status_code=500, detail=str(e))

    return PMDecisionResponse(**result)


@router.post("/{rfq_id}/send-back", response_model=PMDecisionResponse)
def send_back_rfq(
    rfq_id: str,
    body: PMDecisionRequest,
    usuario: UsuarioSesion = Depends(exige("rfq:dictaminar")),
):
    """El Plant Manager DEVUELVE el RFQ con una nota: ni aprueba ni declina.

    No sale nada hacia el comprador. Queda en revisión con la nota debajo y
    un aviso en el buzón para quien cotiza.
    """
    try:
        import app.feasibility.pm_decision as pm_decision
        result = pm_decision.devolver(rfq_id, nota=body.nota, usuario=usuario.correo)
    except ValueError as e:
        # 404 si no existe; 422 si falta la nota, que es un error del cliente.
        codigo = 404 if "No existe" in str(e) else 422
        raise HTTPException(status_code=codigo, detail=str(e))
    except Exception as e:
        log.exception("Failed to send back RFQ %s", rfq_id)
        raise HTTPException(status_code=500, detail=str(e))
    return PMDecisionResponse(**result)


# ---------------------------------------------------------------------------
# La ventana de revisión del PM
# ---------------------------------------------------------------------------
#
# Todo lo que la ventana pinta, en una sola respuesta: quién pide qué, lo que
# extrajo el sistema del correo y del plano, el dictamen de factibilidad, y
# los TRAMOS COSTEADOS con el motor (app/rfq/costeo.py): precio, margen,
# cascada, material, ruta, ingreso y C/CV por hora, uno por cada cantidad que
# venía en el RFQ. La oferta al cliente sale del mismo costeo.

@router.get("/{rfq_id}/revision")
def revision_rfq(
    rfq_id: str,
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """Todo lo que necesita la ventana de revisión del PM, ya costeado."""
    detalle = get_rfq(rfq_id, None, usuario)          # reutiliza la carga y el 404
    resorte = detalle.resorte or {}

    # Esta es la ventana donde se APRUEBA o se DECLINA. Si el resorte no trae
    # diámetro de alambre y hay plano guardado, se lee aquí con la API antes
    # de enseñar nada: dictaminar factibilidad sobre un RFQ cuyo dibujo nunca
    # se leyó es dictaminar sobre seis rayas. Leerlo después de aprobar no
    # sirve —la decisión ya está tomada—.
    #
    # Sólo se gasta la llamada cuando falta el calibre Y hay plano, así que
    # abrir la ventana de un RFQ ya leído no cuesta nada.
    import app.rfq.relectura as relectura
    asegurado = relectura.asegurar_resorte(
        rfq_id, resorte, message_id=detalle.message_id or "")

    return _ventana(detalle, usuario,
                    resorte=asegurado["resorte"] or {},
                    lectura=asegurado["lectura"])


def _ventana(detalle, usuario, resorte=None, lectura=None, recalculo=None):
    """La respuesta de la ventana de revisión, en un solo sitio.

    La arman dos caminos —abrirla y recalcularla— y tienen que devolver lo
    mismo: si el PM pulsa «Recalcular» y recibe una respuesta con otra forma,
    la pantalla tendría que saber repintarse de dos maneras distintas, y tarde
    o temprano una de las dos se queda atrás.
    """
    rfq_id = detalle.rfq_id
    datos = detalle.datos_json or {}
    resorte = resorte if resorte is not None else (detalle.resorte or {})
    # El dictamen recién hecho manda sobre el que estaba guardado: es el que
    # corresponde a las cotas que el PM tiene delante.
    factibilidad = ((recalculo or {}).get("factibilidad")
                    or datos.get("factibilidad") or {})
    banderas = detalle.banderas
    veredicto_sistema = detalle.veredicto_sistema
    score_rfq = detalle.score
    if recalculo and recalculo.get("factibilidad"):
        veredicto_sistema = factibilidad.get("veredicto") or veredicto_sistema
        score_rfq = factibilidad.get("score", score_rfq)
        banderas = [{"nivel": m.get("nivel"), "titulo": m.get("texto"),
                     "codigo": m.get("codigo"),
                     "datos": {k: v for k, v in m.items()
                               if k not in ("nivel", "texto", "codigo")}}
                    for m in (factibilidad.get("motivos") or [])]

    lectura = ({k: v for k, v in lectura.items() if k != "resorte"}
               if lectura else None)

    costeado = costeo_rfq.costear(rfq_id, datos, resorte, detalle.material)

    return {
        "rfq": {
            "rfq_id": detalle.rfq_id, "version": detalle.version,
            "estado": detalle.estado, "part_number": detalle.part_number,
            "cliente_id": detalle.cliente_id,
            "customer": datos.get("customer") or detalle.cliente_id,
            "remitente": datos.get("remitente"),
            "asunto": datos.get("asunto"),
            "fecha": detalle.fecha_registro,
            "tipo_resorte": resorte.get("tipo_resorte"),
            "veredicto_sistema": veredicto_sistema,
            "veredicto_final": detalle.veredicto_final,
            "score": costeo_rfq.num(score_rfq),
            "notas": detalle.notas,
        },
        "comunes": costeado["comunes"],
        "cantidades": costeado["cantidades"],
        "tramos": costeado["tramos"],
        "factibilidad": {
            "veredicto": factibilidad.get("veredicto"),
            "score": costeo_rfq.num(factibilidad.get("score")),
            "banda": factibilidad.get("banda"),
            "motivos": factibilidad.get("motivos") or [],
        },
        "banderas": banderas,
        # La geometría con la que se está dictaminando, para que se vea en la
        # ventana y no haya que abrir la ficha para saber si hay cotas.
        "resorte": {
            "tipo": resorte.get("tipo_resorte"),
            "diametro_alambre_mm": costeo_rfq.num(resorte.get("diametro_alambre_mm")),
            "diametro_exterior_mm": costeo_rfq.num(resorte.get("diametro_exterior_mm")),
            "longitud_libre_mm": costeo_rfq.num(resorte.get("longitud_libre_mm")),
            "espiras_totales": costeo_rfq.num(resorte.get("numero_espiras_totales")),
            "confianza": costeo_rfq.num(resorte.get("confianza")),
        },
        # Si hizo falta leer el plano al abrir esta ventana, qué salió.
        # `None` = no hizo falta, el resorte ya estaba completo.
        "lectura_plano": lectura,
        "en_revision": datos.get("en_revision") or {},
        "campos_faltantes": datos.get("campos_faltantes") or [],
        "costeo": costeado["costeo"],
        "error_costeo": costeado["error_costeo"],
        "puede_dictaminar": usuario.puede("rfq:dictaminar"),
    }


@router.post("/{rfq_id}/recalcular")
def recalcular_rfq(
    rfq_id: str,
    body: RecalculoRequest,
    usuario: UsuarioSesion = Depends(exige("rfq:dictaminar")),
):
    """Rehace el dictamen con lo que el PM corrija, y con el plano si lo pide.

    El veredicto de factibilidad se calculaba una sola vez, al entrar el
    correo, y se quedaba grabado. Eso dejaba al PM dictaminando sobre datos
    viejos en dos casos que pasan a diario: el plano se lee después y aparecen
    cotas que antes no estaban, o el PM mira el dibujo y corrige un valor que
    el modelo leyó mal. Ninguno de los dos tenía dónde ir.

    Pide ``rfq:dictaminar`` —no ``rfq:leer``— porque esto reescribe el
    veredicto del sistema y sus banderas, y porque leer el plano gasta una
    llamada al modelo.

    Devuelve la ventana entera, ya recalculada, para que la pantalla repinte
    sin volver a pedirla.
    """
    detalle = get_rfq(rfq_id, None, usuario)          # 404 si no existe
    resorte = detalle.resorte or {}
    lectura = None

    if body.leer_plano:
        # A petición expresa: se relee aunque el resorte ya tenga cotas. El PM
        # puede querer las del dibujo justamente porque duda de las que hay.
        import app.rfq.relectura as relectura
        lectura = relectura.releer(rfq_id, message_id=detalle.message_id or "")
        if lectura["estado"] == "leido" and lectura["resorte"]:
            resorte = lectura["resorte"]

    import app.rfq.recalculo as recalculo_mod
    recalculo = recalculo_mod.recalcular(
        rfq_id, resorte, ajustes=body.ajustes, usuario=usuario.correo,
        version=detalle.version, message_id=detalle.message_id or "")

    log.info("RFQ %s recalculado por %s (plano=%s, tocados=%s).",
             rfq_id, usuario.correo, body.leer_plano,
             ", ".join(recalculo["tocados"]) or "nada")

    ventana = _ventana(detalle, usuario,
                       resorte=recalculo["resorte"], lectura=lectura,
                       recalculo=recalculo)
    ventana["recalculo"] = {
        "tocados": recalculo["tocados"],
        "guardado": recalculo["guardado"],
        "error": recalculo["error"],
    }
    return ventana


# ---------------------------------------------------------------------------
# Abrir la cotización completa con lo que trajo el correo
# ---------------------------------------------------------------------------
#
# "Abrir cotización completa" lleva a la calculadora, y la calculadora tiene
# que abrirse YA LLENA: cliente, número de parte, material, diámetro, peso y un
# tramo por cada cantidad del correo. Antes abría en blanco y decía "Needs the
# customer, at least one quantity before it can be approved" — es decir, había
# que volver a teclear a mano lo que el sistema acababa de leer.
#
# Lo que se manda es el MISMO PN que se le pasa al motor para costear, y tiene
# la forma exacta del borrador de la calculadora, así que allí se adopta tal
# cual. Si el número que ve el PM y el que abre la hoja salieran de dos sitios
# distintos, tarde o temprano no coincidirían.


def _planos_listados(rfq_id: str) -> list:
    """Los planos guardados de este RFQ: primero la base, luego el disco.

    La base manda porque es lo único que ven los dos lados: el lector de
    escritorio guarda en SU computadora y el servidor en un disco que se borra
    al desplegar. El disco se sigue mirando para los RFQ de antes de que esto
    existiera.
    """
    import app.persistence.blueprint_store as almacen

    de_base = almacen.listar_de_base(rfq_id)
    if de_base:
        return [{"nombre": p["nombre"], "bytes": p["bytes"]} for p in de_base]

    carpeta = _carpeta_de_planos(rfq_id)
    if carpeta is None:
        return []
    return [{"nombre": h.name, "bytes": h.stat().st_size}
            for h in sorted(carpeta.iterdir()) if h.is_file()]


@router.get("/{rfq_id}/cotizacion-inicial")
def cotizacion_inicial(
    rfq_id: str,
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """El PN y la cabecera con los que la calculadora abre este RFQ."""
    detalle = get_rfq(rfq_id, None, usuario)          # reutiliza la carga y el 404
    datos = detalle.datos_json or {}
    resorte = detalle.resorte or {}

    # Abrir la cotización completa tiene que abrirla COMPLETA. Si el resorte
    # no trae diámetro de alambre —porque el día que entró el correo el
    # formato no estaba soportado, o la firma se coló como si fuera el plano,
    # o el modelo se atragantó— se vuelve a leer aquí el plano guardado con la
    # API de visión, y el resultado queda persistido para la ficha y el
    # costeo. El PM no tiene por qué saber que aquel día falló, ni volver a
    # subir un archivo que el sistema ya tiene.
    import app.rfq.relectura as relectura
    asegurado = relectura.asegurar_resorte(
        rfq_id, resorte, message_id=datos.get("message_id") or "")
    resorte = asegurado["resorte"] or {}
    # Sin el resorte entero dentro: ya va aparte en esta misma respuesta.
    lectura = ({k: v for k, v in asegurado["lectura"].items() if k != "resorte"}
               if asegurado["lectura"] else None)

    armado = costeo_rfq.pn_inicial(rfq_id, datos, resorte, detalle.material)
    pn = armado["pn"]

    # La ficha del cliente, si el dominio del remitente ya estaba dado de alta.
    # La calculadora tiene su propio catálogo de clientes, y con esto puede
    # darlo de alta allí sin que nadie teclee dos veces lo mismo: el alta la
    # decidió Pohua cuando registró el dominio, aquí sólo se copia.
    cliente = None
    if detalle.cliente_id:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT razon_social, payment_terms FROM clientes "
                    "WHERE cliente_id = %s;", (detalle.cliente_id,))
                fila = cur.fetchone()
        if fila:
            cliente = {"codigo": detalle.cliente_id,
                       "razon_social": fila[0], "payment_terms": fila[1]}

    # El número de parte del correo manda sobre el identificador del RFQ: es lo
    # que el cliente escribe en su pedido y lo que va impreso en la oferta.
    if pn and detalle.part_number:
        pn["pn"] = detalle.part_number

    return {
        "rfq_id": detalle.rfq_id,
        "pn": pn,
        "header": {
            # El nombre tal como vino; la calculadora lo casa contra su
            # catálogo de clientes y, si no está, lo deja dicho en vez de
            # inventarse un código.
            "customer": datos.get("customer") or detalle.cliente_id,
            # Y el código con el que está dado de alta en Pohua: el catálogo de
            # la calculadora a veces guarda el código y no el nombre, así que
            # van los dos y allí se prueba con ambos.
            "cliente_id": detalle.cliente_id,
            # Dado de alta en Pohua: nombre y términos tal como están en la
            # base. Si viene, la calculadora puede copiarlo a su catálogo.
            "cliente": cliente,
            "asunto": datos.get("asunto"),
            "remitente": datos.get("remitente"),
            "contacto": datos.get("contacto_nombre"),
            # Lo que el comprador pidió y no cabe en ninguna casilla: va a las
            # notas internas del PN, que es donde se lee antes de cotizar.
            "notas": datos.get("notas"),
            "entrega": datos.get("fecha_entrega_requerida"),
            "moneda": datos.get("moneda"),
            "incoterm": datos.get("incoterm"),
        },
        # La geometría, para la pestaña de resortes. En mm, como la guarda el
        # extractor; la calculadora de resortes ya sabe convertir.
        "resorte": {
            "tipo": resorte.get("tipo_resorte"),
            "diametro_alambre_mm": costeo_rfq.num(resorte.get("diametro_alambre_mm")),
            "diametro_exterior_mm": costeo_rfq.num(resorte.get("diametro_exterior_mm")),
            "diametro_interior_mm": costeo_rfq.num(resorte.get("diametro_interior_mm")),
            "longitud_libre_mm": costeo_rfq.num(resorte.get("longitud_libre_mm")),
            "longitud_cuerpo_mm": costeo_rfq.num(resorte.get("longitud_cuerpo_mm")),
            "espiras_totales": costeo_rfq.num(resorte.get("numero_espiras_totales")),
            "material_texto": resorte.get("material") or detalle.material,
            "acabado": resorte.get("acabado"),
        },
        # Los dibujos que venían en el correo, para dejarlos puestos en la
        # casilla de "AI Read Drawing" sin ir a buscarlos otra vez al buzón.
        "planos": _planos_listados(rfq_id),
        # Si hizo falta releer el plano aquí mismo, qué salió. `None` cuando
        # el resorte ya venía completo y no se gastó ninguna llamada.
        "lectura_plano": lectura,
        # Lo que el catálogo no pudo resolver: la calculadora lo enseña para
        # que se capture allí, que es donde se captura.
        "faltantes": armado["faltantes"],
        "error": armado["error"],
    }


# ---------------------------------------------------------------------------
# La oferta al cliente (app/rfq/oferta.py)
# ---------------------------------------------------------------------------
#
# GET  /{id}/oferta       → qué saldría: destinatario, tramos, si está lista
# GET  /{id}/oferta/pdf   → el PDF, para verlo antes de mandarlo
# POST /{id}/oferta       → generar el PDF, mandar el correo, dejar constancia

def _opciones_oferta(body) -> dict:
    return {k: v for k, v in (body.model_dump() if body else {}).items()
            if k != "forzar" and v not in (None, "")}


@router.get("/{rfq_id}/oferta")
def ver_oferta(
    rfq_id: str,
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """Vista previa de la oferta: lo que iría en el correo y en el PDF."""
    import app.rfq.oferta as oferta
    try:
        prep = oferta.preparar(rfq_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    rfq = prep["rfq"]
    return {
        "rfq_id": rfq_id, "estado": rfq["estado"],
        "listo": prep["listo"], "motivos": prep["motivos"],
        # Los mismos motivos con su código, para decirlos en el idioma puesto.
        "motivos_i18n": prep.get("motivos_i18n") or [],
        "correo": prep["correo"],
        "pdf": prep["pdf"],
        "costeo": prep["costeado"]["costeo"],
        "oferta_anterior": (rfq["datos"] or {}).get("oferta"),
        # El aviso de "no va a salir" que enseña el diálogo mira el
        # interruptor MANUAL, que es el que decide este envío: con el del
        # robot apagado, la oferta sale igual y decir lo contrario sería
        # mentirle a quien está a punto de pulsar.
        "envio_habilitado": _outbound().envio_habilitado(manual=True),
        # Distinto del interruptor: esto es si el servidor TIENE con qué
        # mandar. Va aquí para que se vea al abrir el diálogo y no al pulsar,
        # que es cuando se veía —con el PDF ya generado y un error que
        # nombraba las variables de SMTP aunque el modo fuera otro—.
        "envio_posible": _outbound().diagnostico_envio(),
        "puede_enviar": usuario.puede("rfq:dictaminar"),
    }


def _outbound():
    import app.email.outbound as outbound
    return outbound


# ---------------------------------------------------------------------------
# Los planos que venían en el correo
# ---------------------------------------------------------------------------
#
# El comprador manda el dibujo adjunto y el sistema lo guarda al dar de alta el
# RFQ (app/persistence/blueprint_store.py: PLANOS_DIR/<rfq_id>/<nombre>). Hasta
# ahora ese fichero no volvía a salir de ahí: para leerlo en la calculadora
# había que ir a buscarlo al correo y subirlo a mano, teniendo el sistema el
# mismo fichero guardado.


def _carpeta_de_planos(rfq_id: str):
    """La carpeta donde quedaron los planos de este RFQ, si existe.

    El saneado del nombre vive en el almacén: tres sitios lo necesitaban
    —listar, descargar y releer el plano— y no puede tener tres copias.
    """
    import app.persistence.blueprint_store as almacen
    return almacen.carpeta_de(rfq_id)


@router.get("/{rfq_id}/planos")
def planos_del_rfq(
    rfq_id: str,
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """Qué dibujos llegaron con este RFQ y cuánto pesan.

    Lista vacía cuando no hay ninguno: un RFQ puede llegar sin plano, y eso no
    es un error. Tampoco lo es que el fichero ya no esté —el disco del
    servidor es de usar y tirar—; en ese caso se dice, que es distinto de
    decir que el correo no traía nada.
    """
    planos = _planos_listados(rfq_id)
    return {"planos": planos, "guardados": bool(planos)}


@router.post("/{rfq_id}/releer-plano")
def releer_plano_del_rfq(
    rfq_id: str,
    usuario: UsuarioSesion = Depends(exige("rfq:dictaminar")),
):
    """Vuelve a leer el plano guardado con la API de visión.

    Existe porque la lectura del dibujo pasa UNA vez, cuando el correo entra,
    y si aquel día falló —formato no soportado, la firma colada como plano, un
    JSON a medias— el RFQ se queda sin cotas para siempre: sin diámetro de
    alambre no hay máquina, no hay peso y el costeo sale orientativo aunque el
    correo viniera completo. Reenviar el correo no sirve: el adjunto ya está
    guardado y el message-id ya está registrado.

    Pide ``rfq:dictaminar`` y no ``rfq:leer`` a propósito: cada pulsación
    gasta una llamada al modelo, así que la tiene quien dictamina, no
    cualquiera que pueda mirar la ficha.
    """
    import app.rfq.relectura as relectura

    get_rfq(rfq_id, None, usuario)                     # 404 si no existe
    lectura = relectura.releer(rfq_id)
    log.info("RFQ %s: relectura del plano pedida por %s → %s.",
             rfq_id, usuario.correo, lectura["estado"])
    return {
        "estado": lectura["estado"],
        "ficheros": lectura.get("ficheros") or [],
        "motivo": lectura.get("motivo"),
        "soportados": lectura.get("soportados"),
        # Lo que se sacó, para que la ficha se repinte sin recargar.
        "resorte": lectura.get("resorte"),
    }


@router.get("/{rfq_id}/planos/{nombre}")
def plano_del_rfq(
    rfq_id: str,
    nombre: str,
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """Un plano concreto, tal cual llegó en el correo."""
    from fastapi.responses import FileResponse, Response
    import os.path
    import app.persistence.blueprint_store as almacen

    # `basename` y nada más: el nombre viene de la URL y no puede salirse de
    # la carpeta de este RFQ.
    limpio = os.path.basename(nombre or "")
    if not limpio:
        raise HTTPException(status_code=404, detail="Ese plano no está guardado.")

    guardado = almacen.leer_de_base(rfq_id, limpio)
    if guardado:
        contenido, tipo = guardado
        return Response(content=contenido, media_type=tipo,
                        headers={"Content-Disposition": f'inline; filename="{limpio}"'})

    carpeta = _carpeta_de_planos(rfq_id)
    ruta = (carpeta / limpio) if carpeta else None
    if not ruta or not ruta.is_file():
        raise HTTPException(status_code=404, detail="Ese plano no está guardado.")

    tipos = {".pdf": "application/pdf", ".png": "image/png",
             ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
    tipo = tipos.get(ruta.suffix.lower(), "application/octet-stream")
    return FileResponse(str(ruta), media_type=tipo, filename=ruta.name)


@router.get("/{rfq_id}/oferta/pdf")
def pdf_oferta(
    rfq_id: str,
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """El PDF de la oferta tal y como saldría, para revisarlo antes."""
    from fastapi.responses import FileResponse
    import app.rfq.oferta as oferta
    try:
        ruta = oferta.generar_pdf(rfq_id)
    except ValueError as e:
        codigo = 404 if "No existe" in str(e) else 409
        raise HTTPException(status_code=codigo, detail=str(e))
    except Exception as e:
        log.exception("RFQ %s: no se pudo generar el PDF de la oferta", rfq_id)
        raise HTTPException(status_code=500, detail=str(e))
    return FileResponse(str(ruta), media_type="application/pdf", filename=ruta.name,
                        headers={"Content-Disposition": f'inline; filename="{ruta.name}"'})


@router.post("/{rfq_id}/oferta")
def enviar_oferta(
    rfq_id: str,
    body: Optional[OfertaRequest] = None,
    usuario: UsuarioSesion = Depends(exige("rfq:dictaminar")),
):
    """Genera el PDF, manda la oferta al cliente y lo anota en el RFQ."""
    import app.rfq.oferta as oferta
    try:
        return oferta.enviar(rfq_id, usuario=usuario.correo,
                             opciones=_opciones_oferta(body),
                             forzar=bool(body and body.forzar))
    except ValueError as e:
        codigo = 404 if "No existe" in str(e) else 409
        raise HTTPException(status_code=codigo, detail=str(e))
    except Exception as e:
        log.exception("RFQ %s: la oferta falló", rfq_id)
        raise HTTPException(status_code=500, detail=str(e))

