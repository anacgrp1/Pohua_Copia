"""Rutas de costeo.

POST /api/price → calcula el precio de un resorte con el motor de Rodea.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.models.schemas import PriceRequest, PriceResponse
from api.security import exige
from app.auth.tokens import UsuarioSesion
from pricing.engine import ErrorMotorCosteo, compute_price_via_node
from pricing.rodea_adapter import build_pn_for_engine, overrides_de_parametros

log = logging.getLogger("cotizador.api.pricing")

router = APIRouter(prefix="/api", tags=["pricing"])


@router.post("/price", response_model=PriceResponse)
def compute_price(
    body: PriceRequest,
    usuario: UsuarioSesion = Depends(exige("precio:calcular")),
):
    """Calcula el precio con el motor JavaScript de Rodea.

    La respuesta lleva ``completo`` y ``faltantes``: si el catálogo no tenía
    algún insumo (precio de alambre, tarifa de la máquina, parámetros
    vigentes), el número que sale es orientativo y hay que decirlo, no
    devolverlo como si fuera cotizable.
    """
    log.info("Costeo solicitado por %s para RFQ %s (tipo=%s, cantidad=%s).",
             usuario.correo, body.rfq_id, body.tipo_resorte, body.cantidad)

    datos_resorte = body.datos_resorte or body.model_dump(exclude={"datos_resorte"})

    # 1. Traducir la petición al esquema PN, leyendo el catálogo de la base.
    try:
        pn_data, catalogo = build_pn_for_engine(body.rfq_id or "UNKNOWN", datos_resorte)
    except Exception as err:
        log.exception("No se pudo preparar el costeo del RFQ %s", body.rfq_id)
        raise HTTPException(
            status_code=503,
            detail=f"No se pudo leer el catálogo de costeo: {err}",
        ) from err

    # 2. Ejecutar el motor.
    try:
        result = compute_price_via_node(
            pn_data,
            ctx_overrides=overrides_de_parametros(
                catalogo.parametros, datos_resorte.get("representante"),
                catalogo.dbs_motor,
            ),
        )
    except ErrorMotorCosteo as err:
        log.error("El motor de costeo falló para el RFQ %s: %s", body.rfq_id, err)
        raise HTTPException(status_code=502, detail=str(err)) from err

    tiers = result.get("tiers") or []
    if not tiers or not tiers[0]:
        detalle = "El motor no devolvió ningún escalón de precio válido."
        if catalogo.faltantes:
            detalle += " Faltan datos: " + "; ".join(catalogo.faltantes)
        raise HTTPException(status_code=422, detail=detalle)

    tier1 = tiers[0]
    pnl = tier1.get("pnl", {}) or {}
    banderas = result.get("flags", []) or []

    # 3. Traducir de vuelta al contrato de la API.
    #    `lead_time_weeks` va en None a propósito: el catálogo no guarda plazos
    #    de entrega por máquina. Antes se devolvía 8 fijo, con un comentario
    #    "Placeholder" — un plazo inventado que salía hacia el cliente.
    #    No entra en `faltantes` porque `faltantes` describe lo que le falta al
    #    CÁLCULO; el plazo es un dato que pone Planeación aparte, y mezclarlos
    #    haría que `completo` y `faltantes` se contradijeran.
    notas_motor = [f.get("m", "") for f in banderas if f.get("t") in ("warn", "err")]
    notas_motor.append("El plazo de entrega no lo calcula el motor: lo fija Planeación.")

    return PriceResponse(
        rfq_id=body.rfq_id,
        precio_unitario_usd=tier1.get("sell"),
        tooling_usd=tier1.get("tool"),
        lead_time_weeks=None,
        desglose={
            "material_cost_usd": tier1.get("mat"),
            "setup_cost_usd": tier1.get("setup"),
            "run_cost_usd": tier1.get("run"),
            "overhead_usd": pnl.get("ohV"),
            "ccv_ratio": pnl.get("ratio"),
            "maquina": (catalogo.maquina or {}).get("nombre"),
            "material": (catalogo.material or {}).get("codigo"),
            "flags": [f.get("m") for f in banderas],
        },
        moneda="USD",
        notas="\n".join(notas_motor),
        origen_datos=catalogo.origen,
        completo=catalogo.completo,
        faltantes=list(catalogo.faltantes),
    )
