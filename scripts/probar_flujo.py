#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""¿Por qué este RFQ no está listo para aprobar y mandar?

Para qué
--------
El recorrido tiene cinco puertas —el plano, el dictamen, el costeo, la oferta y
el envío— y cada una avisa en su propio sitio: una en la ficha, otra en la
ventana de revisión, otra en el registro de Render. Averiguar en cuál se quedó
un RFQ significaba abrir tres pantallas y un traceback.

Esto las recorre todas de una vez contra la base de verdad y dice, en orden,
qué falta y qué hacer. No cambia nada: sólo lee.

    python scripts/probar_flujo.py                  # el RFQ más reciente
    python scripts/probar_flujo.py --rfq INT-2BC4C50E
    python scripts/probar_flujo.py --leer-plano     # además lo relee con la IA

``--leer-plano`` es lo único que gasta: una llamada al modelo. Sin esa bandera
el guion no toca la API.
"""

import os
import sys
from pathlib import Path

# El mismo arranque que scripts/limpiar_rfqs.py: sin esto, `python
# scripts/probar_flujo.py` no encuentra el paquete `app`, porque Python pone
# en la ruta la carpeta del guion y no la raíz del proyecto.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)

OK =    "  [ok]    "
FALTA = "  [falta] "
AVISO = "  [ojo]   "


def _titulo(texto):
    print("\n" + texto)
    print("-" * len(texto))


def _num(valor):
    return "—" if valor is None else valor


def _ultimo_rfq(cur):
    cur.execute("SELECT rfq_id FROM rfqs ORDER BY fecha_registro DESC LIMIT 1;")
    fila = cur.fetchone()
    return fila[0] if fila else None


def main() -> int:
    argumentos = sys.argv[1:]
    leer_plano = "--leer-plano" in argumentos
    rfq_id = None
    if "--rfq" in argumentos:
        i = argumentos.index("--rfq")
        if i + 1 < len(argumentos):
            rfq_id = argumentos[i + 1]

    import app.persistence.duplicates as duplicates

    with duplicates.conexion_bd() as conexion:
        with conexion.cursor() as cur:
            if not rfq_id:
                rfq_id = _ultimo_rfq(cur)
                if not rfq_id:
                    print("No hay ningún RFQ en la base.")
                    return 1
                print(f"Sin --rfq: se toma el más reciente, {rfq_id}.")

            cur.execute(
                "SELECT estado, veredicto_sistema, veredicto_final, score, "
                "       material, part_number, datos_json, message_id "
                "FROM rfqs WHERE rfq_id = %s ORDER BY version DESC LIMIT 1;",
                (rfq_id,))
            fila = cur.fetchone()
            if not fila:
                print(f"No existe el RFQ {rfq_id}.")
                return 1
            (estado, veredicto, veredicto_final, score,
             material, part_number, datos, message_id) = fila
            datos = datos or {}

            cur.execute(
                "SELECT datos_json FROM resortes_cotizacion "
                "WHERE rfq_id = %s ORDER BY id DESC LIMIT 1;", (rfq_id,))
            fila_r = cur.fetchone()
            resorte = (fila_r[0] or {}) if fila_r else {}

    pendientes_para_aprobar = []
    pendientes_para_mandar = []

    print(f"\n{'=' * 66}")
    print(f" RFQ {rfq_id} · {part_number or 'sin número de parte'} · estado {estado}")
    print(f"{'=' * 66}")

    # ---------------------------------------------------------------- 1. plano
    _titulo("1. El plano")
    import app.rfq.relectura as relectura

    if leer_plano:
        print("  Releyendo con la IA (esto gasta una llamada)…")
        lectura = relectura.releer(rfq_id, message_id=message_id or "")
        print(f"  Resultado: {lectura['estado']}")
        if lectura.get("motivo"):
            print(f"  Motivo: {lectura['motivo']}")
        if lectura["estado"] == "leido" and lectura["resorte"]:
            resorte = lectura["resorte"]

    guardados = relectura.planos_guardados(rfq_id)
    if guardados:
        print(OK + f"Hay {len(guardados)} plano/s guardado/s: "
              + ", ".join(plano["nombre"] for plano in guardados))
        legibles = relectura.legibles(guardados)
        if not legibles:
            print(FALTA + "Ninguno es un formato que el lector abra (.pdf/.png/.jpg).")
            pendientes_para_aprobar.append(
                "El plano guardado no está en un formato legible.")
    else:
        print(AVISO + "No hay ningún plano guardado para este RFQ.")

    calibre = resorte.get("diametro_alambre_mm")
    if calibre:
        print(OK + f"Diámetro de alambre: {calibre} mm")
    else:
        print(FALTA + "Sin diámetro de alambre: sin él no hay máquina ni peso.")
        pendientes_para_aprobar.append(
            "Falta el diámetro de alambre. Corre esto con --leer-plano, o "
            "escríbelo en la ventana de revisión y pulsa Recalcular.")

    for etiqueta, clave in (("Diámetro exterior", "diametro_exterior_mm"),
                            ("Longitud libre", "longitud_libre_mm"),
                            ("Espiras totales", "numero_espiras_totales")):
        print(f"            {etiqueta}: {_num(resorte.get(clave))}")

    confianza = resorte.get("confianza")
    if confianza is not None:
        print(f"            Confianza de la lectura: {confianza}")
    if resorte.get("ajustado_por"):
        print(AVISO + f"Valores corregidos a mano por {resorte['ajustado_por']}: "
              + ", ".join(resorte.get("campos_ajustados") or []))

    # --------------------------------------------------------- 2. factibilidad
    _titulo("2. El dictamen de factibilidad")
    try:
        import app.feasibility.engine as engine
        factibilidad = engine.evaluar_factibilidad(resorte)
        print(f"  Veredicto: {factibilidad['veredicto']} · "
              f"score {factibilidad['score']} ({factibilidad.get('banda')})")
        criticos = [m for m in factibilidad["motivos"] if m["nivel"] == "crit"]
        for motivo in factibilidad["motivos"]:
            marca = FALTA if motivo["nivel"] == "crit" else AVISO
            print(marca + f"[{motivo['nivel']}] {motivo['texto']}")
        if factibilidad["veredicto"] == engine.VEREDICTO_FACTIBLE:
            print(OK + "Factible: sólo necesita la aprobación del PM.")
        else:
            razon = ("hay un hallazgo crítico" if criticos
                     else f"el score {factibilidad['score']} no llega al umbral")
            pendientes_para_aprobar.append(
                f"El dictamen dice «requiere revisión» porque {razon}.")
        if veredicto and veredicto != factibilidad["veredicto"]:
            print(AVISO + f"El guardado dice '{veredicto}' y con los datos de "
                  "ahora saldría distinto: pulsa Recalcular en la ventana.")
    except Exception as error:
        print(FALTA + f"No se pudo dictaminar: {error}")
        pendientes_para_aprobar.append(f"El motor de factibilidad falló: {error}")

    # ---------------------------------------------------------------- 3. costeo
    _titulo("3. El costeo")
    try:
        import app.rfq.costeo as costeo_rfq
        costeado = costeo_rfq.costear(rfq_id, datos, resorte, material)
        tramos = costeado["tramos"]
        print("  Cantidades del correo: "
              + (", ".join(str(c) for c in costeado["cantidades"]) or "ninguna"))
        if tramos:
            print(OK + f"{len(tramos)} tramo/s costeado/s:")
            for tramo in tramos:
                print(f"          {tramo['cantidad']:>9} pcs → "
                      f"${tramo['precio_pc']}/pc")
        else:
            print(FALTA + "No hay ni un tramo costeado.")
            pendientes_para_aprobar.append("No hay tramos costeados.")
        if costeado["costeo"].get("completo"):
            print(OK + "El costeo está completo: ningún dato inventado.")
        else:
            for falta in costeado["costeo"].get("faltantes") or []:
                print(AVISO + falta)
            print(AVISO + "El costeo es ORIENTATIVO: la oferta pedirá forzarla.")
        if costeado.get("error_costeo"):
            print(FALTA + f"Error al costear: {costeado['error_costeo']}")
    except Exception as error:
        print(FALTA + f"No se pudo costear: {error}")

    # ---------------------------------------------------------------- 4. oferta
    _titulo("4. La oferta")
    try:
        import app.rfq.oferta as oferta
        prep = oferta.preparar(rfq_id)
        destino = (prep.get("correo") or {}).get("destinatario")
        print(f"  Iría a: {destino or '(sin destinatario)'}")
        if prep["listo"]:
            print(OK + "Lista para mandarse.")
        else:
            for motivo in prep["motivos"]:
                print(AVISO + motivo)
            pendientes_para_mandar.extend(prep["motivos"])
        if not destino:
            pendientes_para_mandar.append(
                "El RFQ no tiene a quién contestarle.")
    except Exception as error:
        print(AVISO + f"Todavía no se puede preparar la oferta: {error}")
        pendientes_para_mandar.append(str(error))

    # ---------------------------------------------------------------- 5. envío
    _titulo("5. El envío del correo")
    import app.email.outbound as outbound
    import app.email.bandeja_salida as bandeja

    manual = outbound.envio_habilitado(manual=True)
    if manual:
        print(OK + "ENVIO_MANUAL encendido: la oferta del PM sí sale.")
    else:
        print(FALTA + "ENVIO_MANUAL apagado: la oferta no se despacharía.")
    if not manual:
        pendientes_para_mandar.append("ENVIO_MANUAL está apagado.")

    diag = outbound.diagnostico_envio()
    if diag["puede"]:
        print(OK + f"Este proceso puede mandar (modo {diag['modo'].upper()}, "
              f"por {diag['canal'].upper()}).")
    else:
        print(AVISO + f"Este proceso NO puede mandar (modo {diag['modo'].upper()}): "
              f"falta {', '.join(diag['faltan'])}.")
        print("          No es un fallo si quien manda es la aplicación de "
              "escritorio: la oferta se encola y sale de allí.")

    try:
        esperando = bandeja.hay_pendientes()
        if esperando:
            print(AVISO + f"{esperando} correo/s esperando en la bandeja de "
                  "salida. Abre la aplicación de escritorio y pulsa «Leer ahora».")
        else:
            print(OK + "La bandeja de salida está vacía.")
    except Exception as error:
        print(AVISO + f"No se pudo mirar la bandeja de salida: {error}")

    # ------------------------------------------------------------- el resumen
    print(f"\n{'=' * 66}")
    if not pendientes_para_aprobar:
        print(" PARA APROBAR: nada. Sólo falta que el PM pulse Aprobar.")
    else:
        print(" PARA APROBAR, falta:")
        for i, falta in enumerate(pendientes_para_aprobar, 1):
            print(f"   {i}. {falta}")

    print()
    if not pendientes_para_mandar:
        print(" PARA QUE LLEGUE AL CLIENTE: nada que dependa de los datos.")
    else:
        print(" PARA QUE LLEGUE AL CLIENTE, falta:")
        for i, falta in enumerate(pendientes_para_mandar, 1):
            print(f"   {i}. {falta}")
    print(f"{'=' * 66}\n")

    return 0 if not pendientes_para_aprobar else 2


if __name__ == "__main__":
    raise SystemExit(main())
