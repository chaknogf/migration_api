# app/exceptions/messages.py
"""
Mensajes de error centralizados
Facilita la internacionalización y mantenimiento
"""

from typing import Dict


# ═══════════════════════════════════════════════════════════
# MENSAJES DE ERROR GENERALES
# ═══════════════════════════════════════════════════════════

GENERAL_ERRORS: Dict[str, str] = {
    "INTERNAL_ERROR": "Error interno del servidor. Por favor, inténtelo más tarde.",
    "NOT_FOUND": "El recurso solicitado no fue encontrado.",
    "UNAUTHORIZED": "No está autorizado para realizar esta acción.",
    "FORBIDDEN": "No tiene permisos suficientes para realizar esta acción.",
    "BAD_REQUEST": "La solicitud contiene datos inválidos.",
    "VALIDATION_ERROR": "Error de validación en los datos proporcionados."
}


# ═══════════════════════════════════════════════════════════
# MENSAJES ESPECÍFICOS DE PACIENTES
# ═══════════════════════════════════════════════════════════

PACIENTE_ERRORS: Dict[str, str] = {
    "NOT_FOUND": "Paciente no encontrado.",
    "NOT_FOUND_BY_ID": "Paciente con ID {id} no encontrado.",
    "NOT_FOUND_BY_EXPEDIENTE": "Paciente con expediente {expediente} no encontrado.",
    "NOT_FOUND_BY_CUI": "Paciente con CUI {cui} no encontrado.",
    "NOT_FOUND_BY_PASAPORTE": "Paciente con pasaporte {pasaporte} no encontrado.",
    
    "ALREADY_EXISTS": "Ya existe un paciente con estos identificadores.",
    "EXPEDIENTE_EXISTS": "Ya existe un paciente con expediente {expediente}.",
    "CUI_EXISTS": "Ya existe un paciente con CUI {cui}.",
    "PASAPORTE_EXISTS": "Ya existe un paciente con pasaporte {pasaporte}.",
    
    "INVALID_CUI": "CUI inválido. Debe tener 13 dígitos.",
    "INVALID_EXPEDIENTE": "Expediente inválido.",
    "INVALID_PASAPORTE": "Pasaporte inválido.",
    
    "MISSING_IDENTIFIER": "Debe proporcionar al menos un identificador (expediente, CUI o pasaporte).",
    "INVALID_DATE": "Fecha inválida.",
    "FUTURE_DATE": "La fecha no puede ser futura.",
    "INVALID_AGE": "Edad inválida.",
    
    "DELETE_FAILED": "No se pudo eliminar el paciente.",
    "UPDATE_FAILED": "No se pudo actualizar el paciente.",
    "CREATE_FAILED": "No se pudo crear el paciente."
}


# ═══════════════════════════════════════════════════════════
# MENSAJES DE MIGRACIÓN
# ═══════════════════════════════════════════════════════════

MIGRATION_ERRORS: Dict[str, str] = {
    "CONNECTION_FAILED": "No se pudo conectar a la base de datos {database}.",
    "MYSQL_UNAVAILABLE": "Base de datos MySQL no disponible.",
    "POSTGRES_UNAVAILABLE": "Base de datos PostgreSQL no disponible.",
    
    "MIGRATION_FAILED": "Error durante el proceso de migración.",
    "BATCH_FAILED": "Error al migrar el lote en offset {offset}.",
    "TRANSFORM_FAILED": "Error al transformar datos del paciente ID {id}.",
    
    "NO_DATA": "No hay datos para migrar.",
    "ALREADY_MIGRATED": "Estos datos ya fueron migrados anteriormente.",
    
    "VALIDATION_FAILED": "Error de validación durante la migración.",
    "DUPLICATE_IN_SOURCE": "Se encontraron duplicados en la base de datos origen."
}


# ═══════════════════════════════════════════════════════════
# MENSAJES DE BASE DE DATOS
# ═══════════════════════════════════════════════════════════

DATABASE_ERRORS: Dict[str, str] = {
    "CONNECTION_ERROR": "Error de conexión a la base de datos.",
    "QUERY_ERROR": "Error al ejecutar la consulta.",
    "TRANSACTION_ERROR": "Error en la transacción de base de datos.",
    "INTEGRITY_ERROR": "Error de integridad: violación de restricción única.",
    "FOREIGN_KEY_ERROR": "Error: referencia a registro inexistente.",
    "TIMEOUT": "Tiempo de espera agotado en la operación de base de datos."
}


# ═══════════════════════════════════════════════════════════
# MENSAJES DE VALIDACIÓN
# ═══════════════════════════════════════════════════════════

VALIDATION_ERRORS: Dict[str, str] = {
    "REQUIRED_FIELD": "El campo {field} es requerido.",
    "INVALID_FORMAT": "El formato de {field} es inválido.",
    "TOO_SHORT": "{field} es muy corto. Mínimo {min} caracteres.",
    "TOO_LONG": "{field} es muy largo. Máximo {max} caracteres.",
    "OUT_OF_RANGE": "{field} fuera de rango. Debe estar entre {min} y {max}.",
    "INVALID_CHOICE": "Valor inválido para {field}. Opciones válidas: {choices}.",
    "INVALID_EMAIL": "Formato de email inválido.",
    "INVALID_PHONE": "Formato de teléfono inválido.",
    "INVALID_DATE_FORMAT": "Formato de fecha inválido. Use YYYY-MM-DD."
}


# ═══════════════════════════════════════════════════════════
# FUNCIONES DE UTILIDAD
# ═══════════════════════════════════════════════════════════

def get_error_message(category: str, key: str, **kwargs) -> str:
    """
    Obtiene un mensaje de error formateado
    
    Args:
        category: Categoría del error (GENERAL, PACIENTE, etc.)
        key: Clave del mensaje
        **kwargs: Parámetros para formatear el mensaje
        
    Returns:
        Mensaje de error formateado
    """
    error_dict = {
        "GENERAL": GENERAL_ERRORS,
        "PACIENTE": PACIENTE_ERRORS,
        "MIGRATION": MIGRATION_ERRORS,
        "DATABASE": DATABASE_ERRORS,
        "VALIDATION": VALIDATION_ERRORS
    }
    
    messages = error_dict.get(category.upper(), GENERAL_ERRORS)
    message = messages.get(key, GENERAL_ERRORS["INTERNAL_ERROR"])
    
    try:
        return message.format(**kwargs)
    except KeyError:
        return message