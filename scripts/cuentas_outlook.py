"""Qué cuentas y buzones ve Pohua en este Outlook, y desde cuál mandaría.

    python scripts/cuentas_outlook.py

Para cuando una respuesta sale con el remitente equivocado. La diferencia que
importa es ésta:

* Una **cuenta** del perfil (la que se añade con Archivo → Agregar cuenta)
  puede mandar correo: el mensaje sale COMO ella.
* Un **buzón abierto** de más —un buzón compartido que aparece en la columna
  de carpetas porque alguien te dio acceso— sirve para leer, pero para mandar
  en su nombre hace falta el permiso "enviar en nombre de" en Exchange.

Si `sales.isc@cgr-international.com` sale abajo en la lista de cuentas, las
respuestas saldrán desde ahí. Si sólo sale como buzón, saldrán desde la cuenta
personal de este perfil mientras no se arregle el permiso.

No manda nada ni toca ningún correo: sólo mira.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)


def main() -> int:
    import app.core.config as config

    buzon = (getattr(config.settings, "OUTLOOK_BUZON", "") or "").strip()
    print(f"OUTLOOK_BUZON = {buzon or '(vacío)'}\n")

    try:
        import pythoncom
        pythoncom.CoInitialize()
        import win32com.client
    except ImportError:
        print("Falta pywin32: pip install -r requirements-desktop.txt")
        return 1

    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mapi = outlook.GetNamespace("MAPI")
    except Exception as error:
        print(f"No se pudo hablar con Outlook (¿abierto, y el clásico?): {error}")
        return 1

    print("CUENTAS DEL PERFIL (éstas sí pueden mandar)")
    cuentas = []
    try:
        lista = outlook.Session.Accounts
        for i in range(lista.Count):
            cuenta = lista.Item(i + 1)
            direccion = str(getattr(cuenta, "SmtpAddress", "") or "")
            nombre = str(getattr(cuenta, "DisplayName", "") or "")
            cuentas.append(direccion.lower())
            print(f"   {direccion or '(sin dirección)':45} {nombre}")
    except Exception as error:
        print(f"   No se pudieron listar: {error}")

    print("\nBUZONES ABIERTOS (de aquí se lee)")
    try:
        for i in range(mapi.Folders.Count):
            print(f"   {mapi.Folders.Item(i + 1).Name}")
    except Exception as error:
        print(f"   No se pudieron listar: {error}")

    print()
    if not buzon:
        print("Sin OUTLOOK_BUZON, el correo saldría desde la cuenta principal "
              "del perfil.")
    elif buzon.lower() in cuentas:
        print(f"Bien: {buzon} es una cuenta de este perfil. Las respuestas "
              f"saldrán como ese buzón.")
    else:
        print(f"Ojo: {buzon} NO es una cuenta de este perfil. Pohua intentará "
              f"mandar 'en nombre de' ese buzón, y eso sólo funciona si "
              f"Exchange te dio ese permiso; si no, el correo saldrá con el "
              f"remitente personal.\n"
              f"Arreglos, por orden: añadir ese buzón como cuenta en Outlook "
              f"(Archivo → Agregar cuenta), o pedir a sistemas el permiso "
              f"'Enviar en nombre de' (o 'Enviar como') sobre él.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
