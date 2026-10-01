"""La oferta al cliente: el PDF de cotización y el correo que lo lleva.

Es el último paso del flujo —lo que el comprador recibe cuando el Plant
Manager ya aprobó— y hasta ahora no estaba cableado: existía la plantilla del
correo (``oferta_cliente``, COT-59) y existía el generador de PDF del núcleo
de ISC (``quote_pdf``, el mismo que usa la calculadora), pero nadie los
juntaba. Este módulo los junta:

    preparar(rfq_id, opciones)  → los datos ya costeados para el PDF
    generar_pdf(rfq_id, opciones) → escribe el PDF y devuelve su ruta
    enviar(rfq_id, usuario, opciones) → PDF + correo + constancia en el RFQ

Reglas que conviene no deshacer sin pensarlo:

* Sólo se oferta un RFQ **aprobado**. Ofertar sin dictamen es saltarse al PM.
* Los precios son los MISMOS que vio el PM en la ventana de revisión: salen
  de ``app.rfq.costeo``, no se recalculan aquí de otra manera.
* Si el catálogo dejó el costeo incompleto (sin precio del alambre, sin
  tarifa de máquina), la oferta NO se manda por defecto: el número es
  orientativo y a un cliente no se le manda un número orientativo. Quien
  oferta puede forzarlo (``forzar=True``) a sabiendas.
* El envío real depende de ``ENVIO_AUTOMATICO`` como todo lo que sale de la
  aplicación: apagado, el PDF se genera y queda en la carpeta de ofertas, el
  correo se construye y se registra, pero no sale. La constancia en el RFQ
  dice cuál de las dos cosas pasó.
* El PDF se guarda en ``vendor/Quotes/`` (ignorada por git), que es donde el
  lector de ISC deja las suyas, o en ``QUOTES_DIR`` si está configurada.
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("cotizador.rfq.oferta")

RAIZ = Path(__file__).resolve().parents[2]

# Valores por defecto de la oferta cuando quien la manda no dice otra cosa.
LEAD_TIME_POR_DEFECTO = "6-8 weeks ARO"
# El mismo que dicen los términos impresos en el PDF del núcleo ("FOB our
# plant in North Kansas City, MO"): el correo y el PDF no pueden contradecirse.
INCOTERM_POR_DEFECTO = "FOB North Kansas City, MO"
VALIDEZ_DIAS_POR_DEFECTO = 30
TERMINOS_POR_DEFECTO = "Net 30"

_TIPOS = {
    "compresion": "Compression spring",
    "extension": "Extension spring",
    "torsion": "Torsion spring",
}


# ---------------------------------------------------------------------------
# Dónde están las cosas
# ---------------------------------------------------------------------------

def carpeta_ofertas() -> Path:
    """La carpeta donde se dejan los PDF. Se crea si no existe."""
    import app.core.config as config
    ruta = getattr(config, "QUOTES_DIR", None) or os.environ.get("QUOTES_DIR")
    carpeta = Path(ruta) if ruta else RAIZ / "vendor" / "Quotes"
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta


def _quote_pdf():
    """Importa el ``quote_pdf`` del núcleo de ISC (la copia vendida, o el clon)."""
    if "isc_quote_pdf" in sys.modules:
        return sys.modules["isc_quote_pdf"]
    candidatos = [RAIZ / "vendor" / "lector" / "quote_pdf.py",
                  RAIZ / "ISCQuotingCore" / "apps" / "lector" / "quote_pdf.py"]
    for ruta in candidatos:
        if ruta.is_file():
            spec = importlib.util.spec_from_file_location("isc_quote_pdf", ruta)
            if spec is None or spec.loader is None:
                continue
            modulo = importlib.util.module_from_spec(spec)
            sys.modules["isc_quote_pdf"] = modulo
            spec.loader.exec_module(modulo)
            return modulo
    raise RuntimeError(
        "No está el generador de PDF del núcleo (vendor/lector/quote_pdf.py). "
        "Corre scripts/vendorizar_nucleo.py para traerlo.")


# ---------------------------------------------------------------------------
# Cargar el RFQ (última versión) con su resorte
# ---------------------------------------------------------------------------

def _cargar(rfq_id: str, conexion=None) -> Dict[str, Any]:
    import app.persistence.duplicates as duplicates
    import app.rfq.repository as repository

    propia = conexion is None
    conn = conexion or duplicates.conectar_bd()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, version, estado, cliente_id, part_number, volumen,
                       material, datos_json, notas, fecha_registro
                FROM rfqs WHERE rfq_id = %s
                ORDER BY version DESC LIMIT 1;""", (rfq_id,))
            fila = cur.fetchone()
            if not fila:
                raise ValueError(f"No existe el RFQ {rfq_id}.")
            cur.execute("""
                SELECT datos_json FROM resortes_cotizacion
                WHERE rfq_id = %s ORDER BY id DESC LIMIT 1;""", (rfq_id,))
            resorte = cur.fetchone()
        return {
            "id": fila[0], "version": fila[1], "estado": fila[2],
            "cliente_id": fila[3], "part_number": fila[4], "volumen": fila[5],
            "material": fila[6], "datos": repository._a_dict(fila[7]),
            "notas": fila[8], "fecha_registro": fila[9],
            "resorte": repository._a_dict(resorte[0]) if resorte else {},
        }
    finally:
        if propia:
            conn.close()


# ---------------------------------------------------------------------------
# Los datos del PDF
# ---------------------------------------------------------------------------

def _pulgadas(mm) -> str:
    try:
        return "%.4f in" % (float(mm) / 25.4)
    except (TypeError, ValueError):
        return ""


def preparar(rfq_id: str, opciones: Optional[dict] = None, conexion=None) -> Dict[str, Any]:
    """Todo lo que hace falta para el PDF y el correo, ya costeado.

    Devuelve ``{rfq, costeado, pdf, correo, listo, motivos}``: ``pdf`` es el
    dict que come ``quote_pdf.build_quote_pdf``; ``listo`` dice si se puede
    mandar sin forzar y ``motivos`` por qué no.
    """
    import app.rfq.costeo as costeo_rfq
    import app.rfq.repository as repository

    opciones = dict(opciones or {})
    rfq = _cargar(rfq_id, conexion=conexion)
    datos, resorte = rfq["datos"], rfq["resorte"]

    costeado = costeo_rfq.costear(rfq_id, datos, resorte, rfq["material"])
    tramos = costeado["tramos"]

    # Los motivos van por duplicado: la frase de siempre —que es la que se
    # registra y la que entiende cualquier versión de la web— y la misma con
    # su código, para que la pantalla la diga en su idioma. Los dos salen de
    # pricing/mensajes.py, así que no pueden decir cosas distintas.
    import pricing.mensajes as mensajes

    motivos = []
    motivos_i18n = []

    def _motivo(codigo, faltantes=None, **datos):
        motivos.append(mensajes.texto(codigo, **datos))
        entrada = mensajes.entrada(codigo, **datos)
        if faltantes:
            entrada["faltantes"] = list(faltantes)
        motivos_i18n.append(entrada)

    faltantes_i18n = costeado["costeo"].get("faltantes_i18n") or []
    # Una oferta por RFQ: si ya salió —o está en la bandeja de salida
    # esperando a Outlook— no se manda otra. Dos correos con la misma oferta
    # (un doble clic, o volver a la pantalla y pulsar otra vez) confunden al
    # cliente y dejan dos constancias distintas.
    previa = (datos or {}).get("oferta") if isinstance((datos or {}).get("oferta"), dict) else None
    if previa and (previa.get("enviada") or previa.get("encolada")):
        _motivo("OFERTA_YA_ENVIADA", destinatario=previa.get("destinatario") or "",
                fecha=str(previa.get("fecha") or "")[:16].replace("T", " "))
    if rfq["estado"] != repository.ESTADO_APROBADO:
        _motivo("OFERTA_NO_APROBADA", estado=rfq["estado"])
    if not tramos:
        _motivo("OFERTA_SIN_TRAMOS", faltantes=faltantes_i18n,
                detalle="; ".join(costeado["costeo"].get("faltantes")
                                  or [costeado.get("error_costeo") or "sin motivo"]))
    elif any(t.get("sin_precio") for t in tramos):
        # Bloquea pase lo que pase: no hay precio que mandar.
        peor = next(t for t in tramos if t.get("sin_precio"))
        _motivo("OFERTA_SIN_PRECIO", contrib=peor.get("contrib_pct"),
                maximo=peor.get("contrib_max"))
    elif not costeado["costeo"].get("completo"):
        _motivo("OFERTA_ORIENTATIVA", faltantes=faltantes_i18n,
                detalle="; ".join(costeado["costeo"].get("faltantes")
                                  or ["al catálogo le faltan datos"]))
    destino = opciones.get("destinatario") or datos.get("remitente")
    if not destino:
        _motivo("OFERTA_SIN_DESTINO")

    hoy = _dt.date.today()
    validez_dias = int(opciones.get("validez_dias") or VALIDEZ_DIAS_POR_DEFECTO)
    # El plazo que el PM puso en la calculadora, si lo puso; si no, el de siempre.
    plazo_pm = ((costeo_rfq.cotizacion_del_pm(datos) or {}).get("cabecera") or {}).get("plazo_dias")
    lead_time = (opciones.get("lead_time")
                 or (f"{int(plazo_pm)} working days" if plazo_pm else None)
                 or LEAD_TIME_POR_DEFECTO)
    terminos = opciones.get("terminos") or TERMINOS_POR_DEFECTO
    incoterm = opciones.get("incoterm") or INCOTERM_POR_DEFECTO

    tipo = _TIPOS.get(str(resorte.get("tipo_resorte") or "").lower(), "Spring")
    comunes = costeado["comunes"] or {}
    material = comunes.get("material_nombre") or comunes.get("material") or rfq["material"] or ""
    cliente = datos.get("customer") or rfq["cliente_id"] or "Customer"

    remarks = []
    if opciones.get("comentarios"):
        remarks.append(str(opciones["comentarios"]))
    if resorte.get("longitud_libre_mm"):
        remarks.append("Free length %s mm · OD %s mm" % (
            resorte.get("longitud_libre_mm"), resorte.get("diametro_exterior_mm") or "-"))

    pdf = {
        "customer": cliente,
        "quoteNo": rfq_id,
        "date": hoy.isoformat(),
        "validDays": validez_dias,
        "paymentTerms": terminos,
        "leadTime": lead_time,
        "lines": [{
            "partNo": rfq["part_number"] or datos.get("part_number") or "-",
            "description": tipo,
            "material": material,
            # Con la cotización del PM manda el alambre de la calculadora:
            # es el que corrigió, y el precio ya sale de él.
            "wireDia": (("%.4f in" % costeado["comunes"]["dia_in"])
                        if costeado["costeo"].get("origen") == "calculadora"
                        and costeado["comunes"].get("dia_in")
                        else _pulgadas(resorte.get("diametro_alambre_mm"))),
            "finish": opciones.get("acabado") or "",
            "quotedQty": tramos[0]["cantidad"] if tramos else None,
            "price": tramos[0]["precio_pc"] if tramos else None,
            "tiers": [{"qty": t["cantidad"], "price": t["precio_pc"]} for t in tramos],
            "remarks": "\n".join(remarks),
        }],
    }

    correo = {
        "destinatario": destino,
        "asunto_original": datos.get("asunto") or f"Quotation {rfq_id}",
        "nombre_proyecto": rfq["part_number"] or datos.get("nombre_proyecto") or rfq_id,
        "lead_time": lead_time,
        "incoterm": incoterm,
        "validez_oferta": "%d days (until %s)" % (
            validez_dias, (hoy + _dt.timedelta(days=validez_dias)).strftime("%m/%d/%Y")),
    }

    return {"rfq": rfq, "costeado": costeado, "pdf": pdf, "correo": correo,
            "listo": not motivos, "motivos": motivos,
            "motivos_i18n": motivos_i18n}


def generar_pdf(rfq_id: str, opciones: Optional[dict] = None,
                preparado: Optional[dict] = None, conexion=None) -> Path:
    """Escribe el PDF de la oferta en la carpeta de ofertas y devuelve su ruta."""
    prep = preparado or preparar(rfq_id, opciones, conexion=conexion)
    if not prep["costeado"]["tramos"]:
        raise ValueError("No hay tramos costeados: no se puede generar la oferta. "
                         + " ".join(prep["motivos"]))
    qp = _quote_pdf()
    nombre = qp.quote_filename(prep["pdf"]["customer"], rfq_id)
    destino = carpeta_ofertas() / nombre
    qp.build_quote_pdf(dict(prep["pdf"]), str(destino))
    log.info("RFQ=%s: oferta generada en %s", rfq_id, destino)
    return destino


# ---------------------------------------------------------------------------
# Mandarla
# ---------------------------------------------------------------------------

def enviar(rfq_id: str, usuario: Optional[str] = None,
           opciones: Optional[dict] = None, forzar: bool = False,
           conexion=None) -> Dict[str, Any]:
    """Genera el PDF, construye el correo de oferta, lo despacha y deja constancia.

    Devuelve ``{rfq_id, archivo, destinatario, enviado, listo, motivos,
    envio_habilitado}``. Lanza ``ValueError`` si el RFQ no existe, no está
    aprobado, o no se puede ofertar y no se forzó.
    """
    import app.email.outbound as outbound
    import app.email.templates as templates
    import app.rfq.repository as repository

    prep = preparar(rfq_id, opciones, conexion=conexion)
    # Lo que impide mandar pase lo que pase, por CÓDIGO. Se miraba cómo
    # empezaba la frase ("El RFQ está en…"), así que el día que esa frase
    # cambie —o se diga en otro idioma— dejarían de detectarse y la oferta
    # saldría sin tramos o sin destinatario.
    _BLOQUEAN = ("OFERTA_NO_APROBADA", "OFERTA_SIN_TRAMOS", "OFERTA_SIN_DESTINO",
                 "OFERTA_SIN_PRECIO", "OFERTA_YA_ENVIADA")
    bloqueos = [m.get("texto") or m.get("codigo")
                for m in prep.get("motivos_i18n") or []
                if m.get("codigo") in _BLOQUEAN]
    if bloqueos:
        raise ValueError(" ".join(bloqueos))
    if prep["motivos"] and not forzar:
        raise ValueError("La oferta no está lista para mandarse: " + " ".join(prep["motivos"])
                         + " Si aun así hay que mandarla, hay que forzarla.")

    archivo = generar_pdf(rfq_id, opciones, preparado=prep, conexion=conexion)

    params = dict(prep["correo"])
    params["rfq_id"] = rfq_id          # va en el asunto, para el hilo
    params["nombre_comprador"] = outbound.nombre_comprador({"remitente": params["destinatario"]})
    params["adjuntos"] = [str(archivo)]
    # Lo que el PM escribió para el cuerpo del correo (como al rechazar):
    # va en el correo tal cual y queda también en las notas del RFQ.
    nota_correo = str((opciones or {}).get("nota_correo") or "").strip() or None
    params["nota"] = nota_correo
    contenido = templates.construir_correo("oferta_cliente", params)

    # La oferta la manda una PERSONA desde la pantalla, con el destinatario y
    # las condiciones delante, así que va por el interruptor manual y no por
    # el del robot: pedir ENVIO_AUTOMATICO para esto significaba que, para que
    # llegara una oferta, el sistema quedaba suelto contestando solo.
    habilitado = outbound.envio_habilitado(manual=True)
    enviado = False
    encolada = False
    if habilitado:
        # Quien arma la oferta no siempre es quien puede mandarla: el buzón de
        # ISC se abre por el Outlook de una computadora y esto corre en Render.
        # Antes eso terminaba en excepción con el PDF ya generado —la oferta
        # existía para todos menos para el cliente—. Ahora el correo espera en
        # la bandeja de salida a que pase el lector de escritorio.
        diag = outbound.diagnostico_envio()
        if not diag["puede"]:
            import app.email.bandeja_salida as bandeja
            try:
                salida_id = bandeja.encolar(contenido, rfq_id=rfq_id, por=usuario)
                encolada = True
                log.info("RFQ=%s: este proceso no puede mandar (modo %s, falta "
                         "%s); la oferta queda en la bandeja de salida (id=%s) "
                         "para el lector de escritorio.",
                         rfq_id, diag["modo"], ", ".join(diag["faltan"]), salida_id)
            except Exception as error:
                log.error("RFQ=%s: no se pudo encolar la oferta: %s", rfq_id, error)
                raise RuntimeError(
                    "La oferta se generó pero el correo no salió ni se pudo "
                    f"dejar en la bandeja de salida: {error}") from error
        else:
            try:
                enviado = bool(outbound.enviar(contenido))
            except Exception as error:  # el PDF y la constancia se quedan igual
                log.error("RFQ=%s: la oferta no salió: %s", rfq_id, error)
                raise RuntimeError(f"La oferta se generó pero el correo no salió: {error}") from error
    else:
        log.info("RFQ=%s: oferta LISTA pero no enviada (ENVIO_MANUAL apagado). "
                 "Para: %s · %s", rfq_id, params["destinatario"], archivo)

    ahora = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    oferta = {
        "archivo": str(archivo),
        "destinatario": params["destinatario"],
        "enviada": enviado,
        # Encolada = el correo está redactado y esperando a que el lector de
        # escritorio lo despache por Outlook. No es lo mismo que "no se mandó".
        "encolada": encolada,
        "fecha": ahora,
        "por": usuario,
        "lead_time": params["lead_time"],
        "incoterm": params["incoterm"],
        "validez": params["validez_oferta"],
        "tramos": [{"cantidad": t["cantidad"], "precio_pc": t["precio_pc"]}
                   for t in prep["costeado"]["tramos"]],
        "costeo_completo": bool(prep["costeado"]["costeo"].get("completo")),
        "nota_correo": nota_correo,
    }
    quien = f"[PM: {usuario}] " if usuario else ""
    nota = (f"{quien}OFERTA {'ENVIADA' if enviado else 'GENERADA (sin enviar)'} — "
            f"{archivo.name} → {params['destinatario']}")
    if nota_correo:
        nota += f"\nNota en el correo: {nota_correo}"
    repository.anotar_oferta(rfq_id, oferta, nota=nota, conexion=conexion)

    return {"rfq_id": rfq_id, "archivo": str(archivo), "nombre_archivo": archivo.name,
            "destinatario": params["destinatario"], "enviado": enviado,
            # Para que la pantalla no diga "no se envió" cuando lo que pasa es
            # que está esperando a quien tiene Outlook abierto.
            "encolada": encolada,
            "envio_habilitado": habilitado, "listo": prep["listo"],
            "motivos": prep["motivos"],
            "motivos_i18n": prep.get("motivos_i18n") or []}
