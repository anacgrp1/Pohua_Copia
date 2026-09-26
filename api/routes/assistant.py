"""Rutas del asistente de la barra inferior.

Cuatro endpoints, y la diferencia entre ellos importa:

    GET  /api/assistant/pipeline    → SQL puro
    GET  /api/assistant/summary     → SQL puro
    GET  /api/assistant/attention   → SQL puro
    GET  /api/assistant/top-clientes → SQL puro
    GET  /api/assistant/export      → SQL puro, devuelto como Excel
    POST /api/assistant/ask         → ÚNICO que llama al modelo de IA

Los tres primeros son agregados de la base de datos: no cuestan API, no
inventan nada y responden igual sin clave de IA configurada. Sólo el
chat gasta tokens, y sólo cuando alguien escribe una pregunta.

Todo va detrás de ``rfq:leer``: quien no puede ver las RFQs tampoco puede
preguntar por ellas ni exportarlas.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

import app.core.config as config
from api.dependencies import get_db
from api.models.schemas import (
    AssistantAnswer,
    AssistantAttention,
    AssistantQuestion,
    AssistantSummary,
    AssistantTopClientes,
    PipelineFlow,
    PipelineStage,
)
from api.security import exige
from app.auth.tokens import UsuarioSesion

log = logging.getLogger("cotizador.api.assistant")

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

# Cuántas RFQs se le enseñan al modelo. Cada fila son ~30 tokens; 60 filas es
# contexto de sobra para una pregunta y mantiene la llamada barata y rápida.
_MAX_FILAS_CONTEXTO = 60

# Tope de la pregunta. Sin él, un pegado accidental de medio correo se
# convierte en una llamada cara sin que nadie se dé cuenta.
_MAX_CARACTERES_PREGUNTA = 1000


# --------------------------------------------------------------------------- #
# Agregados (sin IA)
# --------------------------------------------------------------------------- #

def _resumen() -> dict:
    """Cuenta lo que hay en la base. Ni un número calculado fuera de SQL."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE fecha_registro >= NOW() - INTERVAL '7 days'),
                       COUNT(*) FILTER (WHERE fecha_registro >= NOW() - INTERVAL '30 days'),
                       COUNT(DISTINCT cliente_id) FILTER (WHERE cliente_id IS NOT NULL)
                FROM rfqs;
            """)
            total, semana, mes, clientes = cur.fetchone()

            cur.execute("""
                SELECT estado, COUNT(*)
                FROM rfqs GROUP BY estado ORDER BY COUNT(*) DESC;
            """)
            por_estado = [{"estado": e, "total": n} for e, n in cur.fetchall()]

            cur.execute("""
                SELECT material, COUNT(*)
                FROM rfqs
                WHERE material IS NOT NULL AND material <> ''
                GROUP BY material ORDER BY COUNT(*) DESC LIMIT 5;
            """)
            materiales = [{"material": m, "total": n} for m, n in cur.fetchall()]

            cur.execute("SELECT MAX(fecha_registro)::text FROM rfqs;")
            ultima = cur.fetchone()[0]

            # Los clientes estrella (COT-71): el Top 12 que hace ~la mitad de
            # las ventas de ISC. La marca vive en `clientes.es_estrella`, no en
            # una lista dentro del código: si mañana entra o sale uno, se
            # cambia en la base y esta pantalla se entera sola.
            #
            # `LEFT JOIN` y no `JOIN`: un cliente estrella sin ninguna RFQ
            # todavía es exactamente lo que el Plant Manager quiere ver —una
            # cuenta grande que lleva tiempo sin pedir—, y con `JOIN`
            # desaparecería justo ése.
            cur.execute("""
                SELECT c.cliente_id, c.razon_social, c.payment_terms,
                       COUNT(r.id) AS rfqs,
                       MAX(r.fecha_registro)::text AS ultima,
                       FLOOR(EXTRACT(EPOCH FROM (NOW() - MAX(r.fecha_registro)))
                             / 86400)::int AS dias
                FROM clientes c
                LEFT JOIN rfqs r ON r.cliente_id = c.cliente_id
                WHERE c.es_estrella
                GROUP BY c.cliente_id, c.razon_social, c.payment_terms
                -- Primero los que han escrito hace menos, y los que no han
                -- escrito nunca al final. Es el orden que responde a la
                -- pregunta del Plant Manager: ¿a quién le toca una llamada?
                ORDER BY MAX(r.fecha_registro) DESC NULLS LAST, c.razon_social
                LIMIT 12;
            """)
            estrella = [
                {"cliente_id": cid, "razon_social": nombre,
                 "payment_terms": terminos, "total": int(n or 0),
                 "ultima": ult, "dias": None if dias is None else int(dias)}
                for cid, nombre, terminos, n, ult, dias in cur.fetchall()
            ]

            # Cuánto del trabajo viene de esas cuentas. Es la cifra que hace
            # informativo el panel: el Top 12 es ~la mitad de las VENTAS, y
            # aquí se puede comprobar si también lo es de las solicitudes.
            #
            # Se cuenta en SQL contra la marca de la base, no dividiendo en el
            # navegador la lista de arriba: esa lista está recortada a 12 y
            # daría un porcentaje distinto en cuanto haya un estrella número 13.
            cur.execute("""
                SELECT COUNT(*) FILTER (
                           WHERE cliente_id IN (SELECT cliente_id FROM clientes
                                                WHERE es_estrella))
                FROM rfqs;
            """)
            rfqs_estrella = int(cur.fetchone()[0] or 0)

    return {
        "total": total,
        "ultimos_7_dias": semana,
        "ultimos_30_dias": mes,
        "clientes": clientes,
        "por_estado": por_estado,
        "materiales": materiales,
        "ultima_rfq": ultima,
        "estrella": estrella,
        "rfqs_estrella": rfqs_estrella,
    }


# Por qué espera cada RFQ, de lo que la base sabe con certeza.
MOTIVO_REVISION = "revision"          # en revisión, o con banderas del sistema
MOTIVO_VALIDACION = "validacion"      # factible y cotizado: falta el visto bueno


def _motivo(estado: str, criticas: int, avisos: int) -> str:
    if estado == "RequiresReview" or criticas or avisos:
        return MOTIVO_REVISION
    return MOTIVO_VALIDACION


def _atencion(limite: int = 20) -> dict:
    """RFQs que esperan a una persona, con los días que llevan esperando.

    Es TODO lo que todavía no tiene dictamen, no sólo lo que tiene banderas.
    Un RFQ factible con score 100 también espera: le falta que el PM valide
    la cotización, y es justo el que la campana anuncia como «Quote
    validation required». Hasta 2026-09 aquí sólo salían los parados en
    revisión y los marcados, así que la campana decía «1 waiting» y este
    panel «Nothing is waiting»: dos respuestas a la misma pregunta.

    No es un modelo de riesgo: es lo que la base sabe decir con certeza —qué
    espera, por qué (`motivo`) y desde cuándo—. Sólo cuenta la última versión
    de cada RFQ: un dictamen se apunta en esa versión.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT r.rfq_id, r.version, r.cliente_id, r.part_number,
                       r.estado, r.score,
                       FLOOR(EXTRACT(EPOCH FROM (NOW() - r.fecha_registro)) / 86400)::int,
                       COUNT(*) FILTER (WHERE b.nivel = 'crit'),
                       COUNT(*) FILTER (WHERE b.nivel = 'warn'),
                       COALESCE(
                           (ARRAY_AGG(b.titulo ORDER BY
                                CASE b.nivel WHEN 'crit' THEN 0 ELSE 1 END)
                            FILTER (WHERE b.nivel IN ('crit', 'warn')))[1],
                           ''),
                       NULLIF(r.datos_json->>'customer', '')
                FROM rfqs r
                LEFT JOIN rfq_banderas b ON b.rfq_version_id = r.id
                WHERE r.estado NOT IN ('Approved', 'Declined')
                  AND r.version = (SELECT MAX(x.version) FROM rfqs x
                                    WHERE x.rfq_id = r.rfq_id)
                GROUP BY r.id, r.rfq_id, r.version, r.cliente_id, r.part_number,
                         r.estado, r.score, r.fecha_registro, r.datos_json
                ORDER BY COUNT(*) FILTER (WHERE b.nivel = 'crit') DESC,
                         r.fecha_registro ASC
                LIMIT %s;
            """, (limite,))
            filas = cur.fetchall()

    columnas = ("rfq_id", "version", "cliente_id", "part_number", "estado",
                "score", "dias_esperando", "criticas", "avisos", "bandera",
                "cliente_nombre")
    pendientes = [dict(zip(columnas, f)) for f in filas]
    for p in pendientes:
        p["motivo"] = _motivo(p["estado"], p["criticas"], p["avisos"])

    return {
        "pendientes": pendientes,
        "total": len(pendientes),
        "criticas": sum(1 for p in pendientes if p["criticas"]),
    }


def _top_clientes(dias: int = 7, limite: int = 10) -> dict:
    """Quién pidió más en los últimos ``dias``, de más a menos.

    El cliente se toma del catálogo cuando el dominio del remitente ya está
    dado de alta, y del propio correo cuando no. Sin esa segunda mitad, una
    semana entera de peticiones de empresas que todavía no están en la base
    saldría como una sola fila vacía: precisamente la semana que interesa
    mirar.

    `es_nuevo` es del cliente, no del RFQ: nadie del catálogo detrás del
    dominio. Eso es lo que convierte la lista en una de trabajo —a quién hay
    que dar de alta— y no en otra tabla de conteos.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COALESCE(c.razon_social,
                                NULLIF(TRIM(r.datos_json->>'customer'), ''),
                                NULLIF(TRIM(r.datos_json->>'dominio'), ''),
                                NULLIF(split_part(COALESCE(r.datos_json->>'remitente', ''), '@', 2), ''),
                                'Sin cliente')            AS nombre,
                       (c.cliente_id IS NULL)              AS es_nuevo,
                       COALESCE(c.es_estrella, FALSE)      AS estrella,
                       -- DISTINCT: un RFQ con tres versiones es UNA
                       -- petición de ese cliente, no tres.
                       COUNT(DISTINCT r.rfq_id)            AS rfqs,
                       MAX(r.fecha_registro)::text         AS ultima
                FROM rfqs r
                LEFT JOIN clientes c ON c.cliente_id = r.cliente_id
                WHERE r.fecha_registro >= NOW() - (%s || ' days')::interval
                GROUP BY 1, 2, 3
                ORDER BY rfqs DESC, MAX(r.fecha_registro) DESC
                LIMIT %s;
                """,
                (str(int(dias)), limite),
            )
            filas = [
                {"cliente": nombre, "es_nuevo": bool(nuevo), "estrella": bool(estrella),
                 "total": int(n or 0), "ultima": ultima}
                for nombre, nuevo, estrella, n, ultima in cur.fetchall()
            ]

            # El total NO se suma de la lista de arriba: está recortada al
            # top 10 y daría una cifra corta en cuanto haya un cliente más.
            cur.execute(
                "SELECT COUNT(DISTINCT rfq_id) FROM rfqs "
                "WHERE fecha_registro >= NOW() - (%s || ' days')::interval;",
                (str(int(dias)),),
            )
            total = int(cur.fetchone()[0] or 0)

    return {
        "clientes": filas,
        "dias": int(dias),
        "total_rfqs": total,
        # Los que habría que dar de alta. La fila "Sin cliente" no cuenta:
        # no es una empresa sin catalogar, es un correo del que no se sacó
        # ningún nombre, y darla de alta no significa nada.
        "nuevos": sum(1 for f in filas
                      if f["es_nuevo"] and f["cliente"] != "Sin cliente"),
    }


@router.get("/top-clientes", response_model=AssistantTopClientes)
def top_clientes(
    dias: int = Query(7, ge=1, le=90),
    limit: int = Query(10, ge=1, le=50),
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """Los clientes que más pidieron en los últimos días."""
    return AssistantTopClientes(**_top_clientes(dias, limit))


@router.get("/summary", response_model=AssistantSummary)
def resumen(usuario: UsuarioSesion = Depends(exige("rfq:leer"))):
    """Cifras de la base: totales, estados, materiales más pedidos."""
    return AssistantSummary(**_resumen())


@router.get("/attention", response_model=AssistantAttention)
def atencion(
    limit: int = Query(20, ge=1, le=100),
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """RFQs paradas o con banderas, ordenadas por gravedad y antigüedad."""
    return AssistantAttention(**_atencion(limit))


# --------------------------------------------------------------------------- #
# La hoja de cálculo del resumen
# --------------------------------------------------------------------------- #

# Ancho de cada columna, en caracteres. Se fija a mano y no se calcula del
# contenido: una hoja cuyas columnas cambian de ancho según el lote no se puede
# comparar de un vistazo con la de la semana pasada.
_COLUMNAS = (
    ("RFQ", 16),
    ("Versión", 8),
    ("Cliente", 30),
    ("¿Nuevo?", 10),
    ("Contacto", 32),
    ("Asunto / proyecto", 34),
    ("N° de parte", 18),
    ("Volumen", 12),
    ("Cantidades pedidas", 24),
    ("Material", 34),
    ("Estado", 20),
    ("Veredicto del sistema", 22),
    ("Score", 8),
    ("Dictamen final", 18),
    ("Precio tramo 1 (US$/pza)", 14),
    ("Cotizado por", 22),
    ("Falta", 30),
    ("Entró", 18),
)

# Lo que la base guarda en inglés, como se lee en la hoja (en español: la hoja
# la lee ventas en Querétaro). Lo desconocido sale tal cual.
_ESTADOS = {"New": "Nuevo", "RequiresReview": "En revisión", "Approved": "Aprobado",
            "Declined": "Rechazado", "Incomplete": "Esperando al cliente"}
_VEREDICTOS = {"feasible": "Factible", "requires review": "Requiere revisión",
               "not feasible": "No factible"}
_FALTANTES = {"volumen": "volumen", "tiene_adjunto": "plano", "part_number": "número de parte",
              "material": "material", "customer": "cliente"}


def _texto(mapa, valor):
    return mapa.get(str(valor), valor) if valor not in (None, "") else ""


def _datos_de_la_fila(fila, datos: dict) -> dict:
    """Lo que falta en las columnas de `rfqs`, buscado en `datos_json`.

    La hoja salía con «Proyecto», «Veredicto del sistema» y «Score» en blanco:
    esas columnas sólo se llenan en unos caminos del flujo (el veredicto se
    escribe al dictaminar; el proyecto casi nunca lo dice el comprador),
    mientras que `datos_json` sí lo tiene siempre —la factibilidad completa,
    el asunto, los escalones—. Se toma de la columna y, si está vacía, de ahí.
    """
    factibilidad = datos.get("factibilidad") if isinstance(datos.get("factibilidad"), dict) else {}
    escalones = datos.get("escalones_cantidad")
    if isinstance(escalones, list):
        cantidades = " / ".join(f"{int(float(str(x).replace(',', ''))):,}" for x in escalones
                                if str(x).replace(",", "").replace(".", "", 1).isdigit())
    else:
        cantidades = str(escalones or "")
    pm = datos.get("cotizacion_pm") if isinstance(datos.get("cotizacion_pm"), dict) else None
    precio = None
    if pm:
        tiers = ((pm.get("resultado") or {}).get("tiers") or [])
        primero = next((t for t in tiers if isinstance(t, dict)), None)
        try:
            venta = primero.get("sell") if primero else None
            precio = float(venta) if venta is not None else None
        except (TypeError, ValueError):
            precio = None
    faltan = datos.get("campos_faltantes") or []
    return {
        "proyecto": fila[3] or datos.get("nombre_proyecto") or datos.get("asunto") or "",
        "cantidades": cantidades,
        "veredicto": fila[8] or factibilidad.get("veredicto"),
        "score": fila[10] if fila[10] is not None else factibilidad.get("score"),
        "precio": precio,
        "cotizado_por": (f"PM v{pm.get('n')} · {str(pm.get('por') or '').split('@')[0]}"
                         if pm else ("Sistema" if factibilidad else "")),
        "falta": ", ".join(_FALTANTES.get(f, f) for f in faltan) if fila[7] == "Incomplete" else "",
    }


def _cliente_de(fila) -> tuple:
    """El nombre del cliente y si es nuevo, para una fila de la consulta.

    Un RFQ trae el cliente por dos caminos: el catálogo, cuando el dominio del
    remitente ya está dado de alta (`cliente_id` → `clientes.razon_social`), y
    lo que el modelo leyó del correo, que es lo único que hay cuando el
    comprador escribe por primera vez. La columna miraba sólo el primero, así
    que un cliente nuevo salía en blanco — justo el caso en el que hace falta
    saber quién es.
    """
    cliente_id, razon_social, datos = fila[2], fila[12], fila[13] or {}
    if razon_social:
        return razon_social, "No"          # ya está en el catálogo
    delcorreo = (datos.get("customer") or "").strip()
    dominio = (datos.get("dominio") or "").strip()
    remitente = (datos.get("remitente") or "").strip()
    nombre = delcorreo or dominio or (remitente.split("@")[-1] if remitente else "")
    return (nombre or cliente_id or "—"), "Sí"


@router.get("/export")
def exportar(
    limit: int = Query(1000, ge=1, le=5000),
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """La lista de RFQs como hoja de Excel, lista para leerse.

    Era un CSV en crudo: columnas del ancho de fábrica, fechas con
    microsegundos y zona horaria, y el cliente en blanco siempre que no
    estuviera en el catálogo. Ahora es un .xlsx con la cabecera fija, filtros,
    los anchos puestos y una columna que dice si el cliente es nuevo.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM (
                    -- Una fila por RFQ: su última versión. Antes salía una
                    -- por versión y el mismo RFQ aparecía repetido.
                    SELECT DISTINCT ON (r.rfq_id)
                           r.rfq_id, r.version, r.cliente_id, r.nombre_proyecto,
                           r.part_number, r.volumen, r.material, r.estado,
                           r.veredicto_sistema, r.veredicto_final, r.score,
                           r.fecha_registro, c.razon_social, r.datos_json
                    FROM rfqs r
                    LEFT JOIN clientes c ON c.cliente_id = r.cliente_id
                    ORDER BY r.rfq_id, r.version DESC
                ) ultimas
                ORDER BY fecha_registro DESC
                LIMIT %s;
            """, (limit,))
            filas = cur.fetchall()

    libro = Workbook()
    hoja = libro.active
    hoja.title = "RFQs"

    cabecera = Font(bold=True, color="FFFFFF")
    fondo = PatternFill("solid", fgColor="1B3D79")      # el navy de la casa
    for i, (titulo, ancho) in enumerate(_COLUMNAS, start=1):
        celda = hoja.cell(row=1, column=i, value=titulo)
        celda.font = cabecera
        celda.fill = fondo
        celda.alignment = Alignment(vertical="center")
        hoja.column_dimensions[get_column_letter(i)].width = ancho
    hoja.row_dimensions[1].height = 22

    for fila in filas:
        cliente, nuevo = _cliente_de(fila)
        datos = fila[13] or {}
        if isinstance(datos, str):
            try:
                datos = json.loads(datos)
            except ValueError:
                datos = {}
        extra = _datos_de_la_fila(fila, datos)
        volumen = fila[5]
        try:
            volumen = int(str(volumen).replace(",", "")) if volumen else None
        except (TypeError, ValueError):
            pass                                        # se queda como texto
        fecha = fila[11]
        if fecha is not None and getattr(fecha, "tzinfo", None):
            # Excel no guarda zonas horarias; con una dentro, openpyxl falla.
            fecha = fecha.replace(tzinfo=None)
        score = extra["score"]
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None
        contacto = datos.get("contacto_nombre") or ""
        remitente = datos.get("remitente") or ""
        hoja.append([
            fila[0], fila[1], cliente, nuevo,
            f"{contacto} <{remitente}>" if contacto and remitente else (remitente or contacto),
            extra["proyecto"], fila[4] or datos.get("part_number") or "", volumen,
            extra["cantidades"],
            fila[6] or datos.get("material") or "",
            _texto(_ESTADOS, fila[7]),
            _texto(_VEREDICTOS, extra["veredicto"]),
            score,
            (_texto(_VEREDICTOS, fila[9])
             or ("Pendiente" if fila[7] not in ("Approved", "Declined") else "")),
            extra["precio"], extra["cotizado_por"], extra["falta"],
            fecha,
        ])

    ultima = max(hoja.max_row, 1)
    for f in range(2, ultima + 1):
        hoja.cell(row=f, column=8).number_format = "#,##0"          # volumen
        hoja.cell(row=f, column=13).number_format = "0"             # score
        hoja.cell(row=f, column=15).number_format = "$#,##0.0000"   # precio
        # Sin microsegundos: la fecha se lee, no se audita.
        hoja.cell(row=f, column=18).number_format = "yyyy-mm-dd hh:mm"

    # La cabecera se queda a la vista al bajar, y con filtros para ordenar por
    # cliente o por estado sin tener que preparar nada.
    hoja.freeze_panes = "A2"
    hoja.auto_filter.ref = f"A1:{get_column_letter(len(_COLUMNAS))}{ultima}"

    buffer = io.BytesIO()
    libro.save(buffer)
    buffer.seek(0)
    nombre = f"rfqs-{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    return StreamingResponse(
        buffer,
        media_type=("application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"),
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


# --------------------------------------------------------------------------- #
# Chat (única llamada al modelo)
# --------------------------------------------------------------------------- #

_SISTEMA = """Eres el asistente del cotizador de resortes industriales de ISC
(CGR International). Respondes preguntas del equipo sobre las RFQs registradas.

Reglas:
- Respondes ÚNICAMENTE con los datos del contexto. Si el contexto no alcanza
  para responder, dilo con claridad y di qué dato faltaría.
- No inventas cifras, clientes, materiales ni fechas.
- No propones precios ni decisiones de negocio: eso lo dictamina una persona.
- Respondes en el mismo idioma de la pregunta, en tres frases o menos, sin
  encabezados ni listas salvo que la pregunta pida un listado."""


def _contexto() -> str:
    """Lo que el modelo puede ver: agregados y las últimas RFQs, en texto."""
    resumen = _resumen()
    lineas = [
        "CIFRAS GENERALES",
        f"- Total de RFQs: {resumen['total']}",
        f"- Últimos 7 días: {resumen['ultimos_7_dias']}",
        f"- Últimos 30 días: {resumen['ultimos_30_dias']}",
        f"- Clientes distintos: {resumen['clientes']}",
        f"- Última RFQ registrada: {resumen['ultima_rfq'] or 'ninguna'}",
        "",
        "POR ESTADO",
    ]
    lineas += [f"- {e['estado']}: {e['total']}" for e in resumen["por_estado"]] or ["- (sin datos)"]

    if resumen["materiales"]:
        lineas += ["", "MATERIALES MÁS PEDIDOS"]
        lineas += [f"- {m['material']}: {m['total']}" for m in resumen["materiales"]]

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rfq_id, version, cliente_id, part_number, material,
                       volumen, estado, score, fecha_registro::date::text
                FROM rfqs
                ORDER BY fecha_registro DESC
                LIMIT %s;
            """, (_MAX_FILAS_CONTEXTO,))
            filas = cur.fetchall()

    if filas:
        lineas += ["", f"ÚLTIMAS {len(filas)} RFQs",
                   "rfq | v | cliente | part number | material | volumen | estado | score | fecha"]
        for f in filas:
            lineas.append(" | ".join("" if v is None else str(v) for v in f))

    return "\n".join(lineas)


@router.post("/ask", response_model=AssistantAnswer)
def preguntar(
    peticion: AssistantQuestion,
    usuario: UsuarioSesion = Depends(exige("rfq:leer")),
):
    """Responde una pregunta sobre las RFQs con el modelo de Anthropic."""
    pregunta = (peticion.pregunta or "").strip()
    if not pregunta:
        raise HTTPException(status_code=400, detail="La pregunta está vacía.")
    if len(pregunta) > _MAX_CARACTERES_PREGUNTA:
        raise HTTPException(
            status_code=400,
            detail=f"La pregunta no puede pasar de {_MAX_CARACTERES_PREGUNTA} caracteres.",
        )

    # Se comprueba antes de montar el contexto: si no hay clave, no tiene
    # sentido consultar la base para nada.
    if not getattr(config, "ANTHROPIC_API_KEY", ""):
        raise HTTPException(
            status_code=503,
            detail="El chat del asistente necesita ANTHROPIC_API_KEY. "
                   "Los botones de resumen, atención y exportar funcionan sin ella.",
        )

    try:
        import anthropic
    except ImportError:
        raise HTTPException(status_code=503,
                            detail="El paquete 'anthropic' no está instalado en el servidor.")

    modelo = getattr(config, "LLM_MODEL", "") or config.VISION_MODEL
    contexto = _contexto()

    log.info("Consulta del asistente de %s (%d caracteres).", usuario.correo, len(pregunta))

    try:
        cliente = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
        # Sin `temperature`: los modelos recientes la rechazan con un 400 y
        # tumbaban la consulta entera. Lo que se les pide aquí es leer cifras
        # ya contadas en SQL, no redactar, y para eso su comportamiento por
        # defecto sirve. `crear_mensaje` además la quita sola si alguien la
        # vuelve a poner por configuración.
        import app.core.modelo as modelo_api
        respuesta = modelo_api.crear_mensaje(
            cliente,
            model=modelo,
            max_tokens=600,
            system=_SISTEMA,
            messages=[{
                "role": "user",
                # El contexto va delimitado y antes de la pregunta: si un
                # correo trajera texto con pinta de instrucción, queda dentro
                # de los datos y no se lee como orden.
                "content": (f"<datos>\n{contexto}\n</datos>\n\n"
                            f"Pregunta del equipo: {pregunta}"),
            }],
        )
    except Exception as err:
        # El mensaje de la librería puede llevar detalles de la cuenta: se
        # registra entero y al navegador va sólo lo justo. Pero «inténtalo de
        # nuevo» a secas era peor que inútil cuando la causa no se arregla
        # reintentando —sin saldo, clave revocada, modelo retirado—: se podía
        # pulsar cien veces y fallar las cien, sin una pista de por qué.
        import app.core.modelo_errores as modelo_errores
        motivo = modelo_errores.explicar(err)
        log.exception("Fallo al consultar el modelo (%s).", motivo["codigo"])
        raise HTTPException(
            status_code=502 if motivo["reintentar"] else 503,
            detail=motivo["texto"],
            headers={"X-Motivo": motivo["codigo"]},
        ) from err

    partes = [b.text for b in respuesta.content if getattr(b, "text", None)]
    uso = getattr(respuesta, "usage", None)

    return AssistantAnswer(
        respuesta="\n".join(partes).strip() or "El modelo no devolvió texto.",
        modelo=modelo,
        tokens_entrada=getattr(uso, "input_tokens", None),
        tokens_salida=getattr(uso, "output_tokens", None),
    )


# --------------------------------------------------------------------------- #
# Recorrido del correo (sin IA)
# --------------------------------------------------------------------------- #

@router.get("/pipeline", response_model=PipelineFlow)
def recorrido(usuario: UsuarioSesion = Depends(exige("rfq:leer"))):
    """Cuántos correos y RFQs hay en cada etapa del recorrido.

    Las etapas son las que el sistema recorre de verdad, no una metáfora:

        1. El cliente escribe        → correos_procesados
        2. Se extraen los datos      → rfqs registradas
        3. Revisión de una persona   → estado RequiresReview
        4. Dictamen                  → Approved / Declined
        5. Sales                     → las aprobadas, listas para cotizar

    `espera=True` marca las etapas donde el trabajo se queda parado esperando a
    alguien. Son las que el frontend pinta distinto: es el dato que importa
    cuando alguien mira esta pantalla para saber dónde se atasca la cosa.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE fecha_registro >= NOW() - INTERVAL '7 days')
                FROM correos_procesados;
            """)
            correos, correos_semana = cur.fetchone()

            cur.execute("""
                SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE estado = 'RequiresReview'),
                       COUNT(*) FILTER (WHERE estado = 'New'),
                       COUNT(*) FILTER (WHERE estado = 'Approved'),
                       COUNT(*) FILTER (WHERE estado = 'Declined'),
                       COUNT(*) FILTER (WHERE estado = 'Incomplete'),
                       COUNT(*) FILTER (WHERE estado = 'Approved'
                                        AND datos_json->'oferta'->>'enviada' = 'true')
                FROM rfqs;
            """)
            (total, revision, nuevas, aprobadas,
             declinadas, incompletas, ofertadas) = cur.fetchone()

    etapas = [
        PipelineStage(clave="cliente", etiqueta="Customer email",
                      total=correos,
                      detalle=f"{correos_semana} in the last 7 days"),
        PipelineStage(clave="extraccion", etiqueta="Data extracted",
                      total=total,
                      detalle="RFQs registered from those emails"),
        # Los que entraron pero se quedaron sin datos (COT-76). Se cuentan aquí
        # porque si no, el embudo mentía: "Data extracted" los incluye en el
        # total y luego no aparecían en ninguna etapa.
        PipelineStage(clave="incompletas", etiqueta="Waiting on customer",
                      total=incompletas, espera=False,
                      detalle="Missing data: we asked the buyer"),
        PipelineStage(clave="revision", etiqueta="Needs review",
                      total=revision, espera=revision > 0,
                      detalle="Low-confidence extraction: a person checks it"),
        PipelineStage(clave="dictamen", etiqueta="Awaiting decision",
                      total=nuevas, espera=nuevas > 0,
                      detalle="Waiting for approve or decline"),
        # Aprobadas que todavía no se han ofertado: el PM tiene que mandar la
        # cotización (pantalla Quote). Es la última parada donde algo espera.
        PipelineStage(clave="sales", etiqueta="Ready for Sales",
                      total=aprobadas - ofertadas, espera=(aprobadas - ofertadas) > 0,
                      detalle=f"{declinadas} declined"),
        PipelineStage(clave="oferta", etiqueta="Quote sent",
                      total=ofertadas,
                      detalle="Offer PDF emailed to the customer"),
    ]

    # El estado del worker vive en api.routes.status; se lee de allí para no
    # tener dos versiones de la misma verdad.
    from api.routes import status as estado_mod
    try:
        estado = estado_mod._snapshot()
        corriendo = bool(estado.get("running"))
        ultimo = estado.get("last_cycle")
    except Exception:
        log.debug("No se pudo leer el estado del worker.", exc_info=True)
        corriendo, ultimo = False, None

    return PipelineFlow(etapas=etapas, corriendo=corriendo, ultimo_ciclo=ultimo)
