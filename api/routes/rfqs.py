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
        SELECT b.nivel, b.titulo
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
                banderas = [{"nivel": r[0], "titulo": r[1]} for r in cur.fetchall()]
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
    datos = detalle.datos_json or {}
    resorte = detalle.resorte or {}
    factibilidad = datos.get("factibilidad") or {}

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
            "veredicto_sistema": detalle.veredicto_sistema,
            "veredicto_final": detalle.veredicto_final,
            "score": costeo_rfq.num(detalle.score),
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
        "banderas": detalle.banderas,
        "en_revision": datos.get("en_revision") or {},
        "campos_faltantes": datos.get("campos_faltantes") or [],
        "costeo": costeado["costeo"],
        "error_costeo": costeado["error_costeo"],
        "puede_dictaminar": usuario.puede("rfq:dictaminar"),
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
        "correo": prep["correo"],
        "pdf": prep["pdf"],
        "costeo": prep["costeado"]["costeo"],
        "oferta_anterior": (rfq["datos"] or {}).get("oferta"),
        "envio_habilitado": __import__("app.email.outbound", fromlist=["x"]).envio_habilitado(),
        "puede_enviar": usuario.puede("rfq:dictaminar"),
    }


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

