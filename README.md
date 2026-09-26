# Estructura del Proyecto — ISC by CGR Cotizador "Pohua"

---

## Arquitectura General

```
┌────────────────────────────────────────────────────────────────────────┐
│                          ENTRADAS EXTERNAS                             │
│    IMAP / SMTP (Local)            Microsoft Graph API (OAuth Token)    │
└───────────────────┬────────────────────────────────┬───────────────────┘
                    │                                │
                    ▼                                ▼
┌────────────────────────────────────────────────────────────────────────┐
│                           RENDER (Web App)                             │
│                                                                        │
│  ┌───────────────────────┐          ┌───────────────────────────────┐  │
│  │    Frontend (PWA)     │ ◄──────► │      API (FastAPI + Uvicorn)  │  │
│  │  HTML5 / CSS3 / ES6+  │  REST/UI │  • api/server.py              │  │
│  │  Login + token JWT    │  Bearer  │  • api/security.py (sesión)   │  │
│  │  Service Worker (sw)  │          │  • /auth /rfqs /status /price │  │
│  └───────────────────────┘          └──────────────┬────────────────┘  │
│                                                    │                   │
│  ┌─────────────────────────────────────────────────┴────────────────┐  │
│  │                    Background Worker Loop                        │  │
│  │                    app/main.py: ciclo_deteccion()                │  │
│  │                                                                  │  │
│  │  ┌────────────────────┐   ┌─────────────────┐   ┌─────────────┐  │  │
│  │  │ app/email/         │   │ app/rfq/        │   │ app/clients/│  │  │
│  │  │ IMAP/Graph Factory │   │ Flujo & Estado  │   │ Mapeo Clie. │  │  │
│  │  └────────┬───────────┘   └────────┬────────┘   └─────────────┘  │  │
│  │           │                        │                             │  │
│  │           ▼                        ▼                             │  │
│  │  ┌────────────────────┐   ┌─────────────────┐   ┌─────────────┐  │  │
│  │  │ app/vision/ &      │   │ app/feasibility/│   │ app/core/   │  │  │
│  │  │ app/extraction/    │   │ Motor de Reglas │   │ Config, Log │  │  │
│  │  │ (IA Multimodal)    │   │ & Decisión PM   │   │ Exceptions  │  │  │
│  │  └────────────────────┘   └─────────────────┘   └─────────────┘  │  │
│  │                                                                  │  │
│  │  ┌────────────────────────────────────────────────────────────┐  │  │
│  │  │ app/persistence/ + app/auth/ (usuarios, roles, permisos)   │  │  │
│  │  └──────────────────────────────┬─────────────────────────────┘  │  │
│  └─────────────────────────────────┼────────────────────────────────┘  │
└────────────────────────────────────┼───────────────────────────────────┘
                                     │ psycopg2 (DATABASE_URL)
                                     ▼
┌────────────────────────────────────────────────────────────────────────┐
│                        NEON — POSTGRESQL                               │
│   Base de datos relacional: RFQs, clientes, usuarios/roles y el        │
│   catálogo de costeo (máquinas, tarifas, materiales, parámetros)       │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Árbol de Archivos

```
Cotizador/
│
├── 📁 app/                          ← LÓGICA DE NEGOCIO
│   ├── main.py                      ← Ciclo principal de detección de correos
│   │
│   ├── 📁 core/                     ← Configuración central
│   │   ├── config.py                ← Settings + DATABASE_URL + PG_* + validación
│   │   ├── exceptions.py            ← Excepciones personalizadas
│   │   └── logging.py               ← Sistema de logs
│   │
│   ├── 📁 email/                    ← Lectura y envío de correos
│   │   ├── base_provider.py         ← Interfaz abstracta del proveedor
│   │   ├── imap_provider.py         ← Proveedor IMAP (modo local)
│   │   ├── graph_provider.py        ← Proveedor Microsoft Graph (modo token)
│   │   ├── factory.py               ← Fábrica: elige IMAP o Graph según AUTH_METHOD
│   │   ├── smtp_sender.py           ← Envío vía SMTP
│   │   ├── graph_sender.py          ← Envío vía Graph API
│   │   ├── outbound.py              ← Despacho unificado de correos salientes
│   │   └── templates.py             ← Plantillas de correos (declinación, etc.)
│   │
│   ├── 📁 rfq/                      ← Flujo de RFQ (Request for Quotation)
│   │   ├── flow.py                  ← Clasificación y orquestación del flujo
│   │   ├── detector.py              ← Detecta IDs de RFQ en asuntos
│   │   ├── repository.py            ← Persistencia de RFQs (psycopg2 directo)
│   │   └── thread_validator.py      ← Asocia correos a hilos de RFQ existentes
│   │
│   ├── 📁 vision/                   ← IA — Lectura de dibujos técnicos
│   │   ├── pipeline.py              ← Pipeline multimodal (PDF/PNG → Modelo de visión)
│   │   └── spring_extractor.py      ← Extrae variables de resortes del dibujo
│   │
│   ├── 📁 extraction/               ← IA — Extracción del cuerpo del correo
│   │
│   ├── 📁 feasibility/              ← Motor de factibilidad
│   │   ├── engine.py                ← Evaluación automática vs directrices
│   │   ├── rules.py                 ← Reglas de la planta (rangos/materiales)
│   │   └── pm_decision.py           ← Dictamen del Plant Manager (aprobar/declinar)
│   │
│   ├── 📁 clients/                  ← Mapeo de clientes
│   │   └── mapper.py                ← Dominio del remitente → cliente existente
│   │
│   ├── 📁 auth/                     ← Autenticación de usuarios
│   │   ├── passwords.py             ← Hash PBKDF2-SHA256 y política de contraseñas
│   │   ├── tokens.py                ← Tokens de sesión (JWT HS256) y permisos
│   │   └── repository.py            ← Tablas usuarios / roles / permisos
│   │
│   └── 📁 persistence/              ← Capa de datos
│       ├── duplicates.py            ← conectar_bd() + control de duplicados
│       ├── schema.py                ← Verificación de tablas existentes
│       ├── spring_repository.py     ← Persistencia de datos de resortes
│       └── blueprint_store.py       ← Almacenamiento de planos (local/Azure Blob)
│
├── 📁 api/                          ← CAPA WEB (FastAPI)
│   ├── server.py                    ← App FastAPI + worker en background + CORS
│   ├── dependencies.py              ← get_db(), get_config() para inyección
│   ├── 📁 models/
│   │   └── schemas.py               ← Modelos Pydantic (request/response)
│   ├── security.py                  ← Dependencias de sesión y permisos
│   └── 📁 routes/
│       ├── auth.py                  ← Login, sesión actual, cambio de contraseña
│       ├── rfqs.py                  ← CRUD de RFQs + approve/decline del PM
│       ├── status.py                ← Estado del worker, health check
│       └── pricing.py               ← Endpoints de costeo
│
├── 📁 frontend/                     ← PWA (Progressive Web App)
│   ├── index.html                   ← SPA principal
│   ├── manifest.json                ← Configuración PWA
│   ├── sw.js                        ← Service Worker
│   ├── 📁 css/                      ← Estilos
│   ├── 📁 js/                       ← Lógica del frontend
│   └── 📁 assets/                   ← Recursos estáticos
│
├── 📁 desktop_app/                  ← App de escritorio (PySide6)
│   └── main.py                      ← Lee el buzón por el Outlook de la máquina
│                                      (MAIL_MODE=outlook) + latido al servidor
│
├── 📁 sql/                          ← Esquema de la BD
│   ├── schema.sql                   ← DDL principal (6 tablas + roles PostgREST)
│   └── 📁 migrations/
│       ├── 004_prep_base.sql        ← Veredictos + score
│       ├── 005_extension_costeo.sql ← Tablas de costeo, usuarios y roles
│       ├── 006_auth_roles.sql       ← Roles y permisos del login
│       └── 007_catalogo_costeo.sql  ← Catálogo migrado desde engine.js
│
├── 📁 reglas/                       ← Directrices de la planta
│   └── factibilidad.json            ← Rangos/materiales para factibilidad
│
├── 📁 pricing/                      ← Costeo
│   ├── 📁 nucleo/                   ← Copia del núcleo: motor, reglas y resortes (no tocar)
│   ├── runner.js                    ← Puente stdin/stdout con el motor del núcleo
│   ├── engine.py                    ← Envoltorio Python del motor
│   ├── repository.py                ← Lee el catálogo de costeo de PostgreSQL
│   └── rodea_adapter.py             ← Datos del resorte → esquema PN del motor
├── 📁 tests/                        ← Tests unitarios e integración
├── 📁 docs/
│   └── OPERACION.md                 ← Puesta en marcha, despliegue, pendientes
├── 📁 scripts/
│   ├── db_init.sh                   ← Levanta la BD y aplica las migraciones
│   └── crear_usuario.py             ← Alta de usuarios (no se expone por HTTP)
│
├── run_web.py                       ← Lanzador del servidor web
├── ver_local.bat                    ← Vista local en Windows (doble clic)
├── Dockerfile                       ← Imagen de despliegue (Python + Node + cliente de PostgreSQL)
├── package.json                     ← Declara Node para el motor de costeo
├── docker-compose.yml               ← PostgreSQL 16 (dev local); PostgREST opcional
├── postgrest.conf                   ← Config PostgREST (solo dev local)
├── Makefile                         ← Atajos: db-up, test, lint, usuario
├── requirements.txt                 ← Dependencias del servidor
├── requirements-desktop.txt         ← Sólo para la app de escritorio (PySide6 + pywin32)
├── requirements-dev.txt             ← Tests y linters
├── .env                             ← Variables de entorno (local, nunca al repo)
└── .env.example                     ← Plantilla documentada
```

---

## Infraestructura en la Nube

| Servicio | Plataforma | Qué hace |
|---|---|---|
| **Web App** | Render | Servidor FastAPI + Frontend PWA + Background Worker |
| **Base de datos** | Neon | PostgreSQL serverless (`Cotizador`) |
| **IA Multimodal** | AI API | Análisis de planos técnicos (visión) y extracción de correo |
| **Correo** | IMAP / Microsoft Graph | Ingesta de solicitudes y despacho de respuestas (configurable) |
| **Planos** | Local / Azure Blob | Repositorio de almacenamiento para archivos técnicos y planos |
```

---

## Puesta en marcha

```bash
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                 # y rellena DATABASE_URL y JWT_SECRET
make db-up                           # PostgreSQL + esquema + migraciones
make usuario CORREO=tu@cgr-international.com NOMBRE="Tu Nombre" ROL=admin
python run_web.py --reload
```

En Windows, para ver los cambios sin publicar nada, doble clic en
**`ver_local.bat`**: levanta el cotizador en <http://localhost:8000>, apaga el
lector de correo y el envío automático (para que tu equipo no interfiera con
producción) y avisa contra qué base de datos estás trabajando. Detalles en
`docs/OPERACION.md`.

`make help` lista el resto de atajos. Para desplegar, capturar el catálogo de
costeo o dar de alta más usuarios, ver **[docs/OPERACION.md](docs/OPERACION.md)**.

## Acceso

La API requiere sesión. Se entra con correo y contraseña en la propia PWA; el
navegador guarda un token que caduca a las 8 horas. Cuatro roles:

| Rol | Permisos |
|---|---|
| `admin` | Todo. Da de alta usuarios y opera el worker |
| `pm` | Ver RFQs, aprobar/declinar, costear, operar el worker |
| `quoter` | Los mismos que `pm` |

`pm` y `quoter` comparten permisos pero son dos roles separados a propósito: el
rol viaja en el token y queda en la bitácora, así que al revisar quién aprobó o
declinó un RFQ se distingue si fue Planta o quien cotiza.

`sql/migrations/006_auth_roles.sql` explica cómo añadir otros puestos de ISC
cuando haga falta; no requiere tocar código.

Las cuentas se crean desde el servidor con `scripts/crear_usuario.py`; no hay
registro por HTTP a propósito.

## Costeo

`POST /api/price` devuelve, además del precio, tres campos que hay que mirar
antes de mandar nada a un cliente:

- `completo` — `true` sólo si todos los insumos salieron del catálogo.
- `faltantes` — qué faltó, en lenguaje llano.
- `origen_datos` — de dónde salió cada número (máquina, material, parámetros).

Mientras `material_precios` esté vacía, todo costeo saldrá con
`completo: false`. La captura pendiente está descrita en `docs/OPERACION.md`.
