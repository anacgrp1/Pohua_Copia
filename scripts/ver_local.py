#!/usr/bin/env python
"""Arranca el cotizador en tu computadora para ver los cambios al instante.

Lo llama ``ver_local.bat``. La lógica vive aquí y no en el .bat porque en
Python se puede leer, probar y entender; el .bat sólo es el doble clic.

Qué hace, en orden:

1. Comprueba que las dependencias estén instaladas.
2. Se asegura de que exista un ``.env`` con una ``JWT_SECRET`` utilizable.
3. **Apaga el worker y el envío de correo** para esta ejecución (ver abajo).
4. Dice contra qué base de datos vas a trabajar, y avisa si es la de producción.
5. Levanta uvicorn con recarga automática y abre el navegador.

Por qué apaga el worker y el correo
-----------------------------------
Si tu ``.env`` apunta a Neon, un servidor local sin estas dos protecciones
haría dos cosas que sí se notan fuera de tu computadora:

* leería el MISMO buzón que el servidor de Render y marcaría los correos como
  leídos, así que producción dejaría de verlos;
* al declinar un RFQ para probar, saldría un correo de verdad a un comprador.

Las variables de entorno tienen prioridad sobre el ``.env`` (así está escrito
``app/core/config.py``), así que fijarlas aquí gana sin que tengas que editar
nada.
"""

from __future__ import annotations

import os
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

RAIZ = Path(__file__).resolve().parent.parent
PUERTO = 8000

# Este script vive en scripts/, así que Python pone scripts/ en sys.path, no la
# raíz del proyecto: sin esta línea, `import app...` falla con "No module named
# 'app'" y el servidor no llega a levantar. Cambiar de directorio con chdir NO
# basta, porque sys.path se fija al arrancar el intérprete.
sys.path.insert(0, str(RAIZ))

def _habilitar_colores() -> bool:
    """True si la consola entiende códigos de color.

    En Windows, cmd.exe sólo interpreta las secuencias ANSI si se le activa el
    modo "virtual terminal"; sin activarlo salen impresas como basura del tipo
    ``[92m``. Se intenta activar, y si no se puede se trabaja sin color.
    """
    if not sys.stdout.isatty():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # -11 = STD_OUTPUT_HANDLE, 0x0004 = ENABLE_VIRTUAL_TERMINAL_PROCESSING
        modo = ctypes.c_uint32()
        handle = kernel32.GetStdHandle(-11)
        if not kernel32.GetConsoleMode(handle, ctypes.byref(modo)):
            return False
        return bool(kernel32.SetConsoleMode(handle, modo.value | 0x0004))
    except Exception:
        return False


_COLOR = _habilitar_colores()

VERDE = "\033[92m" if _COLOR else ""
AMARILLO = "\033[93m" if _COLOR else ""
ROJO = "\033[91m" if _COLOR else ""
GRIS = "\033[90m" if _COLOR else ""
FIN = "\033[0m" if _COLOR else ""


def aviso(texto: str) -> None:
    print(f"{AMARILLO}  {texto}{FIN}")


def error(texto: str) -> None:
    print(f"{ROJO}  {texto}{FIN}")


def ok(texto: str) -> None:
    print(f"{VERDE}  {texto}{FIN}")


# ---------------------------------------------------------------------------
# 1. Dependencias
# ---------------------------------------------------------------------------

def comprobar_dependencias() -> bool:
    """True si están todas; si no, dice cómo instalarlas."""
    faltan = []
    for modulo, paquete in [("fastapi", "fastapi"), ("uvicorn", "uvicorn[standard]"),
                            ("psycopg2", "psycopg2-binary"), ("jwt", "pyjwt"),
                            ("flask", "Flask")]:
        try:
            __import__(modulo)
        except ImportError:
            faltan.append(paquete)

    if faltan:
        error("Faltan dependencias: " + ", ".join(faltan))
        print(f"{GRIS}  Instálalas con:{FIN}")
        print("      pip install -r requirements.txt")
        return False
    return True


# ---------------------------------------------------------------------------
# 2. El archivo .env
# ---------------------------------------------------------------------------

def _leer_env(ruta: Path) -> dict:
    valores = {}
    if not ruta.is_file():
        return valores
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#") or "=" not in linea:
            continue
        clave, valor = linea.split("=", 1)
        valores[clave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def preparar_env() -> dict:
    """Crea el .env si no existe y le pone una JWT_SECRET si le falta."""
    ruta = RAIZ / ".env"
    plantilla = RAIZ / ".env.example"

    if not ruta.is_file():
        if not plantilla.is_file():
            error("No hay .env ni .env.example. No puedo continuar.")
            return {}
        shutil.copy(plantilla, ruta)
        aviso("No había .env: lo creé a partir de .env.example.")

    valores = _leer_env(ruta)

    # Sin JWT_SECRET el login no funciona. Se genera una y se escribe.
    if not valores.get("JWT_SECRET"):
        secreto = secrets.token_urlsafe(48)
        texto = ruta.read_text(encoding="utf-8")
        if "JWT_SECRET=" in texto:
            texto = texto.replace("JWT_SECRET=", f"JWT_SECRET={secreto}", 1)
        else:
            texto += f"\nJWT_SECRET={secreto}\n"
        ruta.write_text(texto, encoding="utf-8")
        valores["JWT_SECRET"] = secreto
        ok("Generé una JWT_SECRET para tu .env (sólo local).")

    return valores


# ---------------------------------------------------------------------------
# 3. Protecciones y aviso sobre la base de datos
# ---------------------------------------------------------------------------

def aplicar_protecciones() -> None:
    """Apaga el worker de correo y el envío automático para esta ejecución."""
    os.environ["WORKER_AUTOSTART"] = "false"
    os.environ["ENVIO_AUTOMATICO"] = "False"
    os.environ["APP_ENV"] = "dev"


def describir_base(valores: dict) -> None:
    """Dice contra qué base vas a trabajar. Avisa fuerte si es producción."""
    url = os.environ.get("DATABASE_URL") or valores.get("DATABASE_URL", "")
    if not url:
        aviso("No hay DATABASE_URL: la aplicación arranca, pero el login fallará.")
        print(f"{GRIS}      Rellena DATABASE_URL en el .env, o levanta una base"
              f" local con: make db-up{FIN}")
        return

    try:
        host = urlparse(url).hostname or "?"
    except ValueError:
        host = "?"

    if host in ("localhost", "127.0.0.1", "db", "::1"):
        ok(f"Base de datos local ({host}). Puedes probar sin miedo.")
    else:
        print()
        print(f"{AMARILLO}  {'-' * 68}{FIN}")
        print(f"{AMARILLO}  ATENCIÓN: estás apuntando a la base de PRODUCCIÓN{FIN}")
        print(f"{AMARILLO}  {'-' * 68}{FIN}")
        print(f"      Host: {host}")
        print()
        print("      Para ver cambios visuales no pasa nada. Pero lo que hagas en")
        print("      los RFQ se guarda de verdad: si apruebas o declinas algo aquí,")
        print("      queda registrado en la base que usa la planta.")
        print()
        print(f"{GRIS}      Ya apagué el lector de correo y el envío automático, así que")
        print("      ningún correo va a salir hacia un cliente desde tu equipo.")
        print(f"      Para trabajar aislada del todo:  make db-up{FIN}")
        print()


# ---------------------------------------------------------------------------
# 4. Comprobaciones antes de arrancar
# ---------------------------------------------------------------------------

def puerto_ocupado(puerto: int) -> bool:
    """True si ya hay algo escuchando en ese puerto."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", puerto)) == 0


def rellenar_correo_si_falta() -> None:
    """Pone valores de relleno para las variables de correo que falten.

    La configuración exige, según AUTH_METHOD, o las tres de IMAP o las tres de
    Azure; si falta una, la aplicación se niega a arrancar. Eso está bien en el
    servidor, pero aquí impide algo tan inocente como mirar un cambio de CSS.

    Como el lector de correo va apagado y el envío automático también, estos
    valores no se usan para nada: sólo dejan que la aplicación levante. No se
    escriben en el .env.
    """
    metodo = (os.environ.get("AUTH_METHOD")
              or _leer_env(RAIZ / ".env").get("AUTH_METHOD", "local")).lower()

    if metodo == "token":
        requeridas = ("AZURE_CLIENT_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_SECRET")
        relleno = "no-usado-en-local"
    else:
        requeridas = ("IMAP_SERVER", "IMAP_USER", "IMAP_PASSWORD")
        relleno = "no-usado-en-local"

    del_env = _leer_env(RAIZ / ".env")
    faltan = [v for v in requeridas
              if not os.environ.get(v) and not del_env.get(v)]
    if not faltan:
        return

    for variable in faltan:
        os.environ[variable] = relleno
    aviso("Faltan en el .env: " + ", ".join(faltan))
    print(f"{GRIS}      Les puse un valor de relleno para que la aplicación pueda")
    print("      arrancar. No se usan: el lector de correo está apagado y no se")
    print(f"      escribe nada en tu .env.{FIN}")


def revisar_configuracion() -> bool:
    """Carga la configuración y traduce el error si algo falta.

    Sin esto, un problema de configuración salía como un traceback de Python
    dentro de uvicorn y el navegador se quedaba en "no se puede acceder al
    sitio", sin pista de por qué.
    """
    try:
        import app.core.config  # noqa: F401
    except Exception as err:
        error("La aplicación no puede arrancar con la configuración actual:")
        print()
        print(f"      {err}")
        print()
        print(f"{GRIS}      Revisa el archivo .env en la carpeta del proyecto.{FIN}")
        return False
    return True


# ---------------------------------------------------------------------------
# 5. Arranque
# ---------------------------------------------------------------------------

def esperar_y_abrir(url: str, puerto: int, segundos: int = 60) -> None:
    """Abre el navegador cuando el servidor RESPONDE, no antes.

    Antes se abría a los 2.5 segundos fijos. En Windows, uvicorn con recarga
    automática tarda bastante más en levantar (importa el SDK de IA, azure,
    psycopg2...), así que el navegador llegaba primero y mostraba
    ERR_CONNECTION_REFUSED aunque todo estuviera bien.
    """
    def _esperar():
        import time
        for _ in range(segundos * 2):
            if puerto_ocupado(puerto):
                time.sleep(0.4)      # un respiro para que termine de atender
                webbrowser.open(url)
                return
            time.sleep(0.5)
        print()
        aviso(f"El servidor no respondió en {segundos} segundos.")
        print(f"{GRIS}      Mira los mensajes de arriba: si hay un error de Python,"
              f" ahí está el motivo.{FIN}")

    threading.Thread(target=_esperar, daemon=True).start()


def main() -> int:
    print()
    print(f"  {VERDE}CGR Cotizador — vista local{FIN}")
    print(f"  {GRIS}{'-' * 68}{FIN}")

    os.chdir(RAIZ)

    if not comprobar_dependencias():
        return 1

    valores = preparar_env()
    if not valores:
        return 1

    aplicar_protecciones()
    ok("Lector de correo y envío automático: APAGADOS para esta ejecución.")

    if puerto_ocupado(PUERTO):
        error(f"El puerto {PUERTO} ya está ocupado.")
        print(f"{GRIS}      Puede que ya tengas el servidor corriendo en otra ventana:")
        print(f"      prueba a abrir http://localhost:{PUERTO} antes de nada.")
        print("      Si no, cierra la otra ventana negra y vuelve a intentarlo.")
        print(f"{FIN}")
        return 1

    rellenar_correo_si_falta()
    describir_base(valores)

    if not revisar_configuracion():
        return 1

    url = f"http://localhost:{PUERTO}"
    print(f"  {GRIS}{'-' * 68}{FIN}")
    print(f"  Abriendo {VERDE}{url}{FIN}")
    print(f"  {GRIS}El navegador se abre solo en cuanto el servidor responda")
    print("  (la primera vez puede tardar medio minuto).")
    print("  Guarda cualquier archivo y el servidor se reinicia solo.")
    print("  Para los cambios de CSS o JS basta con refrescar el navegador (Ctrl+F5).")
    print(f"  Ctrl+C para parar.{FIN}")
    print()

    esperar_y_abrir(url, PUERTO)

    # uvicorn arranca en otro proceso (y con --reload, en un tercero), así que
    # necesita la raíz del proyecto en PYTHONPATH: heredar el sys.path de aquí
    # no le sirve.
    entorno = dict(os.environ)
    ruta_previa = entorno.get("PYTHONPATH", "")
    entorno["PYTHONPATH"] = (str(RAIZ) + os.pathsep + ruta_previa) if ruta_previa else str(RAIZ)

    try:
        return subprocess.call([
            sys.executable, "-m", "uvicorn", "api.server:app",
            "--host", "127.0.0.1", "--port", str(PUERTO),
            "--reload", "--app-dir", str(RAIZ), "--log-level", "info",
        ], env=entorno, cwd=str(RAIZ))
    except KeyboardInterrupt:
        print("\n  Servidor detenido.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
