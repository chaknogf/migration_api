
# app/core/logging.py
"""
Configuración centralizada de logging
"""

import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from app.core.config import settings


def setup_logging():
    """
    Configura el sistema de logging de la aplicación
    
    - Logs a archivo con rotación
    - Logs a consola
    - Diferentes niveles según entorno
    """
    
    # Crear directorio de logs si no existe
    settings.LOGS_DIR.mkdir(exist_ok=True)
    
    # Configurar nivel de log
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    
    # Formato de logs
    formatter = logging.Formatter(settings.LOG_FORMAT)
    
    # Handler para archivo (con rotación)
    log_file = settings.LOGS_DIR / settings.LOG_FILE.split('/')[-1]
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    
    # Handler para consola
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    # Formato más simple para consola
    console_formatter = logging.Formatter(
        '%(levelname)s - %(name)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)
    
    # Configurar logger raíz
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Configurar loggers específicos
    # Reducir verbosidad de librerías externas
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info(f"✅ Logging configurado - Nivel: {settings.LOG_LEVEL}")
    logger.info(f"📁 Logs guardándose en: {log_file}")
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Obtiene un logger con el nombre especificado
    
    Args:
        name: Nombre del logger (generalmente __name__)
        
    Returns:
        Logger configurado
    """
    return logging.getLogger(name)


# Logger para migración
def setup_migration_logging() -> logging.Logger:
    """
    Configura logging específico para el proceso de migración
    
    Returns:
        Logger configurado para migración
    """
    logger = logging.getLogger("migracion")
    logger.setLevel(logging.DEBUG)
    
    # Handler específico para migración
    migration_log_file = settings.LOGS_DIR / settings.MIGRATION_LOG_FILE.split('/')[-1]
    migration_handler = RotatingFileHandler(
        migration_log_file,
        maxBytes=50 * 1024 * 1024,  # 50 MB
        backupCount=10,
        encoding='utf-8'
    )
    
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    migration_handler.setFormatter(formatter)
    
    logger.addHandler(migration_handler)
    
    return logger