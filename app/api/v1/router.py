# app/api/v1/router.py

"""
Router principal que agrupa todos los endpoints de la API v1
"""

from fastapi import APIRouter

from app.api.v1.endpoints import pacientes, migracion, health

api_router = APIRouter()

# Incluir routers de cada módulo
api_router.include_router(
    health.router,
    prefix="/health",
    tags=["Health Check"]
)

api_router.include_router(
    pacientes.router,
    prefix="/pacientes",
    tags=["Pacientes"]
)

api_router.include_router(
    migracion.router,
    prefix="/migracion",
    tags=["Migración"]
)