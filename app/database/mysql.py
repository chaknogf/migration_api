# app/database/mysql.py
"""
Conexión a MySQL - Base de datos legacy
⚠️ SOLO LECTURA - Exclusivamente para migración de datos
"""

from sqlalchemy import create_engine, text, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.pool import QueuePool
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
# Configuración MySQL
# ============================

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
MYSQL_PORT = os.getenv("MYSQL_PORT", "3306")
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "Prometeus.0")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "test_api")

SQLALCHEMY_DATABASE_URL = (
    f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}"
    f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
)

# ============================
# Configuración del Engine
# ============================

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,  # Cambiar a True para debug SQL
    pool_pre_ping=True,
    pool_recycle=3600,
    pool_size=5,  # Pool más pequeño (solo lectura)
    max_overflow=10,
    poolclass=QueuePool,
    connect_args={
        "charset": "utf8mb4",
        "connect_timeout": 10
    }
)

# ============================
# Event Listeners
# ============================

@event.listens_for(engine, "connect")
def receive_connect(dbapi_conn, connection_record):
    """
    Se ejecuta al establecer una nueva conexión
    Configura la sesión en modo de solo lectura
    """
    cursor = dbapi_conn.cursor()
    try:
        # Configurar en modo de solo lectura
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
        logger.debug("Conexión MySQL configurada como READ ONLY")
    except Exception as e:
        logger.warning(f"No se pudo configurar READ ONLY: {e}")
    finally:
        cursor.close()


# ============================
# Test de conexión inicial
# ============================

def test_connection():
    """Verifica que la conexión a MySQL funcione"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT VERSION()"))
            version = result.scalar()
            logger.info(f"✅ MySQL conectado: {version}")
            
            # Verificar que la tabla pacientes existe
            result = conn.execute(text(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = :db AND table_name = 'pacientes'"
            ), {"db": MYSQL_DATABASE})
            
            if result.scalar() == 0:
                logger.warning("⚠️  Tabla 'pacientes' no encontrada en MySQL")
            else:
                # Contar registros
                result = conn.execute(text("SELECT COUNT(*) FROM pacientes"))
                count = result.scalar()
                logger.info(f"📊 Registros en tabla pacientes: {count}")
            
            return True
    except Exception as e:
        logger.error(f"❌ Error conectando a MySQL: {e}")
        raise


# Ejecutar test al importar
try:
    test_connection()
except Exception as e:
    logger.warning(f"⚠️  MySQL no disponible al iniciar: {e}")

# ============================
# SessionLocal
# ============================

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False
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
    Dependencia para inyectar sesión MySQL (solo lectura)
    
    ⚠️ IMPORTANTE: Esta sesión es SOLO LECTURA
    
    Uso en FastAPI:
        @app.get("/migracion/pacientes")
        def get_pacientes_mysql(db: Session = Depends(get_mysql_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Error en sesión MySQL: {e}")
        db.rollback()
        raise
    finally:
        db.close()


# ============================
# Context Manager para scripts
# ============================

@contextmanager
def get_mysql_session() -> Generator[Session, None, None]:
    """
    Context manager para usar en scripts de migración
    
    ⚠️ SOLO LECTURA
    
    Uso:
        with get_mysql_session() as session:
            pacientes = session.query(PacienteMysql).limit(100).all()
    """
    session = SessionLocal()
    try:
        yield session
        # No hacer commit en MySQL (solo lectura)
    except Exception as e:
        logger.error(f"Error en transacción MySQL: {e}")
        session.rollback()
        raise
    finally:
        session.close()


# ============================
# Funciones de utilidad
# ============================

def get_table_count(table_name: str = "pacientes") -> int:
    """
    Obtiene el conteo de registros de una tabla MySQL
    
    Args:
        table_name: Nombre de la tabla (default: pacientes)
        
    Returns:
        Número de registros
    """
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        count = result.scalar()
        return count or 0


def get_table_info(table_name: str = "pacientes") -> dict:
    """
    Obtiene información de una tabla MySQL
    
    Args:
        table_name: Nombre de la tabla
        
    Returns:
        Diccionario con información de la tabla
    """
    with engine.connect() as conn:
        # Estructura de la tabla
        result = conn.execute(text(f"DESCRIBE {table_name}"))
        columns = [dict(row._mapping) for row in result]
        
        # Conteo de registros
        count_result = conn.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
        count = count_result.scalar()
        
        return {
            "table_name": table_name,
            "total_records": count,
            "columns": columns
        }


def get_duplicate_expedientes() -> list:
    """
    Encuentra expedientes duplicados o nulos en MySQL
    
    Returns:
        Lista de expedientes problemáticos
    """
    with engine.connect() as conn:
        # Expedientes nulos
        null_query = text(
            "SELECT COUNT(*) as count FROM pacientes WHERE expediente IS NULL"
        )
        null_count = conn.execute(null_query).scalar()
        
        # Expedientes duplicados
        dup_query = text(
            """
            SELECT expediente, COUNT(*) as count 
            FROM pacientes 
            WHERE expediente IS NOT NULL 
            GROUP BY expediente 
            HAVING COUNT(*) > 1
            """
        )
        duplicates = conn.execute(dup_query).fetchall()
        
        return {
            "expedientes_nulos": null_count,
            "expedientes_duplicados": len(duplicates),
            "duplicados_detalle": [
                {"expediente": row.expediente, "count": row.count}
                for row in duplicates
            ]
        }


def get_invalid_cui_count() -> int:
    """
    Cuenta cuántos DPI/CUI son inválidos (no tienen 13 dígitos)
    
    Returns:
        Número de CUI inválidos
    """
    with engine.connect() as conn:
        query = text(
            """
            SELECT COUNT(*) 
            FROM pacientes 
            WHERE dpi IS NOT NULL 
            AND LENGTH(dpi) != 13
            """
        )
        count = conn.execute(query).scalar()
        return count or 0


def get_database_info() -> dict:
    """
    Obtiene información general de la base de datos MySQL
    
    Returns:
        Diccionario con información de la DB
    """
    with engine.connect() as conn:
        # Versión
        version = conn.execute(text("SELECT VERSION()")).scalar()
        
        # Tamaño de la DB
        size_query = text(
            f"""
            SELECT 
                ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) as size_mb
            FROM information_schema.tables
            WHERE table_schema = '{MYSQL_DATABASE}'
            """
        )
        size_mb = conn.execute(size_query).scalar()
        
        # Número de tablas
        tables_query = text(
            f"""
            SELECT COUNT(*) 
            FROM information_schema.tables
            WHERE table_schema = '{MYSQL_DATABASE}'
            """
        )
        tables = conn.execute(tables_query).scalar()
        
        return {
            "version": version,
            "size_mb": size_mb,
            "tables": tables,
            "database": MYSQL_DATABASE,
            "host": MYSQL_HOST,
            "port": MYSQL_PORT
        }


# ============================
# Health Check
# ============================

def health_check() -> dict:
    """
    Health check de la base de datos MySQL
    
    Returns:
        Diccionario con estado de salud
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        return {
            "status": "healthy",
            "database": "mysql",
            "message": "Conexión exitosa (READ ONLY)"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "database": "mysql",
            "message": str(e)
        }