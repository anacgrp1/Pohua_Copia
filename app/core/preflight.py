"""¿Está todo puesto para que el flujo funcione?

Una sola comprobación, dos puertas: la consola
(``python scripts/comprobar_flujo.py``) y la propia aplicación
(``GET /api/system/preflight``, que la pinta en Perfil → Sistema). Lo segundo
es lo que hace falta para probar en el SERVIDOR DESPLEGADO, donde no siempre
hay una consola a mano: se abre Pohua, se mira la lista y se ve qué falta.

Cada punto dice tres cosas: cómo está (``ok`` / ``falta`` / ``ojo``), qué pasa
en una línea, y qué hacer. ``falta`` es lo que impide la prueba; ``ojo`` es lo
que conviene mirar antes de sacar conclusiones ("no hay correos sin leer" no
es una avería, pero explica que no pase nada).

No manda correos, no marca nada como leído y no escribe en la base: sólo mira.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List

log = logging.getLogger("cotizador.preflight")

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

OK, FALTA, OJO = "ok", "falta", "ojo"


class _Informe:
    """Va juntando los puntos en el orden en que se comprueban."""

    def __init__(self):
        self.puntos: List[Dict[str, Any]] = []
        self.grupo = ""

    def en(self, grupo: str) -> None:
        self.grupo = grupo

    def _apuntar(self, estado, titulo, detalle=""):
        self.puntos.append({"grupo": self.grupo, "estado": estado,
                            "titulo": titulo, "detalle": detalle})

    def ok(self, titulo, detalle=""):
        self._apuntar(OK, titulo, detalle)

    def falta(self, titulo, detalle=""):
        self._apuntar(FALTA, titulo, detalle)

    def ojo(self, titulo, detalle=""):
        self._apuntar(OJO, titulo, detalle)


# --------------------------------------------------------------------------- #
# Las comprobaciones
# --------------------------------------------------------------------------- #

def _entorno(inf, c, desde_escritorio=False):
    """Lo que tiene que estar instalado en ESTE Python.

    Con dos Python en la computadora —el de siempre y uno recién instalado—
    la aplicación puede arrancar con el que no tiene las dependencias. Pasó
    (2026-09-29): la ventana abría, el lector «leía» y cada ciclo decía «0 sin
    leer» mientras no había podido hablar con Outlook, las ofertas de la
    bandeja de salida fallaban una tras otra y el horario caía a UTC. Aquí se
    dice qué falta y con qué orden se instala, con la ruta de este Python.
    """
    import sys

    from app.email.outlook_provider import comando_de_instalacion, falta_pywin32
    inf.en("Instalación")
    faltan = []
    # PySide6 y pywin32 sólo en la aplicación de escritorio: el servidor
    # (Render) no los usa y no puede darlos por faltantes.
    modulos = [("psycopg2", "psycopg2-binary")]
    if desde_escritorio:
        modulos.append(("PySide6", "PySide6"))
    for modulo, paquete in modulos:
        try:
            __import__(modulo)
        except Exception:
            faltan.append(paquete)
    zona = getattr(c, "HORARIO_ZONA", "America/Chicago") or "America/Chicago"
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(zona)
    except Exception:
        faltan.append("tzdata")
    modo = str(getattr(c, "MAIL_MODE", "") or "").lower()
    if desde_escritorio and sys.platform == "win32" and modo == "outlook" and falta_pywin32():
        faltan.append("pywin32")
    if faltan:
        orden = (comando_de_instalacion() if desde_escritorio else
                 "pip install -r requirements.txt")
        inf.falta(f"Faltan paquetes en este Python: {', '.join(faltan)}",
                  f"Instálalos con: {orden}")
    else:
        inf.ok(f"Python {sys.version.split()[0]} con todo lo necesario")


def _configuracion(inf, c):
    inf.en("Configuración")
    inf.ok(f"Entorno: {getattr(c, 'APP_ENV', '') or '(sin definir)'}")

    if (getattr(c, "DATABASE_URL", "") or "").strip():
        from urllib.parse import urlparse
        inf.ok(f"Base de datos: {urlparse(c.DATABASE_URL).hostname or '?'}")
    else:
        inf.falta("No hay DATABASE_URL", "Sin base no hay RFQ que registrar.")

    if (getattr(c, "JWT_SECRET", "") or "").strip():
        inf.ok("JWT_SECRET puesta")
    else:
        inf.falta("Falta JWT_SECRET", "Sin ella no se puede entrar a Pohua.")

    if (getattr(c, "ANTHROPIC_API_KEY", "") or "").strip():
        inf.ok("ANTHROPIC_API_KEY puesta")
    else:
        inf.falta("Falta ANTHROPIC_API_KEY",
                  "El correo se registraría, pero sin extracción: el RFQ "
                  "acabaría en Incomplete.")


def _esquema(inf):
    inf.en("Esquema de la base")
    try:
        import app.persistence.migraciones as migraciones
        estado = migraciones.estado()
    except Exception as error:
        inf.falta("No se pudo consultar el esquema", str(error))
        return

    if not estado.get("disponible"):
        inf.falta("No se pudo conectar a la base", estado.get("motivo", ""))
        return

    pendientes = estado.get("pendientes") or []
    if pendientes:
        inf.falta(f"{len(pendientes)} migración(es) sin aplicar",
                  ", ".join(pendientes))
    else:
        inf.ok(f"Esquema al día ({len(estado.get('aplicadas') or [])} migraciones)")


def _latido_escritorio(c):
    """¿Está la aplicación de escritorio leyendo el correo ahora mismo?

    El latido vive en la memoria del proceso web (``api.server``), que es quien
    lo recibe. Desde la consola ese módulo ni está cargado, y entonces no se
    puede saber: se dice, en vez de dar por hecho que no.

    Se importa por `sys.modules` a propósito: importar `api.server` desde un
    script levantaría la aplicación entera sólo para leer un número.
    """
    import sys
    import time

    servidor = sys.modules.get("api.server")
    if servidor is None:
        return {"sabido": False, "activo": False, "hace": None}

    ultimo = getattr(servidor, "_last_heartbeat_time", 0.0) or 0.0
    if not ultimo:
        return {"sabido": True, "activo": False, "hace": None}

    hace = time.time() - ultimo
    intervalo = int(getattr(c, "INTERVALO_MINUTOS", 5) or 5)
    # La misma tolerancia que usa el worker para apartarse: intervalo + 1 min.
    return {"sabido": True, "activo": hace < (intervalo * 60 + 60), "hace": hace}


def _quien_lee(inf, c, latido, desde_escritorio=False):
    inf.en("Quién lee el correo")

    if desde_escritorio:
        # Lo pregunta la propia aplicación de escritorio: decirle "no se sabe
        # si la aplicación de escritorio está leyendo" sería cómico.
        inf.ok("Lo lees tú, desde esta aplicación",
               "Mientras esté leyendo y el latido llegue, el worker del "
               "servidor se aparta para no leer el mismo buzón dos veces.")
        if not (getattr(c, "WORKER_SECRET_KEY", "") or "").strip():
            inf.ojo("WORKER_SECRET_KEY sin poner: el latido no saldrá",
                    "Sin ella el servidor no acepta el aviso, y podría leer el "
                    "mismo buzón a la vez.")
        return

    if latido["activo"]:
        minutos = int((latido["hace"] or 0) // 60)
        inf.ok("La aplicación de escritorio está leyendo el correo",
               f"Último latido hace {minutos} min. Mientras siga latiendo, el "
               "worker del servidor se aparta a propósito para no leer dos "
               "veces el mismo buzón.")
        return

    auto = str(os.environ.get("WORKER_AUTOSTART",
                              getattr(c, "WORKER_AUTOSTART", "false"))).lower()
    if auto in ("1", "true", "yes", "on"):
        inf.ok("Lo lee el servidor",
               f"El worker arranca con él, cada {getattr(c, 'INTERVALO_MINUTOS', 5)} min.")
    elif not latido["sabido"]:
        inf.ojo("Desde la consola no se sabe si la aplicación de escritorio está leyendo",
                "El latido vive en el proceso web. Míralo en Perfil → Sistema.")
    else:
        inf.ojo("Nadie lee el buzón solo",
                "Se lee al pulsar «Ejecutar ciclo». Para que entre solo: "
                "WORKER_AUTOSTART=true en el servidor, o deja corriendo la "
                "aplicación de escritorio.")

    if not (getattr(c, "WORKER_SECRET_KEY", "") or "").strip():
        inf.ojo("WORKER_SECRET_KEY sin poner: el latido está apagado",
                "Sin ella la aplicación de escritorio no puede avisar de que "
                "ella lee, y los dos leerían el mismo buzón.")


def _buzon(inf, c, con_buzon: bool, latido):
    inf.en("El buzón")
    modo = (getattr(c, "MAIL_MODE", "") or "imap").lower()
    carpeta = (getattr(c, "MAIL_FOLDER", "") or "INBOX")
    inf.ok(f"Modo {modo.upper()}, carpeta '{carpeta}'")

    if carpeta.upper() == "INBOX":
        inf.ojo("Se leerá la BANDEJA DE ENTRADA, no una carpeta de pruebas",
                "Para ensayar sin tocar el correo de ventas: MAIL_FOLDER=TEST.")

    # La lista de qué credenciales hacen falta vive en UN sitio
    # (app/email/entrada.py), el mismo que consulta el ciclo antes de abrir
    # el buzón. Con dos copias, una se queda atrás y el preflight acaba
    # diciendo que está todo bien mientras el ciclo falla.
    import app.email.entrada as entrada
    diagnostico = entrada.diagnostico_lectura()

    # Apagado a propósito no es una falta. Marcar como problema algo que
    # alguien eligió es la forma más rápida de que nadie vuelva a leer estos
    # avisos.
    if diagnostico.get("apagado"):
        inf.ok("Este proceso no lee el buzón, y es a propósito",
               diagnostico["nota"] + " Para que lea el servidor: pon "
               "MAIL_MODE=graph (o imap) con sus credenciales.")
        return

    faltan = diagnostico["faltan"]
    if faltan:
        if latido["activo"]:
            # Con la aplicación de escritorio leyendo, el servidor no necesita
            # credenciales: no es un fallo, es el reparto de trabajo elegido.
            inf.ojo("El servidor no tiene credenciales del buzón",
                    "No hacen falta mientras lea la aplicación de escritorio. "
                    "Si algún día quieres que lea el servidor: " +
                    ", ".join(faltan) + ".")
        else:
            inf.falta("Faltan credenciales del buzón: " + ", ".join(faltan),
                      "O las pones en el servidor (con Microsoft 365, Graph: "
                      "AZURE_* y GRAPH_USER), o dejas leyendo la aplicación de "
                      "escritorio, que las tiene en tu computadora.")
        return

    if not con_buzon:
        inf.ok("Credenciales del buzón puestas",
               "No se probó la conexión en esta comprobación.")
        return

    try:
        from app.email.factory import EmailProviderFactory
        proveedor = EmailProviderFactory.get_provider()
        # `connect()` no lanza: devuelve False y lo apunta en el log. Si no se
        # mirara, `fetch_unread_messages()` devolvería [] y esto diría "no hay
        # correos sin leer" cuando lo que pasa es que no se pudo ni entrar.
        if proveedor.connect() is False:
            inf.falta("No se pudo abrir el buzón",
                      "Revisa las credenciales y que el servidor tenga salida.")
            return
        mensajes = proveedor.fetch_unread_messages()
    except Exception as error:
        inf.falta("No se pudo abrir el buzón", str(error))
        return

    if mensajes:
        asuntos = "; ".join((m.subject or "(sin asunto)")[:60] for m in mensajes[:3])
        inf.ok(f"{len(mensajes)} correo(s) sin leer en '{carpeta}'", asuntos)
    else:
        inf.ojo(f"No hay correos sin leer en '{carpeta}'",
                "El ciclo sólo mira los NO LEÍDOS: marca el de prueba como no "
                "leído antes de lanzarlo.")

    try:
        proveedor.disconnect()
    except Exception:
        pass


def _horario(inf):
    inf.en("Horario de atención")
    try:
        import app.rfq.horario as horario
        estado = horario.estado()
    except Exception as error:
        inf.falta("No se pudo leer el horario", str(error))
        return

    ventana = (f"{estado['desde']}:00–{estado['hasta']}:00 de {estado['ciudad']}, "
               f"días {estado['dias']}")
    if not estado["activo"]:
        inf.ojo("Horario apagado: se lee a cualquier hora", ventana)
    elif estado["abierto"]:
        inf.ok("Abierto ahora mismo",
               f"{ventana} · cierra {estado['proximo_cierre']}")
    else:
        inf.ojo("Cerrado ahora: el ciclo automático no abrirá el buzón",
                f"{ventana} · abre {estado['proxima_apertura']}. "
                "El botón «Ejecutar ciclo» se salta el horario.")


def _envio(inf):
    inf.en("Correo saliente")
    try:
        import app.email.outbound as outbound
        automatico = outbound.envio_habilitado()
        manual = outbound.envio_habilitado(manual=True)
        diag = outbound.diagnostico_envio()
    except Exception as error:
        inf.ojo("No se pudo leer el estado del envío", str(error))
        return

    # Primero lo que hace IMPOSIBLE mandar, porque un interruptor encendido
    # sobre un servidor sin cuenta emisora es un verde que engaña: así se
    # quedó una oferta sin salir, con el PDF ya generado y el error saliendo
    # recién al pulsar.
    if not diag["puede"]:
        inf.falta("El servidor no puede mandar correo: falta " +
                  ", ".join(diag["faltan"]),
                  "Modo %s, por %s. %s" % (diag["modo"].upper(),
                                           diag["canal"].upper(), diag["nota"]))
    else:
        inf.ok("Hay cuenta para mandar (modo %s, por %s)"
               % (diag["modo"].upper(), diag["canal"].upper()))

    if automatico:
        inf.ojo("ENVIO_AUTOMATICO encendido: el sistema escribe solo",
                "Peticiones de datos y recordatorios salen sin que nadie los "
                "mire. Con un buzón de clientes reales, llegan.")
    else:
        inf.ok("ENVIO_AUTOMATICO apagado",
               "Lo que el sistema manda solo se construye y se registra, pero "
               "no sale.")

    # El de la oferta es OTRO interruptor, y es el que la gente busca cuando
    # dice "no me llegó la cotización".
    if manual:
        inf.ok("ENVIO_MANUAL encendido: lo que decide el PM sí sale",
               "La oferta al aprobar y la declinación al declinar.")
    else:
        inf.ojo("ENVIO_MANUAL apagado: ni la oferta ni la declinación saldrán",
                "El PDF se genera y queda archivado, pero ningún correo al "
                "cliente se despacha.")


def _avisos(inf):
    inf.en("Avisos en el teléfono")
    try:
        import app.notifications.push as push
    except Exception as error:
        inf.falta("No se pudo cargar el módulo de avisos", str(error))
        return

    if push.habilitado():
        inf.ok("Claves VAPID puestas")
    else:
        inf.falta("Faltan las claves VAPID",
                  "python scripts/generar_vapid.py, y las dos líneas a Render. "
                  "Sin ellas la campana funciona dentro de Pohua, pero no llega "
                  "nada al teléfono.")

    try:
        suscripciones = push.listar()
    except Exception as error:
        inf.ojo("No se pudo contar los dispositivos suscritos", str(error))
        return

    if suscripciones:
        quienes = ", ".join(sorted({s.get("correo") or "?" for s in suscripciones}))
        inf.ok(f"{len(suscripciones)} dispositivo(s) suscrito(s)", quienes)
    else:
        inf.ojo("Ningún dispositivo suscrito",
                "En cada aparato: abre Pohua, entra en la campana y acepta los "
                "avisos. En iPhone, añade Pohua a la pantalla de inicio antes.")


def _recordatorio(inf):
    inf.en("Recordatorio de lo que espera dictamen")
    import app.rfq.recordatorios as recordatorios

    horas = recordatorios.horas()
    if not horas:
        inf.ojo("Apagado (RECORDATORIO_HORAS=0)",
                "La campana y el teléfono siguen igual; lo que no sale es el "
                "correo de respaldo.")
        return

    inf.ok(f"Encendido: recuerda lo que lleve más de {horas} h esperando")

    enlace = recordatorios.enlace_de("COT-0")
    if enlace:
        inf.ok(f"Enlace del correo: {enlace}")
    else:
        inf.falta("Falta APP_URL",
                  "Sin ella el enlace iría a localhost y el correo no se manda. "
                  "APP_URL=https://tu-servicio.onrender.com")

    try:
        import app.auth.repository as auth
        personas = auth.usuarios_con_permiso("rfq:dictaminar")
    except Exception as error:
        inf.ojo("No se pudo leer quién dictamina", str(error))
        return

    if personas:
        inf.ok(f"{len(personas)} persona(s) lo recibirían",
               ", ".join(f"{p['nombre']} <{p['correo']}>" for p in personas))
    else:
        inf.ojo("Nadie con permiso 'rfq:dictaminar' y correo",
                "Da de alta a quien vaya a dictaminar, con rol pm o admin.")


def _lector(inf):
    inf.en("Lector y calculadoras")
    if os.path.isdir(os.path.join(RAIZ, "vendor", "lector")):
        inf.ok("El lector está en vendor/lector")
    else:
        inf.ojo("No está vendor/lector",
                "El correo se procesa igual; lo que no habrá es lectura del "
                "plano ni recortes.")

    calc = os.path.join(RAIZ, "vendor", "calculadora")
    if os.path.isdir(calc) and os.listdir(calc):
        inf.ok("Las calculadoras están en vendor/calculadora")
    else:
        inf.ojo("No están las calculadoras vendorizadas",
                "scripts/vendorizar_nucleo.py las regenera.")


def _catalogo(inf):
    """¿Está en la base el catálogo que validó el taller?

    Sin él, el costeo del flujo usa los valores de marcador de la migración
    007 —otra escalera de overhead, sin transporte del alambre, máquinas sin
    capacidades— y el precio no es el de la calculadora de la planta, que
    lleva los datos buenos dentro. Se reconoce por el parámetro `transpPerLb`,
    que sólo entra con el extracto.
    """
    inf.en("Catálogo de costeo")
    try:
        from pricing import repository
        params = repository.parametros_vigentes()
    except Exception as error:
        inf.ojo("No se pudo leer el catálogo de costeo", str(error))
        return
    if "transpPerLb" in (params or {}):
        inf.ok("El catálogo validado del taller está cargado")
    else:
        inf.falta("El catálogo validado del taller NO está cargado en la base",
                  "El precio del flujo no va a coincidir con la calculadora. Se carga "
                  "una vez, desde la carpeta del proyecto: python scripts/cargar_catalogo.py "
                  "--carpeta _extracto_catalogo")

    # Y los parámetros del motor tienen que ser los de la calculadora V7. Con
    # la escalera de overheads de la calculadora vieja (12/16/20/24) en vez de
    # la de la V7 (30 plano) la ventana daba $0.3223 donde la calculadora da
    # $0.3946.
    _parametros_del_motor(inf, params or {})


def _parametros_del_motor(inf, params):
    from pricing import nucleo

    motor = nucleo.parametros_del_motor()
    if not motor:
        return
    distintos = [f"{clave}: base {params[clave]!r}, motor {valor!r}"
                 for clave, valor in motor.items()
                 if clave in params and params[clave] != valor]
    if distintos:
        inf.falta("Los parámetros vigentes en la base no son los del motor",
                  "; ".join(distintos) + ". La ventana del RFQ y la calculadora "
                  "dan precios distintos. Los pone la migración 030 (o "
                  "scripts/cargar_catalogo.py); si se cambiaron a propósito, "
                  "hay que cambiarlos igual en la calculadora.")
    else:
        inf.ok("Los parámetros del motor son los de la calculadora")


def _legal(inf):
    """Los datos del responsable en el aviso de privacidad.

    Los llena el área legal en ``frontend/legal/responsable.js``. Mientras
    falten, la página los enseña en rojo como pendientes y el aviso no cumple:
    sin la identidad y el domicilio del responsable no hay aviso de privacidad.
    """
    import re

    from app.legal import VERSION_LEGAL

    inf.en("Aviso de privacidad")
    ruta = os.path.join(RAIZ, "frontend", "legal", "responsable.js")
    try:
        with open(ruta, encoding="utf-8") as f:
            texto = f.read()
    except OSError:
        inf.falta("No está frontend/legal/responsable.js")
        return
    obligatorios = ("razonSocial", "domicilio", "correoPrivacidad",
                    "departamentoDatos", "jurisdiccion")
    huecos = [c for c in obligatorios
              if re.search(r"\b%s:\s*null\b" % c, texto)]
    if huecos:
        inf.ojo("Faltan datos del responsable en el aviso de privacidad",
                "Completar en frontend/legal/responsable.js: " + ", ".join(huecos) +
                ". Hasta entonces la página /legal/ los enseña como pendientes.")
    else:
        inf.ok("Los datos del responsable están completos")
    version = re.search(r"VERSION:\s*'([^']+)'", texto)
    if not version or version.group(1) != VERSION_LEGAL:
        inf.falta("La versión de los documentos legales no coincide",
                  "responsable.js dice %s y app/legal.py %s: tienen que ser la misma."
                  % (version.group(1) if version else "—", VERSION_LEGAL))


# --------------------------------------------------------------------------- #
# Público
# --------------------------------------------------------------------------- #

def revisar(con_buzon: bool = True, desde_escritorio: bool = False) -> Dict[str, Any]:
    """Pasa todas las comprobaciones y devuelve el informe.

    ``con_buzon=False`` se salta la conexión real al correo: sirve para una
    comprobación instantánea cuando no se quiere esperar a la red.

    ``desde_escritorio=True`` lo pone la aplicación de escritorio: ella SABE
    quién lee el correo —ella misma—, y el informe lo dice así en vez de
    preguntárselo al latido.
    """
    import app.core.config as config

    inf = _Informe()
    c = config.settings
    latido = _latido_escritorio(c)

    for comprobacion in (
        lambda: _entorno(inf, c, desde_escritorio),
        lambda: _configuracion(inf, c),
        lambda: _esquema(inf),
        lambda: _quien_lee(inf, c, latido, desde_escritorio),
        lambda: _buzon(inf, c, con_buzon, latido),
        lambda: _horario(inf),
        lambda: _envio(inf),
        lambda: _avisos(inf),
        lambda: _recordatorio(inf),
        lambda: _lector(inf),
        lambda: _catalogo(inf),
        lambda: _legal(inf),
    ):
        # Una comprobación que reviente no puede llevarse por delante el resto
        # del informe: es justo cuando más falta hace verlo entero.
        try:
            comprobacion()
        except Exception as error:
            log.exception("Fallo comprobando el flujo: %s", error)
            inf.falta("Una comprobación falló", str(error))

    bloqueantes = [p for p in inf.puntos if p["estado"] == FALTA]
    avisos = [p for p in inf.puntos if p["estado"] == OJO]
    return {
        "puntos": inf.puntos,
        "bloqueantes": len(bloqueantes),
        "avisos": len(avisos),
        "listo": not bloqueantes,
        "buzon_comprobado": con_buzon,
        "cuando": datetime.now().isoformat(timespec="seconds"),
    }
