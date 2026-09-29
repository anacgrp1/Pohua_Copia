"""Pydantic schemas for API request/response models.

These models define the contract between the FastAPI backend and the
frontend PWA.  They do NOT duplicate the business logic; they only
serialise what the existing ``app/`` modules already produce.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Autenticación
# --------------------------------------------------------------------------- #

class LoginRequest(BaseModel):
    correo: str
    password: str


class UsuarioPublico(BaseModel):
    """Datos del usuario que sí se pueden devolver al navegador."""
    id: int
    correo: str
    nombre: str
    rol: str
    permisos: List[str] = Field(default_factory=list)
    # Para el avatar: si hay foto y de cuándo es. La foto en sí se pide aparte
    # (GET /api/users/{id}/photo); meterla aquí cargaría de bytes una respuesta
    # que se pide en cada arranque de la aplicación.
    tiene_foto: bool = False
    foto_actualizada: Optional[str] = None
    # Entró con una contraseña temporal (alta o restablecimiento del
    # administrador): la aplicación le pide la suya nada más entrar.
    debe_cambiar_password: bool = False
    # La versión del aviso de privacidad y los términos que tiene que aceptar
    # antes de seguir (app/legal.py), o None si ya aceptó la vigente.
    legal_pendiente: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    usuario: UsuarioPublico


class CambioPasswordRequest(BaseModel):
    password_actual: str
    password_nueva: str


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #

class EstadoHorario(BaseModel):
    """El horario de atención tal y como lo necesita la pantalla.

    Los instantes viajan en ISO CON su huso (``2026-09-14T06:00:00-05:00``)
    para que el navegador los pinte en la ciudad del reloj sin que el servidor
    tenga que saber en qué idioma está la sesión. La ventana es una sola —la
    de la planta—; lo que cambia es en qué reloj se lee.
    """
    activo: bool = True
    abierto: bool = True
    zona: str = "America/Chicago"
    ciudad: str = "Kansas City"
    desde: int = 6
    hasta: int = 18
    dias: List[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    ahora_local: Optional[str] = None
    proxima_apertura: Optional[str] = None
    proximo_cierre: Optional[str] = None


class ServiceStatus(BaseModel):
    running: bool = False
    mode: str = "imap"
    # La carpeta del buzón que se está leyendo (MAIL_FOLDER). Se enseña en el
    # Monitor: trabajar contra TEST y creer que se está leyendo la bandeja de
    # ventas —o al revés— es un susto que se evita diciéndolo.
    folder: str = ""
    last_cycle: Optional[str] = None
    next_cycle: Optional[str] = None
    interval_minutes: int = 5
    total_processed: int = 0
    total_rfqs: int = 0
    total_errors: int = 0
    horario: Optional[EstadoHorario] = None


class CycleResult(BaseModel):
    """Result of a single detection cycle."""
    messages_found: int = 0
    new_processed: int = 0
    errors: int = 0
    timestamp: str = ""
    details: List[str] = Field(default_factory=list)
    # False cuando el ciclo no se ejecutó por estar fuera de horario.
    en_horario: bool = True


# --------------------------------------------------------------------------- #
# RFQ
# --------------------------------------------------------------------------- #

class RFQSummary(BaseModel):
    id: int
    rfq_id: str
    version: int
    cliente_id: Optional[str] = None
    nombre_proyecto: Optional[str] = None
    part_number: Optional[str] = None
    volumen: Optional[str] = None
    material: Optional[str] = None
    estado: str = "New"
    message_id: Optional[str] = None
    veredicto_sistema: Optional[str] = None
    veredicto_final: Optional[str] = None
    score: Optional[float] = None
    fecha_registro: Optional[str] = None
    # El nombre del cliente tal como lo dejó el flujo (razón social o, si no
    # se reconoció, lo que dijo el correo). Sin él, un RFQ cuyo cliente no
    # está en la cartera salía en las listas como "—".
    cliente_nombre: Optional[str] = None
    # Lo que se le pidió al comprador, en los que esperan al cliente.
    campos_faltantes: Optional[List[str]] = None
    # En los aprobados: 'enviada', 'en_cola' (en la bandeja de salida) o
    # 'pendiente' (nadie ha pulsado «Enviar oferta»). None en los demás.
    oferta: Optional[str] = None


class RFQDetail(RFQSummary):
    datos_json: Optional[Dict[str, Any]] = None
    notas: Optional[str] = None
    banderas: List[Dict[str, Any]] = Field(default_factory=list)
    resorte: Optional[Dict[str, Any]] = None


class RFQListResponse(BaseModel):
    rfqs: List[RFQSummary]
    total: int


class PMDecisionRequest(BaseModel):
    nota: Optional[str] = None
    destinatario: Optional[str] = None
    enviar_correo: bool = True
    # `usuario` ya NO se acepta del cliente: quién dictamina se toma del token
    # de sesión, para que la bitácora no dependa de lo que escriba el navegador.


class PMDecisionResponse(BaseModel):
    id: int
    rfq_id: str
    version: int
    # None cuando el PM DEVUELVE en vez de dictaminar: no hay veredicto.
    veredicto_final: Optional[str] = None
    estado: str
    correo_enviado: bool = False


# --------------------------------------------------------------------------- #
# Costeo
# --------------------------------------------------------------------------- #

class PriceRequest(BaseModel):
    """Input for the pricing engine."""
    rfq_id: Optional[str] = None
    tipo_resorte: str = "compresion"
    material: Optional[str] = None
    diametro_alambre_mm: Optional[float] = None
    diametro_exterior_mm: Optional[float] = None
    longitud_libre_mm: Optional[float] = None
    cantidad: Optional[float] = None
    # The full resorte dict can be passed instead of individual fields
    datos_resorte: Optional[Dict[str, Any]] = None


class PriceResponse(BaseModel):
    rfq_id: Optional[str] = None
    precio_unitario_usd: Optional[float] = None
    tooling_usd: Optional[float] = None
    lead_time_weeks: Optional[int] = None
    desglose: Dict[str, Any] = Field(default_factory=dict)
    moneda: str = "USD"
    notas: Optional[str] = None
    # Trazabilidad del costeo: de dónde salió cada insumo del cálculo.
    # `completo=False` significa que faltaban datos en el catálogo y el motor
    # tiró de valores por defecto: el precio NO se puede mandar al cliente así.
    origen_datos: Dict[str, str] = Field(default_factory=dict)
    completo: bool = False
    faltantes: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Asistente de la barra inferior
# --------------------------------------------------------------------------- #

class AssistantSummary(BaseModel):
    """Cifras contadas en SQL. Ninguna sale de un modelo de lenguaje."""
    total: int = 0
    ultimos_7_dias: int = 0
    ultimos_30_dias: int = 0
    clientes: int = 0
    por_estado: List[Dict[str, Any]] = Field(default_factory=list)
    materiales: List[Dict[str, Any]] = Field(default_factory=list)
    ultima_rfq: Optional[str] = None
    # Los clientes marcados como estrella en la base (el Top 12 de COT-71),
    # con cuántas RFQs lleva cada uno.
    estrella: List[Dict[str, Any]] = Field(default_factory=list)
    # RFQs que vienen de un cliente estrella, sobre el total.
    rfqs_estrella: int = 0


class AssistantAttention(BaseModel):
    """RFQs paradas o con banderas: lo que espera a una persona."""
    pendientes: List[Dict[str, Any]] = Field(default_factory=list)
    total: int = 0
    criticas: int = 0


class AssistantTopClientes(BaseModel):
    """Quién pidió más en los últimos días, y si es de los grandes."""
    clientes: List[Dict[str, Any]] = Field(default_factory=list)
    dias: int = 7
    total_rfqs: int = 0
    nuevos: int = 0


class AssistantQuestion(BaseModel):
    pregunta: str


class AssistantAnswer(BaseModel):
    respuesta: str
    modelo: Optional[str] = None
    # Se devuelven para poder vigilar el gasto de API desde el propio registro.
    tokens_entrada: Optional[int] = None
    tokens_salida: Optional[int] = None


class LogLine(BaseModel):
    """Una línea de app.log ya troceada, para pintarla con color por nivel."""
    marca: Optional[str] = None
    nivel: str = "INFO"
    origen: Optional[str] = None
    mensaje: str = ""


class LogTail(BaseModel):
    lineas: List[LogLine] = Field(default_factory=list)
    archivo: Optional[str] = None
    total: int = 0
    disponible: bool = True
    aviso: Optional[str] = None


class PipelineStage(BaseModel):
    """Una etapa del recorrido de un correo, con lo que hay en ella ahora."""
    clave: str
    etiqueta: str
    total: int = 0
    detalle: Optional[str] = None
    # 'espera' marca las etapas donde el trabajo se queda parado hasta que
    # alguien actúa. Es lo que el frontend pinta en ámbar.
    espera: bool = False


class PipelineFlow(BaseModel):
    etapas: List[PipelineStage] = Field(default_factory=list)
    corriendo: bool = False
    ultimo_ciclo: Optional[str] = None


# --------------------------------------------------------------------------- #
# Usuarios y perfil
# --------------------------------------------------------------------------- #

class RolPublico(BaseModel):
    codigo: str
    nombre: str
    descripcion: str = ""


class UsuarioListado(BaseModel):
    """Lo mínimo de un usuario. Nunca lleva el hash de la contraseña."""
    id: int
    correo: str
    nombre: str
    rol: str = ""
    activo: bool = True
    # De fuera de ISC. Es una marca informativa: quien decide lo que se puede
    # hacer sigue siendo el rol.
    externo: bool = False


class UsuarioAdmin(UsuarioListado):
    """La vista de administración: añade actividad y si tiene foto.

    `tiene_foto` en vez de la foto: pintar una lista no debe arrastrar los
    bytes de todas las imágenes. `foto_actualizada` va en la URL de la imagen
    para que el navegador la cachee hasta que cambie de verdad.
    """
    ultimo_acceso: Optional[str] = None
    creado_en: Optional[str] = None
    tiene_foto: bool = False
    foto_actualizada: Optional[str] = None
    # Sigue con la temporal que le puso el administrador: en la lista se ve
    # quién no ha entrado todavía (o no ha cambiado la suya).
    debe_cambiar_password: bool = False


class UsuarioCreado(UsuarioAdmin):
    """La respuesta del alta: el usuario y, UNA sola vez, su contraseña temporal.

    No se vuelve a poder leer: el servidor sólo guarda el hash. Quien
    administra la copia o la manda al teléfono de la persona desde la misma
    pantalla.
    """
    password_temporal: str


class PasswordRestablecida(BaseModel):
    """Lo que devuelve el restablecimiento por el administrador."""
    password_temporal: str
    # Si se pidió mandarla por notificación: a cuántos dispositivos de la
    # persona llegó. 0 dispositivos = no tiene los avisos activados en ningún
    # teléfono; hay que dársela en persona.
    notificada: bool = False
    dispositivos: int = 0
    entregados: int = 0


class RecalculoRequest(BaseModel):
    """Lo que el PM ajusta en la ventana de revisión antes de dictaminar.

    ``ajustes`` son campos del resorte: sólo se aplican los de la lista de
    ``app/rfq/recalculo.py``, y sólo los que vengan con valor —mandar el
    formulario entero no borra lo que no se tocó—. Para vaciar un campo a
    propósito se manda ``"-"``.

    ``leer_plano`` fuerza la lectura del dibujo con la IA antes de recalcular,
    que es el botón «Leer el plano con IA»: el PM puede querer las cotas del
    dibujo aunque el resorte ya tenga algo escrito.
    """
    ajustes: Optional[Dict[str, Any]] = None
    leer_plano: bool = False


class CotizacionPMRequest(BaseModel):
    """La cotización que el PM dejó en la calculadora completa.

    ``pn`` es el PN tal como quedó en la hoja (la forma de ``blankPn()``),
    ``resultado`` lo que devolvió ``ENGINE.computePN`` para ese PN (tramos y
    banderas) y ``contribution`` el objetivo con el que se calculó. La
    ``cabecera`` lleva número de cotización, representante, plazo y
    condiciones de pago, sólo para enseñarlos.
    """
    pn: Dict[str, Any]
    resultado: Dict[str, Any]
    contribution: Optional[float] = None
    cabecera: Dict[str, Any] = Field(default_factory=dict)
    material_nombre: Optional[str] = None
    # "guardado": el guardado automático mientras se escribe (actualiza la
    # versión en curso). "volver": el PM volvió a la revisión (la fija).
    motivo: str = "guardado"
    # La marca de la versión escogida en la ventana con la que se cargó la
    # hoja (``pm_restauracion.en``). Si alguien escogió otra después, lo que
    # manda la hoja es viejo y no se guarda: la calculadora recarga la elegida.
    restauracion: Optional[str] = None


class VersionPMRequest(BaseModel):
    """Qué versión de la cotización del PM usar; ``None`` = el cálculo del sistema."""
    version: Optional[int] = None


class OfertaRequest(BaseModel):
    """Lo que el PM puede ajustar antes de mandar la oferta al cliente."""
    destinatario: Optional[str] = None      # por defecto, el remitente del RFQ
    lead_time: Optional[str] = None
    incoterm: Optional[str] = None
    terminos: Optional[str] = None          # "Net 30"
    validez_dias: Optional[int] = None
    comentarios: Optional[str] = None       # va en las observaciones de la línea
    acabado: Optional[str] = None
    # Mandarla aunque el costeo sea orientativo (al catálogo le faltan datos).
    forzar: bool = False

