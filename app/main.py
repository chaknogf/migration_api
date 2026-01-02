"""
Sistema de Gestión de Pacientes
API FastAPI para gestión de pacientes con migración MySQL → PostgreSQL

Autor: Tu Nombre
Versión: 1.0.0
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time

from app.core.config import settings, print_settings
from app.core.logging import setup_logging, get_logger
from app.core.middleware import (
    LoggingMiddleware,
    RequestIDMiddleware,
    CORSHeadersMiddleware
)
from app.core.dependencies import validate_environment
from app.exceptions.handlers import add_exception_handlers
from app.api.v1.router import api_router
from app.database import postgres, mysql


# ═══════════════════════════════════════════════════════════
# CONFIGURACIÓN DE LOGGING
# ═══════════════════════════════════════════════════════════

setup_logging()
logger = get_logger(__name__)


# ═══════════════════════════════════════════════════════════
# LIFESPAN EVENTS
# ═══════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gestión del ciclo de vida de la aplicación
    - Startup: Inicialización y verificaciones
    - Shutdown: Limpieza y cierre de conexiones
    """
    # ────────────────────────────────────────────────────────
    # STARTUP
    # ────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("🚀 INICIANDO APLICACIÓN")
    logger.info("=" * 60)
    
    # Imprimir configuración
    print_settings()
    
    # Validar entorno
    try:
        validate_environment()
        logger.info("✅ Entorno validado correctamente")
    except RuntimeError as e:
        logger.error(f"❌ Error en validación de entorno: {e}")
        raise
    
    # Verificar conexión a PostgreSQL
    try:
        postgres.test_connection()
        logger.info("✅ PostgreSQL conectado")
    except Exception as e:
        logger.error(f"❌ Error conectando a PostgreSQL: {e}")
        # No lanzar excepción, permitir que la app inicie
    
    # Verificar conexión a MySQL (opcional)
    try:
        mysql.test_connection()
        logger.info("✅ MySQL conectado (modo lectura)")
    except Exception as e:
        logger.warning(f"⚠️  MySQL no disponible: {e}")
        logger.warning("   La funcionalidad de migración no estará disponible")
    
    # Información adicional
    logger.info(f"📊 Entorno: {settings.ENVIRONMENT}")
    logger.info(f"🔧 Debug: {settings.DEBUG}")
    logger.info(f"📝 Logs: {settings.LOG_FILE}")
    logger.info(f"🌐 API Prefix: {settings.API_V1_PREFIX}")
    
    logger.info("=" * 60)
    logger.info("✅ APLICACIÓN LISTA")
    logger.info("=" * 60)
    
    yield
    
    # ────────────────────────────────────────────────────────
    # SHUTDOWN
    # ────────────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("🛑 CERRANDO APLICACIÓN")
    logger.info("=" * 60)
    
    # Aquí puedes agregar lógica de limpieza
    logger.info("Cerrando conexiones...")
    
    logger.info("=" * 60)
    logger.info("✅ APLICACIÓN CERRADA")
    logger.info("=" * 60)


# ═══════════════════════════════════════════════════════════
# CREAR APLICACIÓN FASTAPI
# ═══════════════════════════════════════════════════════════

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.DESCRIPTION,
    version=settings.VERSION,
    docs_url=settings.docs_url,
    redoc_url=settings.redoc_url,
    openapi_url=settings.openapi_url,
    lifespan=lifespan,
    # Metadata adicional para OpenAPI
    contact={
        "name": "Equipo de Desarrollo",
        "email": "dev@hospital.com",
    },
    license_info={
        "name": "MIT",
    },
    openapi_tags=[
        {
            "name": "Health Check",
            "description": "Endpoints para verificar el estado del sistema"
        },
        {
            "name": "Pacientes",
            "description": "Operaciones CRUD y consultas de pacientes"
        },
        {
            "name": "Migración",
            "description": "Endpoints para el proceso de migración MySQL → PostgreSQL"
        }
    ]
)


# ═══════════════════════════════════════════════════════════
# MIDDLEWARE
# ═══════════════════════════════════════════════════════════

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time", "X-Request-ID"]
)

# Custom Middlewares
app.add_middleware(CORSHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)


# ═══════════════════════════════════════════════════════════
# MANEJADORES DE EXCEPCIONES
# ═══════════════════════════════════════════════════════════

add_exception_handlers(app)


# ═══════════════════════════════════════════════════════════
# ROUTERS
# ═══════════════════════════════════════════════════════════

# Incluir router principal de la API
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


# ═══════════════════════════════════════════════════════════
# ENDPOINTS RAÍZ
# ═══════════════════════════════════════════════════════════

@app.get(
    "/",
    tags=["Root"],
    summary="Endpoint raíz",
    description="Información básica de la API"
)
async def root():
    """
    Endpoint raíz de la API
    
    Returns:
        Información básica del sistema
    """
    return {
        "message": f"Bienvenido a {settings.PROJECT_NAME}",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "docs": f"{settings.API_V1_PREFIX}/docs" if settings.ENVIRONMENT != "production" else None,
        "health": f"{settings.API_V1_PREFIX}/health/"
    }


@app.get(
    "/info",
    tags=["Root"],
    summary="Información del sistema",
    description="Información detallada de la aplicación"
)
async def info():
    """
    Información detallada del sistema
    
    Returns:
        Configuración y estado del sistema
    """
    return {
        "application": {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "description": settings.DESCRIPTION,
            "environment": settings.ENVIRONMENT,
            "debug": settings.DEBUG
        },
        "api": {
            "prefix": settings.API_V1_PREFIX,
            "docs_url": settings.docs_url,
            "redoc_url": settings.redoc_url
        },
        "databases": {
            "postgresql": {
                "host": settings.POSTGRES_HOST,
                "port": settings.POSTGRES_PORT,
                "database": settings.POSTGRES_DB
            },
            "mysql": {
                "host": settings.MYSQL_HOST,
                "port": settings.MYSQL_PORT,
                "database": settings.MYSQL_DATABASE,
                "mode": "read_only"
            }
        }
    }


# ═══════════════════════════════════════════════════════════
# MANEJO DE ERRORES 404
# ═══════════════════════════════════════════════════════════

@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    """
    Manejador personalizado para errores 404
    """
    return JSONResponse(
        status_code=404,
        content={
            "error": True,
            "message": "Endpoint no encontrado",
            "path": str(request.url.path),
            "suggestion": f"Revisa la documentación en {settings.API_V1_PREFIX}/docs"
        }
    )


# ═══════════════════════════════════════════════════════════
# EVENTOS ADICIONALES (OPCIONAL)
# ═══════════════════════════════════════════════════════════

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """
    Middleware adicional para agregar tiempo de procesamiento
    (Alternativa al LoggingMiddleware, ya incluido arriba)
    """
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(round(process_time, 4))
    return response


# ═══════════════════════════════════════════════════════════
# PUNTO DE ENTRADA PARA DESARROLLO
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    logger.info("🚀 Iniciando servidor de desarrollo...")
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8010,
        reload=True,  # Auto-reload en desarrollo
        log_level="info",
        access_log=True
    )