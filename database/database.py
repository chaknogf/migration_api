#!/usr/bin/env python3
# database/database.py

"""
Configuración de conexiones para migración MySQL → PostgreSQL
Centraliza engines y sesiones
"""

import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
import sys

# ============================================================================
# CARGA DE VARIABLES DE ENTORNO
# ============================================================================

load_dotenv()

# ============================================================================
# CONSTRUCCIÓN DE URLs
# ============================================================================

def construir_url_mysql():
    user = os.getenv("MYSQL_USER", "root")
    password = os.getenv("MYSQL_PASSWORD", "Prometeus.0")
    host = os.getenv("MYSQL_HOST", "localhost")
    port = os.getenv("MYSQL_PORT", "3306")
    database = os.getenv("MYSQL_DATABASE", "test_api")
    
    return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"


def construir_url_postgres():
    user = os.getenv("POSTGRES_USER", "postgres")
    password = os.getenv("POSTGRES_PASSWORD", "secreto123")
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    database = os.getenv("POSTGRES_DB", "hospital")
    
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"


MYSQL_URL = construir_url_mysql()
POSTGRES_URL = construir_url_postgres()

# ============================================================================
# CREACIÓN DE ENGINES
# ============================================================================

def crear_engines(echo: bool = False):
    try:
        mysql_engine = create_engine(MYSQL_URL, echo=echo)
        postgres_engine = create_engine(POSTGRES_URL, echo=echo)
        return mysql_engine, postgres_engine
    except Exception as e:
        print(f"❌ Error creando engines: {e}")
        sys.exit(1)


# ============================================================================
# CREACIÓN DE SESIONES
# ============================================================================

def crear_sesiones(mysql_engine, postgres_engine):
    try:
        MySQLSession = sessionmaker(bind=mysql_engine)
        PostgresSession = sessionmaker(bind=postgres_engine)
        return MySQLSession, PostgresSession
    except Exception as e:
        print(f"❌ Error creando sesiones: {e}")
        sys.exit(1)


# ============================================================================
# VALIDACIÓN DE CONEXIÓN
# ============================================================================

def probar_conexion(engine, nombre="DB"):
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"✅ Conexión exitosa: {nombre}")
    except Exception as e:
        print(f"❌ Error en conexión {nombre}: {e}")
        sys.exit(1)


# ============================================================================
# INICIALIZACIÓN GENERAL
# ============================================================================

def init_db(echo: bool = False):
    print("\n🔌 Inicializando conexiones...")

    mysql_engine, postgres_engine = crear_engines(echo)
    MySQLSession, PostgresSession = crear_sesiones(mysql_engine, postgres_engine)

    probar_conexion(mysql_engine, "MySQL")
    probar_conexion(postgres_engine, "PostgreSQL")

    print("🚀 Todo listo para migración\n")

    return {
        "mysql_engine": mysql_engine,
        "postgres_engine": postgres_engine,
        "MySQLSession": MySQLSession,
        "PostgresSession": PostgresSession,
    }


# ============================================================================
# EJECUCIÓN DIRECTA (DEBUG)
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("🔧 TEST DE CONEXIÓN - DATABASE")
    print("=" * 80)

    print(f"MySQL:       {MYSQL_URL.split('@')[1]}")
    print(f"PostgreSQL:  {POSTGRES_URL.split('@')[1]}")

    init_db(echo=False)