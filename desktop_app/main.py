import sys
import time
import requests
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                               QHBoxLayout, QPushButton, QTextEdit, QLabel)
from PySide6.QtCore import QThread, Signal, QTimer

# Add parent directory to path so we can import 'app'
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.core import config
from app.core.logging import configure_logging
from app.main import ciclo_deteccion

configure_logging()

class WorkerThread(QThread):
    log_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.is_running = True
        
    def run(self):
        self.log_signal.emit("Iniciando trabajador de lectura de correos...")
        interval = getattr(config, "INTERVALO_MINUTOS", 5)
        
        while self.is_running:
            try:
                self.log_signal.emit("Ejecutando ciclo de detección...")
                ciclo_deteccion()
                self.log_signal.emit("Ciclo completado. Esperando...")
            except Exception as e:
                self.log_signal.emit(f"Error en el ciclo: {str(e)}")
                
            # Sleep in chunks to allow responsive stopping
            for _ in range(interval * 60):
                if not self.is_running:
                    break
                time.sleep(1)
                
    def stop(self):
        self.is_running = False
        self.log_signal.emit("Deteniendo trabajador...")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CGR Cotizador - Lector Local de Correos")
        self.resize(600, 400)
        
        self.worker_thread = None
        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.timeout.connect(self.send_heartbeat)
        
        self.init_ui()
        
    def init_ui(self):
        widget = QWidget()
        layout = QVBoxLayout()
        
        # Status Label
        self.status_label = QLabel("Estado: Detenido")
        self.status_label.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.status_label)
        
        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_start = QPushButton("Iniciar Lector")
        self.btn_start.clicked.connect(self.start_worker)
        
        self.btn_stop = QPushButton("Detener Lector")
        self.btn_stop.clicked.connect(self.stop_worker)
        self.btn_stop.setEnabled(False)
        
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        layout.addLayout(btn_layout)
        
        # Log Output
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)
        
        widget.setLayout(layout)
        self.setCentralWidget(widget)
        
    def log(self, message):
        self.log_output.append(f"[{time.strftime('%H:%M:%S')}] {message}")
        
    def start_worker(self):
        if self.worker_thread is None or not self.worker_thread.isRunning():
            self.worker_thread = WorkerThread()
            self.worker_thread.log_signal.connect(self.log)
            self.worker_thread.start()
            
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.status_label.setText("Estado: Ejecutándose")
            self.status_label.setStyleSheet("color: green; font-weight: bold;")
            
            # Start heartbeat
            self.heartbeat_timer.start(60000) # Every 1 minute
            self.send_heartbeat() # Send first heartbeat immediately
            
    def stop_worker(self):
        if self.worker_thread and self.worker_thread.isRunning():
            self.worker_thread.stop()
            self.worker_thread.wait()
            
            self.btn_start.setEnabled(True)
            self.btn_stop.setEnabled(False)
            self.status_label.setText("Estado: Detenido")
            self.status_label.setStyleSheet("color: red; font-weight: bold;")
            
            self.heartbeat_timer.stop()
            
    def send_heartbeat(self):
        url = getattr(config, "WEB_SERVER_URL", "http://localhost:8000").rstrip("/") + "/api/worker/heartbeat"
        secret = getattr(config, "WORKER_SECRET_KEY", "default_secret_for_dev")
        
        try:
            response = requests.post(url, json={"secret_key": secret}, timeout=5)
            if response.status_code == 200:
                self.log("Heartbeat enviado exitosamente al servidor web.")
            else:
                self.log(f"Error enviando heartbeat: HTTP {response.status_code}")
        except Exception as e:
            self.log(f"Fallo al conectar con el servidor web (heartbeat): {str(e)}")

    def closeEvent(self, event):
        self.stop_worker()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
