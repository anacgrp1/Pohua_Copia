"""
SUBTAREA 2 [Lógica - Persistencia]
Almacena en PostgreSQL las variables físicas del resorte extraídas del dibujo,
asociadas a un RFQ y al correo (message-id) de origen.

Reutiliza la conexión de control_duplicados para mantener una sola fuente de
configuración de base de datos.
"""
import json
import logging

import app.persistence.duplicates as duplicates  # reutiliza conectar_bd()

log = logging.getLogger("cotizador.repositorio")


def inicializar_bd():
    """Verifica que exista la tabla ``resortes_cotizacion``.

    Ya no crea nada: el esquema lo aplica ``make db-up`` (COT-93).
    """
    import app.persistence.schema as schema
    schema.verificar_tablas(("resortes_cotizacion",))


def guardar(rfq_id, message_id, origen_archivo, datos):
    """
    Inserta el resultado de la extracción. `datos` es el dict producido por
    spring_extractor.interpretar(). El dict completo se guarda en datos_json
    (JSONB) y los campos clave en columnas para consultas/filtros rápidos.
    Devuelve el id insertado.
    """
    sql = """
    INSERT INTO resortes_cotizacion (
        rfq_id, message_id, origen_archivo,
        tipo_resorte, material,
        diametro_alambre_mm, diametro_exterior_mm, diametro_interior_mm,
        diametro_medio_mm, longitud_libre_mm,
        numero_espiras_totales, numero_espiras_activas, paso_mm,
        sentido_enrollado, tipo_extremos, constante_resorte_n_mm,
        acabado, cantidad, unidad, confianza, listo_para_cotizar, datos_json
    ) VALUES (
        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
        %s, %s, %s, %s, %s, %s
    ) RETURNING id;
    """
    valores = (
        rfq_id, message_id, origen_archivo,
        datos.get("tipo_resorte"), datos.get("material"),
        datos.get("diametro_alambre_mm"), datos.get("diametro_exterior_mm"),
        datos.get("diametro_interior_mm"), datos.get("diametro_medio_mm"),
        datos.get("longitud_libre_mm"),
        datos.get("numero_espiras_totales"), datos.get("numero_espiras_activas"),
        datos.get("paso_mm"), datos.get("sentido_enrollado"),
        datos.get("tipo_extremos"), datos.get("constante_resorte_N_mm"),
        datos.get("acabado"), datos.get("cantidad"), datos.get("unidad"),
        datos.get("confianza"), datos.get("listo_para_cotizar"),
        json.dumps(datos, ensure_ascii=False),
    )
    with duplicates.conexion_bd() as conexion:
        with conexion.cursor() as cursor:
            cursor.execute(sql, valores)
            nuevo_id = cursor.fetchone()[0]
    log.info("Resorte guardado (id=%s, rfq=%s, archivo=%s).",
             nuevo_id, rfq_id, origen_archivo)
    return nuevo_id


if __name__ == "__main__":
    inicializar_bd()
    print("Tabla 'resortes_cotizacion' lista.")
