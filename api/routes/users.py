"""Perfil propio y administración de usuarios.

Dos bloques con permisos muy distintos, y la separación es el punto:

    /api/me/*      cualquiera con sesión, y SÓLO sobre sí mismo
    /api/users/*   requiere 'usuario:gestionar' (hoy, sólo el rol admin)

Ningún endpoint de /api/me acepta un id de usuario: el id sale del token de
sesión. Así no hay forma de cambiarle el nombre o la foto a otro colándose por
la puerta del perfil propio.

Las fotos se guardan en la base de datos: en Render el disco es efímero y una
carpeta de subidas se vaciaría en cada despliegue.
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from api.models.schemas import (
    RolPublico,
    UsuarioAdmin,
    UsuarioListado,
)
from api.security import exige, usuario_actual
from app.auth import repository
from app.auth.tokens import UsuarioSesion

log = logging.getLogger("cotizador.api.users")

router = APIRouter(tags=["usuarios"])

_TIPOS_FOTO = ("image/png", "image/jpeg", "image/webp")


# --------------------------------------------------------------------------- #
# Cuerpos de petición
# --------------------------------------------------------------------------- #

class PerfilPropio(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)


class FotoSubida(BaseModel):
    """La imagen llega en base64 porque el navegador la recorta antes de subir.

    Sale de un <canvas>, así que ya viene como data URL; mandarla como JSON
    evita montar multipart para un único campo.
    """
    tipo: str
    datos_base64: str


class UsuarioNuevo(BaseModel):
    correo: str = Field(min_length=3, max_length=200)
    nombre: str = Field(min_length=1, max_length=120)
    rol: str
    password: str
    externo: bool = False


class UsuarioCambio(BaseModel):
    nombre: Optional[str] = Field(default=None, max_length=120)
    rol: Optional[str] = None
    activo: Optional[bool] = None
    externo: Optional[bool] = None


class PasswordAjena(BaseModel):
    password_nueva: str


# --------------------------------------------------------------------------- #
# Perfil propio
# --------------------------------------------------------------------------- #

@router.patch("/api/me", response_model=UsuarioListado)
def cambiar_mi_perfil(
    cambio: PerfilPropio,
    usuario: UsuarioSesion = Depends(usuario_actual),
):
    """Cambia el nombre propio. El correo y el rol no se tocan desde aquí."""
    try:
        repository.actualizar_usuario(usuario.id, nombre=cambio.nombre)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    fila = repository.obtener_por_id(usuario.id)
    if not fila:
        raise HTTPException(status_code=404, detail="El usuario ya no existe.")
    return UsuarioListado(
        id=fila["id"], correo=fila["correo"], nombre=fila["nombre"],
        rol=fila.get("rol", ""), activo=fila.get("activo", True),
    )


@router.post("/api/me/photo", status_code=204)
def subir_mi_foto(
    foto: FotoSubida,
    usuario: UsuarioSesion = Depends(usuario_actual),
):
    """Guarda la foto propia, ya recortada a 256x256 por el navegador."""
    if foto.tipo not in _TIPOS_FOTO:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no admitido. Se aceptan: {', '.join(_TIPOS_FOTO)}.")
    try:
        # validate=True para que un base64 corrupto dé 400 y no 500.
        crudo = base64.b64decode(foto.datos_base64, validate=True)
    except Exception as err:
        raise HTTPException(status_code=400, detail="La imagen no es base64 válido.") from err

    try:
        repository.guardar_foto(usuario.id, crudo, foto.tipo)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return Response(status_code=204)


@router.delete("/api/me/photo", status_code=204)
def borrar_mi_foto(usuario: UsuarioSesion = Depends(usuario_actual)):
    repository.borrar_foto(usuario.id)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Fotos (lectura)
# --------------------------------------------------------------------------- #

@router.get("/api/users/{usuario_id}/photo")
def ver_foto(
    usuario_id: int,
    usuario: UsuarioSesion = Depends(usuario_actual),
):
    """La foto de cualquier usuario. Basta con tener sesión: las caras del
    equipo salen en la lista de usuarios y junto a las decisiones de un RFQ.
    """
    foto = repository.obtener_foto(usuario_id)
    if not foto:
        raise HTTPException(status_code=404, detail="Sin foto.")
    datos, tipo = foto
    return Response(
        content=datos,
        media_type=tipo,
        # Privada y de vida corta: la URL lleva el sello de actualización, así
        # que al cambiar la foto cambia la URL y el navegador la vuelve a pedir.
        headers={"Cache-Control": "private, max-age=300"},
    )


# --------------------------------------------------------------------------- #
# Administración
# --------------------------------------------------------------------------- #

@router.get("/api/roles", response_model=list[RolPublico])
def roles(usuario: UsuarioSesion = Depends(exige("usuario:gestionar"))):
    """Los roles que existen, para el desplegable del alta."""
    return [RolPublico(**r) for r in repository.listar_roles()]


@router.get("/api/users", response_model=list[UsuarioAdmin])
def listar(usuario: UsuarioSesion = Depends(exige("usuario:gestionar"))):
    return [UsuarioAdmin(**u) for u in repository.listar_usuarios()]


@router.post("/api/users", response_model=UsuarioAdmin, status_code=201)
def crear(
    nuevo: UsuarioNuevo,
    usuario: UsuarioSesion = Depends(exige("usuario:gestionar")),
):
    """Da de alta un usuario.

    La contraseña la escribe quien administra y se la pasa a la persona; ella
    la cambia desde su perfil. No se manda por correo: este sistema ya envía
    correos a clientes y una credencial en el mismo buzón es mala idea.
    """
    correo = nuevo.correo.strip().lower()
    if "@" not in correo:
        raise HTTPException(status_code=400, detail="El correo no es válido.")

    existente = repository.obtener_por_correo(correo)
    if existente:
        raise HTTPException(
            status_code=409,
            detail=f"Ya existe un usuario con el correo {correo}.")

    try:
        repository.crear_usuario(correo, nuevo.nombre, nuevo.password, nuevo.rol)
        if nuevo.externo:
            # En un segundo paso a propósito: `crear_usuario` es el camino que
            # usan también el arranque y los scripts, y no se le añade un
            # parámetro que sólo interesa al alta desde la pantalla.
            creado_id = repository.obtener_por_correo(correo)
            if creado_id:
                repository.actualizar_usuario(creado_id["id"], externo=True)
    except ValueError as err:
        # PasswordInvalida hereda de ValueError, así que esto cubre tanto la
        # política de contraseñas como un rol inexistente.
        raise HTTPException(status_code=400, detail=str(err)) from err

    log.info("Usuario %s dado de alta por %s.", correo, usuario.correo)
    creado = next((u for u in repository.listar_usuarios() if u["correo"] == correo), None)
    if not creado:
        raise HTTPException(status_code=500, detail="El usuario no se pudo leer tras crearlo.")
    return UsuarioAdmin(**creado)


@router.patch("/api/users/{usuario_id}", response_model=UsuarioAdmin)
def cambiar(
    usuario_id: int,
    cambio: UsuarioCambio,
    usuario: UsuarioSesion = Depends(exige("usuario:gestionar")),
):
    """Cambia nombre, rol, marca de externo o alta-baja de otro usuario."""
    # Quitarse a uno mismo el rol o darse de baja deja el sistema sin nadie que
    # pueda administrarlo si es el único admin: se corta antes de intentarlo.
    if usuario_id == usuario.id:
        if cambio.activo is False:
            raise HTTPException(status_code=400, detail="No puedes darte de baja a ti mismo.")
        if cambio.rol is not None and cambio.rol != usuario.rol:
            raise HTTPException(status_code=400, detail="No puedes cambiarte el rol a ti mismo.")

    try:
        existe = repository.actualizar_usuario(
            usuario_id, nombre=cambio.nombre, rol_codigo=cambio.rol,
            activo=cambio.activo, externo=cambio.externo)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    if not existe:
        raise HTTPException(status_code=404, detail="Ese usuario no existe.")

    actualizado = next((u for u in repository.listar_usuarios() if u["id"] == usuario_id), None)
    if not actualizado:
        raise HTTPException(status_code=404, detail="Ese usuario no existe.")
    log.info("Usuario %s modificado por %s.", usuario_id, usuario.correo)
    return UsuarioAdmin(**actualizado)


@router.post("/api/users/{usuario_id}/password", status_code=204)
def resetear_password(
    usuario_id: int,
    cuerpo: PasswordAjena,
    usuario: UsuarioSesion = Depends(exige("usuario:gestionar")),
):
    """Asigna una contraseña temporal a otro usuario.

    Quien administra nunca ve la anterior —sólo se guarda su hash—, así que
    esto no es "recuperar" una contraseña sino sustituirla. Queda en el
    registro quién lo hizo y sobre quién.
    """
    if usuario_id == usuario.id:
        raise HTTPException(
            status_code=400,
            detail="Para cambiar tu propia contraseña usa el perfil: pide la actual.")

    if not repository.obtener_por_id(usuario_id):
        raise HTTPException(status_code=404, detail="Ese usuario no existe.")

    try:
        repository.cambiar_password(usuario_id, cuerpo.password_nueva)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    log.warning("Contraseña del usuario %s restablecida por %s.", usuario_id, usuario.correo)
    return Response(status_code=204)


# --------------------------------------------------------------------------- #
# Configuración del sistema (sólo lectura)
# --------------------------------------------------------------------------- #

@router.get("/api/system/config")
def configuracion(usuario: UsuarioSesion = Depends(exige("usuario:gestionar"))):
    """La configuración efectiva del servidor, con los secretos tapados.

    Es de SÓLO LECTURA, y no por pereza: la pantalla anterior decía "edits the
    backend environment variables (.env)" y eso no podía funcionar en Render.
    Allí las variables se inyectan desde el panel del servicio, no se leen de
    un fichero; y el disco es efímero, así que escribir un .env no sobrevive
    al siguiente despliegue. Un formulario de guardar habría dado "guardado"
    sin cambiar nada — peor que no tenerlo.

    Lo que sí es útil, y es lo que hace: enseñar con qué configuración está
    corriendo el servidor AHORA, para poder comprobar que lo que se puso en
    Render es lo que llegó.
    """
    import app.core.config as config

    ajustes = config.settings

    # `to_dict()` recorre __dict__, que sólo tiene lo que __init__ llegó a
    # asignar: los ajustes que se quedaron con su valor por defecto de clase no
    # salían, y son justo los que interesa comprobar. Se parte de las
    # anotaciones de la clase, que sí las declaran todas.
    claves = set(getattr(type(ajustes), "__annotations__", {}))
    claves |= {k for k in vars(ajustes) if not k.startswith("_")}

    entradas = []
    for clave in sorted(claves):
        valor = getattr(ajustes, clave, None)
        if callable(valor):
            continue
        sensible = ajustes.es_sensible(clave)
        # Un secreto SIN poner es el fallo que cuesta media hora encontrar
        # ("¿por qué no responde el modelo?"), así que se distingue de uno
        # puesto: el valor nunca sale, pero sí si está vacío.
        vacio = valor in (None, "")
        entradas.append({
            "clave": clave,
            "valor": "" if vacio else ("[REDACTED]" if sensible else str(valor)),
            "sensible": sensible,
            "vacio": vacio,
        })

    # El estado del esquema, junto a la configuración. Cuando algo devuelve 500
    # al leer o guardar datos, lo primero que hay que descartar es que la base
    # se haya quedado atrás respecto al código; verlo aquí evita tener que
    # entrar a Neon a comprobarlo.
    import app.persistence.migraciones as migraciones

    return {
        "entradas": entradas,
        "editable": False,
        "nota": ("Read-only. These values come from the environment "
                 "(Render → Environment). Change them there and redeploy."),
        "esquema": migraciones.estado(),
    }
