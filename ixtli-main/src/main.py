"""
Ixtli
"""
from __future__ import annotations

import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageTk

from core.extractor import ExtractionEngine

import sys
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"

# ─── Configuración global ──────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# ─── Paleta de colores original ───────────────────────────────────────────────
C = {
    "sidebar_bg":   "#0F172A",
    "main_bg":      "#E2E8F0",
    "card_bg":      "#FFFFFF",
    "accent":       "#D81B60",
    "accent_hover": "#C2185B",
    "accent_light": "#FDEEFF",
    "text_dark":    "#1E293B",
    "text_light":   "#64748B",
    "border":       "#E2E8F0",
    "dark_panel":   "#0F1C2E",
    "dark_hdr":     "#1E293B",
    "terminal_bg":  "#0D1117",
    "terminal_hdr": "#111827",
    "success":      "#10B981",
    "warning":      "#F59E0B",
    "danger":       "#EF4444",
    "teal":         "#14B8A6",
    "zip_color":    "#8B5CF6",
}


# ══════════════════════════════════════════════════════════════════════════════
#  VENTANA PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
class App(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.withdraw()
        
        # ─── FIX NATIVO DE WINDOWS ───
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("nexus.logistics.outlook.final")
        except: pass

        self.title("Ixtli")
        self.geometry("1400x900")
        self.minsize(1000, 680)
        self.configure(fg_color=C["main_bg"])
        
        self._setup_native_icon()

        self._bg_original = None
        self._bg_photo = None
        self._last_bg_size = (0, 0)
        try:
            fondo_path = ASSETS_DIR / "fondo.png"
            if fondo_path.exists():
                self._bg_original = Image.open(str(fondo_path))
        except Exception: pass

        self._engine = None
        self._worker = None
        self._log_queue = queue.Queue()
        self._preview_queue = queue.Queue()
        self._stats_queue = queue.Queue()
        self._dest_var = tk.StringVar()
        self._progress_var = tk.DoubleVar(value=1.0)
        self._anio_var = ctk.StringVar(value="Todos")
        self._running = False
        self._is_manual_stop = False
        self._count_pdf = 0
        self._count_zip = 0

        self._build_ui()
        self._poll_queues()
        
        self.after(0, lambda: self.state('zoomed'))
        self.deiconify()

    def _setup_native_icon(self):
        def apply():
            try:
                logo_path = ASSETS_DIR / "logo.png"
                ico_path = ASSETS_DIR / "app_icon.ico"
                
                if logo_path.exists():
                    img = Image.open(str(logo_path))
                    img.save(str(ico_path), format='ICO', sizes=[(16,16), (32,32), (48,48)])
                    self.iconbitmap(str(ico_path))
                    photo = ImageTk.PhotoImage(img.resize((32,32)))
                    self._app_icon_photo = photo
                    self._app_ico_path = str(ico_path)
                    self.wm_iconphoto(True, photo)
            except: pass
        self.after(500, apply)

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=230, fg_color=C["sidebar_bg"], corner_radius=0)
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        self._tech_canvas = tk.Canvas(sb, bg="#08142A", highlightthickness=0)
        self._tech_canvas.place(relx=0, rely=0, relwidth=1, relheight=1)
        self._tech_canvas.bind("<Configure>", self._draw_tech_bg)
        header = ctk.CTkFrame(sb, fg_color=C["accent"], corner_radius=0, height=120)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)
        header.grid_columnconfigure(0, weight=1); header.grid_rowconfigure(0, weight=1)
        ctk.CTkLabel(header, text="PANEL DE CONTROL", text_color="#FFFFFF", font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0)
        line = ctk.CTkFrame(sb, fg_color="#B0154D", height=5)
        line.pack(side="top", fill="x")

    def _draw_tech_bg(self, event=None):
        c = self._tech_canvas; w = c.winfo_width(); h = c.winfo_height()
        if w <= 1 or h <= 1: return
        if (w, h) == self._last_bg_size: return
        c.delete("all"); self._last_bg_size = (w, h)
        try:
            if self._bg_original:
                img_w, img_h = self._bg_original.size
                scale = max(w/img_w, h/img_h)
                nw, nh = int(img_w*scale), int(img_h*scale)
                resized = self._bg_original.resize((nw, nh), Image.Resampling.BILINEAR)
                self._bg_photo = ImageTk.PhotoImage(resized)
                c.create_image((w-nw)//2, (h-nh)//2, image=self._bg_photo, anchor="nw")
                return
        except: pass
        for i in range(h):
            ratio = i / h
            r, g, b = int(15 - ratio*10), int(23 - ratio*15), int(46 - ratio*20)
            c.create_line(0, i, w, i, fill=f"#{r:02x}{g:02x}{b:02x}")

    def _build_main(self):
        main = ctk.CTkFrame(self, fg_color=C["main_bg"], corner_radius=0)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(0, weight=1); main.grid_columnconfigure(0, weight=1)
        content = ctk.CTkFrame(main, fg_color=C["main_bg"], corner_radius=0)
        content.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        content.grid_columnconfigure(0, weight=1); content.grid_rowconfigure(1, weight=1)
        self._build_stat_cards(content)
        
        self.tabs = ctk.CTkTabview(content, fg_color="transparent", segmented_button_fg_color="#E2E8F0",
                                   segmented_button_selected_color=C["accent"],
                                   segmented_button_selected_hover_color=C["accent_hover"],
                                   segmented_button_unselected_color="#475569",
                                   text_color="#FFFFFF",
                                   corner_radius=30)
        self.tabs.grid(row=1, column=0, sticky="nsew", pady=(15, 0))
        self.tabs._segmented_button.configure(font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"), height=60, corner_radius=30)
        
        t1 = self.tabs.add("  ⚙️ CONFIGURACIÓN Y CONTROL  ")
        t2 = self.tabs.add("  📄 DOCUMENTOS RECOLECTADOS  ")
        t1.grid_columnconfigure(0, weight=1); t1.grid_rowconfigure(0, weight=1)
        t2.grid_columnconfigure(0, weight=1); t2.grid_rowconfigure(0, weight=1)
        self._build_orchestration(t1); self._build_preview_panel(t2)

    def _build_stat_cards(self, parent):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", pady=(0, 10)); row.grid_columnconfigure((0,1,2,3,4), weight=1)
        self._stat_labels = {}
        cards = [
            ("total_files",    "📊", "GLOBAL",  "#4F46E5", "#1E40AF", "TOTAL DE\nARCHIVOS", "#EFF6FF"),
            ("saved",          "💾", "VIVO",    C["success"], C["success"], "REGISTROS\nGUARDADOS", "#ECFDF5"),
            ("zips_extracted", "📁", "ZIP",     C["zip_color"], C["zip_color"], "PAQUETES\nZIP", "#F5F3FF"),
            ("skipped",        "⚠️", "IGNORADO", C["warning"], C["warning"], "YA DESCARGADOS\nO NO REQUERIDOS", "#FFFBEB"),
            ("errors",         "🔴", "FALLO",    C["danger"], C["danger"], "ARCHIVO DAÑADO\nO SIN PERMISOS", "#FEF2F2"),
        ]
        for i, (key, icon, badge, b_color, n_color, txt, bg) in enumerate(cards):
            card = ctk.CTkFrame(row, fg_color=bg, corner_radius=25, border_width=1, border_color=b_color)
            card.grid(row=0, column=i, sticky="nsew", padx=6)
            top = ctk.CTkFrame(card, fg_color="transparent"); top.pack(fill="x", padx=14, pady=(14, 0))
            ctk.CTkLabel(top, text=icon, font=ctk.CTkFont(size=22)).pack(side="left")
            ctk.CTkLabel(top, text=badge, font=ctk.CTkFont(size=8, weight="bold"), text_color=b_color).pack(side="right")
            lbl = ctk.CTkLabel(card, text="0", font=ctk.CTkFont(size=36, weight="bold"), text_color=n_color, anchor="w")
            lbl.pack(fill="x", padx=14); self._stat_labels[key] = lbl
            ctk.CTkLabel(card, text=txt, font=ctk.CTkFont(size=8, weight="bold"), text_color=C["text_light"], anchor="w", justify="left").pack(fill="x", padx=14, pady=(2, 14))

    def _build_orchestration(self, parent):
        card = ctk.CTkFrame(parent, fg_color=C["card_bg"], corner_radius=30, border_width=1, border_color=C["border"])
        card.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        inner = ctk.CTkFrame(card, fg_color="transparent"); inner.pack(expand=True, pady=8)
        icon_bg = ctk.CTkFrame(inner, fg_color=C["accent_light"], width=54, height=54, corner_radius=27)
        icon_bg.pack(pady=(4, 6)); icon_bg.pack_propagate(False)
        ctk.CTkLabel(icon_bg, text="📥", font=ctk.CTkFont(size=26), text_color=C["accent"]).place(relx=0.5, rely=0.5, anchor="center")
        ctk.CTkLabel(inner, text="Gestión de Documentos", font=ctk.CTkFont(size=20, weight="bold"), text_color=C["text_dark"]).pack()
        ctk.CTkLabel(inner, text="Ajusta la ruta de destino e inicia el proceso", font=ctk.CTkFont(size=11), text_color=C["text_light"]).pack(pady=(2, 0))
        row = ctk.CTkFrame(inner, fg_color="transparent"); row.pack(pady=12)
        self._dest_entry = ctk.CTkEntry(row, textvariable=self._dest_var, width=300, height=45, corner_radius=15, border_color=C["border"], fg_color="#F8FAFC")
        self._dest_entry.pack(side="left")
        ctk.CTkButton(row, text="📂", width=46, height=45, fg_color="#F1F5F9", hover_color="#E2E8F0", corner_radius=15, text_color=C["text_dark"], font=ctk.CTkFont(size=16), command=self._browse_dest).pack(side="left", padx=6)
        self._anio_btn = ctk.CTkOptionMenu(
            row, values=["Todos", "2030", "2029", "2028", "2027", "2026", "2025", "2024", "2023", "2022", "2021"],
            variable=self._anio_var, width=120, height=45, corner_radius=15,
            fg_color=C["accent"], button_color=C["accent"], button_hover_color=C["accent_hover"],
            dropdown_fg_color=C["sidebar_bg"], dropdown_hover_color=C["accent"], dropdown_text_color="#FFFFFF",
            font=ctk.CTkFont(size=13, weight="bold"), dropdown_font=ctk.CTkFont(size=13, weight="bold")
        )
        self._anio_btn.pack(side="left", padx=(4, 0))
        self._btn_start = ctk.CTkButton(inner, text="INICIAR PROCESAMIENTO", fg_color=C["accent"], hover_color=C["accent_hover"], height=52, width=320, corner_radius=26, font=ctk.CTkFont(size=14, weight="bold"), command=self._start_extraction)
        self._btn_start.pack(pady=(5, 8))
        self._btn_stop = ctk.CTkButton(inner, text="⏹  Detener Operación", fg_color="#F8FAFC", border_width=1, border_color="#CBD5E1", text_color="#64748B", hover_color="#F1F5F9", width=280, height=50, corner_radius=25, font=ctk.CTkFont(size=13, weight="bold"), command=self._stop_extraction)
        self._btn_stop.pack(pady=(8, 0))

    def _build_preview_panel(self, parent):
        panel = ctk.CTkFrame(parent, fg_color=C["dark_panel"], corner_radius=30)
        panel.pack(fill="both", expand=True, padx=5, pady=5)
        hdr = ctk.CTkFrame(panel, fg_color=C["dark_hdr"], height=65, corner_radius=25)
        hdr.pack(side="top", fill="x", padx=10, pady=(10, 5))
        
        self._preview_title_var = tk.StringVar(value="📄 0 Documentos recolectados")
        ctk.CTkLabel(hdr, textvariable=self._preview_title_var, text_color="#FFFFFF", font=ctk.CTkFont(size=13, weight="bold")).pack(side="left", padx=25)
        
        self._preview_filter_var = ctk.StringVar(value="Directos (.PDF)")
        self._preview_filter = ctk.CTkSegmentedButton(
            hdr, 
            values=["Directos (.PDF)", "Desde Pedimentos (.ZIP)"], 
            variable=self._preview_filter_var,
            command=self._on_preview_filter_change,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#0F172A", 
            selected_color=C["accent"],
            selected_hover_color=C["accent_hover"], 
            unselected_color="#1E293B",
            unselected_hover_color="#334155",
            text_color="#FFFFFF",
            corner_radius=16,
            height=34
        )
        self._preview_filter.pack(side="left", padx=20)
        
        ctk.CTkButton(hdr, text="Limpiar Lista", width=110, height=32, fg_color="#334155", hover_color="#475569", corner_radius=16, command=self._clear_preview).pack(side="right", padx=20)
        
        split = ctk.CTkFrame(panel, fg_color="transparent")
        split.pack(fill="both", expand=True, padx=10, pady=(5, 15))
        split.grid_columnconfigure(0, weight=3); split.grid_columnconfigure(1, weight=7); split.grid_rowconfigure(0, weight=1)
        
        self._preview_list_pdf = ctk.CTkScrollableFrame(split, fg_color="#0F172A", corner_radius=25)
        self._preview_list_pdf.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        
        self._preview_list_zip = ctk.CTkScrollableFrame(split, fg_color="#0F172A", corner_radius=25)
        # El de ZIP está oculto inicialmente
        
        self._detail_panel = ctk.CTkFrame(split, fg_color="#1E293B", corner_radius=25)
        self._detail_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        self._show_empty_detail()

    def _on_preview_filter_change(self, value):
        if value == "Directos (.PDF)":
            self._preview_list_zip.grid_remove()
            self._preview_list_pdf.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        else:
            self._preview_list_pdf.grid_remove()
            self._preview_list_zip.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self._update_preview_title()

    def _update_preview_title(self):
        val = self._count_pdf if self._preview_filter_var.get() == "Directos (.PDF)" else self._count_zip
        self._preview_title_var.set(f"📄 {val} Documentos recolectados")

    def _show_empty_detail(self):
        for c in self._detail_panel.winfo_children(): c.destroy()
        ctk.CTkLabel(self._detail_panel, text="Selecciona un archivo", text_color="#64748B", font=ctk.CTkFont(size=13)).place(relx=0.5, rely=0.5, anchor="center")

    def _browse_dest(self):
        f = filedialog.askdirectory(); self._dest_var.set(f) if f else None

    def _clear_preview(self):
        self._count_pdf = 0
        self._count_zip = 0
        for c in self._preview_list_pdf.winfo_children(): c.destroy()
        for c in self._preview_list_zip.winfo_children(): c.destroy()
        self._update_preview_title()
        self._show_empty_detail()

    def _copy_to_clipboard(self, t):
        self.clipboard_clear(); self.clipboard_append(t); self.update()
        if hasattr(self, "_status_label"): self._status_label.configure(text="❯ 📋 Dirección copiada!")

    def _set_preview_file(self, m):
        p = Path(m["Ruta_Destino"])
        is_zip_extracted = "[ZIP]" in m.get("Ubicacion_Original", "")
        ext = p.suffix.lower()
        
        # Filtrado para las pestañas
        if ext == ".pdf" and not is_zip_extracted:
            parent_list = self._preview_list_pdf
            self._count_pdf += 1
        elif ext == ".pdf" and is_zip_extracted:
            # Archivo PDF extraído de un pedimento/zip
            parent_list = self._preview_list_zip
            self._count_zip += 1
        else:
            # Ignoramos los .zip en bruto (porque ya mostramos su PDF) y los .xml visualmente
            return
            
        card = ctk.CTkFrame(parent_list, fg_color="#1E293B", corner_radius=15)
        card.pack(fill="x", pady=5, padx=10)

        # Badge tipo de archivo → abre el archivo
        badge_text = p.suffix.upper().replace(".", "") or "DOC"
        badge = ctk.CTkLabel(card, text=badge_text,
                             fg_color=C["accent"], text_color="#FFFFFF",
                             width=45, height=26, corner_radius=8, cursor="hand2")
        badge.pack(side="left", padx=12, pady=12)
        badge.bind("<Button-1>", lambda e, m_ref=m: self._open_file(m_ref))

        # Nombre del archivo → muestra detalles en panel derecho
        # Si viene de ZIP, le damos más espacio visual
        display_name = p.name[:35] if is_zip_extracted else p.name[:28]
        name_lbl = ctk.CTkLabel(card, text=display_name, text_color="#E2E8F0",
                                font=ctk.CTkFont(size=11, weight="bold"), cursor="hand2")
        name_lbl.pack(side="left")
        name_lbl.bind("<Button-1>", lambda e, m_ref=m: self._show_file_summary(m_ref))

        self._update_preview_title()

    def _open_file(self, m):
        """Abre el archivo con el programa predeterminado del sistema."""
        try:
            import subprocess
            subprocess.Popen(f'start "" "{m["Ruta_Destino"]}"', shell=True)
        except Exception: pass

    def _show_file_summary(self, m):
        for c in self._detail_panel.winfo_children(): c.destroy()
        sc = ctk.CTkScrollableFrame(self._detail_panel, fg_color="transparent")
        sc.pack(fill="both", expand=True, padx=18, pady=18)
        p = Path(m["Ruta_Destino"])

        def section_title(parent, text):
            ctk.CTkLabel(parent, text=text, font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=C["accent"]).pack(anchor="w", pady=(14, 6))

        def field_row(parent, label, value, copyable=False):
            row = ctk.CTkFrame(parent, fg_color="#0F172A", corner_radius=14)
            row.pack(fill="x", pady=4)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=10)
            ctk.CTkLabel(inner, text=label, font=ctk.CTkFont(size=9, weight="bold"),
                         text_color="#64748B").pack(anchor="w")
            if copyable:
                val_row = ctk.CTkFrame(inner, fg_color="transparent")
                val_row.pack(fill="x", pady=(3, 0))
                ctk.CTkLabel(val_row, text=value, font=ctk.CTkFont(size=10),
                             text_color="#E2E8F0", wraplength=300, justify="left", anchor="w").pack(side="left", fill="x", expand=True)
                ctk.CTkButton(val_row, text="COPIAR", width=80, height=28,
                              fg_color=C["accent"], hover_color=C["accent_hover"],
                              corner_radius=14, font=ctk.CTkFont(size=9, weight="bold"),
                              command=lambda v=value: self._copy_to_clipboard(v)).pack(side="right", padx=(8, 0))
            else:
                ctk.CTkLabel(inner, text=value, font=ctk.CTkFont(size=10),
                             text_color="#E2E8F0", wraplength=350, justify="left", anchor="w").pack(anchor="w", pady=(3, 0))

        # ─── SECCIÓN 1: Resumen del Archivo ───
        section_title(sc, "RESUMEN DEL ARCHIVO")
        field_row(sc, "NOMBRE", p.name)
        field_row(sc, "TIPO DE ARCHIVO", p.suffix.upper() or "Desconocido")
        field_row(sc, "CATEGORÍA", m.get("Categoria", "—"))
        field_row(sc, "UBICACIÓN EN DISCO", str(p.parent), copyable=True)

        # ─── SECCIÓN 2: Resumen del Correo ───
        section_title(sc, "RESUMEN DEL CORREO")
        field_row(sc, "CARPETA DE ORIGEN", m.get("Ubicacion_Original", "—"))
        field_row(sc, "FECHA DE RECEPCIÓN", m.get("Fecha", "—"))
        field_row(sc, "REMITENTE", m.get("Remitente", "—"))


    def _poll_queues(self):
        limit_per_tick = 25
        try:
            processed = 0
            while processed < limit_per_tick: 
                msg = self._log_queue.get_nowait()
                processed += 1
                if msg == "JOB_DONE": 
                    self.after(0, self._on_done)
                    break
                else: 
                    self._write_log(msg)
        except queue.Empty: pass
        
        try:
            processed = 0
            while processed < limit_per_tick: 
                self._set_preview_file(self._preview_queue.get_nowait())
                processed += 1
        except queue.Empty: pass
        
        try:
            processed = 0
            while processed < limit_per_tick: 
                self._update_stats_ui(self._stats_queue.get_nowait())
                processed += 1
        except queue.Empty: pass
        self.after(100, self._poll_queues)

    def _update_stats_ui(self, stats: dict):
        if "saved" in stats: self._stat_labels["saved"].configure(text=str(stats["saved"]))
        if "errors" in stats: self._stat_labels["errors"].configure(text=str(stats["errors"]))
        if "skipped" in stats: self._stat_labels["skipped"].configure(text=str(stats["skipped"]))
        if "zips_extracted" in stats: self._stat_labels["zips_extracted"].configure(text=str(stats["zips_extracted"]))
        if "total_files" in stats: self._stat_labels["total_files"].configure(text=str(stats["total_files"]))

    def _write_log(self, msg):
        if self._running and msg.startswith("PROGRESS:"):
            if "ERROR_SERVER" in msg:
                self._btn_start.configure(text="⚠️ SERVIDOR NO SOPORTADO", text_color="#FFFFFF")
            self._btn_start.update_idletasks()

    def _start_extraction(self):
        if not self._dest_var.get().strip(): return
        for lbl in self._stat_labels.values(): lbl.configure(text="0")
        self._clear_preview(); self._show_empty_detail()
        self._running = True; self._is_manual_stop = False
        self._btn_start.configure(state="disabled", text="⏳ PROCESANDO...")
        threading.Thread(target=self._worker_run, daemon=True).start()

    def _worker_run(self):
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except: pass
        
        try:
            self._engine = ExtractionEngine(self._dest_var.get(), self._log_queue.put, lambda c,t: None, self._preview_queue.put, self._anio_var.get() if self._anio_var.get() != "Todos" else None, stats_cb=self._stats_queue.put, workers=16)
            self._engine.run()
        except Exception as e:
            with open("debug_log.txt", "a", encoding="utf-8") as f:
                f.write(f"[CRITICAL ERROR IN WORKER] {e}\n")
                import traceback
                f.write(traceback.format_exc() + "\n")
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except: pass
            self._log_queue.put("JOB_DONE")

    def _on_done(self):
        self._running = False; self._btn_start.configure(state="normal", text="INICIAR PROCESAMIENTO")
        if not self._is_manual_stop:
            stats = self._engine.stats if hasattr(self, "_engine") and hasattr(self._engine, "stats") else {"saved": 0}
            if stats.get("saved", 0) == 0 and stats.get("zips_extracted", 0) == 0:
                self._show_empty_modal()
            else:
                self._show_completion_modal()

    def _show_empty_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Sin Resultados")

        def _force_icon():
            try:
                ico = getattr(self, "_app_ico_path", None)
                photo = getattr(self, "_app_icon_photo", None)
                if ico and os.path.exists(ico):
                    modal.iconbitmap(ico)
                if photo:
                    modal.wm_iconphoto(True, photo)
            except: pass

        modal.after(250, _force_icon)
        
        modal.geometry("380x320"); modal.attributes("-topmost", True); modal.configure(fg_color=C["main_bg"]); modal.grab_set()
        modal.update_idletasks(); x = self.winfo_x() + (self.winfo_width() // 2) - 190; y = self.winfo_y() + (self.winfo_height() // 2) - 160; modal.geometry(f"+{x}+{y}")
        
        frame = ctk.CTkFrame(modal, fg_color=C["card_bg"], corner_radius=30, border_width=1, border_color=C["border"]); frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        icon_cir = ctk.CTkFrame(frame, fg_color="#FFFBEB", width=80, height=80, corner_radius=40); icon_cir.pack(pady=(30, 15)); icon_cir.pack_propagate(False)
        ctk.CTkLabel(icon_cir, text="⚠️", font=ctk.CTkFont(size=38), text_color="#F59E0B").place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(frame, text="BÚSQUEDA COMPLETADA", font=ctk.CTkFont(size=20, weight="bold"), text_color=C["text_dark"]).pack()
        ctk.CTkLabel(frame, text="No se encontraron nuevos correos o archivos\npara extraer en esta búsqueda.", font=ctk.CTkFont(size=12), text_color=C["text_light"], justify="center").pack(pady=(6, 0))
        
        ctk.CTkButton(frame, text="ENTENDIDO", fg_color="#F59E0B", hover_color="#D97706", corner_radius=22, height=52, width=200, font=ctk.CTkFont(size=14, weight="bold"), command=modal.destroy).pack(pady=30)

    def _show_completion_modal(self):
        modal = ctk.CTkToplevel(self)
        modal.title("Ixtli")

        def _force_icon():
            try:
                ico = getattr(self, "_app_ico_path", None)
                photo = getattr(self, "_app_icon_photo", None)
                if ico and os.path.exists(ico):
                    modal.iconbitmap(ico)
                if photo:
                    modal.wm_iconphoto(True, photo)
            except: pass

        modal.after(250, _force_icon)
        
        modal.geometry("380x320"); modal.attributes("-topmost", True); modal.configure(fg_color=C["main_bg"]); modal.grab_set()
        modal.update_idletasks(); x = self.winfo_x() + (self.winfo_width() // 2) - 190; y = self.winfo_y() + (self.winfo_height() // 2) - 160; modal.geometry(f"+{x}+{y}")
        
        frame = ctk.CTkFrame(modal, fg_color=C["card_bg"], corner_radius=30, border_width=1, border_color=C["border"]); frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        icon_cir = ctk.CTkFrame(frame, fg_color=C["accent_light"], width=80, height=80, corner_radius=40); icon_cir.pack(pady=(30, 15)); icon_cir.pack_propagate(False)
        ctk.CTkLabel(icon_cir, text="✅", font=ctk.CTkFont(size=38)).place(relx=0.5, rely=0.5, anchor="center")
        
        ctk.CTkLabel(frame, text="PROCESO COMPLETADO", font=ctk.CTkFont(size=20, weight="bold"), text_color=C["text_dark"]).pack()
        ctk.CTkLabel(frame, text="Los archivos se han recuperado exitosamente.", font=ctk.CTkFont(size=12), text_color=C["text_light"]).pack(pady=(6, 0))
        
        ctk.CTkButton(frame, text="ACEPTAR", fg_color=C["accent"], hover_color=C["accent_hover"], corner_radius=22, height=52, width=200, font=ctk.CTkFont(size=14, weight="bold"), command=modal.destroy).pack(pady=30)

    def _stop_extraction(self):
        if self._engine: self._is_manual_stop = True; self._engine.stop()

if __name__ == "__main__":
    App().mainloop()
