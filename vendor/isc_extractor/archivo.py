"""Politica de retencion y archivado del spec.

El problema
-----------
Cada lectura dejaba tres cosas y no se borraba ninguna:

  _uploads/<job>.pdf   el plano del cliente, ~0,4 MB
  _crops/*.png         ~82 recortes por plano, ~1,05 MB   <- el 70% del volumen
  _specs/<job>.json    la extraccion, ~10 KB

Medido sobre los 9 planos del banco. En un puesto real eso es un archivo de
documentacion de clientes creciendo sin control dentro de una carpeta que se
llama "to share".

La politica
-----------
Se borra lo reproducible y se conserva lo que costo dinero:

  * Los **recortes** son una ayuda de revision. Su vida util es la sesion en la
    que se revisa la oferta, y se pueden regenerar desde la pagina y el `nbox`
    que ya vive en `spec.localizacion`. Se borran a los N dias.
  * El **plano subido** es un duplicado: la calculadora ya archiva el original
    en `QUOTES/<cliente>/RFQ Info/` con su nombre real. Se borra a los N dias.
  * El **spec** es lo unico irrecuperable -- rehacerlo cuesta ~$0,20 de API --
    y ademas es lo que tiene valor a futuro. No se borra nunca, y se archiva
    junto al plano.

El archivado
------------
El spec se copia a `QUOTES/<cliente>/RFQ Info/<PN>.spec.json`, es decir, al lado
del plano del que salio. Ojo con el nombre de la carpeta: la calculadora usa el
nombre del cliente **de su base de datos**, no el texto que pone el plano. Si
aqui usaramos el texto del plano, el spec acabaria en una carpeta distinta de la
del plano. Por eso se lee `ISC_V4_DATA.json` y se resuelve el cliente con el
mismo criterio que usa la calculadora.

El sobre
--------
El JSON archivado no es el spec pelado: va envuelto con los metadatos que
identifican la lectura. Eso es a proposito -- cuando esto pase a PostgreSQL, las
claves del sobre son columnas y `spec` es un JSONB. Asi la migracion es un
`COPY`, no un reprocesado.
"""

import json
import os
import re
import time

ESQUEMA = "isc-spec-archivo/1"
RETENCION_DIAS = 7
EFIMERAS = ("_crops", "_uploads")       # lo reproducible
PERMANENTES = ("_specs",)               # lo que nunca se toca


# ---------------------------------------------------------------- retencion
def purgar(base, dias=None, log=None):
    """Borra de `_crops` y `_uploads` lo que pase de `dias`. -> resumen.

    Nunca toca `_specs` ni `_gasto.json`: si alguna vez se anade una carpeta
    nueva hay que decidir a que lista pertenece, no heredar el borrado.
    """
    dias = RETENCION_DIAS if dias is None else dias
    if not dias or dias <= 0:                     # 0 o negativo = desactivado
        return {"activo": False}
    limite = time.time() - dias * 86400
    res = {"activo": True, "dias": dias, "ficheros": 0, "mb": 0.0}
    for carpeta in EFIMERAS:
        d = os.path.join(str(base), carpeta)
        if not os.path.isdir(d):
            continue
        for nombre in os.listdir(d):
            p = os.path.join(d, nombre)
            try:
                st = os.stat(p)
                if not os.path.isfile(p) or st.st_mtime >= limite:
                    continue
                os.remove(p)
                res["ficheros"] += 1
                res["mb"] += st.st_size / 1048576.0
            except Exception:
                pass                              # un fichero en uso no puede
                                                  # tumbar la limpieza entera
    res["mb"] = round(res["mb"], 2)
    if log and res["ficheros"]:
        log("Retencion: %d ficheros borrados (%.2f MB) de mas de %d dias."
            % (res["ficheros"], res["mb"], dias))
    return res


# ---------------------------------------------------------------- archivado
def _sanear(texto):
    """Mismo saneado que `sanitize()` de la calculadora, para que coincidan."""
    t = re.sub(r'[\\/:*?"<>|]', "_", str(texto or "")).strip()
    return re.sub(r"[. ]+$", "", t)


def _normalizar(texto):
    """Para casar nombres de cliente: mayusculas y solo alfanumericos."""
    return re.sub(r"[^A-Z0-9]", "", str(texto or "").upper())


def resolver_cliente(compartida, nombre_plano):
    """Nombre del cliente segun la BD compartida. -> (nombre_carpeta, codigo).

    Replica la busqueda de `autoFill()`: primero coincidencia exacta de nombre o
    codigo, luego por subcadena en cualquiera de los dos sentidos. Si no se
    encuentra, se usa el texto del plano tal cual.
    """
    crudo = _sanear(nombre_plano) or "CUSTOMER"
    p = os.path.join(str(compartida or ""), "ISC_V4_DATA.json")
    if not os.path.isfile(p):
        return crudo, None
    try:
        with open(p, encoding="utf-8") as f:
            datos = json.load(f)
        clientes = ((datos.get("dbs") or {}).get("customers")) or []
    except Exception:
        return crudo, None

    cn = _normalizar(nombre_plano)
    if not cn:
        return crudo, None
    for c in clientes:
        if _normalizar(c.get("name")) == cn or _normalizar(c.get("code")) == cn:
            return _sanear(c.get("name")) or crudo, c.get("code")
    for c in clientes:
        n = _normalizar(c.get("name"))
        if n and (cn in n or n in cn):
            return _sanear(c.get("name")) or crudo, c.get("code")
    return crudo, None


def _carpeta_quotes(compartida):
    """QUOTES dentro de la carpeta compartida, con las variantes que acepta la
    calculadora. Se crea si no existe."""
    raiz = str(compartida)
    for nm in ("QUOTES", "Quotes", "quotes"):
        d = os.path.join(raiz, nm)
        if os.path.isdir(d):
            return d
    d = os.path.join(raiz, "QUOTES")
    os.makedirs(d, exist_ok=True)
    return d


MAX_PN = 60          # la carpeta compartida suele colgar de OneDrive, y
MAX_REV = 20         # Windows corta la ruta entera en 260 caracteres


def nombre_fichero(spec, job):
    """`<PN>[__rev].spec.json`. Sin PN, el id del trabajo.

    Se sobrescribe a proposito: releer la misma pieza y revision es una lectura
    mejor de lo mismo, no un documento nuevo. La fecha queda en el sobre.

    PN y revision se recortan porque algunos planos traen designaciones muy
    largas y la carpeta compartida cuelga de OneDrive: entre la ruta del
    sincronizador, el nombre del cliente y "RFQ Info" se llega al limite de 260
    caracteres de Windows antes de lo que parece.
    """
    idf = spec.get("identificacion") or {}
    pn = _sanear(idf.get("numero_parte") or idf.get("numero_plano") or "")[:MAX_PN]
    rev = _sanear(idf.get("revision") or "")[:MAX_REV]
    if not pn:
        return "%s.spec.json" % job
    return "%s%s.spec.json" % (pn, ("__" + rev) if rev else "")


def sobre(spec, payload, job, archivo_origen, cfg, codigo_cliente=None,
          coste_usd=None):
    """El spec envuelto con lo que lo identifica.

    Las claves de este nivel son las columnas que tendria en PostgreSQL; `spec`
    es el JSONB. Por eso van planas y con nombres estables.
    """
    idf = spec.get("identificacion") or {}
    meta = spec.get("metadatos_extraccion") or {}
    return {
        "esquema": ESQUEMA,
        "archivado_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "job": job,
        "motor": payload.get("engine"),
        "modelo_router": (cfg or {}).get("model_router"),
        "modelo_extractor": (cfg or {}).get("model_extractor"),
        "fichero_origen": archivo_origen,
        "cliente": idf.get("cliente"),
        "cliente_codigo": codigo_cliente,
        "numero_parte": idf.get("numero_parte"),
        "numero_plano": idf.get("numero_plano"),
        "revision": idf.get("revision"),
        "tipo": payload.get("tipo"),
        "spring_type": payload.get("springType"),
        "confianza": meta.get("confianza_general"),
        "coste_usd": round(coste_usd, 5) if coste_usd is not None else None,
        # Los avisos viajan como {text, severity}; en el sobre se guarda el
        # texto, que es lo unico que tiene sentido revisar meses despues.
        "avisos": [w if isinstance(w, str) else str((w or {}).get("text", ""))
                   for w in (payload.get("warnings") or [])],
        "spec": spec,
    }


def archivar(compartida, spec, payload, job, archivo_origen, cfg,
             coste_usd=None, log=None):
    """Guarda el spec junto al plano. -> ruta escrita, o None si no aplica.

    Nunca lanza: que falle el archivado no puede tumbar una lectura que ya se
    ha pagado.
    """
    if not compartida or not os.path.isdir(str(compartida)):
        return None
    try:
        idf = spec.get("identificacion") or {}
        carpeta, codigo = resolver_cliente(compartida, idf.get("cliente"))
        destino = os.path.join(_carpeta_quotes(compartida), carpeta, "RFQ Info")
        os.makedirs(destino, exist_ok=True)
        ruta = os.path.join(destino, nombre_fichero(spec, job))
        datos = sobre(spec, payload, job, archivo_origen, cfg, codigo, coste_usd)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(datos, f, indent=2, ensure_ascii=False)
        os.replace(tmp, ruta)
        if log:
            log("Spec archivado en %s" % ruta)
        return ruta
    except Exception as e:
        if log:
            log("No se pudo archivar el spec (%s). La lectura no se ve afectada." % e)
        return None
