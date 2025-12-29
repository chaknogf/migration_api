"""
Schemas Pydantic para validación y serialización
"""

from app.schemas.paciente import (
    # Schemas base
    NombreSchema,
    DireccionSchema,
    ContactoSchema,
    ResponsableSchema,
    ReferenciasSchema,
    DemograficosSchema,
    SocioeconomicosSchema,
    DefuncionSchema,
    DatosExtraSchema,
    MetadatosSchema,
    
    # Schemas principales
    PacienteBase,
    PacienteCreate,
    PacienteUpdate,
    PacienteResponse,
    PacienteListResponse,
    
    # Schemas de búsqueda
    PacienteSearchParams,
    
    # Schemas de migración
    MigracionStats,
    MigracionResponse
)

__all__ = [
    # Base
    "NombreSchema",
    "DireccionSchema",
    "ContactoSchema",
    "ResponsableSchema",
    "ReferenciasSchema",
    "DemograficosSchema",
    "SocioeconomicosSchema",
    "DefuncionSchema",
    "DatosExtraSchema",
    "MetadatosSchema",
    
    # Principales
    "PacienteBase",
    "PacienteCreate",
    "PacienteUpdate",
    "PacienteResponse",
    "PacienteListResponse",
    
    # Búsqueda
    "PacienteSearchParams",
    
    # Migración
    "MigracionStats",
    "MigracionResponse"
]