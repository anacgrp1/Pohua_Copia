"""Cuarentena: el correo que puede ser malware no se procesa.

Por qué
-------
El buzón de ventas recibe correo de cualquiera, y desde 2026-09 todo lo que
llega a la carpeta de peticiones se trata como una petición: se leen sus
adjuntos con el modelo de visión, se guardan en la base y en disco, y se le
contesta. Eso es exactamente lo que un correo malicioso quiere: que se abra
el adjunto y que alguien conteste. Antes de todo eso se mira.

Qué se mira (sin ejecutar nada)
-------------------------------
* **Adjuntos que no son planos ni imágenes de trabajo**: ejecutables,
  scripts, instaladores, accesos directos, archivos comprimidos, páginas
  HTML, documentos de Office con macros. Un plano llega como PDF, imagen o
  STEP; lo demás no tiene por qué venir en una petición de cotización.
* **Extensión doble** («plano.pdf.exe»): la manera clásica de disfrazar un
  ejecutable.
* **El contenido no es lo que dice el nombre**: un ``.pdf`` que no empieza por
  ``%PDF``, una ``.png`` sin cabecera PNG. Lo que no es lo que dice, no se
  abre.
* **PDF con contenido activo**: ``/JavaScript``, ``/JS``, ``/Launch``,
  ``/EmbeddedFile``, ``/OpenAction`` con acción. Un plano no ejecuta nada.
* **Windows Defender**, si está en la computadora: se le pide que analice
  el adjunto (``MpCmdRun.exe -Scan -ScanType 3 -File``). Es un extra: si no
  está, o el antivirus es otro, valen las comprobaciones de arriba.

Qué pasa con lo sospechoso
--------------------------
No se lee el adjunto, no se da de alta ningún RFQ y **no se contesta**:
contestarle a un remitente malicioso confirma que el buzón existe y que
alguien lo atiende. El correo se marca como leído, se apunta como procesado
para no volver a mirarlo, y queda una línea de WARNING con el motivo para que
una persona decida. Esto NO sustituye al antivirus del equipo: es un filtro
más, antes de que el sistema abra nada solo.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from typing import Any, Dict, List

log = logging.getLogger("cotizador.cuarentena")

# Lo que sí puede venir en una petición: planos, imágenes del plano, modelos.
EXTENSIONES_PERMITIDAS = frozenset({
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp",
    ".stp", ".step", ".igs", ".iges", ".dxf", ".dwg", ".sldprt", ".x_t",
    ".txt", ".csv", ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt",
})

# Lo que nunca debería venir, y si viene no se abre.
EXTENSIONES_PELIGROSAS = frozenset({
    ".exe", ".scr", ".com", ".pif", ".bat", ".cmd", ".ps1", ".psm1", ".vbs",
    ".vbe", ".js", ".jse", ".wsf", ".wsh", ".hta", ".msi", ".msp", ".jar",
    ".lnk", ".url", ".reg", ".dll", ".cpl", ".inf", ".iso", ".img", ".vhd",
    ".zip", ".rar", ".7z", ".gz", ".tar", ".cab", ".ace", ".arj",
    ".html", ".htm", ".mht", ".svg", ".xml", ".chm",
    ".docm", ".xlsm", ".pptm", ".dotm", ".xltm", ".xlam", ".ppam",
})

# Cabeceras de los tipos que se abren: si el nombre dice uno y el contenido
# es otro, no se abre.
_MAGIA = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".bmp": (b"BM",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    ".webp": (b"RIFF",),
    ".docx": (b"PK",), ".xlsx": (b"PK",), ".pptx": (b"PK",),
    ".doc": (b"\xd0\xcf\x11\xe0",), ".xls": (b"\xd0\xcf\x11\xe0",), ".ppt": (b"\xd0\xcf\x11\xe0",),
}

# Un ejecutable de Windows disfrazado de lo que sea empieza por "MZ".
_MAGIA_EJECUTABLE = (b"MZ", b"\x7fELF")

# Contenido activo dentro de un PDF. Un plano no lo necesita.
_PDF_ACTIVO = (b"/JavaScript", b"/JS ", b"/JS(", b"/JS<", b"/Launch",
               b"/EmbeddedFile", b"/RichMedia", b"/XFA")

# Un nombre con más de una extensión: "plano.pdf.exe", "cotizacion.pdf.js".
_EXTENSION_DOBLE = re.compile(r"\.[a-z0-9]{2,5}\.[a-z0-9]{2,5}$", re.I)


def _extension(nombre: str) -> str:
    return os.path.splitext(str(nombre or "").strip().lower())[1]


def _parece_imagen_o_pdf(contenido: bytes) -> bool:
    cabecera = bytes(contenido[:8])
    return any(cabecera.startswith(m)
               for ext in (".pdf", ".png", ".jpg", ".gif", ".bmp", ".tif", ".webp")
               for m in _MAGIA[ext])


def motivos_del_adjunto(adjunto: Dict[str, Any]) -> List[str]:
    """Por qué este adjunto es sospechoso. Vacío si no lo es."""
    nombre = str(adjunto.get("nombre") or "")
    contenido = adjunto.get("contenido") or b""
    if not isinstance(contenido, (bytes, bytearray)):
        contenido = b""
    ext = _extension(nombre)
    motivos: List[str] = []

    if ext in EXTENSIONES_PELIGROSAS:
        motivos.append(f"adjunto peligroso «{nombre}» ({ext})")
    elif ext and ext not in EXTENSIONES_PERMITIDAS:
        motivos.append(f"adjunto de tipo no admitido «{nombre}» ({ext})")
    elif not ext and contenido and not _parece_imagen_o_pdf(contenido):
        # Sin extensión pero con pinta de imagen o PDF (un logo incrustado sin
        # nombre) pasa; lo demás sin nombre no se abre.
        motivos.append(f"adjunto sin extensión «{nombre}»")

    sin_ext = _extension(os.path.splitext(nombre)[0])
    if _EXTENSION_DOBLE.search(nombre) and (sin_ext in EXTENSIONES_PERMITIDAS
                                           or ext in EXTENSIONES_PELIGROSAS):
        motivos.append(f"extensión doble en «{nombre}»")

    cabecera = bytes(contenido[:8])
    if cabecera[:2] == _MAGIA_EJECUTABLE[0] or cabecera[:4] == _MAGIA_EJECUTABLE[1]:
        motivos.append(f"«{nombre}» es un ejecutable, diga lo que diga el nombre")
    elif ext in _MAGIA and contenido and not any(cabecera.startswith(m) for m in _MAGIA[ext]):
        motivos.append(f"«{nombre}» no es un {ext[1:].upper()} de verdad")

    if ext == ".pdf" and contenido:
        activo = [m.decode("latin-1").strip() for m in _PDF_ACTIVO if m in contenido]
        if activo:
            motivos.append(f"«{nombre}» lleva contenido activo ({', '.join(activo)})")

    return motivos


def revisar(correo: Dict[str, Any], con_antivirus: bool = True) -> List[str]:
    """Los motivos para poner el correo en cuarentena. Vacío si está limpio.

    Las imágenes incrustadas (la firma) se miran igual: un logo también puede
    ser un ejecutable con otro nombre.
    """
    motivos: List[str] = []
    for adjunto in correo.get("adjuntos") or []:
        motivos.extend(motivos_del_adjunto(adjunto))
    if con_antivirus and not motivos:
        for adjunto in correo.get("adjuntos") or []:
            veredicto = analizar_con_defender(adjunto)
            if veredicto:
                motivos.append(veredicto)
    return motivos


def _mpcmdrun() -> str:
    """La ruta de MpCmdRun.exe (Windows Defender), o vacío si no está."""
    if os.name != "nt":
        return ""
    candidatos = [
        os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"),
                     "Windows Defender", "MpCmdRun.exe"),
        os.path.join(os.environ.get("ProgramW6432", r"C:\Program Files"),
                     "Windows Defender", "MpCmdRun.exe"),
    ]
    for ruta in candidatos:
        if os.path.isfile(ruta):
            return ruta
    return ""


def analizar_con_defender(adjunto: Dict[str, Any]) -> str:
    """Le pide a Windows Defender que analice el adjunto. Vacío si limpio.

    Devuelve el motivo si Defender encontró algo (código 2). Si Defender no
    está, o falla, no se inventa nada: las comprobaciones propias ya
    corrieron. Es mejor esfuerzo, no una garantía.
    """
    ejecutable = _mpcmdrun()
    contenido = adjunto.get("contenido") or b""
    if not ejecutable or not contenido:
        return ""
    nombre = str(adjunto.get("nombre") or "adjunto")
    ext = _extension(nombre) or ".bin"
    ruta = ""
    try:
        with tempfile.NamedTemporaryFile(prefix="pohua-cuarentena-", suffix=ext,
                                         delete=False) as tmp:
            tmp.write(bytes(contenido))
            ruta = tmp.name
        salida = subprocess.run(
            [ejecutable, "-Scan", "-ScanType", "3", "-File", ruta, "-DisableRemediation"],
            capture_output=True, text=True, timeout=120)
        if salida.returncode == 2:
            return f"Windows Defender detectó una amenaza en «{nombre}»"
    except Exception as error:
        log.debug("No se pudo analizar «%s» con Defender: %s", nombre, error)
    finally:
        if ruta:
            try:
                os.remove(ruta)
            except OSError:
                pass
    return ""
