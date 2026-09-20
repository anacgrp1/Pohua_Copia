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
Como Pohua: el mismo azul de la casa, las mismas palabras y el mismo horario
de atención. Quien la abre no tiene que aprender otra aplicación; tiene que
poder mirar la ventana y saber si está leyendo, desde qué buzón y qué pasó en
el último ciclo.

Arrancarla:

    pip install -r requirements.txt -r requirements-desktop.txt
    python desktop_app/main.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# El proyecto entero cuelga de la carpeta de arriba: la app de escritorio usa
# EL MISMO ciclo que el servidor, no una copia.
RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from PySide6.QtCore import Qt, QThread, QTimer, Signal          # noqa: E402
from PySide6.QtGui import QFont                                  # noqa: E402
from PySide6.QtWidgets import (                                  # noqa: E402
    QApplication, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

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
"""


def ajuste(nombre, por_defecto=""):
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
        self._forzar = False       # "Leer ahora": se salta el horario

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
                except Exception as error:      # el ciclo nunca tumba la app
                    self.dice.emit("error", f"El ciclo falló: {error}")

            # La espera, en trozos de un segundo: así "Detener" y "Leer ahora"
            # contestan al momento y no dentro de cinco minutos.
            for _ in range(minutos * 60):
                if not self._corriendo or self._forzar:
                    break
                time.sleep(1)

        self.cambia_estado.emit("parado")
        self.dice.emit("info", "Lector detenido.")


# --------------------------------------------------------------------------- #
# La ventana
# --------------------------------------------------------------------------- #

class Ventana(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pohua · Lector local")
        self.resize(760, 620)
        self.setStyleSheet(ESTILO)

        self.lector = None
        self.totales = {"correos": 0, "rfqs": 0, "errores": 0}

        self.latido = QTimer(self)
        self.latido.timeout.connect(self.mandar_latido)

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
        raiz = QWidget()
        capa = QVBoxLayout(raiz)
        capa.setContentsMargins(18, 16, 18, 16)
        capa.setSpacing(14)

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

        self.setCentralWidget(raiz)

    # -------------------------------------------------------------- decir

    def escribir(self, nivel, texto):
        color = COLOR_NIVEL.get(nivel, APAGADO)
        hora = time.strftime("%H:%M:%S")
        self.registro.append(
            f'<span style="color:#64748b">{hora}</span> '
            f'<span style="color:{color}">{texto}</span>')
        barra = self.registro.verticalScrollBar()
        barra.setValue(barra.maximum())

    def pintar_estado(self, cual):
        colores = {"leyendo": (VERDE, "Leyendo el buzón"),
                   "espera": (NARANJA, "En espera (fuera de horario)"),
                   "parado": (ROSA, "Detenido")}
        color, texto = colores.get(cual, (ROSA, "Detenido"))
        self.punto.setStyleSheet(f"color: {color}; font-size: 16px;")
        self.estado.setText(texto)

    # ------------------------------------------------- comprobación inicial

    def _comprobar_de_entrada(self):
        """Antes de leer nada: ¿está todo puesto?

        La misma comprobación que enseña Pohua en Perfil → Sistema
        (`app/core/preflight.py`). Aquí se pasa sin tocar el buzón —eso lo
        hará el primer ciclo— y sólo se escriben los avisos y lo que falta:
        enumerar quince cosas que están bien no ayuda a nadie.
        """
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

        if informe["listo"]:
            self.escribir("ok", "Todo en su sitio. Puedes iniciar el lector.")
        else:
            self.escribir("aviso", f"Faltan {informe['bloqueantes']} cosa(s); "
                                   "el lector puede arrancar igual, pero fallará ahí.")

    # ----------------------------------------------------------- arrancar

    def arrancar(self):
        if self.lector and self.lector.isRunning():
            return
        self.lector = Lector()
        self.lector.dice.connect(self.escribir)
        self.lector.ciclo.connect(self.apuntar_ciclo)
        self.lector.cambia_estado.connect(self.pintar_estado)
        self.lector.start()

        self.btn_arrancar.setEnabled(False)
        self.btn_parar.setEnabled(True)
        self.btn_ahora.setEnabled(True)
        self.pintar_estado("leyendo")

        self.latido.start(60_000)
        self.mandar_latido()

    def leer_ahora(self):
        if self.lector and self.lector.isRunning():
            self.escribir("info", "Ciclo a mano: se salta el horario.")
            self.lector.leer_ahora()

    def parar(self):
        if self.lector and self.lector.isRunning():
            self.escribir("info", "Deteniendo…")
            self.lector.parar()
            self.lector.wait(3000)
        self.btn_arrancar.setEnabled(True)
        self.btn_parar.setEnabled(False)
        self.btn_ahora.setEnabled(False)
        self.latido.stop()
        self.pintar_estado("parado")

    def apuntar_ciclo(self, resultado):
        if not getattr(resultado, "en_horario", True):
            return
        self.totales["correos"] += getattr(resultado, "procesados", 0)
        self.totales["rfqs"] += getattr(resultado, "rfqs", 0)
        self.totales["errores"] += getattr(resultado, "errores", 0)
        self.val_correos.setText(str(self.totales["correos"]))
        self.val_rfqs.setText(str(self.totales["rfqs"]))
        self.val_errores.setText(str(self.totales["errores"]))

    # ------------------------------------------------------------- latido

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
            self.pie.setText("Sin latido: falta APP_URL o WORKER_SECRET_KEY. "
                             "El servidor podría leer el mismo buzón.")
            return

        try:
            respuesta = requests.post(f"{base}/api/worker/heartbeat",
                                      json={"secret_key": secreto}, timeout=8)
            if respuesta.status_code == 200:
                self.pie.setText(f"Latido enviado a {base} · "
                                 f"{time.strftime('%H:%M:%S')}")
            elif respuesta.status_code == 403:
                self.pie.setText("El servidor rechazó el latido: "
                                 "WORKER_SECRET_KEY no coincide.")
                self.escribir("error", "Latido rechazado: el secreto no coincide "
                                       "con el del servidor.")
            else:
                self.pie.setText(f"El servidor contestó {respuesta.status_code} "
                                 "al latido.")
        except Exception as error:
            self.pie.setText(f"No se pudo mandar el latido: {error}")

    def closeEvent(self, evento):
        self.parar()
        evento.accept()


def main():
    aplicacion = QApplication(sys.argv)
    aplicacion.setStyle("Fusion")
    ventana = Ventana()
    ventana.show()
    sys.exit(aplicacion.exec())


if __name__ == "__main__":
    main()
