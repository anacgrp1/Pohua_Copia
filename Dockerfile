# Imagen de despliegue del Cotizador (Render).
#
# Existe porque la app necesita tres cosas que el runtime de Python de Render no
# trae por sí solo:
#   1. Node.js — el motor de costeo (pricing/engine.js) corre en un subproceso
#      de Node. Sin él, POST /api/price devuelve 502 con el motivo.
#   2. Las librerías nativas de WeasyPrint (pango, cairo) para generar el PDF
#      de la cotización.
#   3. El cliente de PostgreSQL, para poder aplicar migraciones desde el propio
#      contenedor si hace falta.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# --- Dependencias del sistema ---------------------------------------------
# nodejs      : motor de costeo
# libpango/cairo/gdk-pixbuf : WeasyPrint
# postgresql-client : psql para migraciones
RUN apt-get update && apt-get install -y --no-install-recommends \
        nodejs \
        postgresql-client \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi8 \
        shared-mime-info \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Las dependencias primero, para que la capa se cachee entre despliegues.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Comprobación de arranque: si Node no está, el costeo no funciona y es mejor
# enterarse al construir la imagen que cuando un usuario pida un precio.
RUN node --version && python -c "import jwt, jinja2, fastapi; print('deps python OK')"

# Usuario sin privilegios: la app no necesita root para nada.
RUN useradd --create-home --shell /bin/bash cotizador \
    && chown -R cotizador:cotizador /app
USER cotizador

EXPOSE 8000

# Render inyecta $PORT. En local, 8000.
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]
