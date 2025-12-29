# app/exceptions/handlers.py
"""
Excepciones personalizadas y sus manejadores para la aplicación
"""

from typing import Union, Dict, Any
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
from pydantic import ValidationError as PydanticValidationError
import logging

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# EXCEPCIONES PERSONALIZADAS
# ═══════════════════════════════════════════════════════════

class AppException(Exception):
    """Excepción base de la aplicación"""
    
    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Dict[str, Any] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(self.message)


class PacienteNotFoundError(AppException):
    """Excepción cuando un paciente no es encontrado"""
    
    def __init__(self, identifier: Union[int, str], identifier_type: str = "ID"):
        message = f"Paciente con {identifier_type} '{identifier}' no encontrado"
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details={
                "identifier": identifier,
                "identifier_type": identifier_type
            }
        )


class PacienteAlreadyExistsError(AppException):
    """Excepción cuando se intenta crear un paciente que ya existe"""
    
    def __init__(
        self,
        identifier: Union[int, str],
        identifier_type: str = "expediente"
    ):
        message = f"Ya existe un paciente con {identifier_type} '{identifier}'"
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details={
                "identifier": identifier,
                "identifier_type": identifier_type
            }
        )


class InvalidIdentifierError(AppException):
    """Excepción cuando un identificador es inválido"""
    
    def __init__(self, identifier_type: str, reason: str):
        message = f"Identificador '{identifier_type}' inválido: {reason}"
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details={
                "identifier_type": identifier_type,
                "reason": reason
            }
        )


class ValidationError(AppException):
    """Excepción para errores de validación de negocio"""
    
    def __init__(self, field: str, message: str):
        super().__init__(
            message=f"Error de validación en '{field}': {message}",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={
                "field": field,
                "validation_error": message
            }
        )


class MigrationError(AppException):
    """Excepción durante el proceso de migración"""
    
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message=f"Error en migración: {message}",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details or {}
        )


class DatabaseConnectionError(AppException):
    """Excepción cuando hay problemas de conexión a la base de datos"""
    
    def __init__(self, database: str, original_error: str = None):
        message = f"Error de conexión a {database}"
        if original_error:
            message += f": {original_error}"
        
        super().__init__(
            message=message,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details={
                "database": database,
                "original_error": original_error
            }
        )


class DuplicateEntryError(AppException):
    """Excepción cuando se viola una restricción de unicidad"""
    
    def __init__(self, field: str, value: Any):
        message = f"Ya existe un registro con {field} = '{value}'"
        super().__init__(
            message=message,
            status_code=status.HTTP_409_CONFLICT,
            details={
                "field": field,
                "value": str(value)
            }
        )


class InsufficientPermissionsError(AppException):
    """Excepción cuando el usuario no tiene permisos suficientes"""
    
    def __init__(self, action: str):
        message = f"No tiene permisos para realizar la acción: {action}"
        super().__init__(
            message=message,
            status_code=status.HTTP_403_FORBIDDEN,
            details={"action": action}
        )


# ═══════════════════════════════════════════════════════════
# MANEJADORES DE EXCEPCIONES
# ═══════════════════════════════════════════════════════════

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """
    Manejador para todas las excepciones personalizadas de la aplicación
    """
    logger.error(
        f"AppException: {exc.message} - "
        f"Status: {exc.status_code} - "
        f"Path: {request.url.path} - "
        f"Details: {exc.details}"
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.message,
            "details": exc.details,
            "path": request.url.path
        }
    )


async def validation_exception_handler(
    request: Request,
    exc: Union[RequestValidationError, PydanticValidationError]
) -> JSONResponse:
    """
    Manejador para errores de validación de Pydantic/FastAPI
    """
    errors = []
    
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        message = error["msg"]
        error_type = error["type"]
        
        errors.append({
            "field": field,
            "message": message,
            "type": error_type
        })
    
    logger.warning(
        f"Validation Error: {len(errors)} errores - "
        f"Path: {request.url.path}"
    )
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": True,
            "message": "Error de validación en los datos enviados",
            "validation_errors": errors,
            "path": request.url.path
        }
    )


async def sqlalchemy_exception_handler(
    request: Request,
    exc: SQLAlchemyError
) -> JSONResponse:
    """
    Manejador para errores de SQLAlchemy
    """
    logger.error(
        f"SQLAlchemy Error: {str(exc)} - "
        f"Path: {request.url.path}",
        exc_info=True
    )
    
    # Manejar errores de integridad (unique constraints, etc.)
    if isinstance(exc, IntegrityError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": True,
                "message": "Error de integridad en la base de datos",
                "details": {
                    "type": "integrity_error",
                    "description": "Violación de restricción de unicidad o llave foránea"
                },
                "path": request.url.path
            }
        )
    
    # Error genérico de base de datos
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": True,
            "message": "Error en la operación de base de datos",
            "details": {
                "type": "database_error"
            },
            "path": request.url.path
        }
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """
    Manejador genérico para excepciones no capturadas
    """
    logger.error(
        f"Unhandled Exception: {type(exc).__name__} - {str(exc)} - "
        f"Path: {request.url.path}",
        exc_info=True
    )
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": True,
            "message": "Error interno del servidor",
            "details": {
                "type": type(exc).__name__
            },
            "path": request.url.path
        }
    )


# ═══════════════════════════════════════════════════════════
# FUNCIÓN PARA REGISTRAR TODOS LOS MANEJADORES
# ═══════════════════════════════════════════════════════════

def add_exception_handlers(app: FastAPI) -> None:
    """
    Registra todos los manejadores de excepciones en la aplicación FastAPI
    
    Args:
        app: Instancia de FastAPI
    """
    # Excepciones personalizadas
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(PacienteNotFoundError, app_exception_handler)
    app.add_exception_handler(PacienteAlreadyExistsError, app_exception_handler)
    app.add_exception_handler(InvalidIdentifierError, app_exception_handler)
    app.add_exception_handler(ValidationError, app_exception_handler)
    app.add_exception_handler(MigrationError, app_exception_handler)
    app.add_exception_handler(DatabaseConnectionError, app_exception_handler)
    app.add_exception_handler(DuplicateEntryError, app_exception_handler)
    app.add_exception_handler(InsufficientPermissionsError, app_exception_handler)
    
    # Excepciones de validación
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(PydanticValidationError, validation_exception_handler)
    
    # Excepciones de SQLAlchemy
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(IntegrityError, sqlalchemy_exception_handler)
    
    # Excepción genérica (catch-all)
    app.add_exception_handler(Exception, generic_exception_handler)
    
    logger.info("✅ Manejadores de excepciones registrados")