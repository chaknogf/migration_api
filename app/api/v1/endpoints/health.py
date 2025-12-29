# app/api/v1/endpoints/health.py

"""
Endpoints de health check y estado del sistema
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any

from app.api.deps import get_db, get_mysql
from app.database import postgres, mysql

router = APIRouter()


@router.get("/", response_model=Dict[str, Any])
def health_check():
    """
    Health check básico de la API
    
    Returns:
        Estado de la API
    """
    return {
        "status": "healthy",
        "service": "API de Gestión de Pacientes",
        "version": "1.0.0"
    }


@router.get("/database", response_model=Dict[str, Any])
def database_health_check(
    db_postgres: Session = Depends(get_db),
    db_mysql: Session = Depends(get_mysql)
):
    """
    Health check de las bases de datos
    
    Returns:
        Estado de PostgreSQL y MySQL
    """
    return {
        "postgresql": postgres.health_check(),
        "mysql": mysql.health_check()
    }


@router.get("/database/info", response_model=Dict[str, Any])
def database_info():
    """
    Información detallada de las bases de datos
    
    Returns:
        Información de PostgreSQL y MySQL
    """
    return {
        "postgresql": postgres.get_database_info(),
        "mysql": mysql.get_database_info()
    }


@router.get("/database/stats", response_model=Dict[str, Any])
def database_stats(db: Session = Depends(get_db)):
    """
    Estadísticas de las tablas
    
    Returns:
        Conteos de registros
    """
    from app.crud.paciente import crud_paciente
    
    return {
        "postgresql": {
            "pacientes": crud_paciente.get_count(db)
        },
        "mysql": {
            "pacientes": mysql.get_table_count("pacientes")
        }
    }