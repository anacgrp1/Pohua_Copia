"""Autenticación de usuarios del cotizador (COT-100).

Tres piezas, deliberadamente separadas:

* ``passwords``  — hash y verificación de contraseñas (PBKDF2-SHA256, stdlib).
* ``tokens``     — emisión y lectura de tokens de sesión (JWT HS256).
* ``repository`` — lectura/escritura de la tabla ``usuarios`` y sus permisos.

La capa HTTP (``api/security.py`` y ``api/routes/auth.py``) sólo consume esto;
aquí no se importa FastAPI a propósito, para que el alta de usuarios se pueda
hacer desde un script de consola sin levantar el servidor.
"""
