"""COT-74 [Código · Config] Formato y carga de las directrices de factibilidad.

Propósito
---------
Definir **dónde y en qué formato** viven las directrices de la planta (rangos
fabricables, materiales soportados, tipos de resorte, tolerancia mínima) para
que el motor de COT-75 las lea **sin modificar código**. Cambiar un rango es
editar un archivo de datos, no tocar Python.

Alcance
-------
* **Sí hace:** localizar la fuente, leerla, validar su forma y exponerla como
  un objeto ``Reglas`` con las consultas que necesita el motor.
* **NO hace:** evaluar resortes (eso es ``motor_factibilidad``, COT-75) ni
  decidir los valores: los rangos vigentes viven en el archivo de datos y los
  mantiene COT-73 con las directrices de la planta.

Fuente de las reglas
--------------------
Hoy: ``reglas/factibilidad.json`` (JSON de librería estándar, versionado en
git, con historial de quién cambió qué rango y cuándo). La ruta se mueve con
``config.REGLAS_FACTIBILIDAD``.

Mañana: si el PM necesita editarlas desde la aplicación, se implementa una
``FuenteTabla(conexion)`` con el mismo método ``leer()`` y se le pasa a
``cargar_reglas(fuente=...)``. El motor no se entera del cambio — por eso la
lectura está detrás de una fuente y no de un ``open()`` directo.

Función pública
---------------
``cargar_reglas(fuente=None, refrescar=False) -> Reglas``
"""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("cotizador.reglas")

# Ruta por defecto, relativa a la raíz del proyecto (la carpeta que contiene
# `src/`). Se resuelve así y no contra el cwd porque el proceso se lanza
# indistintamente desde `Programación/` o desde `src/`.
RUTA_POR_DEFECTO = "reglas/factibilidad.json"
_RAIZ = Path(__file__).resolve().parent.parent.parent

# Clave de los rangos/requeridos que aplican a todos los tipos de resorte.
COMUN = "_comun"


class ReglasInvalidasError(Exception):
    """El archivo (o la tabla) de directrices no tiene la forma esperada."""


# --------------------------------------------------------------------------- #
# Fuentes
# --------------------------------------------------------------------------- #

class FuenteReglas:
    """Interfaz de una fuente de directrices.

    Implementarla es lo único que hace falta para mover las reglas a una
    tabla: ``leer()`` devuelve el mismo dict que hoy trae el JSON, e ``id()``
    devuelve una cadena que cambia cuando cambian los datos (para la caché).
    """

    def id(self) -> str:  # pragma: no cover - interfaz
        raise NotImplementedError

    def leer(self) -> dict:  # pragma: no cover - interfaz
        raise NotImplementedError


class FuenteArchivo(FuenteReglas):
    """Lee las directrices de un archivo JSON en disco."""

    def __init__(self, ruta: Optional[str] = None) -> None:
        self.ruta = _resolver_ruta(ruta)

    def id(self) -> str:
        try:
            marca = self.ruta.stat().st_mtime_ns
        except OSError:
            marca = 0
        return f"archivo:{self.ruta}:{marca}"

    def leer(self) -> dict:
        try:
            with open(self.ruta, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError as error:
            raise ReglasInvalidasError(
                f"No se encontró el archivo de directrices: {self.ruta}. "
                "Revisa config.REGLAS_FACTIBILIDAD."
            ) from error
        except json.JSONDecodeError as error:
            raise ReglasInvalidasError(
                f"El archivo de directrices no es JSON válido ({self.ruta}): {error}"
            ) from error


def _resolver_ruta(ruta: Optional[str]) -> Path:
    """Ruta efectiva del archivo: argumento > config > valor por defecto."""
    if ruta is None:
        try:
            import app.core.config as config
            ruta = getattr(config, "REGLAS_FACTIBILIDAD", None) or RUTA_POR_DEFECTO
        except Exception:  # config no disponible (pruebas, scripts sueltos)
            ruta = RUTA_POR_DEFECTO
    candidata = Path(ruta)
    return candidata if candidata.is_absolute() else (_RAIZ / candidata)


# --------------------------------------------------------------------------- #
# Reglas
# --------------------------------------------------------------------------- #

class Reglas:
    """Directrices ya validadas, con las consultas que necesita el motor."""

    def __init__(self, datos: dict) -> None:
        _validar(datos)
        self._datos = datos
        self.version: str = datos["version"]
        self.actualizado: Optional[str] = datos.get("actualizado")
        self.fuente: Optional[str] = datos.get("fuente")
        self.tolerancia_minima_mm: Optional[float] = _opt_float(
            datos.get("tolerancia_minima_mm"))
        self.confianza_minima: Optional[float] = _opt_float(
            datos.get("confianza_minima"))
        self.tipos_fabricables: Tuple[str, ...] = tuple(
            _normalizar(t) for t in datos["tipos_fabricables"])
        self._puntuacion: dict = datos.get("puntuacion") or {}
        self.umbral_factible: Optional[float] = _opt_float(
            self._puntuacion.get("umbral_factible"))
        self._materiales: Tuple[dict, ...] = tuple(datos["materiales_soportados"])
        self._indice_materiales = _indexar_materiales(self._materiales)
        self._familias = _indexar_familias(datos.get("familias_genericas") or ())

    # -- tipos ------------------------------------------------------------- #

    def tipo_fabricable(self, tipo: Optional[str]) -> bool:
        return _normalizar(tipo or "") in self.tipos_fabricables

    # -- materiales -------------------------------------------------------- #

    @property
    def materiales(self) -> Tuple[str, ...]:
        """Nombres canónicos de los materiales soportados."""
        return tuple(m["nombre"] for m in self._materiales)

    def material_soportado(self, texto: Optional[str]) -> Optional[str]:
        """Nombre canónico del material, o ``None`` si no está soportado.

        El material llega como texto libre del plano ("MUSIC WIRE ASTM A228",
        "ac. inox 302"), así que se compara contra el nombre canónico y contra
        los alias declarados en el archivo, ignorando acentos y mayúsculas.
        """
        if not texto or not str(texto).strip():
            return None
        objetivo = _normalizar(texto)
        for patron, nombre in self._indice_materiales:
            if patron.search(objetivo):
                return nombre
        return None

    def material_generico(self, texto: Optional[str]) -> Optional[str]:
        """Código del material cuando el plano nombra la FAMILIA, no el material.

        "Spring wire" no es un material: es la familia entera. No resolvía a
        ningún código, y sin código no hay módulo de cortante —así que el
        lector no puede deducir las espiras desde la rigidez ni comprobar las
        del plano— ni precio por libra. La oferta acababa en revisión por un
        material que en la práctica ya está decidido: en ISC, Music Wire.

        Es el ÚLTIMO recurso, y por eso vive aparte del índice de alias en vez
        de dentro de él. Metido ahí, "spring wire" (once letras) le ganaría por
        longitud a "hard drawn" (diez) y un plano que dice "hard drawn spring
        wire" se cotizaría como Music Wire. Aquí el orden lo decide el archivo,
        no la casualidad de cuántas letras tiene cada alias: gana la primera
        que case, y las concretas van escritas primero.
        """
        if not texto or not str(texto).strip():
            return None
        objetivo = _normalizar(texto)
        for patron, codigo in self._familias:
            if patron.search(objetivo):
                return codigo
        return None

    def nombre_por_codigo(self, codigo: Optional[str]) -> Optional[str]:
        """El nombre canónico del material a partir de su código.

        Hace falta porque `material_generico` devuelve el CÓDIGO de la familia
        ("MW") y el resto del dictamen trabaja con el nombre canónico ("Music
        Wire (ASTM A228)"): sin esta vuelta, un material resuelto por familia
        no podría comprobarse contra su banda de calibres.
        """
        if not codigo:
            return None
        for material in self._materiales:
            if material.get("codigo") == codigo:
                return material.get("nombre")
        return None

    def codigo_material(self, texto: Optional[str]) -> Optional[str]:
        """Código de catálogo del material, a partir del texto libre del RFQ.

        El correo y el plano hablan como habla un comprador —"ASTM A228 music
        wire, zinc plated finish"—, y el catálogo de costeo guarda códigos
        ("MW"). Sin esta traducción el costeo buscaba en ``materiales`` una
        fila cuyo código fuera esa frase entera, nunca la encontraba, y daba
        por faltante un material que sí está en la planta.

        Se apoya en el mismo índice de alias que ``material_soportado``, así
        que declarar un alias nuevo en ``reglas/factibilidad.json`` arregla a
        la vez el dictamen y el precio.
        """
        nombre = self.material_soportado(texto)
        if nombre is None:
            # Ningún material concreto casó. Puede que el plano sólo nombre la
            # familia ("spring wire"), que sí se sabe cotizar.
            return self.material_generico(texto)
        for material in self._materiales:
            if material["nombre"] == nombre:
                return material.get("codigo")
        return None

    def rango_alambre_material(self, nombre: Optional[str]) -> Optional[dict]:
        """Calibres en los que se consigue ese material, si el archivo lo declara.

        Es distinto de lo que la máquina puede enrollar: aquí manda el
        proveedor de alambre. La envolvente fabricable real es la
        intersección de ambos.
        """
        if not nombre:
            return None
        for material in self._materiales:
            if material["nombre"] == nombre:
                return material.get("rango_alambre_mm")
        return None

    # -- rangos ------------------------------------------------------------ #

    def rangos(self, tipo: Optional[str]) -> Dict[str, dict]:
        """Rangos aplicables a un tipo: los comunes, pisados por los del tipo.

        La fusión es **por clave dentro de cada campo**, no por campo entero:
        un tipo puede cambiarle sólo la penalización a un rango y heredar sus
        límites. Es lo que pide el modelo de ISC, que usa los mismos umbrales
        de índice de resorte para los tres tipos pero castiga distinto
        (compresión 26/20, torsión y extensión 24/18).
        """
        todos = self._datos.get("rangos", {})
        comunes = todos.get(COMUN, {})
        del_tipo = todos.get(_normalizar(tipo or ""), {})
        combinados = {campo: dict(limites) for campo, limites in comunes.items()}
        for campo, limites in del_tipo.items():
            combinados.setdefault(campo, {}).update(limites)
        return combinados

    def rango(self, tipo: Optional[str], campo: str) -> Optional[dict]:
        return self.rangos(tipo).get(campo)

    def requeridos(self, tipo: Optional[str]) -> Tuple[str, ...]:
        """Campos sin los cuales no se puede dictaminar (comunes + del tipo)."""
        todos = self._datos.get("requeridos", {})
        campos: List[str] = list(todos.get(COMUN, []))
        for campo in todos.get(_normalizar(tipo or ""), []):
            if campo not in campos:
                campos.append(campo)
        return tuple(campos)

    # -- puntuación -------------------------------------------------------- #

    @property
    def puntua(self) -> bool:
        """``True`` si las directrices traen el modelo de puntuación.

        Es opcional: sin él, el motor dictamina sólo por presencia de motivos.
        """
        return bool(self._puntuacion) and self.umbral_factible is not None

    def penalizacion(self, codigo: str, limites: Optional[dict] = None,
                     lado: Optional[str] = None) -> float:
        """Puntos que resta un hallazgo.

        Tres niveles, de más específico a más general:

        1. La tabla del propio rango (``penalizacion``), que es donde viven
           los números de ISC por tipo de resorte.
        2. Dentro de ella, el **lado** violado: ISC no cobra lo mismo un
           índice por debajo del mínimo (C<4, 26 puntos en compresión) que
           por encima del máximo (C>15, 20 puntos). Un valor puede declararse
           como número, y entonces aplica a los dos lados, o como
           ``{"min": …, "max": …}``.
        3. La tabla general de ``puntuacion.penalizaciones``.

        Lo que nadie declara no resta.
        """
        if limites:
            propia = limites.get("penalizacion") or {}
            if codigo in propia:
                return _puntos(propia[codigo], lado)
        general = self._puntuacion.get("penalizaciones") or {}
        return _puntos(general.get(codigo, 0), lado)

    def banda(self, score) -> Optional[str]:
        """Etiqueta de la banda en la que cae un score (vocabulario de ISC)."""
        if score is None:
            return None
        for tramo in self._puntuacion.get("bandas") or []:
            if float(score) >= float(tramo["desde"]):
                return tramo["banda"]
        return None

    def to_dict(self) -> dict:
        """Copia de los datos crudos (para log/diagnóstico)."""
        return json.loads(json.dumps(self._datos))


# --------------------------------------------------------------------------- #
# Validación de forma
# --------------------------------------------------------------------------- #

def _validar(datos) -> None:
    """Falla temprano y con nombre propio si las directrices están mal formadas.

    Un rango invertido o un material sin nombre no revienta al cargar, pero
    hace que el motor dictamine mal en silencio: es justo lo que hay que cazar
    aquí y no en producción.
    """
    if not isinstance(datos, dict):
        raise ReglasInvalidasError("Las directrices deben ser un objeto JSON.")
    _rechazar_desconocidas("directrices", datos, CLAVES_RAIZ)
    _validar_familias(datos)

    version = datos.get("version")
    if not isinstance(version, str) or not version.strip():
        raise ReglasInvalidasError("Falta 'version' (cadena no vacía).")

    tipos = datos.get("tipos_fabricables")
    if not isinstance(tipos, list) or not tipos:
        raise ReglasInvalidasError("'tipos_fabricables' debe ser una lista no vacía.")
    if not all(isinstance(t, str) and t.strip() for t in tipos):
        raise ReglasInvalidasError("'tipos_fabricables' sólo admite cadenas.")

    materiales = datos.get("materiales_soportados")
    if not isinstance(materiales, list) or not materiales:
        raise ReglasInvalidasError(
            "'materiales_soportados' debe ser una lista no vacía.")
    for material in materiales:
        if not isinstance(material, dict) or not material.get("nombre"):
            raise ReglasInvalidasError(
                "Cada material necesita al menos {'nombre': ...}.")
        alias = material.get("alias", [])
        if not isinstance(alias, list) or not all(isinstance(a, str) for a in alias):
            raise ReglasInvalidasError(
                f"'alias' de {material['nombre']!r} debe ser una lista de cadenas.")
        _rechazar_desconocidas(f"material {material['nombre']}", material, CLAVES_MATERIAL)
        if "rango_alambre_mm" in material:
            _validar_limites(f"material {material['nombre']}", material["rango_alambre_mm"])

    rangos = datos.get("rangos", {})
    if not isinstance(rangos, dict):
        raise ReglasInvalidasError("'rangos' debe ser un objeto.")
    for tipo, campos in rangos.items():
        if not isinstance(campos, dict):
            raise ReglasInvalidasError(f"'rangos.{tipo}' debe ser un objeto.")
        for campo, limites in campos.items():
            _validar_limites(f"{tipo}.{campo}", limites)

    requeridos = datos.get("requeridos", {})
    if not isinstance(requeridos, dict):
        raise ReglasInvalidasError("'requeridos' debe ser un objeto.")
    for tipo, campos in requeridos.items():
        if not isinstance(campos, list) or not all(isinstance(c, str) for c in campos):
            raise ReglasInvalidasError(
                f"'requeridos.{tipo}' debe ser una lista de nombres de campo.")

    _validar_puntuacion(datos.get("puntuacion"))

    for clave in ("tolerancia_minima_mm", "confianza_minima"):
        valor = datos.get(clave)
        if valor is not None and not _es_numero(valor):
            raise ReglasInvalidasError(f"'{clave}' debe ser numérico.")
    confianza = datos.get("confianza_minima")
    if confianza is not None and not 0 <= float(confianza) <= 1:
        raise ReglasInvalidasError("'confianza_minima' debe estar entre 0 y 1.")


def _validar_puntuacion(puntuacion) -> None:
    """Valida el modelo de puntuación, que es opcional.

    Sin él el motor dictamina por presencia de motivos; con él, suma
    penalizaciones y compara contra un umbral. Que sea opcional permite
    apagarlo editando el archivo, sin tocar código.
    """
    if puntuacion is None:
        return
    if not isinstance(puntuacion, dict):
        raise ReglasInvalidasError("'puntuacion' debe ser un objeto.")
    _rechazar_desconocidas("puntuacion", puntuacion, CLAVES_PUNTUACION)


    umbral = puntuacion.get("umbral_factible")
    if umbral is None:
        raise ReglasInvalidasError("'puntuacion' necesita 'umbral_factible'.")
    if not _es_numero(umbral) or not 0 <= float(umbral) <= 100:
        raise ReglasInvalidasError(
            "'puntuacion.umbral_factible' debe ser un número de 0 a 100.")

    bandas = puntuacion.get("bandas") or []
    if not isinstance(bandas, list) or not bandas:
        raise ReglasInvalidasError("'puntuacion.bandas' debe ser una lista no vacía.")
    anterior = None
    for tramo in bandas:
        if not isinstance(tramo, dict) or "desde" not in tramo or not tramo.get("banda"):
            raise ReglasInvalidasError(
                "Cada banda necesita {'desde': número, 'banda': texto}.")
        if not _es_numero(tramo["desde"]) or not 0 <= float(tramo["desde"]) <= 100:
            raise ReglasInvalidasError("'desde' de una banda debe ir de 0 a 100.")
        # De mayor a menor: `banda()` devuelve la primera que alcanza el score.
        if anterior is not None and float(tramo["desde"]) >= anterior:
            raise ReglasInvalidasError(
                "'puntuacion.bandas' debe ir de mayor a menor 'desde'.")
        anterior = float(tramo["desde"])
    if anterior != 0:
        raise ReglasInvalidasError(
            "La última banda debe arrancar en 0; si no, hay scores sin banda.")

    _validar_penalizaciones("puntuacion.penalizaciones",
                            puntuacion.get("penalizaciones") or {})


LADOS = ("min", "max")


def _puntos(valor, lado: Optional[str]) -> float:
    """Resuelve una penalización declarada como número o por lado.

    Si viene por lado y el hallazgo no tiene lado (un material ausente no está
    "por debajo" de nada), se toma la mayor de las declaradas. Es una captura
    equivocada, y ante la duda conviene que penalice de más y se note, no que
    valga 0 y desaparezca del score sin que nadie se entere.
    """
    if isinstance(valor, dict):
        if lado is not None:
            return float(valor.get(lado, 0))
        return max((float(v) for v in valor.values()), default=0.0)
    return float(valor or 0)


def _validar_penalizaciones(donde: str, tabla) -> None:
    if not isinstance(tabla, dict):
        raise ReglasInvalidasError(f"'{donde}' debe ser un objeto código -> puntos.")
    for codigo, puntos in tabla.items():
        if not isinstance(codigo, str):
            raise ReglasInvalidasError(f"'{donde}': los códigos deben ser texto.")
        # Un número aplica a los dos lados; un objeto {min, max} distingue.
        if isinstance(puntos, dict):
            if not puntos or any(lado not in LADOS for lado in puntos):
                raise ReglasInvalidasError(
                    f"'{donde}.{codigo}' por lado sólo admite {' y '.join(LADOS)}.")
            valores = list(puntos.values())
        elif _es_numero(puntos):
            valores = [puntos]
        else:
            raise ReglasInvalidasError(
                f"'{donde}.{codigo}' debe ser un número o {{min, max}}.")
        for valor in valores:
            if not _es_numero(valor):
                raise ReglasInvalidasError(
                    f"'{donde}.{codigo}' debe ser un número de puntos.")
            if float(valor) < 0:
                raise ReglasInvalidasError(
                    f"'{donde}.{codigo}' no puede ser negativo.")


LIMITES = ("min", "max", "preferido_min", "preferido_max")

# Claves admitidas dentro de un rango y dentro de un material. Se validan de
# forma estricta: este archivo lo edita gente, y una clave mal escrita
# (`preferido_maximo` por `preferido_max`) se ignoraría en silencio dejando el
# límite sin efecto. Mejor que reviente al cargar.
CLAVES_RANGO = LIMITES + ("nota", "penalizacion")
CLAVES_MATERIAL = ("nombre", "codigo", "alias", "rango_alambre_mm")
CLAVES_FAMILIA = ("alias", "codigo", "nota")
CLAVES_RAIZ = (
    "version", "actualizado", "fuente", "tipos_fabricables",
    "tolerancia_minima_mm", "confianza_minima", "puntuacion",
    "materiales_soportados", "familias_genericas", "rangos", "requeridos",
    # Bloques de documentación: el motor no los lee, pero viajan con el
    # archivo para que quien edite un rango sepa de dónde salió.
    "pendientes", "referencia",
)
CLAVES_PUNTUACION = ("umbral_factible", "bandas", "penalizaciones", "nota", "origen")


def _rechazar_desconocidas(donde: str, objeto: dict, admitidas) -> None:
    sobrantes = sorted(set(objeto) - set(admitidas))
    if sobrantes:
        raise ReglasInvalidasError(
            f"'{donde}': clave(s) no reconocida(s) {', '.join(sobrantes)}. "
            f"Admitidas: {', '.join(admitidas)}.")



def _validar_familias(datos) -> None:
    """Las familias genéricas, si las hay, bien formadas y apuntando a algo.

    Una familia con un código que no existe en `materiales_soportados` es el
    fallo peor de todos: resuelve, así que nadie ve un material faltante, y
    luego el catálogo no encuentra la fila. El precio sale sin materia prima y
    la oferta se va con él. Se caza aquí, al cargar.
    """
    familias = datos.get("familias_genericas")
    if familias is None:
        return
    if not isinstance(familias, list):
        raise ReglasInvalidasError(
            "'familias_genericas' debe ser una lista, en orden: se prueba de "
            "arriba abajo y gana la primera que case.")

    codigos = {m.get("codigo") for m in datos.get("materiales_soportados") or []}
    vistos = set()
    for i, familia in enumerate(familias):
        donde = f"familias_genericas[{i}]"
        if not isinstance(familia, dict):
            raise ReglasInvalidasError(f"{donde} debe ser un objeto.")
        _rechazar_desconocidas(donde, familia, CLAVES_FAMILIA)

        alias = familia.get("alias")
        if not isinstance(alias, str) or not alias.strip():
            raise ReglasInvalidasError(f"{donde} necesita un 'alias' con texto.")
        clave = _normalizar(alias)
        if clave in vistos:
            raise ReglasInvalidasError(
                f"{donde}: el alias '{alias}' está dos veces. La segunda no se "
                "alcanzaría nunca, porque gana la primera que case.")
        vistos.add(clave)

        codigo = familia.get("codigo")
        if not isinstance(codigo, str) or not codigo.strip():
            raise ReglasInvalidasError(f"{donde} necesita un 'codigo' con texto.")
        if codigo not in codigos:
            raise ReglasInvalidasError(
                f"{donde}: el código '{codigo}' no es ninguno de los "
                f"materiales_soportados. Una familia que resuelve a un código "
                f"inexistente deja el costeo sin materia prima y nadie lo ve.")


def _validar_limites(donde: str, limites) -> None:
    """Valida un rango.

    Un rango puede declarar hasta dos bandas: la **fabricable** (``min`` /
    ``max``, fuera de ella no se puede hacer) y la **preferida**
    (``preferido_min`` / ``preferido_max``, dentro de ella es rutina). Entre
    una y otra el resorte se puede fabricar pero no sin que alguien lo mire —
    p. ej. un alambre de 8 mm: por debajo del máximo del negocio, pero fuera
    de la envolvente de las máquinas con capacidad declarada.

    ``nota`` es texto libre que el motor copia al motivo, para que el PM lea
    la razón del límite y no sólo el número.
    """
    if not isinstance(limites, dict):
        raise ReglasInvalidasError(f"'rangos.{donde}' debe ser un objeto de límites.")
    _rechazar_desconocidas(f"rangos.{donde}", limites, CLAVES_RANGO)
    # Un bloque de tipo puede traer sólo penalizaciones y heredar los límites
    # de `_comun` — así ISC cambia el castigo del índice de resorte por tipo
    # sin repetir los umbrales. Lo que no vale es un rango vacío.
    if not any(clave in limites for clave in LIMITES) and "penalizacion" not in limites:
        raise ReglasInvalidasError(
            f"'rangos.{donde}' no declara ningún límite ({', '.join(LIMITES)}) "
            "ni penalizaciones que heredar.")
    for clave in LIMITES:
        if clave in limites and not _es_numero(limites[clave]):
            raise ReglasInvalidasError(f"'rangos.{donde}.{clave}' debe ser numérico.")
    if "nota" in limites and not isinstance(limites["nota"], str):
        raise ReglasInvalidasError(f"'rangos.{donde}.nota' debe ser texto.")
    if "penalizacion" in limites:
        _validar_penalizaciones(f"rangos.{donde}.penalizacion", limites["penalizacion"])

    for menor, mayor in (("min", "max"), ("preferido_min", "preferido_max")):
        if menor in limites and mayor in limites:
            if float(limites[menor]) > float(limites[mayor]):
                raise ReglasInvalidasError(
                    f"'rangos.{donde}' tiene {menor} mayor que {mayor}.")

    # La banda preferida vive dentro de la fabricable; al revés no significa nada.
    if "min" in limites and "preferido_min" in limites:
        if float(limites["preferido_min"]) < float(limites["min"]):
            raise ReglasInvalidasError(
                f"'rangos.{donde}': preferido_min queda por debajo de min.")
    if "max" in limites and "preferido_max" in limites:
        if float(limites["preferido_max"]) > float(limites["max"]):
            raise ReglasInvalidasError(
                f"'rangos.{donde}': preferido_max queda por encima de max.")


def _es_numero(valor) -> bool:
    return isinstance(valor, (int, float)) and not isinstance(valor, bool)


def _opt_float(valor) -> Optional[float]:
    return None if valor is None else float(valor)


# --------------------------------------------------------------------------- #
# Normalización de texto
# --------------------------------------------------------------------------- #

_NO_ALFANUM = re.compile(r"[^a-z0-9]+")


def _normalizar(texto: str) -> str:
    """Minúsculas, sin acentos y con la puntuación colapsada a espacios."""
    descompuesto = unicodedata.normalize("NFKD", str(texto))
    sin_acentos = "".join(c for c in descompuesto if not unicodedata.combining(c))
    return _NO_ALFANUM.sub(" ", sin_acentos.lower()).strip()


def _indexar_familias(familias) -> Tuple[Tuple[re.Pattern, str], ...]:
    """Las familias genéricas, EN EL ORDEN DEL ARCHIVO.

    A diferencia de `_indexar_materiales`, aquí no se ordena por longitud: el
    orden es la regla. Quien edite el archivo tiene que poder poner lo concreto
    antes que lo general y que eso se respete.
    """
    indice = []
    for familia in familias:
        patron = _normalizar(familia.get("alias", ""))
        if not patron:
            continue
        indice.append(
            (re.compile(rf"(?<![a-z0-9]){re.escape(patron)}(?![a-z0-9])"),
             familia.get("codigo")))
    return tuple(indice)


def _indexar_materiales(materiales) -> Tuple[Tuple[re.Pattern, str], ...]:
    """Precompila un patrón por alias, anclado a límites alfanuméricos.

    Sin el anclaje, el alias "302" casaría dentro de "1302" y cualquier norma
    con esos dígitos daría un material soportado que nadie declaró.
    """
    indice = []
    for material in materiales:
        nombre = material["nombre"]
        for etiqueta in [nombre] + list(material.get("alias", [])):
            patron = _normalizar(etiqueta)
            if not patron:
                continue
            indice.append(
                (re.compile(rf"(?<![a-z0-9]){re.escape(patron)}(?![a-z0-9])"), nombre))
    # Alias más largos primero: "aisi 316" debe ganarle a "316".
    indice.sort(key=lambda par: len(par[0].pattern), reverse=True)
    return tuple(indice)


# --------------------------------------------------------------------------- #
# Carga con caché
# --------------------------------------------------------------------------- #

_CACHE: Dict[str, Reglas] = {}


def cargar_reglas(fuente: Optional[FuenteReglas] = None,
                  refrescar: bool = False) -> Reglas:
    """Devuelve las directrices vigentes.

    Args:
        fuente: de dónde leerlas. Por defecto, el archivo JSON del proyecto.
            Aquí entra una futura ``FuenteTabla`` sin tocar el motor.
        refrescar: ignora la caché y vuelve a leer.

    El resultado se cachea por fuente: el motor se llama una vez por RFQ y no
    tiene por qué releer el archivo cada vez. La clave incluye la marca de
    tiempo del archivo, así que editarlo invalida la caché solo.
    """
    fuente = fuente or FuenteArchivo()
    clave = fuente.id()
    if refrescar:
        _CACHE.pop(clave, None)
    if clave not in _CACHE:
        reglas = Reglas(fuente.leer())
        log.info("Directrices de factibilidad cargadas (versión %s) desde %s.",
                 reglas.version, clave)
        _CACHE[clave] = reglas
    return _CACHE[clave]


def limpiar_cache() -> None:
    """Vacía la caché de reglas (útil en pruebas y tras editar el archivo)."""
    _CACHE.clear()
