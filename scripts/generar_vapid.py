"""Genera el par de claves VAPID para los avisos push.

    python scripts/generar_vapid.py

Imprime las dos líneas que van al .env (y a Render). La privada es un
secreto: no se pega en ningún chat ni va al repositorio.
"""
from __future__ import annotations

import base64


def main() -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    clave = ec.generate_private_key(ec.SECP256R1())
    privada = clave.private_numbers().private_value.to_bytes(32, "big")
    publica = clave.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)

    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    print("VAPID_PUBLIC_KEY=" + b64(publica))
    print("VAPID_PRIVATE_KEY=" + b64(privada))


if __name__ == "__main__":
    main()
