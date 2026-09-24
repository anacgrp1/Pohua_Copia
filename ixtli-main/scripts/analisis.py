import pandas as pd
import os
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from pathlib import Path
from datetime import datetime

# ─── Configuración Visual (Consistente con app.py) ──────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

C = {
    "sidebar_bg":   "#E6685B",
    "main_bg":      "#E2E8F0",
    "card_bg":      "#FFFFFF",
    "accent":       "#D81B60",
    "accent_hover": "#C2185B",
    "text_dark":    "#1E293B",
    "text_light":   "#64748B",
    "border":       "#E2E8F0",
    "success":      "#10B981",
    "warning":      "#F59E0B",
    "danger":       "#EF4444",
    "table_header": "#F1F5F9",
}

class AnalizadorGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Nexus Analizador - Comparación de Documentos")
        self.geometry("900x700")
        self.minsize(800, 600)
        self.configure(fg_color=C["main_bg"])

        self.archivo1 = None
        self.archivo2 = None

        self._init_ui()

    def _init_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color=C["card_bg"], height=80, corner_radius=0)
        header.pack(fill="x", side="top")
        
        ctk.CTkLabel(header, text="📊 COMPARADOR DE DOCUMENTOS EXCEL/CSV", 
                     font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                     text_color=C["text_dark"]).pack(pady=20, padx=30, side="left")

        # Main Content
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=30, pady=30)

        # File Selection Area
        selection_frame = ctk.CTkFrame(self.main_frame, fg_color=C["card_bg"], corner_radius=12, border_width=1, border_color=C["border"])
        selection_frame.pack(fill="x", pady=(0, 20))

        # Row 1: File 1
        f1_row = ctk.CTkFrame(selection_frame, fg_color="transparent")
        f1_row.pack(fill="x", padx=20, pady=15)
        
        ctk.CTkLabel(f1_row, text="Archivo Base:", font=ctk.CTkFont(weight="bold"), text_color=C["text_dark"], width=100, anchor="w").pack(side="left")
        self.lbl_f1 = ctk.CTkLabel(f1_row, text="No seleccionado...", text_color=C["text_light"], anchor="w")
        self.lbl_f1.pack(side="left", fill="x", expand=True, padx=10)
        
        ctk.CTkButton(f1_row, text="Seleccionar", fg_color=C["accent"], hover_color=C["accent_hover"], 
                      text_color="#FFFFFF", width=100, command=lambda: self._select_file(1)).pack(side="right")

        # Row 2: File 2
        f2_row = ctk.CTkFrame(selection_frame, fg_color="transparent")
        f2_row.pack(fill="x", padx=20, pady=(0, 15))
        
        ctk.CTkLabel(f2_row, text="Archivo Nuevo:", font=ctk.CTkFont(weight="bold"), text_color=C["text_dark"], width=100, anchor="w").pack(side="left")
        self.lbl_f2 = ctk.CTkLabel(f2_row, text="No seleccionado...", text_color=C["text_light"], anchor="w")
        self.lbl_f2.pack(side="left", fill="x", expand=True, padx=10)
        
        ctk.CTkButton(f2_row, text="Seleccionar", fg_color=C["accent"], hover_color=C["accent_hover"], 
                      text_color="#FFFFFF", width=100, command=lambda: self._select_file(2)).pack(side="right")

        # Action Button
        self.btn_compare = ctk.CTkButton(self.main_frame, text="ANALIZAR Y COMPARAR", 
                                        font=ctk.CTkFont(size=14, weight="bold"),
                                        fg_color=C["accent"], hover_color=C["accent_hover"],
                                        text_color="#FFFFFF",
                                        height=50, command=self._ejecutar_analisis)
        self.btn_compare.pack(fill="x", pady=10)

        # Results Area
        results_container = ctk.CTkFrame(self.main_frame, fg_color=C["card_bg"], corner_radius=12, border_width=1, border_color=C["border"])
        results_container.pack(fill="both", expand=True, pady=(10, 0))
        
        ctk.CTkLabel(results_container, text="RESULTADOS DEL ANÁLISIS", 
                     font=ctk.CTkFont(weight="bold", size=13),
                     text_color=C["text_dark"]).pack(pady=(15, 5), padx=20, anchor="w")

        self.txt_results = ctk.CTkTextbox(results_container, fg_color="#F8FAFC", font=ctk.CTkFont(family="Consolas", size=12),
                                        text_color=C["text_dark"], border_width=1, border_color="#CBD5E1")
        self.txt_results.pack(fill="both", expand=True, padx=20, pady=(5, 15))

        # Footer
        self.footer = ctk.CTkFrame(results_container, fg_color="transparent")
        self.footer.pack(fill="x", padx=20, pady=(0, 15))
        
        self.btn_export = ctk.CTkButton(self.footer, text="Exportar Reporte (.txt)", 
                                       fg_color="#475569", hover_color="#334155",
                                       state="disabled", command=self._exportar_reporte)
        self.btn_export.pack(side="right")

    def _select_file(self, num):
        file = filedialog.askopenfilename(
            title=f"Seleccionar Archivo {num}",
            filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv")]
        )
        if file:
            if num == 1:
                self.archivo1 = file
                self.lbl_f1.configure(text=Path(file).name)
            else:
                self.archivo2 = file
                self.lbl_f2.configure(text=Path(file).name)

    def _log(self, text, color=None):
        self.txt_results.insert("end", text + "\n")
        self.txt_results.see("end")

    def _ejecutar_analisis(self):
        if not self.archivo1 or not self.archivo2:
            messagebox.showwarning("Faltan archivos", "Por favor seleccione ambos archivos para comparar.")
            return

        self.txt_results.delete("1.0", "end")
        self.btn_export.configure(state="disabled")
        
        self._log(f"--- INICIANDO COMPARACIÓN ---")
        self._log(f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
        self._log("-" * 50)

        try:
            # Lectura de archivos
            df1 = self._load_data(self.archivo1)
            df2 = self._load_data(self.archivo2)

            # Comparación de Metadatos
            peso1 = os.path.getsize(self.archivo1)
            peso2 = os.path.getsize(self.archivo2)
            
            self._log(f"[*] Archivo 1: {Path(self.archivo1).name} ({peso1:,} bytes)")
            self._log(f"[*] Archivo 2: {Path(self.archivo2).name} ({peso2:,} bytes)")
            
            if peso1 == peso2:
                self._log(" ✔️ Los archivos tienen el mismo peso en disco.")
            else:
                diff_peso = abs(peso1 - peso2)
                self._log(f" ⚠️ Diferencia de peso: {diff_peso:,} bytes.")

            self._log("\n[*] ESTRUCTURA DE DATOS:")
            shape1 = df1.shape
            shape2 = df2.shape
            self._log(f" - Dimensiones A1: {shape1[0]} filas, {shape1[1]} columnas")
            self._log(f" - Dimensiones A2: {shape2[0]} filas, {shape2[1]} columnas")

            if shape1 != shape2:
                self._log(f" ❌ Las dimensiones NO coinciden (Diff: {shape2[0]-shape1[0]} filas, {shape2[1]-shape1[1]} cols).")
            else:
                self._log(" ✔️ Las dimensiones son idénticas.")

            # Comparación de Columnas
            cols1 = set(df1.columns)
            cols2 = set(df2.columns)
            
            if cols1 == cols2:
                self._log(" ✔️ Los nombres de las columnas coinciden exactamente.")
            else:
                solo_en_1 = cols1 - cols2
                solo_en_2 = cols2 - cols1
                if solo_en_1: self._log(f" ⚠️ Columnas solo en Archivo 1: {', '.join(solo_en_1)}")
                if solo_en_2: self._log(f" ⚠️ Columnas solo en Archivo 2: {', '.join(solo_en_2)}")

            # Comparación de Contenido (si las estructuras son similares)
            self._log("\n[*] VALIDACIÓN DE CONTENIDO:")
            if df1.equals(df2):
                self._log(" ✅ ¡ÉXITO! El contenido de ambos archivos es 100% IDÉNTICO.")
            else:
                self._log(" ❌ El contenido difiere entre los archivos.")
                
                # Intentar encontrar filas diferentes si tienen las mismas columnas
                if cols1 == cols2:
                    # Filas en df2 que no están en df1
                    try:
                        merged = df1.merge(df2, indicator=True, how='outer')
                        nuevas = merged[merged['_merge'] == 'right_only']
                        eliminadas = merged[merged['_merge'] == 'left_only']
                        
                        if not nuevas.empty:
                            self._log(f" - Se encontraron {len(nuevas)} registros nuevos en el Archivo 2.")
                        if not eliminadas.empty:
                            self._log(f" - Se encontraron {len(eliminadas)} registros del Archivo 1 que no están en el 2.")
                        
                        if nuevas.empty and eliminadas.empty:
                            self._log(" - Los registros son los mismos pero el orden o los tipos de datos varían.")
                    except Exception as e:
                        self._log(f" - No se pudo profundizar en la diferencia de registros: {e}")

            self._log("\n--- ANÁLISIS FINALIZADO ---")
            self.btn_export.configure(state="normal")
            
        except Exception as e:
            self._log(f"\n❌ ERROR CRÍTICO: {e}")
            messagebox.showerror("Error de Análisis", f"No se pudo completar la comparación:\n{e}")

    def _load_data(self, path):
        ext = Path(path).suffix.lower()
        if ext == '.csv':
            return pd.read_csv(path)
        else:
            return pd.read_excel(path)

    def _exportar_reporte(self):
        content = self.txt_results.get("1.0", "end")
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Archivo de texto", "*.txt")],
            initialfile=f"Reporte_Comparativo_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
        )
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            messagebox.showinfo("Exportación", "Reporte guardado correctamente.")

if __name__ == "__main__":
    app = AnalizadorGUI()
    app.mainloop()