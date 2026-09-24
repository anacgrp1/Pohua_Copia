"""
Motor de extracción MAPI via pywin32.
Conecta a Outlook, escanea carpetas y descarga adjuntos.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tempfile
import time
import zipfile
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from core.classifier import classify
from core.sanitizer import sanitize

# ─── Logging de diagnóstico (debug_log.txt) ─────────────────────────────────
#  Logger muy detallado: cada línea incluye fecha/hora con milisegundos, nivel,
#  hilo y la función:línea exacta de origen. Pensado para diagnosticar a fondo
#  cuelgues de COM/MAPI, decisiones de clasificación y errores con traceback.
logger = logging.getLogger("outlook_extractor")

DEBUG_LOG_FILENAME = "debug_log.txt"


def _setup_debug_logger(log_path: str = DEBUG_LOG_FILENAME) -> None:
    """Configura (de forma idempotente) el logger de diagnóstico.

    - Escribe a ``debug_log.txt`` en modo *append*, codificación UTF-8.
    - Formato descriptivo: ``fecha hora.ms | NIVEL | hilo | func:línea | mensaje``.
    - Nivel DEBUG: registra absolutamente todo el recorrido de la extracción.
    """
    logger.setLevel(logging.DEBUG)
    # Evitar handlers duplicados si run() se ejecuta varias veces en la sesión.
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d | %(levelname)-7s | %(threadName)-12s | "
            "%(funcName)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception:
        # Si no se puede abrir el archivo (permisos/ruta), seguimos sin romper la app.
        pass
    logger.propagate = False


# ─── Tipos de callbacks ──────────────────────────────────────────────────────
LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]  # (current, total)
RowCallback = Callable[[dict], None]           # fila del inventario

# ─── Extensiones objetivo ────────────────────────────────────────────────────
TARGET_EXTENSIONS = {".pdf", ".xml", ".zip"}

# ─── Carpetas de Outlook a escanear ─────────────────────────────────────────
FOLDER_MAP = {
    6: "Bandeja de Entrada",  
    5: "Elementos Enviados",   
    3: "Elementos Eliminados", 
}

def _get_unique_path(path: Path) -> Path:
    """Genera una ruta única agregando un sufijo incremental si el archivo ya existe."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return new_path
        counter += 1


class ExtractionEngine:
    """
    Motor principal de extracción.
    Debe ejecutarse en un hilo secundario; nunca en el hilo de la UI.
    """

    def __init__(
        self,
        dest_root: str,
        log_cb: Optional[LogCallback] = None,
        progress_cb: Optional[ProgressCallback] = None,
        row_cb: Optional[RowCallback] = None,
        anio_filtro: Optional[str] = None,
        stats_cb: Optional[Callable[[dict], None]] = None,
        workers: int = 4,
    ):
        self.dest_root = Path(dest_root)
        self.anio_filtro = anio_filtro
        self._log_cb = log_cb or print
        self._workers = workers
        self._progress = progress_cb or (lambda c, t: None)
        self._row = row_cb or (lambda r: None)
        self._stats_cb = stats_cb or (lambda s: None)
        self._stop_event = threading.Event()
        # Lock para acceso seguro entre hilos a _seen_hashes y stats
        self._lock = threading.Lock()
        # Registro de hashes MD5 — evita duplicados entre carpetas/cuentas
        self._seen_hashes: set[str] = set()
        # Pool de hilos para operaciones NO-COM (hash, mover, ZIP, inventario)
        self._executor = ThreadPoolExecutor(max_workers=workers)
        self.stats = {
            "processed": 0,
            "saved": 0,
            "skipped": 0,
            "errors": 0,
            "zips_extracted": 0,
            "total_files": 0,
        }
        self._stats_cb(self.stats)

    # ─── Log unificado: interfaz + archivo de diagnóstico ────────────────────
    def _log(self, msg: str):
        """Envía el mensaje a la interfaz y, además, lo registra en debug_log.txt.

        Así el archivo de diagnóstico contiene TODO lo que ve el usuario en la
        consola de la app, más el detalle técnico adicional (nivel DEBUG).
        """
        try:
            self._log_cb(msg)
        except Exception:
            pass
        # Las marcas de progreso van como DEBUG para no saturar el nivel INFO.
        if isinstance(msg, str) and msg.startswith("PROGRESS:"):
            logger.debug(msg)
        else:
            logger.info(msg)

    def _load_existing_hashes(self):
        """Escanea el directorio de destino y carga los hashes MD5 de archivos existentes."""
        base_extractor = self.dest_root / "Ixtli"
        if not base_extractor.exists():
            logger.info("No existe carpeta previa '%s'; se parte de cero (sin hashes precargados).", base_extractor)
            return

        self._log("Cargando hashes de archivos existentes para evitar duplicados...")
        logger.debug("Escaneando recursivamente '%s' en busca de %s ya descargados.", base_extractor, sorted(TARGET_EXTENSIONS))
        count = 0
        errores = 0
        try:
            for path in base_extractor.rglob("*"):
                if self.should_stop:
                    logger.warning("Carga de hashes interrumpida por el usuario tras %d archivos.", count)
                    break
                if path.is_file() and path.suffix.lower() in TARGET_EXTENSIONS:
                    try:
                        h = _md5(path)
                        with self._lock:
                            self._seen_hashes.add(h)
                        count += 1
                        logger.debug("Hash precargado [%s] de '%s'", h[:10], path)
                    except Exception as e_hash:
                        errores += 1
                        logger.warning("No se pudo hashear '%s': %s", path, e_hash)
        except Exception as e:
            self._log(f"Error escaneando destino: {e}")
            logger.error("Fallo escaneando el destino '%s'.", base_extractor, exc_info=True)
        self._log(f"Se cargaron {count} hashes de archivos existentes.")
        logger.info("Precarga de hashes finalizada: %d cargados, %d con error.", count, errores)

    # ─── Control ─────────────────────────────────────────────────────────────
    def stop(self):
        self._stop_event.set()

    @property
    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    # ─── Punto de entrada ─────────────────────────────────────────────────────
    def run(self):
        """Ejecutar el ciclo completo de extracción."""
        _setup_debug_logger()
        logger.info("=" * 78)
        logger.info("NUEVA SESIÓN DE EXTRACCIÓN — Ixtli")
        logger.info(
            "Destino='%s' | Filtro de año=%s | Hilos=%s | Inicio=%s",
            self.dest_root,
            self.anio_filtro or "Todos",
            self._workers,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        logger.info("Extensiones objetivo: %s", sorted(TARGET_EXTENSIONS))
        logger.info("=" * 78)
        self._load_existing_hashes()
        try:
            import win32com.client  # noqa: PLC0415
            logger.debug("pywin32 (win32com.client) importado correctamente.")
        except ImportError:
            self._log("pywin32 no encontrado. Instalando automáticamente...")
            logger.warning("pywin32 ausente; intentando instalación automática con pip.")
            try:
                import subprocess, sys, os  # noqa: PLC0415
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "--quiet", "pywin32"],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                # Ejecutar el post-install de pywin32 para registrar los COM
                scripts_dir = os.path.join(os.path.dirname(sys.executable), "Scripts")
                post_install = os.path.join(scripts_dir, "pywin32_postinstall.py")
                if os.path.exists(post_install):
                    logger.debug("Ejecutando post-install de pywin32: %s", post_install)
                    subprocess.call(
                        [sys.executable, post_install, "-install"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )
                import win32com.client  # noqa: PLC0415
                self._log("pywin32 instalado correctamente.")
                logger.info("pywin32 instalado y registrado correctamente.")
            except Exception as e_install:
                self._log(f"ERROR: No se pudo instalar pywin32 automáticamente: {e_install}")
                self._log("Solución manual: ejecuta 'pip install pywin32' como administrador.")
                logger.critical("Instalación automática de pywin32 fallida.", exc_info=True)
                return

        self._log("Conectando a Microsoft Outlook via MAPI...")
        try:
            outlook = win32com.client.Dispatch("Outlook.Application")
            namespace = outlook.GetNamespace("MAPI")
        except Exception as exc:
            self._log(f"No se pudo conectar a Outlook: {exc}")
            logger.critical("No se pudo establecer conexión COM/MAPI con Outlook.", exc_info=True)
            return

        self._log("Conexión MAPI establecida. Iniciando procesamiento al vuelo...")
        try:
            logger.info("Buzones/cuentas detectados en el perfil MAPI: %d", namespace.Folders.Count)
        except Exception:
            logger.debug("No se pudo leer namespace.Folders.Count tras conectar.")

        def collect_folder(folder, label: str):
            """Recorre recursivamente la carpeta y procesa al instante."""
            if self.should_stop:
                return

            # Forzar la lectura de TODAS las carpetas (incluyendo Borradores, Eliminados, No Deseado, etc.)
            try:
                # Comentamos los filtros originales para no omitir ninguna carpeta
                # item_type = getattr(folder, "DefaultItemType", 0)
                # name_low = folder.Name.lower()
                # skip_this = (item_type != 0) or any(x in name_low for x in ["borradores", "drafts", "junk", "no deseado", "eliminados", "deleted"])
                skip_this = False
            except Exception:
                skip_this = False

            if not skip_this:
                try:
                    logger.debug("➜ Entrando a carpeta de correo: '%s'", label)
                    items = folder.Items
                    logger.debug("  Colección 'Items' obtenida para '%s'.", label)

                    # Intentar ordenar por ReceivedTime descendente (más nuevo a más viejo)
                    is_sorted = False
                    try:
                        items.Sort("[ReceivedTime]", True)
                        is_sorted = True
                        logger.debug("  Orden por [ReceivedTime] DESC aplicado en '%s'.", label)
                    except Exception as e:
                        logger.warning("  No se pudo ordenar '%s' por fecha: %s (se escanea sin ordenar).", label, e)

                    self._log(f"PROGRESS:Carpeta {folder.Name[:15]}...")
                    msgs = items

                    # Evitamos Count() porque puede colgarse.
                    count = "?"

                    scanned_count = 0
                    logger.debug("  Solicitando primer elemento (GetFirst) de '%s'...", label)
                    try:
                        msg = msgs.GetFirst()
                    except Exception as e:
                        logger.error("  GetFirst falló en '%s': %s", label, e, exc_info=True)
                        msg = None

                    logger.debug("  Iniciando recorrido de mensajes en '%s'.", label)
                    
                    while msg is not None:
                        if self.should_stop:
                            return
                        
                        scanned_count += 1
                        if scanned_count % 15 == 0:
                            self._log(f"PROGRESS:{scanned_count} / ? en {folder.Name[:10]}")
                            logger.debug("  '%s': %d elementos recorridos hasta ahora.", label, scanned_count)

                        # Guardar referencia temporal para procesar
                        msg_current = msg

                        try:
                            msg = msgs.GetNext()
                        except Exception as e:
                            logger.warning("  GetNext falló en el elemento #%d de '%s': %s. Reintentando en 0.5s...", scanned_count, label, e)
                            # Si falla, esperamos e intentamos recuperarnos
                            time.sleep(0.5)
                            try:
                                msg = msgs.GetNext()
                            except Exception as e2:
                                logger.error("  GetNext (reintento) falló en #%d de '%s': %s. Se corta el recorrido de la carpeta.", scanned_count, label, e2, exc_info=True)
                                msg = None

                        try:
                            # Se eliminó la restricción `if getattr(msg_current, "Class", 0) == 43:`
                            # para procesar invitaciones de calendario, elementos guardados u otros tipos ocultos.
                            
                            # Optimization: Break early if sorted and we passed the target year
                            if is_sorted and self.anio_filtro and self.anio_filtro != "Todos":
                                folder_year_opt = None
                                if label:
                                    parts = [p.strip() for p in label.split(">")]
                                    for part in reversed(parts):
                                        match = re.search(r'\b(20\d{2})\b', part)
                                        if match:
                                            folder_year_opt = match.group(1)
                                            break
                                
                                # Solo interrumpir si la carpeta no nos fuerza a un año mayor o igual al filtro
                                if not folder_year_opt or int(folder_year_opt) < int(self.anio_filtro):
                                    received = self._get_date(msg_current)
                                    year_str = received[:4]
                                    if year_str.isdigit():
                                        if int(year_str) < int(self.anio_filtro):
                                            logger.debug("  Corte temprano en '%s': año %s < filtro %s (carpeta ordenada, no quedan más recientes).", label, year_str, self.anio_filtro)
                                            break

                            self._process_message(msg_current, label)
                        except Exception as ep:
                            logger.error("  Error procesando el elemento #%d de '%s': %s", scanned_count, label, ep, exc_info=True)
                        
                        # Liberar el objeto COM para evitar sobrecargar el servidor RPC
                        msg_current = None

                    logger.info("✓ Carpeta '%s' completada: %d elementos escaneados.", label, scanned_count)
                except Exception as exc:
                    self._log(f"Error leyendo '{label}': {exc}")
                    logger.error("Excepción recorriendo la carpeta '%s'.", label, exc_info=True)

            # Recorrer subcarpetas recursivamente
            try:
                sub_count = folder.Folders.Count
                logger.debug("Carpeta '%s' tiene %d subcarpeta(s).", label, sub_count)
                for i in range(1, sub_count + 1):
                    if self.should_stop:
                        return
                    try:
                        sub = folder.Folders.Item(i)
                        logger.debug("  Descendiendo a subcarpeta %d/%d: '%s > %s'", i, sub_count, label, sub.Name)
                        collect_folder(sub, f"{label} > {sub.Name}")
                    except Exception as exc:
                        self._log(f"Error en subcarpeta de '{label}': {exc}")
                        logger.error("  Error accediendo a la subcarpeta #%d de '%s'.", i, label, exc_info=True)
            except Exception as e_sub:
                logger.error("No se pudieron enumerar las subcarpetas de '%s'.", label, exc_info=True)

        # Escanear TODAS las cuentas/buzones configurados en Outlook
        try:
            total_cuentas = namespace.Folders.Count
            for i in range(1, total_cuentas + 1):
                if self.should_stop:
                    logger.warning("Escaneo de cuentas interrumpido por el usuario.")
                    break
                store_root = namespace.Folders.Item(i)
                self._log(f"Iniciando escaneo en cuenta: {store_root.Name}")
                logger.info("━━━ Cuenta %d/%d: '%s' ━━━", i, total_cuentas, store_root.Name)

                # Para evitar procesar la raíz del Store, vamos directo a sus subcarpetas
                try:
                    for j in range(1, store_root.Folders.Count + 1):
                        if self.should_stop:
                            break
                        sub = store_root.Folders.Item(j)
                        collect_folder(sub, f"{store_root.Name} > {sub.Name}")
                except Exception as e_root:
                    self._log(f"No se pudieron leer las carpetas de '{store_root.Name}': {e_root}")
                    logger.error("Error leyendo las carpetas de la cuenta '%s'.", store_root.Name, exc_info=True)
        except Exception as e_ns:
            self._log(f"Error general enumerando buzones: {e_ns}")
            logger.critical("Error general enumerando los buzones MAPI.", exc_info=True)

        # Esperar al pool de hilos
        self._log("Finalizando últimos guardados en disco...")
        logger.info("Esperando a que el pool de hilos termine los guardados pendientes...")
        self._executor.shutdown(wait=True)

        self._log(
            f"\nProceso completado. "
            f"Guardados: {self.stats['saved']} | "
            f"ZIPs extraídos: {self.stats['zips_extracted']} | "
            f"Omitidos: {self.stats['skipped']} | "
            f"Errores: {self.stats['errors']}"
        )
        logger.info("=" * 78)
        logger.info(
            "EXTRACCIÓN FINALIZADA | Procesados=%d Guardados=%d ZIPs=%d Omitidos=%d Errores=%d TotalArchivos=%d",
            self.stats["processed"], self.stats["saved"], self.stats["zips_extracted"],
            self.stats["skipped"], self.stats["errors"], self.stats["total_files"],
        )
        logger.info("Fin de sesión: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        logger.info("=" * 78)

    # ─── Procesamiento por mensaje ────────────────────────────────────────────
    # ─── Etiquetas MAPI (bypasan Object Model Guard de Outlook) ─────────────────
    _PR_BODY        = "http://schemas.microsoft.com/mapi/proptag/0x1000001E"
    _PR_SENDER_NAME = "http://schemas.microsoft.com/mapi/proptag/0x0C1A001E"
    _PR_SENDER_MAIL = "http://schemas.microsoft.com/mapi/proptag/0x0C1F001E"

    def _process_message(self, msg, folder_label: str):
        """Corre en el hilo principal (COM). Lee metadata y lanza adjuntos al pool."""
        try:
            # ── PRIMERO verificar adjuntos (evita leer body en mensajes sin archivos)
            # 1. Filtro Ultraligero (Por Fecha)
            # Leer la fecha es instantáneo porque solo requiere el encabezado del correo.
            received = self._get_date(msg)
            
            # Determinar año correcto buscando primero en el nombre de la carpeta de Outlook
            folder_year = None
            if folder_label:
                parts = [p.strip() for p in folder_label.split(">")]
                for part in reversed(parts):
                    match = re.search(r'\b(20\d{2})\b', part)
                    if match:
                        folder_year = match.group(1)
                        break
            
            try:
                msg_year = received[:4] if received[:4].isdigit() else "Sin_Fecha"
            except Exception:
                msg_year = "Sin_Fecha"
                
            year = folder_year if folder_year else msg_year

            # Filtro de año ("agarra lo nuevo también")
            if self.anio_filtro and self.anio_filtro != "Todos":
                try:
                    year_val = int(year) if year.isdigit() else 0
                    filter_val = int(self.anio_filtro)
                    if year_val < filter_val:
                        return
                except Exception:
                    if year != str(self.anio_filtro):
                        return

            # 2. Filtro Pesado (Por Adjuntos)
            # Leer 'Attachments' puede forzar a Outlook a descargar el correo entero desde Exchange.
            # Al ponerlo de segundo, evitamos descargar miles de correos de años que no nos interesan.
            attachments = getattr(msg, "Attachments", None)
            if not attachments or attachments.Count == 0:
                return

            subject = getattr(msg, "Subject", "") or ""

            with self._lock:
                self.stats["processed"] += 1
            self._stats_cb(self.stats)

            logger.info(
                "✉  Correo con adjuntos | carpeta='%s' | fecha=%s | año=%s | adjuntos=%d | asunto='%s'",
                folder_label, received, year, attachments.Count, subject[:80],
            )

            body = None
            sender = None

            for i in range(1, attachments.Count + 1):
                if self.should_stop:
                    return
                att = attachments.Item(i)

                raw_name = getattr(att, "FileName", "") or "sin_nombre"
                ext = Path(raw_name).suffix.lower()
                logger.debug("  Adjunto %d/%d: '%s' (ext=%s)", i, attachments.Count, raw_name, ext or "—")

                # Filtro temprano para evitar descargar cuerpos de correos con puras imágenes/firmas
                if ext not in TARGET_EXTENSIONS:
                    logger.debug("    ↳ Ignorado: extensión '%s' no está en %s.", ext or "—", sorted(TARGET_EXTENSIONS))
                    with self._lock:
                        self.stats["skipped"] += 1
                    self._stats_cb(self.stats)
                    continue

                if raw_name.upper().startswith("CTA."):
                    self._log(f"Omitiendo archivo CTA: {raw_name}")
                    logger.debug("    ↳ Ignorado: archivo CTA (estado de cuenta) '%s'.", raw_name)
                    with self._lock:
                        self.stats["skipped"] += 1
                    self._stats_cb(self.stats)
                    continue

                # Carga diferida (Lazy Load): Solo leemos el body y el sender si pasamos los filtros
                if body is None:
                    try:
                        body = msg.PropertyAccessor.GetProperty(self._PR_BODY) or ""
                    except Exception:
                        body = ""
                    sender = self._get_sender(msg)

                self._process_attachment(
                    att,
                    raw_name=raw_name,
                    ext=ext,
                    subject=subject,
                    body=body,
                    sender=sender,
                    received=received,
                    folder_label=folder_label,
                    year=year,
                )
        except Exception as exc:
            with self._lock:
                self.stats["errors"] += 1
            self._stats_cb(self.stats)
            self._log(f"Error procesando mensaje: {exc}")
            logger.error("Error procesando un mensaje de '%s'.", folder_label, exc_info=True)

    # ─── Procesamiento por adjunto (COM — hilo principal) ────────────────────
    def _process_attachment(
        self,
        att,
        raw_name: str,
        ext: str,
        subject: str,
        body: str,
        sender: str,
        received: str,
        folder_label: str,
        year: str,
    ):
        """Opera en el hilo COM. Filtra, guarda a temp y delega el resto al pool."""
        try:
            clean_name = sanitize(raw_name)

            # ── Calcular destino antes de descargar para optimizar ──
            result = classify(subject=subject, filename=clean_name, sender=sender, body=body)
            logger.info(
                "  Clasificado '%s' → %s (regla=%s, confianza=%s)",
                clean_name, result.folder_path, result.rule_matched, result.confidence,
            )
            if raw_name != clean_name:
                logger.debug("    Nombre saneado: '%s' → '%s'", raw_name, clean_name)

            folder_path = f"Ixtli/{year}/{result.folder_path}"
            dest_dir = self.dest_root / folder_path
            dest_path = dest_dir / clean_name

            # 1. Si ya existe en el lugar correcto con el mismo tamaño, lo omitimos (optimización)
            if dest_path.exists() and dest_path.stat().st_size == att.Size:
                self._log(f"Ya existe en destino correcto: {clean_name}. Omitiendo.")
                logger.debug("    ↳ Omitido: ya existe en el destino '%s' con el mismo tamaño (%d bytes).", dest_path, att.Size)
                with self._lock:
                    self.stats["skipped"] += 1
                self._stats_cb(self.stats)
                return

            # 2. Buscar si existe en la misma categoría pero en otro año y moverlo (Reorganización)
            base_extractor = self.dest_root / "Ixtli"
            reorganized = False
            if base_extractor.exists():
                for year_dir in base_extractor.iterdir():
                    if year_dir.is_dir() and year_dir.name != year:
                        possible_path = year_dir / result.folder_path / clean_name
                        if possible_path.exists():
                            dest_dir.mkdir(parents=True, exist_ok=True)
                            shutil.move(str(possible_path), str(dest_path))
                            self._log(f"Reorganizado al año correcto ({year}): {clean_name}")
                            logger.info("  ⇄ Reorganizado '%s' de '%s' al año %s ('%s').", clean_name, possible_path, year, dest_path)
                            with self._lock:
                                self.stats["skipped"] += 1
                            self._stats_cb(self.stats)
                            
                            # Si es un ZIP, movemos también la carpeta extraída asociada
                            if ext == ".zip":
                                old_zip_folder = possible_path.parent / possible_path.stem
                                new_zip_folder = dest_path.parent / dest_path.stem
                                if old_zip_folder.exists() and old_zip_folder.is_dir():
                                    shutil.move(str(old_zip_folder), str(new_zip_folder))
                            
                            reorganized = True
                            break

            if reorganized:
                return

            # ── Guardar a archivo temporal (operación COM, debe ir aquí) ──────
            tmp_fd, tmp_path_str = tempfile.mkstemp(suffix=ext)
            os.close(tmp_fd)
            tmp_path = Path(tmp_path_str)
            try:
                att.SaveAsFile(tmp_path_str)
                logger.debug("    Adjunto '%s' volcado a temporal '%s'.", clean_name, tmp_path_str)
            except Exception as e_write:
                tmp_path.unlink(missing_ok=True)
                raise RuntimeError(f"Error al escribir adjunto {clean_name}: {e_write}")

            # ── Delegar trabajo no-COM al pool de hilos ───────────────────────
            logger.debug("    Encolando finalización (hash + mover) de '%s' al pool de hilos.", clean_name)
            self._executor.submit(
                self._finalize_file,
                tmp_path, clean_name, ext,
                subject, body, sender, received, folder_label,
                result, year, dest_path
            )

        except Exception as exc:
            with self._lock:
                self.stats["errors"] += 1
            self._stats_cb(self.stats)
            self._log(f"Error en adjunto '{getattr(att, 'FileName', '?')}': {exc}")
            logger.error("Error procesando el adjunto '%s'.", getattr(att, "FileName", "?"), exc_info=True)

    # ─── Finalización en hilo del pool (sin COM) ──────────────────────────────
    def _finalize_file(
        self,
        tmp_path: Path,
        clean_name: str,
        ext: str,
        subject: str,
        body: str,
        sender: str,
        received: str,
        folder_label: str,
        result,
        year: str,
        dest_path: Path,
    ):
        """Corre en el pool de hilos. No usa COM. Clasifica, deduplica y mueve el archivo."""
        try:
            dest_dir = dest_path.parent
            dest_dir.mkdir(parents=True, exist_ok=True)

            # ── Hash MD5 para deduplicación ───────────────────────────────────
            file_hash = _md5(tmp_path)

            with self._lock:
                # 1. Verificar si el contenido exacto (hash) ya fue procesado
                if file_hash in self._seen_hashes:
                    tmp_path.unlink(missing_ok=True)
                    self._log(f"Duplicado (contenido idéntico): {clean_name}. Omitiendo.")
                    logger.info("  ⊘ Duplicado por contenido: '%s' (md5=%s). Descartado.", clean_name, file_hash[:10])
                    self.stats["skipped"] += 1
                    self._stats_cb(self.stats)
                    return

                # 2. Si el archivo no es duplicado por contenido, pero el nombre ya existe en destino,
                # generamos un nombre único (ej: archivo_1.pdf, archivo_2.pdf) para guardarlo.
                if dest_path.exists():
                    orig_dest_path = dest_path
                    dest_path = _get_unique_path(dest_path)
                    clean_name = dest_path.name
                    logger.info("  ⚠ Conflicto de nombre: '%s' ya existe. Renombrando a '%s'.", orig_dest_path.name, clean_name)

                self._seen_hashes.add(file_hash)

            # ── Mover de temp a destino final ─────────────────────────────────
            shutil.move(str(tmp_path), str(dest_path))

            folder_path_ui = f"Ixtli/{year}/{result.folder_path}"

            if "Eliminados" in folder_label:
                self._log(f"Rescatando de papelera: {clean_name} → {folder_path_ui}")
                logger.info("  ♻ Rescatado de Elementos Eliminados: '%s' → '%s' (md5=%s)", clean_name, dest_path, file_hash[:10])
            else:
                self._log(f"Guardando {clean_name} [{result.rule_matched}] → {folder_path_ui}")
                logger.info("  ✔ GUARDADO: '%s' → '%s' (regla=%s, md5=%s)", clean_name, dest_path, result.rule_matched, file_hash[:10])

            with self._lock:
                self.stats["saved"] += 1
                self.stats["total_files"] += 1
            self._stats_cb(self.stats)

            self._row({
                "Fecha": received,
                "Ubicacion_Original": folder_label,
                "Remitente": sender,
                "Asunto": subject,
                "Nombre_Archivo": clean_name,
                "Categoria": result.folder_path,
                "Regla": result.rule_matched,
                "Ruta_Destino": str(dest_path),
            })

            if ext == ".zip":
                self._extract_zip(dest_path, result, subject, sender, received, folder_label)

        except Exception as exc:
            with self._lock:
                self.stats["errors"] += 1
            self._stats_cb(self.stats)
            self._log(f"Error finalizando '{clean_name}': {exc}")
            logger.error("Error finalizando (hash/mover) '%s' hacia '%s'.", clean_name, dest_path, exc_info=True)
            tmp_path.unlink(missing_ok=True)

    # ─── Extracción de ZIP ────────────────────────────────────────────────────
    def _extract_zip(
        self,
        zip_path: Path,
        result,
        subject: str,
        sender: str,
        received: str,
        folder_label: str,
    ):
        zip_folder = zip_path.parent / zip_path.stem
        zip_folder.mkdir(parents=True, exist_ok=True)

        self._log(
            f"Procesando ZIP en {result.folder_path}/{zip_path.stem}..."
        )
        logger.info("  📦 Abriendo ZIP '%s' → carpeta '%s'", zip_path.name, zip_folder)

        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    if self.should_stop:
                        return
                    # Sanitizar nombre interno
                    raw_member = member.filename.replace("/", os.sep)
                    parts = [sanitize(p) for p in raw_member.split(os.sep) if p]
                    if not parts:
                        continue
                    
                    inner_dest = zip_folder / os.path.join(*parts)
                    inner_dest.parent.mkdir(parents=True, exist_ok=True)

                    # Extraer solo archivos (no directorios)
                    if not member.is_dir():
                        if inner_dest.exists():
                            self._log(f"Ya existe (ruta): {parts[-1]}. Omitiendo.")
                            logger.debug("    ZIP→ ya existe '%s'. Omitido.", inner_dest)
                        else:
                            try:
                                raw_bytes = zf.read(member)
                                file_hash = hashlib.md5(raw_bytes).hexdigest()
                                with self._lock:
                                    if file_hash in self._seen_hashes:
                                        self._log(f"Duplicado (ZIP): {parts[-1]}. Omitiendo.")
                                        logger.info("    ZIP→ ⊘ duplicado '%s' (md5=%s). Omitido.", parts[-1], file_hash[:10])
                                        continue
                                    self._seen_hashes.add(file_hash)
                                with open(inner_dest, "wb") as dst:
                                    dst.write(raw_bytes)
                                self._log(f"Extraído: {parts[-1]}")
                                logger.info("    ZIP→ ✔ extraído '%s' (%d bytes) → '%s'", parts[-1], len(raw_bytes), inner_dest)
                                with self._lock:
                                    self.stats["total_files"] += 1
                                self._stats_cb(self.stats)
                            except Exception as e_write:
                                self._log(f"Error escribiendo archivo {parts[-1]}: {e_write}")
                                logger.error("    ZIP→ error escribiendo '%s'.", parts[-1], exc_info=True)
                                continue

                        # Registrar cada archivo interno
                        self._row({
                            "Fecha": received,
                            "Ubicacion_Original": f"{folder_label} [ZIP]",
                            "Remitente": sender,
                            "Asunto": subject,
                            "Nombre_Archivo": parts[-1],
                            "Categoria": f"{result.folder_path}/{zip_path.stem}",
                            "Regla": f"{result.rule_matched}_ZIP",
                            "Ruta_Destino": str(inner_dest),
                        })

            with self._lock:
                self.stats["zips_extracted"] += 1
            self._stats_cb(self.stats)
            logger.info("  📦 ZIP '%s' procesado por completo.", zip_path.name)
        except zipfile.BadZipFile:
            self._log(f"ZIP corrupto: {zip_path.name}")
            logger.error("  📦 ZIP corrupto/ilegible: '%s'.", zip_path.name)
            with self._lock:
                self.stats["errors"] += 1
            self._stats_cb(self.stats)
        except Exception as exc:
            self._log(f"Error extrayendo ZIP: {exc}")
            logger.error("  📦 Error extrayendo ZIP '%s'.", zip_path.name, exc_info=True)
            with self._lock:
                self.stats["errors"] += 1
            self._stats_cb(self.stats)

    def _get_sender(self, msg) -> str:
        """Lee el remitente vía PropertyAccessor (etiquetas MAPI) para evitar el Object Model Guard."""
        try:
            pa = msg.PropertyAccessor
            name  = pa.GetProperty(self._PR_SENDER_NAME) or ""
            email = pa.GetProperty(self._PR_SENDER_MAIL) or ""
            if email:
                return f"{name} <{email}>".strip(" <>")
            return name or "Desconocido"
        except Exception:
            return "Desconocido"

    @staticmethod
    def _get_date(msg) -> str:
        dt = None
        # Primero intentamos SentOn (para Elementos Enviados)
        try:
            dt = msg.SentOn
        except Exception:
            pass
            
        # Si no, intentamos ReceivedTime
        if not dt:
            try:
                dt = msg.ReceivedTime
            except Exception:
                pass
                
        # Si no, intentamos CreationTime como último recurso
        if not dt:
            try:
                dt = msg.CreationTime
            except Exception:
                pass

        if dt:
            try:
                # Intentar leer atributos de año, mes y día
                return f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
            except Exception:
                return str(dt)[:19]
                
        # Si no se puede obtener fecha, retornamos 'Sin_Fecha'
        # NUNCA usar datetime.now() para evitar agrupar en el año actual
        return "Sin_Fecha"

# ─── Utilidades de módulo ─────────────────────────────────────────────────────
def _md5(path: Path, chunk_size: int = 65536) -> str:
    """Calcula el hash MD5 de un archivo en disco de forma eficiente."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()
