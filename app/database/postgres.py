# app/database/postgres.py
"""
Conexión a PostgreSQL - Base de datos principal del sistema
Compatible con SQLAlchemy 2.0+ y operaciones asíncronas opcionales
"""

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import QueuePool
from urllib.parse import quote_plus
from contextlib import contextmanager
from typing import Generator
import os
from dotenv import load_dotenv
import logging

# ============================
# Configuración de logging
# ============================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================
# Cargar variables de entorno
# ============================

load_dotenv(override=True)

# ============================
# Configuración PostgreSQL
# ============================

POSTGRES_USER = os.getenv("POSTGRES_USER", "admin")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "secreto123")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "hospital")

# Codificar password para URL
PASSWORD_ENCODED = quote_plus(POSTGRES_PASSWORD)

DATABASE_URL = (
    f"postgresql+psycopg2://{POSTGRES_USER}:"
    f"{PASSWORD_ENCODED}@"
    f"{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
)

# ============================
# Configuración del Engine
# ============================

engine = create_engine(
    DATABASE_URL,
    echo=False,  # Cambiar a True para debug SQL
    pool_pre_ping=True,  # Verifica conexiones antes de usar
    pool_recycle=3600,  # Recicla conexiones cada hora
    pool_size=10,  # Tamaño del pool de conexiones
    max_overflow=20,  # Conexiones adicionales permitidas
    poolclass=QueuePool,
    connect_args={
        "connect_timeout": 10,
        "options": "-c timezone=America/Guatemala"  # Zona horaria
    }
)

# ============================
# Event Listeners
# ============================

@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """Se ejecuta al establecer una nueva conexión"""
    logger.debug("Nueva conexión PostgreSQL establecida")


@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_conn, connection_record, connection_proxy):
    """Se ejecuta al sacar una conexión del pool"""
    logger.debug("Conexión PostgreSQL obtenida del pool")


# ============================
# Test de conexión inicial
# ============================

def test_connection():
    """Verifica que la conexión a PostgreSQL funcione"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
            logger.info(f"✅ PostgreSQL conectado: {version}")
            return True
    except Exception as e:
        logger.error(f"❌ Error conectando a PostgreSQL: {e}")
        raise


# Ejecutar test al importar
try:
    test_connection()
except Exception as e:
    logger.warning(f"⚠️  PostgreSQL no disponible al iniciar: {e}")

# ============================
# SessionLocal
# ============================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False  # Evita recargas innecesarias
)

# ============================
# Base declarativa
# ============================

Base = declarative_base()

# ============================
# Dependency para FastAPI
# ============================

def get_db() -> Generator[Session, None, None]:
    """
    Dependencia para inyectar sesión PostgreSQL en endpoints FastAPI
    
    Uso en FastAPI:
        @app.get("/pacientes")
        def get_pacientes(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Error en sesión PostgreSQL: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# ============================
# Context Manager para scripts
# ============================

@contextmanager
def get_postgres_session() -> Generator[Session, None, None]:
    """
    Context manager para usar en scripts de migración
    
    Uso:
        with get_postgres_session() as session:
            paciente = session.query(Paciente).first()
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception as e:
        logger.error(f"Error en transacción PostgreSQL: {e}")
        session.rollback()
        raise
    finally:
        session.close()


# ============================
# Funciones de utilidad
# ============================

def create_tables():
    """
    Crea todas las tablas definidas en los modelos
    ⚠️ Solo usar en desarrollo/testing
    """
    from app.models.postgres.paciente import Paciente
    
    logger.info("Creando tablas en PostgreSQL...")
    Base.metadata.create_all(bind=engine)
    logger.info("✅ Tablas creadas exitosamente")


def drop_tables():
    """
    Elimina todas las tablas
    ⚠️ PELIGRO: Solo usar en desarrollo
    """
    logger.warning("⚠️  Eliminando TODAS las tablas de PostgreSQL...")
    Base.metadata.drop_all(bind=engine)
    logger.info("✅ Tablas eliminadas")


def get_table_count(table_name: str) -> int:
    """
    Obtiene el conteo de registros de una tabla
    
    Args:
        table_name: Nombre de la tabla
        
    Returns:
        Número de registros
    """
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        count = result.scalar()
        return count or 0


def check_table_exists(table_name: str) -> bool:
    """
    Verifica si una tabla existe en la base de datos
    
    Args:
        table_name: Nombre de la tabla
        
    Returns:
        True si existe, False si no
    """
    with engine.connect() as conn:
        result = conn.execute(text(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = :table_name
            )
            """
        ), {"table_name": table_name})
        return result.scalar()


def get_database_info() -> dict:
    """
    Obtiene información general de la base de datos
    
    Returns:
        Diccionario con información de la DB
    """
    with engine.connect() as conn:
        # Versión
        version = conn.execute(text("SELECT version()")).scalar()
        
        # Tamaño de la DB
        size_query = text(
            "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )
        size = conn.execute(size_query).scalar()
        
        # Número de conexiones activas
        connections_query = text(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
        )
        connections = conn.execute(connections_query).scalar()
        
        return {
            "version": version,
            "size": size,
            "active_connections": connections,
            "database": POSTGRES_DB,
            "host": POSTGRES_HOST,
            "port": POSTGRES_PORT
        }


# ============================
# Health Check
# ============================

def health_check() -> dict:
    """
    Health check de la base de datos PostgreSQL
    
    Returns:
        Diccionario con estado de salud
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return {
            "status": "healthy",
            "database": "postgresql",
            "message": "Conexión exitosa"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "postgresql",
            "message": str(e)
        }