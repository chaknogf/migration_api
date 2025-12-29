# app/api/deps.py

"""
Dependencias compartidas para los endpoints
"""

from typing import Generator
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.postgres import get_db as get_postgres_db
from app.database.mysql import get_db as get_mysql_db


# ═══════════════════════════════════════════════════════════
# DEPENDENCIAS DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════

def get_db() -> Generator[Session, None, None]:
    """
    Dependencia para obtener sesión de PostgreSQL (base principal)
    
    Uso:
        @router.get("/pacientes")
        def get_pacientes(db: Session = Depends(get_db)):
            ...
    """
    return get_postgres_db()


def get_mysql() -> Generator[Session, None, None]:
    """
    Dependencia para obtener sesión de MySQL (solo migración)
    
    ⚠️ SOLO LECTURA
    
    Uso:
        @router.get("/migracion/check")
        def check_mysql(db: Session = Depends(get_mysql)):
            ...
    """
    return get_mysql_db()


# ═══════════════════════════════════════════════════════════
# DEPENDENCIAS DE PAGINACIÓN
# ═══════════════════════════════════════════════════════════

def common_pagination_params(
    page: int = 1,
    page_size: int = 10
) -> dict:
    """
    Parámetros comunes de paginación
    
    Args:
        page: Número de página (mínimo 1)
        page_size: Tamaño de página (entre 1 y 100)
        
    Returns:
        Dict con skip y limit
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El número de página debe ser mayor o igual a 1"
        )
    
    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El tamaño de página debe estar entre 1 y 100"
        )
    
    skip = (page - 1) * page_size
    
    return {
        "skip": skip,
        "limit": page_size,
        "page": page,
        "page_size": page_size
    }