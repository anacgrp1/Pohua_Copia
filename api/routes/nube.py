"""El estado de la calculadora, guardado en Neon.

Aquí vive lo que antes hacía la carpeta compartida de OneDrive: guardar el
documento de la calculadora —cotizaciones, clientes, materiales, parámetros,
bitácora— en un sitio que ven todos, y avisar cuando otro lo ha cambiado.

Tres rutas y nada más, porque el contrato que sustituye es igual de pequeño:

    GET    /quoting/estado        el documento entero
    GET    /quoting/estado/rev    sólo el número de revisión (para sondear)
    PUT    /quoting/estado        lo guarda
    POST   /quoting/oferta        archiva un PDF de oferta

Cuelgan de ``/quoting`` y no de ``/api`` a propósito: las llama la calculadora
desde dentro de un iframe, que no manda la cabecera ``Authorization``, así que
se autentican con la cookie de sesión que reparte
``POST /api/quoting/sesion`` — la misma que abre el lector, atada a este
prefijo.

**El sondeo es el motivo de que `rev` exista aparte.** La calculadora pregunta
cada pocos segundos si alguien guardó. Devolverle el documento entero cada vez
—que con unas cuantas cotizaciones son megabytes— para que casi siempre
descubra que no ha cambiado nada sería mover todo el archivo para mirar la
fecha. `rev` es un entero.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from api import lector as lector_montaje
from api.dependencies import get_db
from app.auth.tokens import UsuarioSesion

log = logging.getLogger("cotizador.api.nube")

router = APIRouter(prefix=lector_montaje.RAIZ_QUOTING, tags=["quoting"])

# El PDF de una oferta son unos cientos de kilobytes. El tope está para que un
# fallo del generador —o alguien probando— no meta un fichero enorme en una
# columna de la base, que es de donde peor se sacan después.
MAX_OFERTA = 20 * 1024 * 1024

# Lo mismo para el documento: es grande por naturaleza, pero no ilimitado. Un
# documento que crece sin freno acaba tumbando el guardado de todos a la vez.
MAX_DOCUMENTO = 32 * 1024 * 1024


def _sesion(peticion: Request) -> UsuarioSesion:
    """La sesión, leída de la cookie. Ver `api/lector.py`."""
    return lector_montaje.usuario_de_cookie(peticion)


def _leer_estado(cur) -> Optional[Dict[str, Any]]:
    cur.execute("""
        SELECT documento, rev,
               EXTRACT(EPOCH FROM guardado_en) * 1000 AS mod,
               guardado_por
          FROM cotizador_estado
         WHERE id = 1
    """)
    fila = cur.fetchone()
    if fila is None:
        return None
    documento, rev, mod, por = fila
    return {"documento": documento, "rev": int(rev),
            "mod": int(mod or 0), "guardado_por": por}


@router.get("/estado")
def leer_estado(usuario: UsuarioSesion = Depends(_sesion)) -> Dict[str, Any]:
    """El documento de la calculadora.

    Cuando no hay ninguno todavía devuelve ``estado: "vacio"`` en vez de un 404:
    que la primera persona que entra no encuentre nada es lo normal el primer
    día, no un error, y la calculadora sabe sembrarlo ella misma.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            estado = _leer_estado(cur)

    if estado is None:
        return {"estado": "vacio", "texto": "", "rev": 0, "mod": 0}

    return {
        "estado": "datos",
        # Se devuelve como TEXTO y no como objeto: la calculadora hace
        # JSON.parse de lo que le llega, y volver a serializar aquí un objeto
        # que ya venía serializado de la base sólo añade una vuelta y la
        # posibilidad de que cambie el orden de las claves.
        "texto": json.dumps(estado["documento"], ensure_ascii=False),
        "rev": estado["rev"],
        "mod": estado["mod"],
        "guardado_por": estado["guardado_por"],
    }


@router.get("/estado/rev")
def revision(usuario: UsuarioSesion = Depends(_sesion)) -> Dict[str, Any]:
    """Sólo la revisión y quién guardó. Es lo que se sondea."""
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT rev, EXTRACT(EPOCH FROM guardado_en) * 1000, guardado_por
                  FROM cotizador_estado WHERE id = 1
            """)
            fila = cur.fetchone()
    if fila is None:
        return {"rev": 0, "mod": 0, "guardado_por": None}
    return {"rev": int(fila[0]), "mod": int(fila[1] or 0), "guardado_por": fila[2]}


@router.put("/estado")
async def guardar_estado(
    peticion: Request,
    usuario: UsuarioSesion = Depends(_sesion),
) -> Dict[str, Any]:
    """Guarda el documento y archiva el anterior.

    El anterior se archiva SIEMPRE, antes de escribir el nuevo. La carpeta de
    OneDrive daba versiones sin que nadie las pidiera y eso salvaba de un
    guardado malo; al traernos el documento a una fila hay que traerse también
    esa red. Sin ella, un cliente que escriba basura borra el trabajo de todos
    y no hay dónde volver.

    Se lee el cuerpo en crudo en vez de dejar que Pydantic lo valide: es el
    estado interno de otra aplicación y aquí no se sabe —ni hace falta saber—
    qué forma tiene. Lo único que se exige es que sea un objeto JSON, porque
    guardar una lista o un número dejaría a la calculadora sin poder arrancar.
    """
    crudo = await peticion.body()
    if len(crudo) > MAX_DOCUMENTO:
        raise HTTPException(status_code=413, detail=(
            f"El documento pasa de {MAX_DOCUMENTO // (1024*1024)} MB. "
            "No se guarda: algo lo está haciendo crecer sin control."))
    try:
        documento = json.loads(crudo)
    except json.JSONDecodeError as err:
        raise HTTPException(status_code=400,
                            detail=f"El cuerpo no es JSON válido: {err}") from err
    if not isinstance(documento, dict):
        raise HTTPException(status_code=400,
                            detail="El estado tiene que ser un objeto JSON.")

    texto = json.dumps(documento, ensure_ascii=False)

    with get_db() as conn:
        with conn.cursor() as cur:
            # Archivar lo que había. Si no había nada, no archiva nada.
            cur.execute("""
                INSERT INTO cotizador_estado_historial
                       (rev, documento, guardado_en, guardado_por)
                SELECT rev, documento, guardado_en, guardado_por
                  FROM cotizador_estado WHERE id = 1
            """)
            # Una sola fila, siempre: el UPSERT sobre id=1 es lo que lo mantiene.
            cur.execute("""
                INSERT INTO cotizador_estado (id, documento, rev, guardado_en, guardado_por)
                VALUES (1, %s::jsonb, 1, now(), %s)
                ON CONFLICT (id) DO UPDATE
                   SET documento    = EXCLUDED.documento,
                       rev          = cotizador_estado.rev + 1,
                       guardado_en  = now(),
                       guardado_por = EXCLUDED.guardado_por
                RETURNING rev, EXTRACT(EPOCH FROM guardado_en) * 1000
            """, (texto, usuario.correo))
            rev, mod = cur.fetchone()
        conn.commit()

    log.info("Estado de la calculadora guardado por %s (rev %s, %d KB).",
             usuario.correo, rev, len(crudo) // 1024)
    return {"rev": int(rev), "mod": int(mod or 0), "guardado_por": usuario.correo}


@router.post("/oferta", status_code=201)
async def archivar_oferta(
    peticion: Request,
    cliente: str = Form(...),
    nombre: str = Form(...),
    subcarpeta: str = Form(""),
    archivo: UploadFile = File(...),
    usuario: UsuarioSesion = Depends(_sesion),
) -> Dict[str, Any]:
    """Archiva un PDF de oferta.

    Sustituye a `SFS.saveInto`, que los escribía en `QUOTES/<cliente>/` dentro
    de la carpeta compartida. Para quien cotiza no cambia nada: sigue guardando
    la oferta; lo que cambia es que el archivador es la base y no el disco de
    quien tuviera la carpeta conectada.
    """
    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="La oferta llegó vacía.")
    if len(contenido) > MAX_OFERTA:
        raise HTTPException(status_code=413, detail=(
            f"La oferta pasa de {MAX_OFERTA // (1024*1024)} MB."))

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO cotizador_ofertas
                       (cliente, subcarpeta, nombre, contenido, bytes, creado_por)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (cliente.strip() or "SIN CLIENTE", subcarpeta.strip() or None,
                  nombre.strip(), contenido, len(contenido), usuario.correo))
            ident = cur.fetchone()[0]
        conn.commit()

    log.info("Oferta archivada por %s: %s / %s (%d KB).",
             usuario.correo, cliente, nombre, len(contenido) // 1024)
    return {"id": int(ident), "bytes": len(contenido)}
