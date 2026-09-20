"""
Interpreta el JSON devuelto por el modelo de visión y AÍSLA las
variables físicas del resorte: los datos necesarios para la cotización en el
entorno de ejecución. Los datos se pueden entregar como MATRIZ (a_matriz).

No depende de ningún SDK externo (solo librería estándar): se puede testear
con datos de ejemplo sin llamar a la API.
"""
import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import List, Optional

log = logging.getLogger("cotizador.extractor")

# Tipos válidos de resorte
TIPOS_VALIDOS = {"compresion", "torsion", "extension", "desconocido"}

# Campos numéricos esperados (todos en mm, grados o N/mm según el caso)
CAMPOS_NUMERICOS = (
    "diametro_alambre_mm", "diametro_exterior_mm", "diametro_interior_mm",
    "diametro_medio_mm", "longitud_libre_mm", "longitud_cuerpo_mm",
    "numero_espiras_totales", "numero_espiras_activas", "paso_mm",
    "angulo_brazos_grados", "longitud_gancho_mm", "constante_resorte_N_mm",
    "cantidad",
)
CAMPOS_TEXTO = (
    "num_parte", "material", "norma_material", "sentido_enrollado",
    "tipo_extremos", "acabado", "tolerancias", "unidad", "notas",
)

# Variables mínimas indispensables para poder cotizar.
# Sin ellas, la cotización no es viable y se marca listo_para_cotizar=False.
CAMPOS_REQUERIDOS_COTIZACION = (
    "tipo_resorte", "material", "diametro_alambre_mm", "cantidad",
)

# Orden de las filas de la matriz de entrega
ORDEN_MATRIZ = (
    "num_parte", "tipo_resorte", "material", "norma_material",
    "diametro_alambre_mm", "diametro_exterior_mm", "diametro_interior_mm",
    "diametro_medio_mm", "longitud_libre_mm", "longitud_cuerpo_mm",
    "numero_espiras_totales", "numero_espiras_activas", "paso_mm",
    "sentido_enrollado", "tipo_extremos", "angulo_brazos_grados",
    "longitud_gancho_mm", "constante_resorte_N_mm", "acabado",
    "tolerancias", "cantidad", "unidad", "normas", "notas", "confianza",
)

# Unidad de cada variable (vacío = adimensional/textual)
UNIDADES = {
    "diametro_alambre_mm": "mm", "diametro_exterior_mm": "mm",
    "diametro_interior_mm": "mm", "diametro_medio_mm": "mm",
    "longitud_libre_mm": "mm", "longitud_cuerpo_mm": "mm",
    "numero_espiras_totales": "espiras", "numero_espiras_activas": "espiras",
    "paso_mm": "mm", "angulo_brazos_grados": "grados",
    "longitud_gancho_mm": "mm", "constante_resorte_N_mm": "N/mm",
    "cantidad": "pzas", "confianza": "0-1",
}

# Descripción legible de cada variable
DESCRIPCIONES = {
    "tipo_resorte": "Tipo de resorte (compresión/torsión/extensión)",
    "material": "Material del alambre",
    "norma_material": "Norma del material",
    "diametro_alambre_mm": "Diámetro del alambre (d)",
    "diametro_exterior_mm": "Diámetro exterior (OD)",
    "diametro_interior_mm": "Diámetro interior (ID)",
    "diametro_medio_mm": "Diámetro medio (Dm)",
    "longitud_libre_mm": "Longitud libre, sin carga (L0)",
    "longitud_cuerpo_mm": "Longitud del cuerpo",
    "numero_espiras_totales": "Número total de espiras",
    "numero_espiras_activas": "Número de espiras activas (Na)",
    "paso_mm": "Paso entre espiras (p)",
    "sentido_enrollado": "Sentido de enrollado (derecha/izquierda)",
    "tipo_extremos": "Tipo de extremos / terminales",
    "angulo_brazos_grados": "Ángulo entre brazos (torsión)",
    "longitud_gancho_mm": "Longitud del gancho (extensión)",
    "constante_resorte_N_mm": "Constante del resorte / rigidez (k)",
    "acabado": "Acabado o recubrimiento",
    "tolerancias": "Tolerancias indicadas",
    "cantidad": "Cantidad solicitada",
    "unidad": "Unidad de la cantidad",
    "normas": "Normas aplicables",
    "notas": "Notas adicionales",
    "confianza": "Confianza del modelo de visión",
}


class ExtraccionError(Exception):
    """No se pudo localizar/parsear un JSON válido en la respuesta del modelo."""


@dataclass
class ResorteCotizacion:
    """Variables físicas del resorte aisladas para la cotización."""
    # num_parte no es una variable física: es el identificador comercial
    # de la pieza. Vive aquí porque el plano suele ser la única fuente que
    # lo trae, y el flujo lo necesita para dar de alta el RFQ (COT-61).
    num_parte: Optional[str] = None
    tipo_resorte: str = "desconocido"
    material: Optional[str] = None
    norma_material: Optional[str] = None
    diametro_alambre_mm: Optional[float] = None
    diametro_exterior_mm: Optional[float] = None
    diametro_interior_mm: Optional[float] = None
    diametro_medio_mm: Optional[float] = None
    longitud_libre_mm: Optional[float] = None
    longitud_cuerpo_mm: Optional[float] = None
    numero_espiras_totales: Optional[float] = None
    numero_espiras_activas: Optional[float] = None
    paso_mm: Optional[float] = None
    sentido_enrollado: Optional[str] = None
    tipo_extremos: Optional[str] = None
    angulo_brazos_grados: Optional[float] = None
    longitud_gancho_mm: Optional[float] = None
    constante_resorte_N_mm: Optional[float] = None
    acabado: Optional[str] = None
    tolerancias: Optional[str] = None
    cantidad: Optional[float] = None
    unidad: Optional[str] = None
    normas: List[str] = field(default_factory=list)
    notas: Optional[str] = None
    confianza: float = 0.0
    advertencias: List[str] = field(default_factory=list)

    def faltantes(self) -> List[str]:
        """Campos requeridos para cotizar que vienen vacíos/nulos."""
        faltan = []
        for campo in CAMPOS_REQUERIDOS_COTIZACION:
            valor = getattr(self, campo)
            if valor is None or valor == "" or valor == "desconocido":
                faltan.append(campo)
        return faltan

    @property
    def listo_para_cotizar(self) -> bool:
        return not self.faltantes()

    def to_dict(self) -> dict:
        datos = asdict(self)
        datos["listo_para_cotizar"] = self.listo_para_cotizar
        datos["faltantes"] = self.faltantes()
        return datos

    def a_matriz(self, incluir_encabezado: bool = True) -> List[list]:
        """Entrega las variables del resorte como matriz (lista de filas)."""
        return _construir_matriz(self.to_dict(), incluir_encabezado)


# ============================================================================
# Localización y parseo del JSON
# ============================================================================
_BLOQUE_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


def extraer_json(texto):
    """
    Localiza y parsea el primer objeto JSON dentro del texto del modelo.
    Tolera: JSON puro, JSON dentro de ```json ... ```, o JSON con texto
    introductorio. Lanza ExtraccionError si no encuentra un objeto válido.
    """
    if not texto or not texto.strip():
        raise ExtraccionError("Respuesta vacía del modelo de visión.")

    # 1) Intento directo
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        pass

    # 2) Bloque con fences ```json ... ```
    m = _BLOQUE_FENCE.search(texto)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # 3) Recorte por llaves balanceadas (primer '{' hasta su cierre)
    fragmento = _recortar_objeto(texto)
    if fragmento:
        try:
            return json.loads(fragmento)
        except json.JSONDecodeError as error:
            raise ExtraccionError(f"JSON localizado pero inválido: {error}") from error

    raise ExtraccionError("No se encontró ningún objeto JSON en la respuesta.")


def _recortar_objeto(texto):
    """Devuelve el substring del primer objeto {...} balanceado, o None."""
    inicio = texto.find("{")
    if inicio == -1:
        return None
    profundidad = 0
    en_cadena = False
    escape = False
    for i in range(inicio, len(texto)):
        car = texto[i]
        if en_cadena:
            if escape:
                escape = False
            elif car == "\\":
                escape = True
            elif car == '"':
                en_cadena = False
            continue
        if car == '"':
            en_cadena = True
        elif car == "{":
            profundidad += 1
        elif car == "}":
            profundidad -= 1
            if profundidad == 0:
                return texto[inicio:i + 1]
    return None


# ============================================================================
# Normalización de valores
# ============================================================================
_NUM_RE = re.compile(r"[-+]?\d*[.,]?\d+")


def _a_float(valor):
    """
    Convierte a float tolerando strings con unidades o coma decimal:
    "12.5 mm" -> 12.5, "12,5" -> 12.5, 8 -> 8.0, None/"" -> None.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    if isinstance(valor, str):
        texto = valor.strip().replace(",", ".")
        m = _NUM_RE.search(texto)
        if m:
            try:
                return float(m.group(0))
            except ValueError:
                return None
    return None


def _a_texto(valor):
    """Normaliza a string limpio o None."""
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _normalizar_tipo(valor):
    """Mapea el tipo de resorte a uno de los valores válidos."""
    texto = (str(valor or "")).strip().lower()
    texto = (texto.replace("ó", "o").replace("é", "e")
                  .replace("í", "i").replace("á", "a").replace("ú", "u"))
    if "compres" in texto:
        return "compresion"
    if "tors" in texto:
        return "torsion"
    if "exten" in texto or "tracc" in texto:
        return "extension"
    return "desconocido"


def _a_lista(valor):
    """Normaliza a lista de strings."""
    if valor is None:
        return []
    if isinstance(valor, str):
        return [valor.strip()] if valor.strip() else []
    if isinstance(valor, (list, tuple)):
        return [str(v).strip() for v in valor if str(v).strip()]
    return [str(valor).strip()]


def _a_confianza(valor):
    """Confianza acotada a [0.0, 1.0]."""
    num = _a_float(valor)
    if num is None:
        return 0.0
    return max(0.0, min(1.0, num))


def normalizar(datos_crudos):
    """
    Aísla y normaliza las variables físicas a partir del dict crudo del modelo.
    Devuelve una instancia de ResorteCotizacion.
    """
    if not isinstance(datos_crudos, dict):
        raise ExtraccionError("El JSON del modelo no es un objeto.")

    resorte = ResorteCotizacion()
    resorte.tipo_resorte = _normalizar_tipo(datos_crudos.get("tipo_resorte"))

    for campo in CAMPOS_NUMERICOS:
        setattr(resorte, campo, _a_float(datos_crudos.get(campo)))

    for campo in CAMPOS_TEXTO:
        setattr(resorte, campo, _a_texto(datos_crudos.get(campo)))

    resorte.normas = _a_lista(datos_crudos.get("normas"))
    resorte.advertencias = _a_lista(datos_crudos.get("advertencias"))
    resorte.confianza = _a_confianza(datos_crudos.get("confianza"))

    # Deriva diámetro medio si faltó pero hay exterior y alambre
    if (resorte.diametro_medio_mm is None
            and resorte.diametro_exterior_mm is not None
            and resorte.diametro_alambre_mm is not None):
        resorte.diametro_medio_mm = round(
            resorte.diametro_exterior_mm - resorte.diametro_alambre_mm, 4)

    return resorte


# ============================================================================
# Entrega como MATRIZ
# ============================================================================
ENCABEZADO_MATRIZ = ["Variable", "Descripción", "Valor", "Unidad", "Obligatoria cotizar"]


def _construir_matriz(datos, incluir_encabezado=True) -> list[list]:
    """Construye la matriz (lista de filas) a partir del dict de datos."""
    filas = [list(ENCABEZADO_MATRIZ)] if incluir_encabezado else []
    for campo in ORDEN_MATRIZ:
        valor = datos.get(campo)
        if isinstance(valor, list):
            valor = ", ".join(str(v) for v in valor)
        filas.append([
            campo,
            DESCRIPCIONES.get(campo, ""),
            "" if valor is None else valor,
            UNIDADES.get(campo, ""),
            "Sí" if campo in CAMPOS_REQUERIDOS_COTIZACION else "No",
        ])
    return filas


def a_matriz(datos, incluir_encabezado=True):
    """
    Entrega las variables del resorte como MATRIZ (lista de filas).
    Acepta el dict de interpretar() o una instancia ResorteCotizacion.
    Cada fila: [variable, descripción, valor, unidad, obligatoria].
    """
    if isinstance(datos, ResorteCotizacion):
        datos = datos.to_dict()
    return _construir_matriz(datos, incluir_encabezado)


# ============================================================================
# Punto de entrada
# ============================================================================
def interpretar(respuesta_texto, como_matriz=False):
    """
    Pipeline de extracción: texto del modelo -> JSON -> variables del resorte.
    Devuelve un dict listo para cotización (incluye listo_para_cotizar y
    faltantes). Si como_matriz=True, devuelve además la matriz en datos["matriz"].
    Lanza ExtraccionError si el JSON no es recuperable.
    """
    datos_crudos = extraer_json(respuesta_texto)
    resorte = normalizar(datos_crudos)
    datos = resorte.to_dict()
    if como_matriz:
        datos["matriz"] = resorte.a_matriz()

    if datos["faltantes"]:
        log.warning("Resorte %s: faltan campos para cotizar: %s",
                    resorte.tipo_resorte, ", ".join(datos["faltantes"]))
    else:
        log.info("Resorte %s listo para cotizar (confianza=%.2f).",
                 resorte.tipo_resorte, resorte.confianza)
    return datos


if __name__ == "__main__":
    from app.core.logging import configure_logging
    configure_logging()
    ejemplo = """
    Claro, aquí está el análisis del plano:
    ```json
    {
      "tipo_resorte": "Compresión",
      "material": "Acero ASTM A228 (música)",
      "diametro_alambre_mm": "1.2 mm",
      "diametro_exterior_mm": 12.5,
      "longitud_libre_mm": "40,0",
      "numero_espiras_totales": 8,
      "sentido_enrollado": "derecha",
      "cantidad": 500,
      "unidad": "piezas",
      "normas": "ASTM A228",
      "confianza": 0.87,
      "advertencias": ["Tolerancia del paso ilegible"]
    }
    ```
    """
    resorte = normalizar(extraer_json(ejemplo))
    print("=== Datos limpios (dict) ===")
    print(json.dumps(resorte.to_dict(), indent=2, ensure_ascii=False))
    print("\n=== Datos como MATRIZ ===")
    for fila in resorte.a_matriz():
        print(fila)
