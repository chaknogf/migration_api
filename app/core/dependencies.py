# app/core/dependencies.py
"""
Dependencias compartidas de la aplicación
"""

from typing import Generator, Optional
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.postgres import get_db as get_postgres_db
from app.database.mysql import get_db as get_mysql_db


# ═══════════════════════════════════════════════════════════
# DEPENDENCIAS DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════

def get_db() -> Generator[Session, None, None]:
    """
    Dependencia principal de base de datos (PostgreSQL)
    
    Uso:
        @app.get("/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            ...
    """
    return get_postgres_db()


def get_mysql() -> Generator[Session, None, None]:
    """
    Dependencia de MySQL (solo para migración)
    
    ⚠️ SOLO LECTURA
    """
    return get_mysql_db()


# ═══════════════════════════════════════════════════════════
# DEPENDENCIAS DE PAGINACIÓN
# ═══════════════════════════════════════════════════════════

class PaginationParams:
    """Parámetros de paginación reutilizables"""
    
    def __init__(
        self,
        page: int = 1,
        page_size: int = settings.DEFAULT_PAGE_SIZE
    ):
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El número de página debe ser mayor o igual a 1"
            )
        
        if page_size < 1 or page_size > settings.MAX_PAGE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"El tamaño de página debe estar entre 1 y {settings.MAX_PAGE_SIZE}"
            )
        
        self.page = page
        self.page_size = page_size
        self.skip = (page - 1) * page_size
        self.limit = page_size


def get_pagination_params(
    page: int = 1,
    page_size: int = settings.DEFAULT_PAGE_SIZE
) -> PaginationParams:
    """
    Dependencia de paginación
    
    Uso:
        @app.get("/items")
        def get_items(pagination: PaginationParams = Depends(get_pagination_params)):
            return crud.get_multi(skip=pagination.skip, limit=pagination.limit)
    """
    return PaginationParams(page=page, page_size=page_size)


# ═══════════════════════════════════════════════════════════
# DEPENDENCIAS DE CONFIGURACIÓN
# ═══════════════════════════════════════════════════════════

def get_settings():
    """
    Dependencia para obtener configuración
    
    Uso:
        @app.get("/info")
        def get_info(config = Depends(get_settings)):
            return {"version": config.VERSION}
    """
    return settings


# ═══════════════════════════════════════════════════════════
# DEPENDENCIAS DE VALIDACIÓN
# ═══════════════════════════════════════════════════════════

def validate_environment():
    """
    Valida que el entorno esté correctamente configurado
    """
    required_vars = [
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_HOST",
        "POSTGRES_DB",
        "MYSQL_USER",
        "MYSQL_PASSWORD",
        "MYSQL_DATABASE"
    ]
    
    missing_vars = []
    for var in required_vars:
        if not getattr(settings, var, None):
            missing_vars.append(var)
    
    if missing_vars:
        raise RuntimeError(
            f"Variables de entorno faltantes: {', '.join(missing_vars)}"
        )


# ═══════════════════════════════════════════════════════════
# DEPENDENCIAS DE AUTENTICACIÓN (Para futuro)
# ═══════════════════════════════════════════════════════════

# TODO: Implementar cuando se requiera autenticación
# from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# 
# security = HTTPBearer()
# 
# def get_current_user(
#     credentials: HTTPAuthorizationCredentials = Depends(security)
# ):
#     """Verifica el token JWT y retorna el usuario actual"""
#     pass