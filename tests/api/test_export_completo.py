"""La hoja de RFQs sin huecos (2026-09-30).

Salía con «Precio tramo 1», «Veredicto del sistema», «Score» y «Falta» en
blanco en las filas donde ese dato no se había escrito por el camino de
siempre. Ahora cada columna se toma de la primera fuente que lo tenga.
"""
import io
from datetime import datetime
from unittest import mock

import pytest


@pytest.fixture(autouse=True)
def asis():
    """Se importa dentro: importarlo al cargar el módulo fija la configuración
    antes de que otras pruebas de tests/api pongan la suya (JWT_SECRET)."""
    import api.routes.assistant as modulo
    globals()["asis"] = modulo
    return modulo

RESORTE = {"tipo_resorte": "compresion", "material": "Music wire", "diametro_alambre_mm": 1.2,
           "diametro_exterior_mm": 12.0, "longitud_libre_mm": 40.0, "numero_espiras_totales": 10,
           "cantidad": 20000, "num_parte": "1-633064", "confianza": 0.95}


def fila(estado="Approved", veredicto=None, score=None, final="feasible", **cols):
    # rfq_id, version, cliente_id, nombre_proyecto, part_number, volumen, material,
    # estado, veredicto_sistema, veredicto_final, score, fecha, razon_social, datos_json
    return ["INT-1", 1, None, None, cols.get("pn"), cols.get("vol"), cols.get("mat"),
            estado, veredicto, final, score, datetime(2026, 9, 30, 22, 0), None, {}]


def test_sin_veredicto_guardado_se_dictamina_con_el_resorte(asis):
    e = asis._datos_de_la_fila(fila(), {}, RESORTE)
    assert e["veredicto"] in ("feasible", "requires review")
    assert e["score"] is not None


def test_el_precio_sale_del_pm_luego_de_la_oferta_luego_del_sistema(asis):
    pm = {"n": 1, "por": "miguelangel.rodea@cgr.com",
          "pn": {"pn": "1-633064", "tiers": [{"qty": 20000}]},
          "resultado": {"tiers": [{"qty": 20000, "sell": 3.4335}]}}
    assert asis._datos_de_la_fila(fila(), {"cotizacion_pm": pm})["precio"] == 3.4335
    oferta = {"enviada": True, "tramos": [{"cantidad": 5000, "precio_pc": 0.42}]}
    e = asis._datos_de_la_fila(fila(), {"oferta": oferta})
    assert e["precio"] == 0.42 and e["cotizado_por"] == "Oferta enviada"
    e = asis._datos_de_la_fila(fila(), {"factibilidad": {"veredicto": "feasible"}}, RESORTE,
                               costear=lambda: 0.5314)
    assert e["precio"] == 0.5314 and e["cotizado_por"] == "Sistema"


def test_numero_de_parte_material_y_cantidades_de_donde_haya(asis):
    pm = {"n": 1, "por": "pm@x", "material_nombre": "Music Wire (ASTM A228)",
          "pn": {"pn": "PN-PM", "tiers": [{"qty": 1000}, {"qty": 5000}]},
          "resultado": {"tiers": [{"qty": 1000, "sell": 1.0}]}}
    e = asis._datos_de_la_fila(fila(), {"cotizacion_pm": pm})
    assert e["part_number"] == "PN-PM"
    assert e["material"] == "Music Wire (ASTM A228)"
    assert e["cantidades"] == "1,000 / 5,000" and e["volumen"] == 1000
    e = asis._datos_de_la_fila(fila(), {}, RESORTE)
    assert e["part_number"] == "1-633064" and e["volumen"] == 20000 and e["cantidades"] == "20,000"


def test_falta_dice_que_falta_o_nada(asis):
    assert asis._datos_de_la_fila(fila(), {})["falta"] == "—"
    e = asis._datos_de_la_fila(fila(estado="Incomplete"), {"campos_faltantes": ["volumen"]})
    assert e["falta"] == "volumen"
    assert asis._datos_de_la_fila(fila(estado="Incomplete"), {})["falta"] == "datos del cliente"


def test_la_hoja_sale_entera(asis):
    from openpyxl import load_workbook

    class Cur:
        def __init__(self): self.n = 0
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params=None): self.n += 1
        def fetchall(self):
            if self.n == 1:
                f = fila(veredicto=None, score=None)
                f[13] = {"remitente": "d@cgr.com", "asunto": "RE: 3- Test"}
                return [tuple(f)]
            return [("INT-1", RESORTE)]

    class Conn:
        def cursor(self): return Cur()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    with mock.patch.object(asis, "get_db", return_value=Conn()), \
         mock.patch("app.rfq.costeo.costear",
                    return_value={"tramos": [{"precio_pc": 0.61}]}):
        r = asis.exportar(limit=10, usuario=mock.Mock())
    datos = r.body_iterator
    import asyncio

    async def leer():
        trozos = []
        async for t in datos:
            trozos.append(t)
        return b"".join(trozos)
    contenido = asyncio.run(leer())
    hoja = load_workbook(io.BytesIO(contenido)).active
    cab = [c.value for c in hoja[1]]
    valores = dict(zip(cab, [c.value for c in hoja[2]]))
    assert valores["N° de parte"] == "1-633064"
    assert valores["Volumen"] == 20000
    assert valores["Material"] == "Music wire"
    assert valores["Veredicto del sistema"] in ("Factible", "Requiere revisión")
    assert valores["Score"] is not None
    assert valores["Precio tramo 1 (US$/pza)"] == 0.61
    assert valores["Cotizado por"] == "Sistema"
    assert valores["Falta"] == "—"
