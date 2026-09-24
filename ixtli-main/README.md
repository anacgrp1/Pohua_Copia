# Ixtli — CGR Automation Suite

Aplicación de escritorio (Windows) que se conecta a Microsoft Outlook vía MAPI,
recorre todas las carpetas y cuentas, y descarga/clasifica automáticamente los
adjuntos (`.pdf`, `.xml`, `.zip`) en una estructura de carpetas por año y categoría.

## Estructura del proyecto

```
.
├── src/
│   ├── main.py              # Interfaz gráfica (customtkinter) + orquestación
│   └── core/
│       ├── extractor.py     # Motor de extracción MAPI (pywin32 / COM)
│       ├── classifier.py    # Reglas de clasificación (regex)
│       └── sanitizer.py     # Limpieza de nombres de archivo (Windows)
├── assets/                  # Iconos y fondo de la app
├── scripts/                 # Utilidades de diagnóstico (test_mapi, analisis)
├── Ixtli.spec               # Configuración de build (PyInstaller)
├── iniciar.bat             # Lanzador: instala deps y ejecuta la app
├── requirements.txt
└── busqueda/
    └── Busqueda_V1.py       # Aplicación separada (legado, autor distinto)
```

## Requisitos

- Windows con Microsoft Outlook instalado y configurado.
- Python 3.10 o superior en el PATH.

## Ejecución (desarrollo)

La forma recomendada es el lanzador, que verifica Python, instala dependencias
y registra `pywin32` automáticamente:

```bat
iniciar.bat
```

O manualmente:

```bat
pip install -r requirements.txt
python src\main.py
```

> El motor depende de COM/MAPI de Windows; no funciona en Linux/macOS.

## Compilar el ejecutable

```bat
pip install pyinstaller
pyinstaller Ixtli.spec
```

El resultado queda en `dist/Ixtli/`.

## Notas

- Los builds compilados (`Appv1/`, `Appv2/`, `Appv3/`, `Appv4/`, `build/`, `dist/`) ya no se
  versionan en git (ver `.gitignore`); se mantienen en disco localmente.
- `busqueda/Busqueda_V1.py` es una aplicación independiente y de otro autor; se conserva
  tal cual.
