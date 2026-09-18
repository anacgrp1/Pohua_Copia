"""Antes de probar el flujo completo: ¿está todo puesto?

    python scripts/comprobar_flujo.py

Comprueba, una por una, las piezas que hacen falta para que un correo de la
carpeta de pruebas acabe en una cotización con avisos en el teléfono, y dice
qué falta y dónde se pone. No manda correos, no marca nada como leído y no
escribe en la base: sólo mira.

Se corre donde estén las credenciales: en tu computadora con el `.env`, o en
la consola de Render (Shell) para comprobar lo que hay DESPLEGADO, que es lo
que de verdad va a correr.

Devuelve 1 si falta algo que impida la prueba, 0 si se puede empezar.
"""
from __future__ import annotations

import os
import sys

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

BIEN, MAL, AVISO = "  OK  ", " FALTA", " OJO  "

_problemas = []
_avisos = []


def linea(marca, titulo, detalle=""):
    print(f"[{marca}] {titulo}" + (f"\n         {detalle}" if detalle else ""))


def bien(titulo, detalle=""):
    linea(BIEN, titulo, detalle)


def falta(titulo, detalle=""):
    linea(MAL, titulo, detalle)
    _problemas.append(titulo)


def ojo(titulo, detalle=""):
    linea(AVISO, titulo, detalle)
    _avisos.append(titulo)


def titulo(texto):
    print()
    print(texto)
    print("-" * len(texto))


# --------------------------------------------------------------------------- #

def configuracion(c):
    titulo("1. Configuración")

    entorno = getattr(c, "APP_ENV", "") or "(sin definir)"
    bien(f"Entorno: {entorno}")

    if (getattr(c, "DATABASE_URL", "") or "").strip():
        from urllib.parse import urlparse
        host = urlparse(c.DATABASE_URL).hostname or "?"
        bien(f"Base de datos: {host}")
    else:
        falta("No hay DATABASE_URL", "Sin base no hay RFQ que registrar.")

    if (getattr(c, "JWT_SECRET", "") or "").strip():
        bien("JWT_SECRET puesta (se puede iniciar sesión)")
    else:
        falta("Falta JWT_SECRET", "Sin ella no se puede entrar a Pohua.")

    if (getattr(c, "ANTHROPIC_API_KEY", "") or "").strip():
        bien("ANTHROPIC_API_KEY puesta (se puede leer el correo y el plano)")
    else:
        falta("Falta ANTHROPIC_API_KEY",
              "El correo se registraría, pero sin extracción: el RFQ acabaría "
              "en Incomplete.")


def base_de_datos():
    titulo("2. Esquema de la base")
    try:
        import app.persistence.migraciones as migraciones
        estado = migraciones.estado()
    except Exception as error:
        falta("No se pudo consultar el esquema", str(error))
        return

    if not estado.get("disponible"):
        falta("No se pudo conectar a la base", estado.get("motivo", ""))
        return

    pendientes = estado.get("pendientes") or []
    if pendientes:
        falta(f"{len(pendientes)} migración(es) sin aplicar",
              ", ".join(pendientes) + "\n         Se aplican solas al arrancar "
              "si AUTO_MIGRAR está encendida, o con el workflow de Neon.")
    else:
        bien(f"Esquema al día ({len(estado.get('aplicadas') or [])} migraciones)")


def buzon(c):
    titulo("3. El buzón")

    modo = (getattr(c, "MAIL_MODE", "") or "imap").lower()
    carpeta = (getattr(c, "MAIL_FOLDER", "") or "INBOX")
    bien(f"Modo {modo.upper()}, carpeta '{carpeta}'")
    if carpeta.upper() == "INBOX":
        ojo("Se va a leer la BANDEJA DE ENTRADA, no una carpeta de pruebas",
            "Para probar sin tocar el correo de ventas: MAIL_FOLDER=TEST.")

    try:
        from app.email.factory import EmailProviderFactory
        proveedor = EmailProviderFactory.get_provider()
        # `connect()` no lanza: devuelve False y lo apunta en el log. Si no se
        # mirara, `fetch_unread_messages()` devolvería [] y esto diría "no hay
        # correos sin leer" cuando lo que pasa es que no se pudo ni entrar.
        conectado = proveedor.connect()
        if conectado is False:
            falta("No se pudo abrir el buzón",
                  "Revisa IMAP_SERVER / IMAP_USER / IMAP_PASSWORD (o el token "
                  "de Graph) y que haya salida a internet desde aquí.")
            return
        mensajes = proveedor.fetch_unread_messages()
    except Exception as error:
        falta("No se pudo abrir el buzón", str(error))
        return

    if mensajes:
        bien(f"{len(mensajes)} correo(s) SIN LEER en '{carpeta}'",
             "; ".join((m.subject or "(sin asunto)")[:60] for m in mensajes[:3]))
    else:
        ojo(f"No hay correos sin leer en '{carpeta}'",
            "El ciclo sólo mira los NO LEÍDOS. Marca el de prueba como no "
            "leído antes de lanzarlo.")

    try:
        proveedor.disconnect()
    except Exception:
        pass


def horario_de_atencion():
    titulo("4. Horario de atención")
    try:
        import app.rfq.horario as horario
        estado = horario.estado()
    except Exception as error:
        falta("No se pudo leer el horario", str(error))
        return

    ventana = (f"{estado['desde']}:00–{estado['hasta']}:00 de {estado['ciudad']}, "
               f"días {estado['dias']}")
    if not estado["activo"]:
        ojo("Horario apagado: se lee a cualquier hora", ventana)
    elif estado["abierto"]:
        bien("Abierto ahora mismo", f"{ventana} · cierra {estado['proximo_cierre']}")
    else:
        ojo("CERRADO ahora mismo: el ciclo automático no abrirá el buzón",
            f"{ventana} · abre {estado['proxima_apertura']}\n"
            "         El botón 'Ejecutar ciclo' se salta el horario a propósito.")


def envio(c):
    titulo("5. Correo saliente")
    import app.email.outbound as outbound
    if outbound.envio_habilitado():
        ojo("ENVIO_AUTOMATICO ENCENDIDO: los correos salen de verdad",
            "Con un remitente real, le llega al cliente. Para ensayar sin que "
            "salga nada: ENVIO_AUTOMATICO=false.")
    else:
        bien("ENVIO_AUTOMATICO apagado",
             "Los correos se construyen y se registran en el log, pero no salen.")


def avisos(c):
    titulo("6. Avisos en el teléfono y en la computadora")

    try:
        import app.notifications.push as push
    except Exception as error:
        falta("No se pudo cargar el módulo de avisos", str(error))
        return

    if push.habilitado():
        bien("Claves VAPID puestas: los avisos pueden salir al teléfono")
    else:
        falta("Faltan las claves VAPID",
              "python scripts/generar_vapid.py, y las dos líneas a Render "
              "(Environment). Sin ellas la campana funciona dentro de Pohua, "
              "pero no llega nada al teléfono.")

    try:
        suscripciones = push.listar()
    except Exception as error:
        ojo("No se pudo contar los dispositivos suscritos", str(error))
        return

    if suscripciones:
        quienes = ", ".join(sorted({s.get("correo") or "?" for s in suscripciones}))
        bien(f"{len(suscripciones)} dispositivo(s) suscrito(s)", quienes)
    else:
        ojo("Ningún dispositivo suscrito todavía",
            "En cada aparato: abre Pohua, entra en la campana y acepta los "
            "avisos. En iPhone hay que añadir Pohua a la pantalla de inicio "
            "antes.")


def recordatorio(c):
    titulo("7. Recordatorio de lo que espera dictamen")

    import app.rfq.recordatorios as recordatorios
    horas = recordatorios.horas()
    if not horas:
        ojo("Apagado (RECORDATORIO_HORAS=0)",
            "El aviso de la campana y del teléfono sigue igual; lo que no sale "
            "es el correo de respaldo.")
        return

    bien(f"Encendido: recuerda por correo lo que lleve más de {horas} h esperando")

    if recordatorios.enlace_de("COT-0"):
        bien(f"Enlace del correo: {recordatorios.enlace_de('COT-0')}")
    else:
        falta("Falta APP_URL",
              "Sin ella el enlace del recordatorio iría a localhost y el correo "
              "no se manda. En Render: APP_URL=https://tu-servicio.onrender.com")

    try:
        import app.auth.repository as auth
        personas = auth.usuarios_con_permiso("rfq:dictaminar")
    except Exception as error:
        ojo("No se pudo leer quién dictamina", str(error))
        return

    if personas:
        bien(f"{len(personas)} persona(s) recibirían el recordatorio",
             ", ".join(f"{p['nombre']} <{p['correo']}>" for p in personas))
    else:
        ojo("Nadie con permiso 'rfq:dictaminar' y correo",
            "Da de alta en Pohua a quien vaya a dictaminar, con rol pm o admin.")


def lector():
    titulo("8. El lector de planos")
    ruta = os.path.join(RAIZ, "vendor", "lector")
    if os.path.isdir(ruta):
        bien("El lector está en vendor/lector")
    else:
        ojo("No está vendor/lector en esta copia",
            "El correo se procesa igual; lo que no habrá es lectura del plano "
            "ni recortes.")

    calculadora = os.path.join(RAIZ, "vendor", "calculadora")
    if os.path.isdir(calculadora) and os.listdir(calculadora):
        bien("Las calculadoras están en vendor/calculadora")
    else:
        ojo("No están las calculadoras vendorizadas",
            "scripts/vendorizar_nucleo.py las regenera.")


def main() -> int:
    # El informe lo escribe esto, línea a línea. Los módulos de debajo son
    # habladores —el proveedor de correo escupe la traza entera de un fallo de
    # red— y aquí eso sepulta la única línea que hay que leer.
    import logging
    logging.disable(logging.ERROR)

    print("Comprobación del flujo — Pohua")
    print("=" * 40)

    import app.core.config as config
    c = config.settings

    configuracion(c)
    base_de_datos()
    buzon(c)
    horario_de_atencion()
    envio(c)
    avisos(c)
    recordatorio(c)
    lector()

    titulo("Resumen")
    if _problemas:
        print(f"Falta {len(_problemas)} cosa(s) antes de poder probar:")
        for p in _problemas:
            print(f"  · {p}")
    else:
        print("No falta nada para empezar la prueba.")
    if _avisos:
        print(f"\nY {len(_avisos)} cosa(s) que conviene mirar:")
        for a in _avisos:
            print(f"  · {a}")
    print()
    return 1 if _problemas else 0


if __name__ == "__main__":
    sys.exit(main())
