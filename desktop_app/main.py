"""Pohua · Lector local — la aplicación de escritorio.

Qué es
------
El respaldo para leer el correo cuando el servidor no puede: corre en la
computadora de la planta, entra al buzón por el **Outlook que ya está abierto**
(sin credenciales, sin Azure) y hace el mismo ciclo que haría la nube —
clasificar, extraer, leer el plano, dar de alta el RFQ y avisar—. La base de
datos y los avisos siguen siendo los de siempre: lo único que cambia es quién
abre el buzón.

Mientras esta aplicación está leyendo, le manda un latido al servidor
(``/api/worker/heartbeat``) y el worker de allá **se aparta**: si leyeran los
dos, se pisarían el mismo correo.

Cómo se ve
----------
Es Pohua entera, con el icono de Pohua y dos pestañas: **Pohua**, la misma
aplicación web dentro de la ventana (Monitor, Mail, Quoting, Overview… lo que
vea el usuario que entre), y **Lector local**, el panel del lector de correo:
estado, Iniciar / Leer ahora / Detener, cifras y registro. El lector sigue
leyendo aunque se esté en la otra pestaña.

Además, esta ventana le pone a la página un puente de Qt (`QWebChannel`,
`window.pohuaLector`) con el que el Monitor de la web enseña ese mismo lector
como un apartado más, y lo que el lector escribe viaja con el latido al
servidor, así que el Monitor enseña el registro del servidor y el del lector
juntos y sus cifras suman los correos de los dos.

Si en esta computadora no está el motor web de Qt (PySide6-Addons), queda la
pestaña del lector con un botón para abrir Pohua en el navegador.

Arrancarla:

    pip install -r requirements.txt -r requirements-desktop.txt
    python desktop_app/main.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

# El proyecto entero cuelga de la carpeta de arriba: la app de escritorio usa
# EL MISMO ciclo que el servidor, no una copia.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Y se trabaja DESDE la carpeta del proyecto, pase lo que pase.
#
# La configuración busca el `.env` en la carpeta desde la que se lanzó el
# programa. Al abrir la aplicación con un doble clic, o escribiendo la ruta
# entera desde otro sitio, esa carpeta es cualquier otra: no encuentra el
# `.env`, arranca con los valores por defecto —INBOX, IMAP, base en
# localhost— y la comprobación de arranque dice que falta TODO aunque no
# falte nada. Esto se pone ANTES de importar la configuración, que es cuando
# se lee el fichero.
os.chdir(RAIZ)

from PySide6.QtCore import (                                             # noqa: E402
    QFile, QIODevice, QLockFile, QObject, QThread, QTimer, QUrl, Signal, Slot,
)
from PySide6.QtGui import QDesktopServices, QFont, QIcon                  # noqa: E402
from PySide6.QtWidgets import (                                           # noqa: E402
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QMessageBox,
    QPushButton, QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

# El motor web de Qt viene en PySide6-Addons. Si falta, la ventana lo dice y
# ofrece abrir Pohua en el navegador: el lector no depende de él.
if TYPE_CHECKING:
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import (
        QWebEnginePage, QWebEngineProfile, QWebEngineScript,
    )
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAY_WEB = True
else:
    try:
        from PySide6.QtWebChannel import QWebChannel                            # noqa: E402
        from PySide6.QtWebEngineCore import (                                   # noqa: E402
            QWebEnginePage, QWebEngineProfile, QWebEngineScript,
        )
        from PySide6.QtWebEngineWidgets import QWebEngineView                   # noqa: E402
        HAY_WEB = True
    except ImportError:                                                          # pragma: no cover
        QWebChannel = QWebEnginePage = QWebEngineProfile = QWebEngineScript = None
        QWebEngineView = None
        HAY_WEB = False

# El icono de Pohua: el mismo de la web (frontend/assets), para la ventana y
# la barra de tareas. Sin esto Windows enseñaba el icono de Python.
ICONO = RAIZ / "frontend" / "assets" / "icon-512.png"

import app.core.config as config                                 # noqa: E402
from app.core.logging import configure_logging                   # noqa: E402

configure_logging()

# --------------------------------------------------------------------------- #
# Los colores de la casa (los mismos del brand book que usa la PWA)
# --------------------------------------------------------------------------- #

FONDO = "#0f172a"
PANEL = "#1e293b"
LINEA = "rgba(255,255,255,0.08)"
TINTA = "#f8fafc"
APAGADO = "#94a3b8"
AZUL = "#148ec2"
VERDE = "#a4ae2d"
NARANJA = "#d67c2f"
ROSA = "#b31671"
NAVY = "#1e3a8a"

COLOR_NIVEL = {"info": APAGADO, "ok": VERDE, "aviso": NARANJA, "error": ROSA}

ESTILO = f"""
QWidget {{ background: {FONDO}; color: {TINTA};
           font-family: 'Segoe UI', Arial, sans-serif; font-size: 13px; }}
QFrame#tarjeta {{ background: {PANEL}; border: 1px solid {LINEA};
                  border-radius: 10px; }}
QLabel#titulo {{ font-size: 19px; font-weight: 700; }}
QLabel#sub    {{ color: {APAGADO}; font-size: 12px; }}
QLabel#cifra  {{ font-size: 21px; font-weight: 700; }}
QLabel#pie    {{ color: {APAGADO}; font-size: 11px; }}
QPushButton {{ background: {PANEL}; border: 1px solid {LINEA}; border-radius: 8px;
               padding: 9px 16px; font-weight: 600; }}
QPushButton:hover:!disabled {{ border-color: {AZUL}; }}
QPushButton#principal {{ background: {AZUL}; border-color: {AZUL}; color: white; }}
QPushButton#principal:hover {{ background: #1aa3dd; }}
QPushButton#parar {{ background: {ROSA}; border-color: {ROSA}; color: white; }}
/* Un botón apagado tiene que PARECER apagado: con el color de marca puesto,
   "Detener" se veía igual de encendido con el lector parado que corriendo. */
QPushButton:disabled, QPushButton#principal:disabled, QPushButton#parar:disabled {{
    background: transparent; border-color: {LINEA}; color: #64748b; }}
/* Las etiquetas heredaban el fondo del tema de Fusion y dibujaban una barra
   clara debajo de cada cifra. */
QFrame#tarjeta QLabel {{ background: transparent; }}
QTextEdit {{ background: #0b1220; border: 1px solid {LINEA}; border-radius: 10px;
             font-family: Consolas, 'Courier New', monospace; font-size: 12px; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {APAGADO}; padding: 10px 18px;
                border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {TINTA}; border-bottom-color: {ROSA}; }}
QTabBar::tab:hover:!selected {{ color: {TINTA}; }}
QLabel#estadoLector {{ color: {APAGADO}; font-size: 12px; padding: 0 6px; }}
"""


def direccion_web() -> str:
    """Dónde vive Pohua: APP_URL (Render) y, si no está, el servidor local."""
    return (ajuste("APP_URL", "") or ajuste("WEB_SERVER_URL", "")
            or "http://localhost:8000").rstrip("/")


def ajuste(nombre: str, por_defecto: Any = "") -> Any:
    """Un ajuste de `config.settings`.

    Va por `settings` y no por el módulo: `getattr(config, 'WORKER_SECRET_KEY')`
    no existe y devolvía siempre el valor por defecto, así que el latido salía
    con un secreto inventado y el servidor lo rechazaba sin que se notara.
    """
    return getattr(config.settings, nombre, por_defecto) or por_defecto


# --------------------------------------------------------------------------- #
# El hilo que lee el correo
# --------------------------------------------------------------------------- #

class Lector(QThread):
    """Corre el ciclo del sistema cada cierto tiempo, en su propio hilo.

    No reimplementa nada: llama a `app.main.ciclo_deteccion`, el mismo que
    corre en el servidor. Lo único suyo es el ritmo y saber pararse.
    """

    dice = Signal(str, str)        # (nivel, texto)
    ciclo = Signal(object)         # ResultadoCiclo
    cambia_estado = Signal(str)    # 'leyendo' | 'espera' | 'parado'

    def __init__(self):
        super().__init__()
        self._corriendo = True
        self._forzar = False       # "Leer ahora": ejecuta ciclo de inmediato
        self._salida_espera_hasta = 0.0

    def leer_ahora(self):
        self._forzar = True

    def parar(self):
        self._corriendo = False

    def run(self):
        import app.rfq.horario as horario
        from app.main import ciclo_deteccion

        minutos = int(ajuste("INTERVALO_MINUTOS", 5) or 5)
        self.dice.emit("info", f"Lector en marcha. Un ciclo cada {minutos} min.")
        esperando_apertura = False

        while self._corriendo:
            forzado = self._forzar
            self._forzar = False

            if not forzado and not horario.abierto():
                if not esperando_apertura:
                    esperando_apertura = True
                    self.cambia_estado.emit("espera")
                    self.dice.emit("aviso", horario.motivo_cerrado())
            else:
                esperando_apertura = False
                self.cambia_estado.emit("leyendo")
                try:
                    resultado = ciclo_deteccion(forzar=forzado)
                    self.ciclo.emit(resultado)
                    if not resultado.en_horario:
                        self.dice.emit("aviso", "Ciclo omitido: fuera de horario.")
                    else:
                        self.dice.emit(
                            "ok" if not resultado.errores else "error",
                            f"Ciclo: {resultado.encontrados} sin leer · "
                            f"{resultado.procesados} procesados · "
                            f"{resultado.rfqs} RFQ · {resultado.errores} con error.")
                        for detalle in resultado.detalles[:6]:
                            self.dice.emit("info", f"   {detalle}")

                    # La bandeja de salida. Esta computadora es la única que
                    # tiene Outlook abierto sobre el buzón de ISC, así que las
                    # ofertas que el servidor redactó y no pudo mandar salen
                    # de aquí. Va DESPUÉS de leer y fuera del try de arriba
                    # para que un correo que no sale no se confunda con un
                    # ciclo de lectura fallido.
                    self.despachar_salida()
                except Exception as error:      # el ciclo nunca tumba la app
                    self.dice.emit("error", f"El ciclo falló: {error}")

            # La espera, en trozos de un segundo: así "Detener" y "Leer ahora"
            # contestan al momento y no dentro de cinco minutos.
            #
            # Y mientras se espera, la bandeja de salida se mira cada pocos
            # segundos. La oferta que aprueba el PM se encola en el servidor y
            # sale por ESTE Outlook; esperando al ciclo de lectura tardaba
            # hasta cinco minutos en llegar al cliente. Preguntar si hay algo
            # es una consulta de nada; sólo se abre Outlook si lo hay.
            cada = max(5, int(ajuste("SALIDA_SEGUNDOS", 15) or 15))
            for segundo in range(1, minutos * 60 + 1):
                if not self._corriendo or self._forzar:
                    break
                time.sleep(1)
                if segundo % cada == 0:
                    self.salida_si_hay()

        self.cambia_estado.emit("parado")
        self.dice.emit("info", "Lector detenido.")

    def salida_si_hay(self):
        """Manda la bandeja de salida sólo si tiene algo. Nunca lanza."""
        try:
            import app.email.bandeja_salida as bandeja
            from app.email.outlook_provider import envio_en_pausa
            # Tras un «Deny» no se insiste: esperan al ciclo, sin ventanas.
            # Y tras un fallo, tampoco cada 15 s: cinco intentos seguidos en
            # un minuto dejarían el correo en 'fallo' por un Outlook que sólo
            # se estaba reiniciando.
            if envio_en_pausa() or time.monotonic() < self._salida_espera_hasta:
                return
            if bandeja.hay_pendientes() > 0:
                self.despachar_salida(rapido=True)
        except Exception as error:      # un fallo aquí no para la espera
            self.dice.emit("error", f"No se pudo mirar la bandeja de salida: {error}")

    def despachar_salida(self, rapido=False):
        """Manda las ofertas que el servidor dejó esperando.

        El servidor arma la oferta cuando el plant manager pulsa el botón,
        pero no tiene cuenta emisora: el buzón se abre por el Outlook de ESTA
        computadora. Las dos partes se encuentran en la tabla `correos_salida`
        de la misma base en Neon, igual que ya se encuentran para no leer el
        buzón dos veces.

        Nunca lanza: un correo que no sale no puede impedir que entren los
        RFQ, que es para lo que está esta ventana.
        """
        try:
            import app.email.bandeja_salida as bandeja
            resumen = bandeja.drenar()
        except Exception as error:
            self.dice.emit("error", f"La bandeja de salida falló: {error}")
            return

        if resumen["enviados"]:
            self.dice.emit("ok", f"Bandeja de salida: {resumen['enviados']} "
                                 f"correo/s enviado/s por Outlook.")
        if resumen["fallidos"]:
            self.dice.emit("error", f"Bandeja de salida: {resumen['fallidos']} "
                                    f"no salieron; se reintentan el próximo ciclo.")
        if rapido and resumen["fallidos"]:
            self._salida_espera_hasta = time.monotonic() + 300
        if rapido:
            # Cada 15 s: sólo se dice lo que salió o falló. Lo demás lo cuenta
            # el ciclo completo, una vez cada cinco minutos y no cada 15 s.
            return
        if resumen["pendientes"]:
            self.dice.emit("info", f"   Quedan {resumen['pendientes']} esperando.")
        if resumen.get("denegados"):
            self.dice.emit("aviso",
                           "Outlook no dejó mandar (se pulsó «Deny»). Las ofertas "
                           "siguen en la bandeja de salida; no se vuelve a "
                           "preguntar en 15 min.")
        if resumen.get("omitidos"):
            # Pasa si esta computadora tampoco está configurada para mandar:
            # decirlo aquí ahorra buscar el correo perdido en el servidor.
            self.dice.emit("aviso",
                           f"Hay {resumen['omitidos']} oferta/s esperando, pero "
                           f"esta computadora no está configurada para mandar. "
                           f"Falta MAIL_MODE=outlook y OUTLOOK_BUZON en el .env.")


# --------------------------------------------------------------------------- #
# El puente con la web: el lector, dentro del Monitor de Pohua
# --------------------------------------------------------------------------- #

class PuenteLector(QObject):
    """Lo que la página de Pohua ve como ``window.pohuaLector``.

    Es la misma API que tenían los botones de la ventana: arrancar, parar,
    leer ahora; y dos señales para que la página se entere sin preguntar:
    ``cambio`` (estado y cifras, en JSON) y ``linea`` (una línea nueva del
    registro, en JSON). ``estado()`` e ``historial()`` dan lo que ya había
    cuando la página se abre.
    """
    cambio = Signal(str)
    linea = Signal(str)

    def __init__(self, ventana):
        super().__init__(ventana)
        self._ventana = ventana

    @Slot()
    def arrancar(self):
        self._ventana.arrancar()

    @Slot()
    def parar(self):
        self._ventana.parar()

    @Slot()
    def leer_ahora(self):
        self._ventana.leer_ahora()

    @Slot(result=str)
    def estado(self):
        import json
        return json.dumps(self._ventana.estado_para_la_web(), ensure_ascii=False)

    @Slot(result=str)
    def historial(self):
        import json
        return json.dumps(list(self._ventana.historial), ensure_ascii=False)


def _qwebchannel_js() -> str:
    """El cliente JavaScript de QWebChannel, sacado de los recursos de Qt.

    Se inyecta en la página en vez de pedírselo por ``qrc:///``: una página
    servida por https no puede cargar recursos ``qrc`` y el puente se quedaba
    sin cliente.
    """
    fichero = QFile(":/qtwebchannel/qwebchannel.js")
    if not fichero.open(QIODevice.OpenModeFlag.ReadOnly):
        return ""
    try:
        return bytes(fichero.readAll().data()).decode("utf-8")
    finally:
        fichero.close()


# Se ejecuta en la página al crearse el documento: monta el canal y deja el
# lector en `window.pohuaLector`. La página (js/pages/monitor.js) espera el
# evento por si llega después de pintarse.
_ARRANQUE_JS = """
(function () {
    if (!window.qt || !window.qt.webChannelTransport || typeof QWebChannel === 'undefined') return;
    new QWebChannel(qt.webChannelTransport, function (canal) {
        window.pohuaLector = canal.objects.lector;
        window.POHUA_ESCRITORIO = true;
        document.dispatchEvent(new CustomEvent('pohua:lector-listo'));
    });
})();
"""


# --------------------------------------------------------------------------- #
# La ventana
# --------------------------------------------------------------------------- #

class Ventana(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pohua")
        self.resize(1280, 800)
        self.setStyleSheet(ESTILO)
        if ICONO.is_file():
            self.setWindowIcon(QIcon(str(ICONO)))

        self.lector = None
        self.totales = {"correos": 0, "rfqs": 0, "errores": 0}
        self.estado_actual = "parado"
        # Lo escrito en el registro, para dárselo a la página del Monitor
        # cuando se abra (y para el panel de respaldo si no hay motor web).
        from collections import deque
        self.historial = deque(maxlen=500)
        self.puente: PuenteLector | None = None
        # Los controles del panel de respaldo; None cuando la ventana es la web.
        self.web: QWebEngineView | None = None
        self.donde: QLabel | None = None
        self.registro: QTextEdit | None = None
        self.punto: QLabel | None = None
        self.estado: QLabel | None = None
        self.pie: QLabel | None = None
        self.btn_arrancar: QPushButton | None = None
        self.btn_ahora: QPushButton | None = None
        self.btn_parar: QPushButton | None = None
        self.val_correos: QLabel | None = None
        self.val_rfqs: QLabel | None = None
        self.val_errores: QLabel | None = None

        self.latido = QTimer(self)
        self.latido.timeout.connect(self.mandar_latido)
        # Lo que el lector escribe en su registro, pendiente de mandar al
        # Monitor de la web. Se manda con el latido de cada minuto y, si hay
        # algo nuevo, un par de segundos después de escribirse.
        self._pendientes = []
        self._enviar_pronto = QTimer(self)
        self._enviar_pronto.setSingleShot(True)
        self._enviar_pronto.timeout.connect(self.mandar_latido)

        self._montar()
        self._comprobar_de_entrada()

    # ------------------------------------------------------------ montaje

    def _tarjeta(self):
        caja = QFrame()
        caja.setObjectName("tarjeta")
        return caja

    def _cifra(self, etiqueta, color):
        caja = self._tarjeta()
        fila = QVBoxLayout(caja)
        fila.setContentsMargins(14, 12, 14, 12)
        valor = QLabel("0")
        valor.setObjectName("cifra")
        valor.setStyleSheet(f"color: {color};")
        titulo = QLabel(etiqueta)
        titulo.setObjectName("sub")
        fila.addWidget(valor)
        fila.addWidget(titulo)
        return caja, valor

    def _montar(self):
        """Dos pestañas: Pohua (la web, dentro) y el Lector local.

        El lector tiene su pestaña propia, y además la web lo enseña dentro
        de su Monitor cuando la versión desplegada lo trae. Las dos vistas
        son el mismo lector: lo que se escribe en una se ve en la otra.
        """
        self.pestanas = QTabWidget()
        self.pestanas.setDocumentMode(True)
        if HAY_WEB:
            self.pestanas.addTab(self._pagina_web(), "Pohua")
        self.pestanas.addTab(self._pagina_lector(), "Lector local")
        # El estado del lector, siempre a la vista, esté en la pestaña que esté.
        self.estado_pestanas = QLabel("Lector: detenido")
        self.estado_pestanas.setObjectName("estadoLector")
        self.pestanas.setCornerWidget(self.estado_pestanas)
        self.setCentralWidget(self.pestanas)

    def _pagina_web(self):
        """Pohua entera, dentro de la ventana.

        Es la misma web que se abre en el navegador —Monitor, Mail, Quoting,
        Overview, lo que vea quien entre—, no una copia en Qt: así no hay dos
        pantallas que mantener. El perfil se guarda en disco para que la
        sesión no se pierda al cerrar. Y se le pone el puente con el lector,
        que el Monitor de la web enseña como un apartado más.
        """
        if (not HAY_WEB
                or QWebEngineProfile is None
                or QWebEngineScript is None
                or QWebEngineView is None
                or QWebEnginePage is None
                or QWebChannel is None):
            return self._pagina_lector()

        perfil = QWebEngineProfile("pohua", self)
        perfil.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        carpeta = Path(tempfile.gettempdir()) / "pohua-escritorio-web"
        carpeta.mkdir(parents=True, exist_ok=True)
        perfil.setPersistentStoragePath(str(carpeta))
        perfil.setCachePath(str(carpeta / "cache"))

        cliente = _qwebchannel_js()
        if cliente:
            guion = QWebEngineScript()
            guion.setName("pohua-lector")
            guion.setSourceCode(cliente + "\n" + _ARRANQUE_JS)
            guion.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
            guion.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
            guion.setRunsOnSubFrames(False)
            perfil.scripts().insert(guion)

        self.web = QWebEngineView()
        pagina = QWebEnginePage(perfil, self.web)
        self.puente = PuenteLector(self)
        canal = QWebChannel(pagina)
        canal.registerObject("lector", self.puente)
        pagina.setWebChannel(canal)
        self.web.setPage(pagina)
        # Al terminar de cargar, se comprueba que la página vio el puente: si
        # no lo vio, el Monitor no puede enseñar el lector, y el motivo (la web
        # desplegada aún sin el apartado, o el cliente no inyectado) se deja en
        # el registro en lugar de que se descubra por un hueco en la pantalla.
        self.web.loadFinished.connect(self._comprobar_puente)
        self.web.load(QUrl(direccion_web()))
        return self.web

    def _comprobar_puente(self, bien: bool) -> None:
        import logging
        registro = logging.getLogger("cotizador.escritorio")
        if not bien or self.web is None:
            registro.warning("La web de Pohua no cargó (%s).", direccion_web())
            return

        def contestar(resultado: Any) -> None:
            texto = str(resultado or "")
            if texto.startswith("ok"):
                registro.info("Puente con la web listo: el Monitor puede enseñar el lector "
                              "(%s).", texto)
            else:
                registro.warning("La página no ve el puente del lector (%s). Si la web "
                                 "desplegada aún no trae el apartado «Local reader» en "
                                 "el Monitor, hay que desplegar frontend/.", texto)

        self.web.page().runJavaScript(
            "(function(){"
            " var tiene = typeof window.pohuaLector !== 'undefined';"
            " var monitor = typeof MonitorPage !== 'undefined';"
            " return (tiene ? 'ok' : 'sin puente') + ' · MonitorPage=' + monitor;"
            "})()", contestar)

    def estado_para_la_web(self) -> dict:
        buzon = ajuste("OUTLOOK_BUZON", "") or ajuste("IMAP_USER", "")
        modo = str(ajuste("MAIL_MODE", "imap")).lower()
        como = {"outlook": "Outlook", "graph": "Microsoft Graph"}.get(modo, "IMAP")
        return {
            "estado": self.estado_actual,
            "corriendo": bool(self.lector and self.lector.isRunning()),
            "totales": dict(self.totales),
            "buzon": buzon,
            "carpeta": ajuste("MAIL_FOLDER", "INBOX"),
            "como": como,
        }

    def _avisar_a_la_web(self):
        if self.puente is not None:
            import json
            self.puente.cambio.emit(json.dumps(self.estado_para_la_web(), ensure_ascii=False))

    def _pagina_lector(self):
        """El panel de respaldo: sólo cuando no hay motor web en la máquina."""
        raiz = QWidget()
        capa = QVBoxLayout(raiz)
        capa.setContentsMargins(18, 16, 18, 16)
        capa.setSpacing(14)

        if not HAY_WEB:
            aviso = QLabel("En esta computadora falta el motor web de Qt (PySide6-Addons): "
                           "Pohua se abre en el navegador y aquí queda el lector.")
            aviso.setObjectName("sub")
            aviso.setWordWrap(True)
            abrir = QPushButton("Abrir Pohua en el navegador")
            abrir.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(direccion_web())))
            capa.addWidget(aviso)
            capa.addWidget(abrir)

        # --- cabecera: qué es esto y de dónde lee ---
        cabecera = QVBoxLayout()
        titulo = QLabel("Pohua · Lector local")
        titulo.setObjectName("titulo")
        buzon = ajuste("OUTLOOK_BUZON", "") or ajuste("IMAP_USER", "(buzón por defecto)")
        carpeta = ajuste("MAIL_FOLDER", "INBOX")
        modo = str(ajuste("MAIL_MODE", "imap")).lower()
        como = {"outlook": "por el Outlook de escritorio",
                "graph": "por Microsoft Graph"}.get(modo, "por IMAP")
        self.donde = QLabel(f"{buzon} · carpeta {carpeta} · {como}")
        self.donde.setObjectName("sub")
        cabecera.addWidget(titulo)
        cabecera.addWidget(self.donde)
        capa.addLayout(cabecera)

        # --- estado y botones ---
        barra = QFrame()
        barra.setObjectName("tarjeta")
        fila = QHBoxLayout(barra)
        fila.setContentsMargins(14, 12, 14, 12)
        fila.setSpacing(10)

        self.punto = QLabel("●")
        self.punto.setStyleSheet(f"color: {ROSA}; font-size: 16px;")
        self.estado = QLabel("Detenido")
        self.estado.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        fila.addWidget(self.punto)
        fila.addWidget(self.estado)
        fila.addStretch(1)

        self.btn_arrancar = QPushButton("Iniciar lector")
        self.btn_arrancar.setObjectName("principal")
        self.btn_arrancar.clicked.connect(self.arrancar)
        self.btn_ahora = QPushButton("Leer ahora")
        self.btn_ahora.clicked.connect(self.leer_ahora)
        self.btn_ahora.setEnabled(False)
        self.btn_parar = QPushButton("Detener")
        self.btn_parar.setObjectName("parar")
        self.btn_parar.clicked.connect(self.parar)
        self.btn_parar.setEnabled(False)
        for b in (self.btn_ahora, self.btn_arrancar, self.btn_parar):
            fila.addWidget(b)
        capa.addWidget(barra)

        # --- las cifras del día ---
        cifras = QHBoxLayout()
        cifras.setSpacing(12)
        caja_c, self.val_correos = self._cifra("Correos leídos", AZUL)
        caja_r, self.val_rfqs = self._cifra("RFQ dados de alta", VERDE)
        caja_e, self.val_errores = self._cifra("Con error", NARANJA)
        for caja in (caja_c, caja_r, caja_e):
            cifras.addWidget(caja)
        capa.addLayout(cifras)

        # --- el registro ---
        self.registro = QTextEdit()
        self.registro.setReadOnly(True)
        capa.addWidget(self.registro, 1)

        self.pie = QLabel("El latido avisa al servidor de que aquí se está leyendo.")
        self.pie.setObjectName("pie")
        capa.addWidget(self.pie)
        return raiz

    # -------------------------------------------------------------- decir

    def escribir(self, nivel, texto):
        """Una línea en el registro, con su hora y su color.

        El texto se escapa antes de entrar. El registro se pinta con texto
        enriquecido para poder darle color, y eso significa que cualquier cosa
        entre < y > se toma por una etiqueta y desaparece de la pantalla: un
        "Duplicado omitido: <abc@cliente.com>" se veía como "Duplicado
        omitido:" a secas, justo cuando lo que hacía falta era el dato.
        """
        import html as _html

        color = COLOR_NIVEL.get(nivel, APAGADO)
        hora = time.strftime("%H:%M:%S")
        if self.registro is not None:
            self.registro.append(
                f'<span style="color:#64748b">{hora}</span> '
                f'<span style="color:{color}">{_html.escape(str(texto))}</span>')
            barra = self.registro.verticalScrollBar()
            barra.setValue(barra.maximum())
        linea = {"hora": hora, "nivel": nivel, "texto": str(texto)}
        self.historial.append(linea)
        if self.puente is not None:
            import json
            self.puente.linea.emit(json.dumps(linea, ensure_ascii=False))
        self._apuntar_para_el_monitor(nivel, str(texto))

    # Del color de esta ventana al nivel del registro del servidor.
    _NIVEL_MONITOR = {"info": "INFO", "ok": "INFO", "aviso": "WARNING", "error": "ERROR"}

    def _apuntar_para_el_monitor(self, nivel, texto):
        """La misma línea, en la forma del registro del servidor, para el Monitor.

        La marca va en UTC porque el registro del servidor está en UTC: si
        fuera con la hora local, el Monitor ordenaría las líneas del lector
        seis horas antes que las del servidor.
        """
        marca = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime()) + ",000"
        self._pendientes.append({
            "id": f"{time.time_ns()}",
            "marca": marca,
            "nivel": self._NIVEL_MONITOR.get(nivel, "INFO"),
            "origen": "lector.escritorio",
            "mensaje": texto.strip(),
        })
        del self._pendientes[:-200]
        if not self._enviar_pronto.isActive():
            self._enviar_pronto.start(2000)

    def pintar_estado(self, cual):
        colores = {"leyendo": (VERDE, "Leyendo el buzón"),
                   "espera": (NARANJA, "En espera (fuera de horario)"),
                   "parado": (ROSA, "Detenido")}
        color, texto = colores.get(cual, (ROSA, "Detenido"))
        if self.punto is not None and self.estado is not None:
            self.punto.setStyleSheet(f"color: {color}; font-size: 16px;")
            self.estado.setText(texto)
        self.estado_actual = cual if cual in colores else "parado"
        if getattr(self, "estado_pestanas", None) is not None:
            self.estado_pestanas.setText(f"Lector: {texto.lower()}")
            self.estado_pestanas.setStyleSheet(f"color: {color}; padding: 0 6px;")
        self._avisar_a_la_web()

    # ------------------------------------------------- comprobación inicial

    def _comprobar_de_entrada(self):
        """Antes de leer nada: ¿está todo puesto?

        La misma comprobación que enseña Pohua en Perfil → Sistema
        (`app/core/preflight.py`). Aquí se pasa sin tocar el buzón —eso lo
        hará el primer ciclo— y sólo se escriben los avisos y lo que falta:
        enumerar quince cosas que están bien no ayuda a nadie.
        """
        # Antes que nada, el esquema. Esta aplicación escribe en la MISMA base
        # que el servidor —planos, resortes, la bandeja de salida— con el
        # código de este repositorio. Si el código va por delante del esquema,
        # falla al guardar y el fallo aparece lejos: un plano que no se guarda,
        # una oferta que no se encola. Hasta ahora sólo las aplicaba el
        # servidor web al arrancar, así que quien leía desde aquí dependía de
        # que alguien hubiera desplegado.
        self.escribir("info", "Revisando el esquema de la base…")
        try:
            import app.persistence.migraciones as migraciones
            resumen = migraciones.aplicar_pendientes()
            if resumen.get("error"):
                self.escribir("error", f"Migraciones: {resumen['error']}")
            elif resumen.get("aplicadas"):
                self.escribir("ok", "Esquema actualizado: "
                                    + ", ".join(resumen["aplicadas"]))
            elif not resumen.get("habilitado"):
                self.escribir("aviso", "AUTO_MIGRAR está apagado: el esquema no "
                                       "se toca desde aquí.")
            else:
                self.escribir("info", "El esquema ya estaba al día.")
        except Exception as error:
            self.escribir("error", f"No se pudo revisar el esquema: {error}")

        self.escribir("info", "Comprobando la configuración…")
        try:
            import app.core.preflight as preflight
            informe = preflight.revisar(con_buzon=False, desde_escritorio=True)
        except Exception as error:
            self.escribir("error", f"No se pudo comprobar: {error}")
            return

        for punto in informe["puntos"]:
            if punto["estado"] == "falta":
                self.escribir("error", f"Falta: {punto['titulo']}")
                if punto["detalle"]:
                    self.escribir("info", f"   {punto['detalle']}")
            elif punto["estado"] == "ojo":
                self.escribir("aviso", punto["titulo"])

        self._comprobar_confianza_de_outlook()

        if informe["listo"]:
            self.escribir("ok", "Todo en su sitio. Puedes iniciar el lector.")
        else:
            self.escribir("aviso", f"Faltan {informe['bloqueantes']} cosa(s); "
                                   "el lector puede arrancar igual, pero fallará ahí.")

    def _comprobar_confianza_de_outlook(self):
        """Una vez, al abrir: ¿Outlook va a pedir permiso para cada correo?

        Si no confía en los programas que lo automatizan, saca «A program is
        trying to send an email message on your behalf» en CADA envío, y esa
        ventana no tiene «permitir durante un rato». Se dice aquí, con lo que
        hay que hacer, en lugar de que se descubra a base de ventanas.
        """
        modo = str(ajuste("MAIL_MODE", "")).lower()
        if modo != "outlook":
            return
        from app.email.outlook_provider import outlook_confia
        confia = outlook_confia()
        if confia is None:
            return
        if confia:
            self.escribir("ok", "Outlook confía en Pohua: los correos salen sin "
                                "preguntar.")
            return
        self.escribir("aviso", "Outlook va a pedir permiso para CADA correo que "
                               "mande Pohua (el cuadro «A program is trying to "
                               "send an email…»).")
        self.escribir("info", "   Se quita en Outlook: Archivo → Opciones → Centro "
                              "de confianza → Configuración → Acceso mediante "
                              "programación. «Estado del antivirus» tiene que "
                              "decir Válido; si no, hay que activar o actualizar "
                              "el antivirus (o que TI lo configure).")
        self.escribir("info", "   Mientras tanto: si pulsas «Deny», Pohua deja de "
                              "preguntar 15 min y las ofertas esperan en la "
                              "bandeja de salida.")

    # ----------------------------------------------------------- arrancar

    def arrancar(self):
        if self.lector and self.lector.isRunning():
            return
        self.lector = Lector()
        self.lector.dice.connect(self.escribir)
        self.lector.ciclo.connect(self.apuntar_ciclo)
        self.lector.cambia_estado.connect(self.pintar_estado)
        self.lector.start()

        self._botones(corriendo=True)
        self.pintar_estado("leyendo")

        self.latido.start(60_000)
        self.mandar_latido()

    def _botones(self, corriendo: bool):
        """Los botones del panel de respaldo; la web se entera por `cambio`."""
        if (self.btn_arrancar is None
                or self.btn_parar is None
                or self.btn_ahora is None):
            return
        self.btn_arrancar.setEnabled(not corriendo)
        self.btn_parar.setEnabled(corriendo)
        self.btn_ahora.setEnabled(corriendo)

    def leer_ahora(self):
        if self.lector and self.lector.isRunning():
            self.escribir("info", "Ciclo a mano: se salta el horario.")
            self.lector.leer_ahora()

    def parar(self):
        if self.lector and self.lector.isRunning():
            self.escribir("info", "Deteniendo…")
            self.lector.parar()
            self.lector.wait(3000)
        self._botones(corriendo=False)
        self.latido.stop()
        self.pintar_estado("parado")

    def apuntar_ciclo(self, resultado):
        if not getattr(resultado, "en_horario", True):
            return
        self.totales["correos"] += getattr(resultado, "procesados", 0)
        self.totales["rfqs"] += getattr(resultado, "rfqs", 0)
        self.totales["errores"] += getattr(resultado, "errores", 0)
        if (self.val_correos is not None
                and self.val_rfqs is not None
                and self.val_errores is not None):
            self.val_correos.setText(str(self.totales["correos"]))
            self.val_rfqs.setText(str(self.totales["rfqs"]))
            self.val_errores.setText(str(self.totales["errores"]))
        self._avisar_a_la_web()

    # ------------------------------------------------------------- latido

    def _pie(self, texto):
        """El renglón del latido, en el panel de respaldo y en el registro."""
        if self.pie is not None:
            self.pie.setText(texto)
        else:
            self._ultimo_pie = texto

    def mandar_latido(self):
        """Le dice al servidor que aquí se está leyendo, para que él no lea.

        La dirección sale de APP_URL (la de Render) y, si no está, de
        WEB_SERVER_URL. El secreto es WORKER_SECRET_KEY, el mismo de los dos
        lados: sin él, el servidor apaga el endpoint a propósito.
        """
        import requests

        base = (ajuste("APP_URL", "") or ajuste("WEB_SERVER_URL", "")).rstrip("/")
        secreto = ajuste("WORKER_SECRET_KEY", "")
        if not base or not secreto:
            self._pie("Sin latido: falta APP_URL o WORKER_SECRET_KEY. "
                             "El servidor podría leer el mismo buzón.")
            return

        # Con el latido viaja lo que el Monitor de la web tiene que enseñar:
        # las líneas nuevas del registro, los contadores y en qué está el
        # lector. Si el envío falla, las líneas se quedan para el siguiente.
        lineas = list(self._pendientes)
        carga = {
            "secret_key": secreto,
            "lineas": lineas,
            "totales": {"procesados": self.totales["correos"],
                        "rfqs": self.totales["rfqs"],
                        "errores": self.totales["errores"]},
            "estado": self.estado_actual,
        }
        try:
            respuesta = requests.post(f"{base}/api/worker/heartbeat",
                                      json=carga, timeout=8)
            if respuesta.status_code == 200:
                if lineas:
                    del self._pendientes[:len(lineas)]
                self._pie(f"Latido enviado a {base} · "
                                 f"{time.strftime('%H:%M:%S')}")
            elif respuesta.status_code == 403:
                self._pie("El servidor rechazó el latido: "
                                 "WORKER_SECRET_KEY no coincide.")
                self.escribir("error", "Latido rechazado: el secreto no coincide "
                                       "con el del servidor.")
            else:
                self._pie(f"El servidor contestó {respuesta.status_code} "
                                 "al latido.")
        except Exception as error:
            self._pie(f"No se pudo mandar el latido: {error}")

    def closeEvent(self, evento):
        self.parar()
        if self.web is not None:
            pagina = self.web.page()
            if pagina is not None:
                pagina.deleteLater()
        evento.accept()


def main():
    # En Windows, sin esto la barra de tareas agrupa la ventana bajo Python y
    # enseña el icono de Python aunque la ventana tenga el suyo.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CGR.Pohua")
        except Exception:
            pass

    aplicacion = QApplication(sys.argv)
    aplicacion.setStyle("Fusion")
    aplicacion.setApplicationName("Pohua")
    if ICONO.is_file():
        aplicacion.setWindowIcon(QIcon(str(ICONO)))

    # Una sola copia abierta. Dos leían el mismo buzón y mandaban la misma
    # bandeja de salida a la vez: dos ventanas de permiso de Outlook, una
    # encima de la otra, por cada correo.
    candado = QLockFile(os.path.join(tempfile.gettempdir(), "pohua-escritorio.lock"))
    candado.setStaleLockTime(0)
    if not candado.tryLock(100):
        QMessageBox.information(None, "Pohua",
                                "Pohua ya está abierto en esta computadora.")
        sys.exit(0)

    ventana = Ventana()
    ventana.show()
    sys.exit(aplicacion.exec())


if __name__ == "__main__":
    main()
