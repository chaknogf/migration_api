"""
Configuración de bases de datos para el sistema
- PostgreSQL: Base de datos principal
- MySQL: Base de datos legacy (solo lectura para migración)
"""

from app.database.postgres import (
    engine as postgres_engine,
    SessionLocal as PostgresSessionLocal,
    Base as PostgresBase,
    get_db as get_postgres_db,
    get_postgres_session
)

from app.database.mysql import (
    engine as mysql_engine,
    SessionLocal as MysqlSessionLocal,
    Base as MysqlBase,
    get_db as get_mysql_db,
    get_mysql_session
)

__all__ = [
    # PostgreSQL
    "postgres_engine",
    "PostgresSessionLocal",
    "PostgresBase",
    "get_postgres_db",
    "get_postgres_session",
    
    # MySQL
    "mysql_engine",
    "MysqlSessionLocal",
    "MysqlBase",
    "get_mysql_db",
    "get_mysql_session",
]